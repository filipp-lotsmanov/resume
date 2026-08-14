# latexmk configuration. Engine must be pdflatex: \pdfgentounicode and
# \input{glyphtounicode} are pdfTeX primitives and error under xelatex.
$pdf_mode = 1;
$pdflatex = 'pdflatex -interaction=nonstopmode -halt-on-error -file-line-error %O %S';
$clean_ext = 'synctex.gz fls fdb_latexmk out';
$max_repeat = 3;
