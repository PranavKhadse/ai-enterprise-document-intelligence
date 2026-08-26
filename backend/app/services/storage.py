"""
Storage service abstraction and local filesystem storage implementation.
"""
import hashlib
import os
import re
from pathlib import Path
from typing import Protocol, Tuple
from fastapi import UploadFile
from backend.app.core.config import settings


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class FileSizeExceededError(StorageError):
    """Raised when uploaded file exceeds the configured maximum size limit."""
    pass


class InvalidFileTypeError(StorageError):
    """Raised when file extension or magic bytes do not match supported types."""
    pass


class StorageService(Protocol):
    """
    Protocol interface for file storage implementations (Local, S3, Azure, GCS).
    """
    async def save_file(self, file: UploadFile) -> Tuple[str, str]:
        """
        Saves an uploaded file and returns (file_path, sha256_hash).
        """
        ...

    def delete_file(self, file_path: str) -> None:
        """
        Removes a file from storage.
        """
        ...


class LocalFileStorage:
    """
    Local filesystem storage implementation with streaming validation,
    magic byte checking, and atomic writes.
    """
    BUFFER_SIZE = 64 * 1024  # 64 KB streaming buffer
    PDF_MAGIC_BYTES = b"%PDF-"

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or settings.STORAGE_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitizes filename to prevent directory traversal and special character exploits.
        """
        clean_name = Path(filename).name
        # Keep alphanumeric, underscores, hyphens, and dots
        clean_name = re.sub(r"[^\w\-.]", "_", clean_name)
        return clean_name or "document.pdf"

    async def save_file(self, file: UploadFile) -> Tuple[str, str]:
        """
        Streams an UploadFile to disk while validating size, magic bytes,
        and computing the SHA-256 hash.

        Returns:
            Tuple[str, str]: (absolute_or_normalized_file_path, sha256_hex_hash)
        """
        if not file.filename:
            raise InvalidFileTypeError("File must have a valid filename.")

        sanitized_name = self._sanitize_filename(file.filename)
        file_ext = Path(sanitized_name).suffix.lower()

        if file_ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
            raise InvalidFileTypeError(
                f"Unsupported file extension '{file_ext}'. Allowed extensions: {settings.ALLOWED_UPLOAD_EXTENSIONS}"
            )

        sha256_hasher = hashlib.sha256()
        bytes_read = 0
        temp_file_path = self.base_dir / f"tmp_{os.urandom(8).hex()}_{sanitized_name}"
        is_first_chunk = True

        try:
            with open(temp_file_path, "wb") as buffer:
                while chunk := await file.read(self.BUFFER_SIZE):
                    bytes_read += len(chunk)

                    if bytes_read > settings.MAX_UPLOAD_SIZE_BYTES:
                        raise FileSizeExceededError(
                            f"File size exceeds maximum permitted limit of {settings.MAX_UPLOAD_SIZE_BYTES} bytes."
                        )

                    # Validate PDF magic bytes on initial buffer
                    if is_first_chunk:
                        if len(chunk) < 5 or not chunk.startswith(self.PDF_MAGIC_BYTES):
                            raise InvalidFileTypeError(
                                "Invalid PDF content. File header does not match standard PDF signature (%PDF-)."
                            )
                        is_first_chunk = False

                    sha256_hasher.update(chunk)
                    buffer.write(chunk)

            if bytes_read == 0:
                raise InvalidFileTypeError("Uploaded file is empty (0 bytes).")

            file_hash = sha256_hasher.hexdigest()
            final_filename = f"{file_hash[:16]}_{sanitized_name}"
            final_path = self.base_dir / final_filename

            # Atomic move from temporary file to final hash-named file
            if temp_file_path.exists():
                temp_file_path.replace(final_path)

            return str(final_path.resolve()), file_hash

        except Exception:
            # Clean up temporary artifact on validation or write failure
            if temp_file_path.exists():
                temp_file_path.unlink(missing_ok=True)
            raise

    def delete_file(self, file_path: str) -> None:
        """
        Deletes the file at file_path if it exists.
        """
        path = Path(file_path)
        if path.exists():
            path.unlink(missing_ok=True)


# Global storage service instance
storage_service = LocalFileStorage()
