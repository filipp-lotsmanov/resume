# Uses > instead of TAB as the recipe prefix (GNU Make 3.82+), so copy-pasting
# or editing this file cannot break it by converting tabs to spaces.
.RECIPEPREFIX = >
.DEFAULT_GOAL := all

TEX      := resume.tex
PDF      := $(TEX:.tex=.pdf)
NAME     := FILIPP LOTSMANOV
KEYWORDS := PyTorch,FastAPI,PostgreSQL,Docker,XGBoost,MediaPipe,TorchScript,Kubernetes,Data Science
VERIFY   := scripts/verify_pdf.py

.PHONY: all pdf verify watch clean tools

all: verify

pdf: $(PDF)

$(PDF): $(TEX)
> latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error $(TEX)
> @if grep -qE 'Overfull|Underfull' $(basename $(TEX)).log; then \
>   echo "--- box warnings ---"; grep -E 'Overfull|Underfull' $(basename $(TEX)).log; \
>   exit 1; fi

verify: $(PDF)
> uv run $(VERIFY) $(PDF) --name "$(NAME)" --max-font-families 2 --keywords "$(KEYWORDS)"

# Recompile on save. Ctrl-C to stop.
watch:
> latexmk -pdf -pvc -interaction=nonstopmode $(TEX)

clean:
> latexmk -C
> rm -f *.aux *.log *.out *.fls *.fdb_latexmk *.synctex.gz

tools:
> @command -v pdflatex >/dev/null || { echo "MISSING pdflatex"; exit 1; }
> @command -v latexmk  >/dev/null || { echo "MISSING latexmk";  exit 1; }
> @command -v uv       >/dev/null || { echo "MISSING uv";       exit 1; }
> @kpsewhich charter.sty >/dev/null || { echo "MISSING charter.sty"; exit 1; }
> @kpsewhich bchr8a.pfb  >/dev/null || { echo "MISSING Charter Type1 binaries (texlive-fonts-recommended)"; exit 1; }
> @kpsewhich titlesec.sty >/dev/null || { echo "MISSING titlesec.sty"; exit 1; }
> @kpsewhich enumitem.sty >/dev/null || { echo "MISSING enumitem.sty"; exit 1; }
> @kpsewhich hyphenat.sty >/dev/null || { echo "MISSING hyphenat.sty"; exit 1; }
> @echo "toolchain ok"
