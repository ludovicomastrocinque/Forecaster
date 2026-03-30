"""File text extraction for PDF, DOCX, TXT uploads."""

import io


def extract_text(uploaded_file, filename):
    """Route to the correct parser based on file extension. Returns plain text."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "pdf":
        return _parse_pdf(uploaded_file)
    elif ext == "docx":
        return _parse_docx(uploaded_file)
    elif ext == "txt":
        return uploaded_file.read().decode("utf-8")
    else:
        raise ValueError(f"Unsupported file type: .{ext}")


def _parse_pdf(uploaded_file):
    from PyPDF2 import PdfReader
    reader = PdfReader(io.BytesIO(uploaded_file.read()))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _parse_docx(uploaded_file):
    from docx import Document
    doc = Document(io.BytesIO(uploaded_file.read()))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs).strip()
