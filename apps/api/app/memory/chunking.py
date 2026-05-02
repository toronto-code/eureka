"""ChunkingService: turn arbitrary source artefacts into `ProjectChunk`-shaped dicts.

Separate chunkers per source type so each preserves what matters:
- **Code**: byte-safe split by line ranges, keeps `file_path`, `language`,
  `start_line`, `end_line`, `branch`, `commit_sha`.
- **Docs / markdown**: split on heading boundaries where possible.
- **Jira tickets**: one chunk for title+description, one per comment.
- **PRs**: one chunk for title+body, optional chunks for long bodies.
- **Commits**: one chunk per commit (message + author).
- **Comments**: one chunk per comment.

The chunker never writes to the DB — it returns plain dicts. Persistence
happens in `ProjectDataService.upsert_chunks`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# -----------------------------------------------------------------------------
# Tunables (chars, not tokens — keeps the chunker dependency-free)
# -----------------------------------------------------------------------------

CODE_CHUNK_LINES = 80
CODE_CHUNK_OVERLAP = 15
DOC_CHUNK_CHARS = 2400
DOC_CHUNK_OVERLAP = 240
LONG_TEXT_THRESHOLD = 1200  # above this, split
MAX_CHUNK_CHARS = 8000  # hard safety cap (embeddings limit)


# -----------------------------------------------------------------------------
# Output shape
# -----------------------------------------------------------------------------


@dataclass
class ChunkDraft:
    """Plain-dict chunk ready to be inserted into project_chunks."""

    project_id: str
    source_type: str
    source_id: str | None = None
    repo_id: str | None = None
    jira_ticket_id: str | None = None
    file_path: str | None = None
    language: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    branch: str | None = None
    commit_sha: str | None = None
    chunk_index: int = 0
    chunk_text: str = ""
    token_count: int | None = None
    chunk_metadata: dict[str, Any] = field(default_factory=dict)

    def to_model_kwargs(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "repo_id": self.repo_id,
            "jira_ticket_id": self.jira_ticket_id,
            "file_path": self.file_path,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "chunk_index": self.chunk_index,
            "chunk_text": self.chunk_text[:MAX_CHUNK_CHARS],
            "token_count": self.token_count,
            "chunk_metadata": dict(self.chunk_metadata),
        }


# -----------------------------------------------------------------------------
# Language detection (extension-based; good enough for metadata)
# -----------------------------------------------------------------------------

_EXT_LANG = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".sql": "sql",
    ".sh": "shell",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".mdx": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
}


def detect_language(path: str | None) -> str | None:
    if not path:
        return None
    lower = path.lower()
    for ext, lang in _EXT_LANG.items():
        if lower.endswith(ext):
            return lang
    return None


# -----------------------------------------------------------------------------
# Chunkers
# -----------------------------------------------------------------------------


class ChunkingService:
    """Produces ChunkDraft lists for each supported source type."""

    # ---------------- Code ---------------------------------------------------

    def chunk_code_file(
        self,
        *,
        project_id: str,
        repo_id: str | None,
        file_path: str,
        content: str,
        branch: str | None = None,
        commit_sha: str | None = None,
        language: str | None = None,
        repo_file_id: str | None = None,
    ) -> list[ChunkDraft]:
        """Split a code file into overlapping line-range chunks."""
        if not content:
            return []
        language = language or detect_language(file_path) or "text"
        lines = content.splitlines()
        if not lines:
            return []

        drafts: list[ChunkDraft] = []
        idx = 0
        i = 0
        while i < len(lines):
            end = min(i + CODE_CHUNK_LINES, len(lines))
            slice_text = "\n".join(lines[i:end])
            if not slice_text.strip():
                i = end
                continue
            drafts.append(
                ChunkDraft(
                    project_id=project_id,
                    source_type="code_file",
                    source_id=repo_file_id or file_path,
                    repo_id=repo_id,
                    file_path=file_path,
                    language=language,
                    start_line=i + 1,
                    end_line=end,
                    branch=branch,
                    commit_sha=commit_sha,
                    chunk_index=idx,
                    chunk_text=slice_text,
                    chunk_metadata={"lines_total": len(lines)},
                )
            )
            idx += 1
            if end >= len(lines):
                break
            i = end - CODE_CHUNK_OVERLAP
            if i <= 0:
                i = end  # prevent infinite loop on short files
        return drafts

    # ---------------- Docs / markdown ----------------------------------------

    def chunk_doc(
        self,
        *,
        project_id: str,
        source_id: str,
        title: str | None,
        content: str,
        repo_id: str | None = None,
        file_path: str | None = None,
        language: str | None = None,
    ) -> list[ChunkDraft]:
        if not content:
            return []
        text = (f"# {title}\n\n{content}" if title else content).strip()
        sections = _split_markdown_sections(text)
        drafts: list[ChunkDraft] = []
        idx = 0
        for section in sections:
            for piece in _split_on_chars(
                section, DOC_CHUNK_CHARS, DOC_CHUNK_OVERLAP
            ):
                drafts.append(
                    ChunkDraft(
                        project_id=project_id,
                        source_type="doc",
                        source_id=source_id,
                        repo_id=repo_id,
                        file_path=file_path,
                        language=language or "markdown",
                        chunk_index=idx,
                        chunk_text=piece,
                        chunk_metadata={"title": title} if title else {},
                    )
                )
                idx += 1
        return drafts

    # ---------------- Jira tickets ------------------------------------------

    def chunk_jira_ticket(
        self,
        *,
        project_id: str,
        jira_ticket_id: str,
        key: str,
        title: str,
        description: str | None,
        comments: list[dict[str, Any]] | None = None,
        labels: list[str] | None = None,
        status: str | None = None,
    ) -> list[ChunkDraft]:
        drafts: list[ChunkDraft] = []
        header = f"[{key}] {title}"
        body = (description or "").strip()
        main_text = f"{header}\n\n{body}" if body else header
        drafts.append(
            ChunkDraft(
                project_id=project_id,
                source_type="jira_ticket",
                source_id=jira_ticket_id,
                jira_ticket_id=jira_ticket_id,
                chunk_index=0,
                chunk_text=main_text,
                chunk_metadata={
                    "key": key,
                    "labels": labels or [],
                    "status": status,
                    "part": "body",
                },
            )
        )
        for ci, comment in enumerate(comments or []):
            body = (comment.get("body") or "").strip()
            if not body:
                continue
            author = comment.get("author") or "unknown"
            drafts.append(
                ChunkDraft(
                    project_id=project_id,
                    source_type="comment",
                    source_id=f"{jira_ticket_id}:comment:{ci}",
                    jira_ticket_id=jira_ticket_id,
                    chunk_index=ci + 1,
                    chunk_text=f"[{key} comment by {author}]\n{body}",
                    chunk_metadata={"key": key, "author": author, "part": "comment"},
                )
            )
        return drafts

    # ---------------- PRs ----------------------------------------------------

    def chunk_pull_request(
        self,
        *,
        project_id: str,
        repo_id: str,
        pull_request_id: str,
        number: int,
        title: str,
        body: str | None,
        head_branch: str | None = None,
        base_branch: str | None = None,
        state: str | None = None,
    ) -> list[ChunkDraft]:
        text = f"PR #{number}: {title}"
        if body:
            text += f"\n\n{body.strip()}"
        drafts: list[ChunkDraft] = []
        for idx, piece in enumerate(
            _split_on_chars(text, DOC_CHUNK_CHARS, DOC_CHUNK_OVERLAP)
        ):
            drafts.append(
                ChunkDraft(
                    project_id=project_id,
                    source_type="pr",
                    source_id=pull_request_id,
                    repo_id=repo_id,
                    branch=head_branch,
                    chunk_index=idx,
                    chunk_text=piece,
                    chunk_metadata={
                        "number": number,
                        "state": state,
                        "head_branch": head_branch,
                        "base_branch": base_branch,
                    },
                )
            )
        return drafts

    # ---------------- Commits -----------------------------------------------

    def chunk_commit(
        self,
        *,
        project_id: str,
        repo_id: str,
        commit_id: str,
        sha: str,
        message: str | None,
        author: str | None = None,
        branch: str | None = None,
    ) -> list[ChunkDraft]:
        if not message:
            return []
        text = f"commit {sha[:12]} by {author or 'unknown'}\n\n{message.strip()}"
        return [
            ChunkDraft(
                project_id=project_id,
                source_type="commit",
                source_id=commit_id,
                repo_id=repo_id,
                commit_sha=sha,
                branch=branch,
                chunk_index=0,
                chunk_text=text,
                chunk_metadata={"author": author, "sha": sha},
            )
        ]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


_HEADING_RE = re.compile(r"(?m)^(#{1,6})\s+.+$")


def _split_markdown_sections(text: str) -> list[str]:
    """Split markdown by heading boundaries; fall back to the whole doc."""
    positions = [m.start() for m in _HEADING_RE.finditer(text)]
    if not positions:
        return [text]
    # Ensure we include the prelude before the first heading if there is one.
    if positions[0] > 0:
        positions = [0] + positions
    sections: list[str] = []
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            sections.append(chunk)
    return sections or [text]


def _split_on_chars(text: str, size: int, overlap: int) -> list[str]:
    """Sliding-window char split; returns whole text if it already fits."""
    if not text:
        return []
    if len(text) <= size:
        return [text]
    pieces: list[str] = []
    i = 0
    while i < len(text):
        end = min(i + size, len(text))
        piece = text[i:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        i = end - overlap
        if i <= 0:
            break
    return pieces


def is_binary_like(content: str) -> bool:
    """Best-effort check to reject binary blobs from chunking."""
    if not content:
        return False
    if "\x00" in content[:2048]:
        return True
    sample = content[:2048]
    printable = sum(
        1 for c in sample if c.isprintable() or c in ("\n", "\r", "\t")
    )
    return printable / max(1, len(sample)) < 0.85
