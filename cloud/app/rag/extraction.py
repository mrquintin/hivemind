import io
import re

import fitz
from docx import Document


def _strip_html(text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_text_from_bytes(content_type: str, data: bytes) -> str:
    if content_type == "application/pdf" or data[:4] == b"%PDF":
        doc = fitz.open(stream=data, filetype="pdf")
        pages = [page.get_text() for page in doc]
        return "\n\n".join(pages).strip()

    if content_type in {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }:
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs).strip()

    text = data.decode("utf-8", errors="ignore")
    if content_type in {"text/html", "application/xhtml+xml"}:
        return _strip_html(text)

    return text.strip()
