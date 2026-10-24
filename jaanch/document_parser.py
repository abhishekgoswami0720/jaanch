"""Document content and metadata extraction pipeline for Jaanch.

Supports:
- PDF (via pypdf, with encrypted PDF detection and page-by-page location tracking)
- DOCX (via python-docx, extracting paragraphs, tables, and headers)
- Images (JPG, PNG, WEBP via Pillow with optional OCR integration)
- Plain Text (TXT with automatic encoding detection)

Normalizes whitespace, eliminates extraction artifacts, protects against
prompt injection, and enforces minimum readable text thresholds.
"""

from dataclasses import dataclass, field
import io
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union


from .document_security import EncryptedDocumentError

LOGGER = logging.getLogger("jaanch.document_parser")

MIN_TEXT_CHARS = 30
MIN_TEXT_WORDS = 5


class DocumentParsingError(Exception):
    """Base error for document parsing failures."""
    pass


class InsufficientTextError(DocumentParsingError):
    """Raised when the document contains too little readable text."""
    pass


@dataclass
class ExtractedDocument:
    """Structured extraction result of an offer letter document."""

    doc_id: str
    filename: str
    file_type: str  # "pdf" | "docx" | "image" | "txt"
    full_text: str
    pages_text: Dict[int, str] = field(default_factory=dict)
    total_pages: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    character_count: int = 0
    word_count: int = 0
    is_scanned: bool = False
    warnings: List[str] = field(default_factory=list)


def normalize_document_text(text: str) -> str:
    """Normalizes extracted text by standardizing whitespace, removing invisible

    control characters, and fixing extraction artifacts while preserving case,
    punctuation, currency signs (₹, $, INR), and formatting structure.
    """
    if not text:
        return ""

    # Replace non-breaking spaces and zero-width spaces
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")

    # Standardize fancy quotes and dashes
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    text = text.replace("—", " - ").replace("–", " - ")

    # Remove non-printable control characters except standard whitespace (\n, \r, \t)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalize horizontal whitespace
    text = re.sub(r"[ \t]+", " ", text)

    # Collapse excessive newlines (max 2 consecutive newlines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_from_pdf(file_bytes: bytes, filename: str, doc_id: str) -> ExtractedDocument:
    """Extracts text and metadata from a PDF document, preserving page numbers."""
    try:
        import pypdf  # optional: the chat agent must start even without it
    except ImportError:
        raise DocumentParsingError("PDF support needs pypdf: pip install pypdf")
    stream = io.BytesIO(file_bytes)
    try:
        reader = pypdf.PdfReader(stream)
    except Exception as err:
        raise DocumentParsingError(f"Failed to read PDF document: {err}")

    # Check for password protection / encryption
    if reader.is_encrypted:
        try:
            # Attempt empty password decryption in case it is read-restricted only
            decrypted = reader.decrypt("")
            if not decrypted:
                raise EncryptedDocumentError(
                    "Document is password-protected or encrypted. Please provide an unencrypted version."
                )
        except Exception:
            raise EncryptedDocumentError(
                "Document is password-protected or encrypted. Please provide an unencrypted version."
            )

    pages_text: Dict[int, str] = {}
    total_pages = len(reader.pages)
    warnings = []

    for idx, page in enumerate(reader.pages, start=1):
        try:
            raw_page_text = page.extract_text() or ""
            clean_page_text = normalize_document_text(raw_page_text)
            pages_text[idx] = clean_page_text
        except Exception as err:
            LOGGER.warning(f"Error extracting text from page {idx} of {filename}: {err}")
            pages_text[idx] = ""
            warnings.append(f"Could not extract text from Page {idx} ({type(err).__name__}).")

    full_text = "\n\n".join(
        f"[Page {p}]\n{t}" if t else f"[Page {p}]\n(no selectable text)"
        for p, t in pages_text.items()
    )
    all_text = "\n\n".join(t for t in pages_text.values() if t)

    is_scanned = len(all_text.strip()) < MIN_TEXT_CHARS

    metadata: Dict[str, Any] = {
        "format": "PDF",
        "page_count": total_pages,
    }
    if reader.metadata:
        for k in ("title", "author", "creator", "producer", "creation_date"):
            val = getattr(reader.metadata, k, None)
            if val:
                metadata[k] = str(val)

    if is_scanned:
        # Document has pages but no selectable text (scanned image)
        warnings.append(
            "Document appears to be a scanned image-only PDF with minimal selectable text. "
            "OCR may be required for full extraction."
        )

    words = all_text.split()

    return ExtractedDocument(
        doc_id=doc_id,
        filename=filename,
        file_type="pdf",
        full_text=full_text,
        pages_text=pages_text,
        total_pages=total_pages,
        metadata=metadata,
        character_count=len(all_text),
        word_count=len(words),
        is_scanned=is_scanned,
        warnings=warnings,
    )


def extract_from_docx(file_bytes: bytes, filename: str, doc_id: str) -> ExtractedDocument:
    """Extracts text, tables, and headers from a DOCX Word document."""
    try:
        import docx
    except ImportError:
        raise DocumentParsingError("python-docx is not installed.")

    stream = io.BytesIO(file_bytes)
    try:
        doc = docx.Document(stream)
    except Exception as err:
        raise DocumentParsingError(f"Failed to read DOCX document: {err}")

    sections_text: List[str] = []

    # 1. Paragraphs
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            sections_text.append(txt)

    # 2. Tables
    for table_idx, table in enumerate(doc.tables, start=1):
        table_rows = []
        for row in table.rows:
            cell_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cell_texts:
                table_rows.append(" | ".join(cell_texts))
        if table_rows:
            sections_text.append("\n".join(table_rows))

    raw_text = "\n\n".join(sections_text)
    clean_text = normalize_document_text(raw_text)

    pages_text = {1: clean_text}
    words = clean_text.split()

    metadata: Dict[str, Any] = {
        "format": "DOCX",
        "paragraph_count": len(doc.paragraphs),
        "table_count": len(doc.tables),
    }

    return ExtractedDocument(
        doc_id=doc_id,
        filename=filename,
        file_type="docx",
        full_text=f"[Page 1]\n{clean_text}",
        pages_text=pages_text,
        total_pages=1,
        metadata=metadata,
        character_count=len(clean_text),
        word_count=len(words),
        is_scanned=False,
        warnings=[],
    )


