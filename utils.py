from pathlib import Path
import os
import fitz
from docx import Document
import io

def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """text extraction"""
    ext = filename.split('.')[-1].lower()

    try:
        if ext == 'pdf':
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                if doc.page_count == 0:
                    return "ERROR_EMPTY_FILE"
                
                # Joins all page text into a single string
                text = "\n".join([page.get_text() for page in doc])
            
            return text.strip() if text.strip() else "ERROR_IMAGE_ONLY_PDF"

        elif ext in ['docx', 'doc']:
            with io.BytesIO(file_bytes) as docx_stream:
                doc = Document(docx_stream)
                text = "\n".join([para.text for para in doc.paragraphs])
                return text.strip() if text.strip() else "ERROR_EMPTY_FILE"

    except Exception:
        return "ERROR_PROCESSING_DOCUMENT"

    return "ERROR_UNSUPPORTED_FORMAT"

def chunk_text(text: str, max_chars: int = 5000):
    """Generator for chunking large text without high memory overhead."""
    for i in range(0, len(text), max_chars):
        yield text[i:i + max_chars]
