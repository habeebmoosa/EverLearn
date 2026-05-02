"""
File Reader Tool

Reads content from text files, PDFs, and DOCX files for research input.
"""

import os
import logging

logger = logging.getLogger("everlearn.tools.file_reader")


def read_text_file(file_path: str) -> dict:
    """
    Read content from a text file (.txt, .md, .csv, .json, etc.).

    Args:
        file_path: Path to the text file

    Returns:
        dict: File content with keys:
            - text: File content string
            - char_count: Number of characters
            - line_count: Number of lines
            - file_name: Name of the file

    Example:
        >>> read_text_file("/path/to/notes.txt")
        {
            'text': 'File content here...',
            'char_count': 500,
            'line_count': 20,
            'file_name': 'notes.txt'
        }
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    try:
        # Try UTF-8 first, fallback to latin-1
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                text = f.read()

        logger.info(f"Read text file: {file_path} ({len(text)} chars)")
        return {
            "text": text,
            "char_count": len(text),
            "line_count": text.count("\n") + 1,
            "file_name": os.path.basename(file_path),
        }
    except Exception as e:
        return {"error": f"Failed to read {file_path}: {str(e)}"}


def read_pdf_file(file_path: str, max_pages: int = 50) -> dict:
    """
    Extract text content from a PDF file.

    Args:
        file_path: Path to the PDF file
        max_pages: Maximum pages to extract (default 50)

    Returns:
        dict: Extracted text with keys:
            - text: Extracted text content
            - page_count: Total pages in PDF
            - pages_read: Number of pages extracted
            - char_count: Number of characters
            - file_name: Name of the file

    Example:
        >>> read_pdf_file("/path/to/paper.pdf")
        {
            'text': 'Extracted PDF content...',
            'page_count': 12,
            'pages_read': 12,
            'char_count': 25000,
            'file_name': 'paper.pdf'
        }
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        pages_to_read = min(total_pages, max_pages)

        text_parts = []
        for i in range(pages_to_read):
            page_text = reader.pages[i].extract_text()
            if page_text:
                text_parts.append(f"--- Page {i + 1} ---\n{page_text}")

        text = "\n\n".join(text_parts)

        logger.info(f"Read PDF: {file_path} ({pages_to_read}/{total_pages} pages, {len(text)} chars)")
        return {
            "text": text,
            "page_count": total_pages,
            "pages_read": pages_to_read,
            "char_count": len(text),
            "file_name": os.path.basename(file_path),
        }
    except ImportError:
        return {"error": "PyPDF2 is not installed. Install with: pip install PyPDF2"}
    except Exception as e:
        return {"error": f"Failed to read PDF {file_path}: {str(e)}"}


def read_docx_file(file_path: str) -> dict:
    """
    Extract text content from a DOCX (Word) file.

    Args:
        file_path: Path to the DOCX file

    Returns:
        dict: Extracted text with keys:
            - text: Extracted text content
            - paragraph_count: Number of paragraphs
            - char_count: Number of characters
            - file_name: Name of the file

    Example:
        >>> read_docx_file("/path/to/document.docx")
        {
            'text': 'Document content here...',
            'paragraph_count': 45,
            'char_count': 12000,
            'file_name': 'document.docx'
        }
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    try:
        from docx import Document

        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n\n".join(paragraphs)

        logger.info(f"Read DOCX: {file_path} ({len(paragraphs)} paragraphs, {len(text)} chars)")
        return {
            "text": text,
            "paragraph_count": len(paragraphs),
            "char_count": len(text),
            "file_name": os.path.basename(file_path),
        }
    except ImportError:
        return {"error": "python-docx is not installed. Install with: pip install python-docx"}
    except Exception as e:
        return {"error": f"Failed to read DOCX {file_path}: {str(e)}"}


def read_file(file_path: str) -> dict:
    """
    Auto-detect file type and read content. Supports PDF, DOCX, and text files.

    Args:
        file_path: Path to the file to read

    Returns:
        dict: Extracted content with text, char_count, file_name, and type-specific fields.

    Example:
        >>> read_file("/path/to/document.pdf")
        {'text': '...', 'char_count': 5000, 'file_name': 'document.pdf', ...}
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return read_pdf_file(file_path)
    elif ext in (".docx",):
        return read_docx_file(file_path)
    else:
        # Treat everything else as text (.txt, .md, .csv, .json, .html, etc.)
        return read_text_file(file_path)
