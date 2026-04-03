"""Assemble the final prompt with System Prompt + dynamic term injection + retrieved chunks.

Simulates: Azure AI Foundry Prompt Flow prompt assembly step.
"""

from config import SYSTEM_PROMPT_PATH
from data_loader import KnowledgeBase
from search import SearchResult


def load_system_prompt_template() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def build_retrieval_context(results: list[SearchResult]) -> str:
    """Format retrieved chunks for injection into the prompt."""
    parts = []
    for i, r in enumerate(results, 1):
        sources = ", ".join(r.match_sources)
        parts.append(
            f"### 檢索結果 {i}（{r.article}，分數: {r.score:.4f}，來源: {sources}）\n"
            f"Chunk ID: {r.chunk_id}\n"
            f"{r.content}"
        )
    return "\n\n".join(parts)


def build_messages(
    query: str,
    term_block: str,
    retrieval_context: str,
) -> list[dict[str, str]]:
    """Build the final chat messages array for OpenAI API call.

    The system prompt template has placeholder sections that we replace
    with dynamic content.
    """
    template = load_system_prompt_template()

    # Replace dynamic sections
    system_prompt = template.replace(
        "{動態注入的術語定義區塊 — 由 RAG 系統根據查詢動態填入}",
        term_block,
    ).replace(
        "{RAG 檢索結果 — 由系統動態填入相關條文 chunk}",
        retrieval_context,
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query},
    ]
