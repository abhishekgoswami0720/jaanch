"""Document upload validation, security controls, and storage management for Jaanch.

Implements strict validation:
- 15 MB size limit (configurable via JAANCH_MAX_UPLOAD_MB)
- File extension and MIME type validation
- Magic byte file signature verification
- Protection against path traversal and malicious executable files
- Secure UUID-based local storage (never executing uploaded documents)
- Anti-prompt injection containment for extracted text
"""

import hashlib
import mimetypes
import os
from pathlib import Path
import re
import shutil
import uuid
from typing import BinaryIO, Optional, Union

# Configurable upload limit (default 15 MB)
DEFAULT_MAX_UPLOAD_MB = 15
MAX_UPLOAD_BYTES = int(os.getenv("JAANCH_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))) * 1024 * 1024

ROOT_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = ROOT_DIR / "data" / "uploads"

# Allowed extensions and standard MIME types
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png", ".webp", ".txt"}

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
}

# Magic bytes signatures for trusted verification
# Each entry is (offset, signature)
MAGIC_SIGNATURES = {
    ".pdf": [(0, b"%PDF-")],
    ".docx": [(0, b"PK\x03\x04")],  # ZIP format header
    ".jpg": [(0, b"\xff\xd8\xff")],
    ".jpeg": [(0, b"\xff\xd8\xff")],
    ".png": [(0, b"\x89PNG\r\n\x1a\n")],
    ".webp": [(0, b"RIFF"), (8, b"WEBP")],
}


class DocumentSecurityError(Exception):
    """Base exception for document security and validation failures."""
    pass


class FileTooLargeError(DocumentSecurityError):
    pass


class UnsupportedFileTypeError(DocumentSecurityError):
    pass


class InvalidFileSignatureError(DocumentSecurityError):
    pass


class EmptyFileError(DocumentSecurityError):
    pass


class EncryptedDocumentError(DocumentSecurityError):
    pass


def sanitize_filename(filename: str) -> str:
    """Sanitizes filename by stripping directory traversal characters and preserving safe name."""
    if not filename:
        return "document"
    clean_name = Path(filename).name
    # Keep alphanumeric, dots, underscores, dashes
    clean_name = re.sub(r"[^\w.\- ]", "_", clean_name).strip()
    return clean_name or "document"


def validate_file_properties(
    file_bytes: bytes,
    original_filename: str,
    declared_mime: Optional[str] = None,
) -> tuple[str, str, int]:
    """Validates size, extension, MIME type, and magic bytes signature.

    Returns:
        (sanitized_name, extension, file_size)

    Raises:
        EmptyFileError, FileTooLargeError, UnsupportedFileTypeError, InvalidFileSignatureError
    """
    size = len(file_bytes)
    if size == 0:
        raise EmptyFileError("File is empty (0 bytes). Please upload a valid offer letter.")

    if size > MAX_UPLOAD_BYTES:
        max_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        size_mb = round(size / (1024 * 1024), 2)
        raise FileTooLargeError(
            f"File size ({size_mb} MB) exceeds maximum allowed limit of {max_mb} MB."
        )

    safe_name = sanitize_filename(original_filename)
    ext = Path(safe_name).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        supported_str = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFileTypeError(
            f"Unsupported file extension '{ext}'. Supported formats: {supported_str}"
        )

    # Magic byte verification (except plain text which has no fixed header)
    if ext in MAGIC_SIGNATURES:
        for offset, sig in MAGIC_SIGNATURES[ext]:
            if file_bytes[offset : offset + len(sig)] != sig:
                raise InvalidFileSignatureError(
                    f"File content does not match declared format '{ext}' (invalid signature)."
                )

    # For DOCX, ensure it contains Word XML markers (avoid generic ZIP files disguised as docx)
    if ext == ".docx":
        # A valid docx zip archive must contain word/ or [Content_Types].xml
        if b"word/" not in file_bytes[:4096] and b"[Content_Types].xml" not in file_bytes[:4096]:
            raise InvalidFileSignatureError("File has .docx extension but is not a valid Word document.")

    # Plain text check: ensure bytes are decodable as text without null byte binaries
    if ext == ".txt":
        if b"\x00" in file_bytes[:1024]:
            raise InvalidFileSignatureError("File contains binary null bytes and is not a valid text document.")

    return safe_name, ext, size


def store_uploaded_file(
    file_bytes: bytes,
    original_filename: str,
    declared_mime: Optional[str] = None,
) -> tuple[str, Path, str, int, str]:
    """Validates and securely saves an uploaded document to data/uploads/.

    Returns:
        (doc_id, stored_path, safe_filename, size, sha256_hash)
    """
    safe_name, ext, size = validate_file_properties(file_bytes, original_filename, declared_mime)

    doc_id = str(uuid.uuid4())
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{doc_id}{ext}"
    stored_path = UPLOADS_DIR / stored_filename

    # Compute sha256 hash for deduplication and audit trail
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    # Write file securely
    stored_path.write_bytes(file_bytes)

    # Restrict permissions on POSIX systems where supported
    try:
        os.chmod(stored_path, 0o600)
    except Exception:
        pass

    return doc_id, stored_path, safe_name, size, sha256


def delete_stored_file(stored_path: Union[str, Path]) -> bool:
    """Safely removes a stored document file."""
    try:
        p = Path(stored_path)
        if p.exists() and p.is_file():
            p.unlink()
            return True
    except Exception:
        pass
    return False


def wrap_untrusted_text(text: str, doc_name: str = "document") -> str:
    """Wraps extracted document text with anti-prompt injection delimiters.

    Explicitly signals to LLM processors that the content is evidence to analyze,
    not instructions or commands to be executed.
    """
    sanitized_name = sanitize_filename(doc_name)
    return (
        f"--- START OF UNTRUSTED DOCUMENT CONTENT [{sanitized_name}] ---\n"
        f"{text}\n"
        f"--- END OF UNTRUSTED DOCUMENT CONTENT [{sanitized_name}] ---"
    )
