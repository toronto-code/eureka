"""InquiryLane: answer a question using retrieved chunks, with citations."""
from __future__ import annotations

import json
import logging
from typing import Any

from app.agents.lanes.base import BaseLane, LaneContext
from app.agents.llm_client import OpenAIClient, get_llm_client
from app.agents.ol.prompts import INQUIRY_SYSTEM_PROMPT
from app.agents.ol.schemas import LaneResult
from app.memory.retrieval import RetrievedChunk

logger = logging.getLogger(__name__)


class InquiryLane(BaseLane):
    name = "inquiry"

    def __init__(self, llm: OpenAIClient | None = None) -> None:
        self._llm = llm or get_llm_client()

    def run(self, ctx: LaneContext) -> LaneResult:
        result = self._empty_result(self.name)
        result.citations = self._citations_from(ctx.retrieved_chunks)
        chunks_prompt = _render_chunks(ctx.retrieved_chunks)
        user_prompt = (
            f"Question:\n{ctx.request.user_request.strip()}\n\n"
            f"Retrieved chunks:\n{chunks_prompt}"
        )

        if self._llm.configured:
            try:
                data = self._llm.generate_json(
                    system_prompt=INQUIRY_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                )
                answer = data.get("answer") or ""
                citations = data.get("citations") or []
                follow_ups = data.get("follow_up_questions") or []
                result.summary = _first_sentence(answer)
                result.details = answer
                result.extra = {
                    "citations_model": citations,
                    "follow_up_questions": follow_ups,
                    "confidence": data.get("confidence"),
                }
                result.status = "completed"
                ctx.add_step(result, "inquiry.answer_generated", f"{len(ctx.retrieved_chunks)} chunks used")
                return result
            except Exception as exc:  # noqa: BLE001
                logger.warning("InquiryLane LLM call failed: %s", exc)
                ctx.add_step(result, "inquiry.llm_failed", str(exc), ok=False)

        # Deterministic fallback — stitched answer without LLM.
        if not ctx.retrieved_chunks:
            result.status = "completed"
            result.summary = "No project context available yet."
            result.details = (
                "The project has no indexed chunks. Sync GitHub/Jira or ingest "
                "docs, then re-run."
            )
            return result

        bullets = []
        for c in ctx.retrieved_chunks[:5]:
            label = c.file_path or c.source_type
            bullets.append(f"- [{c.id[:8]}] **{label}** — {_snippet(c.chunk_text)}")
        result.summary = (
            f"Fallback answer: surfaced {len(ctx.retrieved_chunks)} project chunks."
        )
        result.details = (
            f"{result.summary}\n\n" + "\n".join(bullets)
        )
        result.status = "completed"
        ctx.add_step(result, "inquiry.fallback_used", "no OpenAI key; returned chunk list")
        return result


def _render_chunks(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(none)"
    out: list[str] = []
    for c in chunks[:15]:
        label = c.file_path or c.source_type
        line_range = (
            f" L{c.start_line}-{c.end_line}" if c.start_line and c.end_line else ""
        )
        out.append(
            f"[{c.id[:8]}] ({c.source_type}) {label}{line_range}\n{c.chunk_text[:1500]}"
        )
    return "\n\n".join(out)


def _snippet(text: str, size: int = 220) -> str:
    if not text:
        return ""
    cleaned = " ".join(text.split())
    return cleaned[:size] + ("…" if len(cleaned) > size else "")


def _first_sentence(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    for end in (". ", "! ", "? ", "\n"):
        idx = cleaned.find(end)
        if idx > 0:
            return cleaned[: idx + 1].strip()
    return cleaned[:240]
