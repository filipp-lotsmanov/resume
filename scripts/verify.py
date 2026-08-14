#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pdfplumber>=0.11.0", "pypdf>=5.0.0"]
# ///
"""Assert the ATS-safety invariants of a compiled resume PDF.

Every check corresponds to a defect that survives a successful LaTeX compile.

Text checks run against TWO extractors, because they disagree on exactly the
defects that matter. pypdf walks the raw content stream, the way many ATS
parsers do; pdfplumber reconstructs text geometrically and silently repairs
stream-order and letterspacing problems. A defect visible to only one of them
is still a defect.

Exits 1 if any check fails, so it can gate CI.

Run:  uv run scripts/verify_pdf.py resume.pdf --name "Your Name"
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass

import pdfplumber
from pypdf import PdfReader

PT_PER_CM = 28.3464567
A4_PT = (595.276, 841.890)
SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")
STYLE_SUFFIX = re.compile(
    r"[-,](Bold|Italic|Oblique|Roman|Regular|BoldItalic|BoldOblique|Light|Medium)$",
    re.I,
)
LETTERSPACED = re.compile(r"(?:[A-Za-z] ){4,}")


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def squash(s: str) -> str:
    """Collapse whitespace. pdfplumber's word-gap heuristic drops spaces other
    extractors keep, so comparisons must be whitespace-insensitive."""
    return re.sub(r"\s+", "", s)


def font_families(reader: PdfReader) -> set[str]:
    """Distinct families across all pages, ignoring subset prefixes and styles.

    Computer Modern ships one font file per style AND size (CMR10, CMBX12,
    CMSY6...), so a CM document legitimately reports many families. Raise
    --max-font-families if you deliberately use CM.
    """
    families: set[str] = set()
    for page in reader.pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        fonts = resources.get_object().get("/Font")
        if fonts is None:
            continue
        for ref in fonts.get_object().values():
            base = ref.get_object().get("/BaseFont")
            if base is None:
                continue
            stem = SUBSET_PREFIX.sub("", str(base).lstrip("/"))
            families.add(STYLE_SUFFIX.sub("", stem))
    return families


def extract_both(path: str, reader: PdfReader) -> dict[str, list[str]]:
    pypdf_pages = [p.extract_text() or "" for p in reader.pages]
    with pdfplumber.open(path) as pdf:
        plumber_pages = [p.extract_text() or "" for p in pdf.pages]
    return {"pypdf": pypdf_pages, "pdfplumber": plumber_pages}


def build_results(path: str, args: argparse.Namespace) -> list[Result]:
    out: list[Result] = []
    reader = PdfReader(path)

    n_pages = len(reader.pages)
    out.append(Result("page count", n_pages <= args.max_pages,
                      f"{n_pages} (max {args.max_pages})"))

    box = reader.pages[0].mediabox
    w, h = float(box.width), float(box.height)
    a4 = abs(w - A4_PT[0]) < 2 and abs(h - A4_PT[1]) < 2
    out.append(Result("page size is A4", a4,
                      f"{w:.0f} x {h:.0f} pt"
                      + ("" if a4 else "  <- US Letter is 612 x 792")))

    meta = reader.metadata or {}
    title, author = str(meta.get("/Title") or ""), str(meta.get("/Author") or "")
    # A leftover template name here shows in the recruiter's PDF viewer title bar.
    surname = args.name.split()[-1].lower()
    meta_ok = bool(title) and bool(author) and surname in (title + author).lower()
    out.append(Result("metadata names you, not a template", meta_ok,
                      f"title={title!r} author={author!r}"))

    families = font_families(reader)
    out.append(Result(f"font families <= {args.max_font_families}",
                      len(families) <= args.max_font_families,
                      ", ".join(sorted(families)) or "none found"))

    texts = extract_both(path, reader)

    bad_first = []
    for engine, pages in texts.items():
        lines = [ln.strip() for ln in pages[0].splitlines() if ln.strip()]
        first = lines[0] if lines else ""
        if squash(first) != squash(args.name):
            bad_first.append(f"{engine}={first!r}")
    out.append(Result("first extracted line is the name", not bad_first,
                      "; ".join(bad_first) if bad_first
                      else f"both extractors agree on {args.name!r}"))

    bad_hyphen = []
    for engine, pages in texts.items():
        broken = [ln for ln in "\n".join(pages).splitlines()
                  if ln.rstrip().endswith("-")]
        if broken:
            bad_hyphen.append(f"{engine}={len(broken)} ({broken[0][-32:]!r})")
    out.append(Result("no hyphen-broken lines", not bad_hyphen,
                      "; ".join(bad_hyphen) if bad_hyphen else "0 in both"))

    bad_spaced = []
    for engine, pages in texts.items():
        hits = LETTERSPACED.findall("\n".join(pages))
        if hits:
            bad_spaced.append(f"{engine}={len(hits)} ({hits[0][:28]!r})")
    out.append(Result("no letterspaced runs", not bad_spaced,
                      "; ".join(bad_spaced) if bad_spaced else "0 in both"))

    bad_glyph = []
    for engine, pages in texts.items():
        joined = "\n".join(pages)
        if joined.count("\ufffd") or len(joined) < args.min_chars:
            bad_glyph.append(
                f"{engine}: {joined.count(chr(0xFFFD))} bad, {len(joined)} chars")
    out.append(Result("no unmapped glyphs", not bad_glyph,
                      "; ".join(bad_glyph) if bad_glyph
                      else f"clean, >{args.min_chars} chars in both"))

    if args.keywords:
        bad_kw = []
        for engine, pages in texts.items():
            joined = squash("\n".join(pages))
            missing = [k for k in args.keywords if squash(k) not in joined]
            if missing:
                bad_kw.append(f"{engine} missing {', '.join(missing)}")
        out.append(Result("keywords survive extraction", not bad_kw,
                          "; ".join(bad_kw) if bad_kw else "all present in both"))

    with pdfplumber.open(path) as pdf:
        words = pdf.pages[0].extract_words()
    if words:
        margins = {
            "L": min(x["x0"] for x in words) / PT_PER_CM,
            "R": (w - max(x["x1"] for x in words)) / PT_PER_CM,
            "T": min(x["top"] for x in words) / PT_PER_CM,
            "B": (h - max(x["bottom"] for x in words)) / PT_PER_CM,
        }
        out.append(Result(f"margins >= {args.min_margin}cm",
                          min(margins.values()) >= args.min_margin,
                          " ".join(f"{k}={v:.2f}" for k, v in margins.items())))
    else:
        out.append(Result("margins", False, "no words extracted"))

    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf")
    ap.add_argument("--name", required=True, help="exact expected first line")
    ap.add_argument("--max-pages", type=int, default=1)
    ap.add_argument("--min-margin", type=float, default=1.2, help="cm")
    ap.add_argument("--max-font-families", type=int, default=1)
    ap.add_argument("--min-chars", type=int, default=1500)
    ap.add_argument("--keywords", default="",
                    help="comma-separated terms that must survive extraction")
    args = ap.parse_args()
    args.keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    try:
        results = build_results(args.pdf, args)
    except FileNotFoundError:
        print(f"error: {args.pdf} not found - compile first", file=sys.stderr)
        return 2

    pad = max(len(r.name) for r in results)
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name:<{pad}}  {r.detail}")

    failed = sum(1 for r in results if not r.ok)
    print(f"\n{len(results) - failed}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
