# tategaki-pdf-to-epub

Given a PDF with tategaki formatting, converts the text into HTML, which can then be pasted into EPUB.

Assumes plain text. Does not support special formatting or images.

## Usage

With files:
```
python3 tategaki_pdf_to_epub.py --file-path <your-pdf-file>
```

With folders:
```
python3 tategaki_pdf_to_epub.py --folder-path <your-pdf-folder>
```

Adjust the parameters in the script as necessary. Inspect the output of the raw HTML to determine the values.
