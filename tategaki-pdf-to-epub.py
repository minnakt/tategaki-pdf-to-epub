import argparse
import html
import math
import sys
from collections import defaultdict
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup


def extract_text_for_page(page, furigana_threshold, footer_y_threshold):
    """ Extract all text fragments from the given page.

    Returns:
        body_chars: The characters in the main text with corresponding position info.
        ruby_chars: The furigana characters with corresponding position info.
    """
    body_chars = []
    ruby_chars = []

    raw_html = page.get_text("html")
    html_output = html.unescape(raw_html) # Print the output here to see what you're working with

    soup = BeautifulSoup(html_output, "html.parser")
    for paragraph in soup.find_all("p"):
        style_str = paragraph["style"]
        style_dict = dict(
            item.split(":") for item in style_str.split(";") if ":" in item
        )

        line_height = float(style_dict["line-height"].rstrip("pt"))
        top = float(style_dict["top"].rstrip("pt"))
        left = float(style_dict["left"].rstrip("pt"))
        text = paragraph.text.strip()

        if top >= footer_y_threshold:
            continue

        if text == "":
            continue

        if line_height <= furigana_threshold:
            ruby_chars.append({ "top": top, "left": left, "text": text })
        else:
            body_chars.append({ "top": top, "left": left, "text": text })    
    return body_chars, ruby_chars

def process_furigana_for_page(body_chars, ruby_chars):
    """ Match furigana to the nearest kanji. Note body_chars will get modified in-place.

    Returns:
        body_chars_with_furigana: Same as body_chars, but characters with ruby text will have a ruby_text field.
    """
    for r in ruby_chars:
        best_match_char = None
        min_distance = float('inf')
        
        for b in body_chars:
            # Ruby text must be visually to the right of the target character (larger X coordinate).
            if r["left"] > b["left"]:
                vertical_dist = r["top"] - b["top"]
                horizontal_dist = r["left"] - b["left"]
                total_dist = math.sqrt(vertical_dist ** 2 + horizontal_dist ** 2)
                
                if total_dist < min_distance:
                    min_distance = total_dist
                    best_match_char = b

        best_match_char.setdefault("ruby_text", "")
        best_match_char["ruby_text"] += r["text"]
    
    return body_chars


def group_columns_for_page(body_chars, col_threshold):
    """ Group the body text into vertical columns.
        We do this to represent the original formatting in the text.

    Returns: 
        columns: A 2D array of the body chars with additional positioning information.
                 Each row represents 1 vertical line (行) in the text. 
                 Each column represents a single character in the line.
    """
    columns_dict = defaultdict(list)
    for char in body_chars:
        # Bucket the characters into their correct groups
        bucket_id = int(char["left"] / col_threshold)
        columns_dict[bucket_id].append(char)
    return list(columns_dict.values())

