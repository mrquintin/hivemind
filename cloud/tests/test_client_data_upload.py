"""Tests for the client data file upload endpoint."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.routers.client_data import upload_client_data


class _FakeUploadFile:
    """Minimal stand-in for FastAPI UploadFile."""

    def __init__(self, filename: str, content: bytes, content_type: str = "text/plain"):
        self.filename = filename
        self.content_type = content_type
        self.file = MagicMock()
        self.file.read.return_value = content


class TestUploadClientData:
    """Unit tests for the upload_client_data endpoint function."""

    @patch("app.routers.client_data.ClientData")
    @patch("app.services.storage.store_file", return_value=("local://uploads/client_uploads/test.txt", "uploads/client_uploads/test.txt"))
    @patch("app.rag.extraction.extract_text_from_bytes", return_value="extracted text content")
    def test_upload_txt_file(self, mock_extract, mock_store, mock_model):
        db = MagicMock()
        user = {"sub": "testuser", "role": "operator"}
        file = _FakeUploadFile("report.txt", b"hello world", "text/plain")

        mock_instance = MagicMock()
        mock_model.return_value = mock_instance

        upload_client_data(
            client_id="client-1",
            file=file,
            label="",
            db=db,
            _user=user,
        )

        mock_extract.assert_called_once_with("text/plain", b"hello world")
        mock_store.assert_called_once_with("report.txt", b"hello world", document_type="client_upload")

        # Verify the model was constructed with correct args
        call_kwargs = mock_model.call_args[1]
        assert call_kwargs["client_id"] == "client-1"
        assert call_kwargs["label"] == "report.txt"  # falls back to filename
        assert call_kwargs["content"] == "extracted text content"
        assert call_kwargs["metadata_"]["filename"] == "report.txt"
        assert call_kwargs["metadata_"]["content_type"] == "text/plain"
        assert call_kwargs["metadata_"]["byte_size"] == 11
        assert call_kwargs["metadata_"]["source"] == "file_upload"

        db.add.assert_called_once_with(mock_instance)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(mock_instance)

    @patch("app.routers.client_data.ClientData")
    @patch("app.services.storage.store_file", return_value=("local://uploads/client_uploads/doc.pdf", "uploads/client_uploads/doc.pdf"))
    @patch("app.rag.extraction.extract_text_from_bytes", return_value="PDF text content")
    def test_upload_with_explicit_label(self, mock_extract, mock_store, mock_model):
        db = MagicMock()
        user = {"sub": "testuser", "role": "operator"}
        file = _FakeUploadFile("doc.pdf", b"%PDF-fake", "application/pdf")

        mock_instance = MagicMock()
        mock_model.return_value = mock_instance

        upload_client_data(
            client_id="client-2",
            file=file,
            label="Q4 Report",
            db=db,
            _user=user,
        )

        call_kwargs = mock_model.call_args[1]
        assert call_kwargs["label"] == "Q4 Report"
        assert call_kwargs["metadata_"]["content_type"] == "application/pdf"

    @patch("app.routers.client_data.ClientData")
    @patch("app.services.storage.store_file", return_value=("local://test", "test"))
    @patch("app.rag.extraction.extract_text_from_bytes", return_value="")
    def test_upload_empty_extraction(self, mock_extract, mock_store, mock_model):
        db = MagicMock()
        user = {"sub": "testuser", "role": "operator"}
        file = _FakeUploadFile("image.png", b"\x89PNG", "image/png")

        mock_instance = MagicMock()
        mock_model.return_value = mock_instance

        upload_client_data(
            client_id="client-3",
            file=file,
            label="",
            db=db,
            _user=user,
        )

        call_kwargs = mock_model.call_args[1]
        assert call_kwargs["content"] == ""
        assert call_kwargs["label"] == "image.png"
