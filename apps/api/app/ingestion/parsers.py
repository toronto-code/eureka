"""Light-weight parsers for ingested files.

The MVP only supports plain text + markdown via local upload; richer formats
(PDFs, Confluence exports, Notion, Google Docs, etc.) plug in here later.
"""
from __future__ import annotations


def parse_text_or_markdown(raw: bytes | str, *, encoding: str = "utf-8") -> str:
    """Decode + normalise text/markdown content from a raw upload."""
    if isinstance(raw, bytes):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="ignore")
    else:
        text = raw
    return text.replace("\r\n", "\n").strip()