def _extract_with_vision_sync(file_bytes: bytes, filename: str) -> Optional[str]:
    """Fallback OCR using ASI1 Vision endpoint if Tesseract is unavailable and API key is present."""
    import base64
    import json
    import os
    import urllib.request

    key = os.getenv("ASI1_API_KEY") or os.getenv("ASI_ONE_API_KEY")
    if not key:
        return None
    try:
        mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{mime};base64,{b64}"
        body = {
            "model": os.getenv("ASI1_MODEL", "asi1"),
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Transcribe the exact text from this job/internship offer screenshot or flyer. Return ONLY the extracted text with no extra commentary.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                }
            ],
            "max_tokens": 1000,
        }
        req = urllib.request.Request(
            "https://api.asi1.ai/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
    except Exception as err:
        LOGGER.warning(f"Vision OCR fallback failed: {err}")
    return None


def extract_from_image(file_bytes: bytes, filename: str, doc_id: str) -> ExtractedDocument:
    """Processes an image offer letter (JPG, PNG, WEBP) with OCR support."""
    try:
        from PIL import Image
    except ImportError:
        raise DocumentParsingError("Pillow is not installed.")

    stream = io.BytesIO(file_bytes)
    try:
        img = Image.open(stream)
        img.verify()
        # Reopen for actual processing as verify closes the file pointer
        stream.seek(0)
        img = Image.open(stream)
    except Exception as err:
        raise DocumentParsingError(f"Corrupt or unreadable image file: {err}")

    metadata: Dict[str, Any] = {
        "format": img.format or "IMAGE",
        "width": img.width,
        "height": img.height,
        "mode": img.mode,
    }

    extracted_text = ""
    warnings = []

    # 1. Attempt OCR if pytesseract is installed
    try:
        import pytesseract
        extracted_text = pytesseract.image_to_string(img) or ""
        clean_text = normalize_document_text(extracted_text)
    except Exception:
        clean_text = ""

    # 2. If local OCR yielded no text, attempt ASI1 Vision OCR fallback
    if not clean_text:
        vision_text = _extract_with_vision_sync(file_bytes, filename)
        if vision_text:
            clean_text = normalize_document_text(vision_text)
            warnings.append("Text extracted via ASI1 Vision OCR engine.")
        else:
            warnings.append(
                "Tesseract OCR is not installed or configured on the system. "
                "Please paste the text directly or configure Tesseract OCR for automated image scanning."
            )

    words = clean_text.split()

    return ExtractedDocument(
        doc_id=doc_id,
        filename=filename,
        file_type="image",
        full_text=f"[Image: {filename}]\n{clean_text}" if clean_text else f"[Image: {filename}]",
        pages_text={1: clean_text},
        total_pages=1,
        metadata=metadata,
        character_count=len(clean_text),
        word_count=len(words),
        is_scanned=True,
        warnings=warnings,
    )


def extract_from_txt(file_bytes: bytes, filename: str, doc_id: str) -> ExtractedDocument:
    """Safely decodes and extracts text from a plain text document across common encodings."""
    raw_text = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            raw_text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if raw_text is None:
        raw_text = file_bytes.decode("utf-8", errors="replace")

    clean_text = normalize_document_text(raw_text)
    words = clean_text.split()

    metadata: Dict[str, Any] = {
        "format": "TXT",
        "encoding": "utf-8",
    }

    return ExtractedDocument(
        doc_id=doc_id,
        filename=filename,
        file_type="txt",
        full_text=f"[Document: {filename}]\n{clean_text}",
        pages_text={1: clean_text},
        total_pages=1,
        metadata=metadata,
        character_count=len(clean_text),
        word_count=len(words),
        is_scanned=False,
        warnings=[],
    )


def parse_document(file_bytes: bytes, filename: str, doc_id: str) -> ExtractedDocument:
    """Parses any supported document format and extracts structured text and metadata.

    Enforces minimum readable text validation.
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        doc = extract_from_pdf(file_bytes, filename, doc_id)
    elif ext == ".docx":
        doc = extract_from_docx(file_bytes, filename, doc_id)
    elif ext in (".jpg", ".jpeg", ".png", ".webp"):
        doc = extract_from_image(file_bytes, filename, doc_id)
    elif ext == ".txt":
        doc = extract_from_txt(file_bytes, filename, doc_id)
    else:
        raise DocumentParsingError(f"Unsupported format '{ext}'.")

    # Minimum readable text check
    if doc.character_count < MIN_TEXT_CHARS or doc.word_count < MIN_TEXT_WORDS:
        # Check if it was an image without OCR or empty file
        if doc.file_type == "image" or doc.is_scanned:
            raise InsufficientTextError(
                f"The document '{filename}' contains too little readable text ({doc.character_count} chars). "
                "For scanned letters or photos, please upload a clear digital PDF or paste the offer text."
            )
        raise InsufficientTextError(
            f"The document '{filename}' contains too little readable text ({doc.character_count} chars). "
            "Please upload a clearer document or paste the text directly."
        )

    return doc