def build_html_for_page(columns, col_threshold, indent_threshold):
    """ Produces the HTML content for one page of the PDF.
    """
    html_page = []

    current_paragraph_text = ""
    current_paragraph_starts_with_bracket = False
    prev_col_x = None

    def append_current_paragraph():
        """ Helper to append the active paragraph with proper indentation. """
        if not current_paragraph_text:
            return
        if current_paragraph_starts_with_bracket:
            html_page.append(f"<p>{current_paragraph_text}</p>")
        else:
            html_page.append(f"<p>　{current_paragraph_text}</p>")

    for col in columns:
        column_text = ""

        for c in col:
            if "ruby_text" in c:
                column_text += f"<ruby><rb>{c['text']}</rb><rt>{c['ruby_text']}</rt></ruby>"
            else:
                column_text += c["text"]
        
        # 1. Handle blank lines (not necessary if you don't care about them)

        # Here we are saving the x-coordinate of the curr column. We will
        # compare this with the x-coordinate prev column.
        # If there is an unusually large gap that exceeds col_threshold * 2, 
        # that means we need to insert a blank line.
        curr_col_x = sum(c["left"] for c in col) / len(col)

        if prev_col_x is not None:
            horizontal_gap = abs(prev_col_x - curr_col_x)
            if horizontal_gap >= col_threshold * 2:
                append_current_paragraph()
                html_page.append("<p>&nbsp;</p>")
                current_paragraph_text = ""
        
        prev_col_x = curr_col_x

        # 2. Check for paragraph boundaries

        # For the purposes of my PDF, every new line either starts with "「" or an
        # indent. We check for these conditions to determine if we should insert a 
        # new paragraph.
        first_char = col[0]
        starts_with_bracket = first_char["text"] == "「"
        
        # ── is a unique case because it renders vertically in the output but its
        # positiong is calculated from its horizontal form. I just adjusted the indent 
        # threshold to account for it.
        has_top_indent = first_char["top"] >= indent_threshold
        if first_char["text"] == "──":
            has_top_indent = first_char["top"] >= indent_threshold - 8

        is_new_paragraph = starts_with_bracket or has_top_indent

        if is_new_paragraph:
            append_current_paragraph()
            current_paragraph_starts_with_bracket = starts_with_bracket
            current_paragraph_text = column_text
        else:
            current_paragraph_text += column_text

    # Append any remaining text left in the buffer
    append_current_paragraph()
            
    return html_page

def convert_tategaki_pdf_to_epub(pdf_path, col_threshold = 14, indent_threshold = 38, footer_y_threshold = 390, furigana_threshold = 5):
    """ Extract text from a PDF written in Japanese tategaki.
        Assumes the whole file is plain text. Does NOT account for images or special formatting.

    Args:
        col_threshold (float): Threshold where to consider next line (行) in the text.
        indent_threshold (float): Threshold to determine if a sentence has been indented (to make a new paragraph).
        footer_y_threshold (float): Use to get rid of stuff in the footer (e.g. page numbers are irrelevant in epubs).
        furigana_threshold (float): Use to determine if characters are furigana and should not be included the main text.
    Returns:
        html_content: <p> tags with paragraphs in each.
    """
    doc = pymupdf.open(pdf_path)
    html_paragraphs = []

    for page_num in range(len(doc)):
        page = doc[page_num]
 
        body_chars, ruby_chars = extract_text_for_page(page, furigana_threshold, footer_y_threshold)
        if not body_chars:
            continue

        body_chars_with_ruby = process_furigana_for_page(body_chars, ruby_chars)

        columns = group_columns_for_page(body_chars_with_ruby, col_threshold)
        if not columns:
            continue

        html_page = build_html_for_page(columns, col_threshold, indent_threshold)
        html_paragraphs.extend(html_page)
                
    return "\n".join(html_paragraphs)

def main():
    parser = argparse.ArgumentParser(
        description="Processes tategaki PDF into HTML, which can then be pasted into EPUBs."
    )
    parser.add_argument(
        "--folder-path", 
        type=str, 
        help="Path to the directory containing PDFs"
    )
    parser.add_argument(
        "--file-path", 
        type=str, 
        help="Path to a single PDF"
    )

    args = parser.parse_args()
    folder_path = args.folder_path
    file_path = args.file_path

    if folder_path:
        print(f"Processing folder: {folder_path}")
        folder = Path(args[folder_path])
        for file in folder.iterdir():
            if file.is_file():
                print(file.name)
                html_content = convert_tategaki_pdf_to_epub(file)
                with open(f"output/{file.stem}.html", "w", encoding="utf-8") as f:
                    f.write(html_content)  
    elif file_path:
        print(f"Processing file: {file_path}")
        html_content = convert_tategaki_pdf_to_epub(file_path)
        with open("html_content.html", "w", encoding="utf-8") as file:
            file.write(html_content)
    else:
        print("Error: You must provide either --folder-path or --file-path.", file=sys.stderr)
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()
