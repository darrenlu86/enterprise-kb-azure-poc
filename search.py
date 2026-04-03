"""Hybrid search engine simulating Azure AI Search.

Implements:
- Vector search (cosine similarity) — maps to Azure AI Search vector query
- Keyword/metadata term match — maps to Azure AI Search $filter + BM25
- Reciprocal Rank Fusion (RRF) — Azure AI Search native behavior
- Query rewriting with synonym map — maps to Azure AI Search Synonym Maps
"""

from dataclasses import dataclass
from openai import OpenAI
import chromadb

from config import (
    CHROMA_DIR, EMBEDDING_MODEL,
    VECTOR_WEIGHT, BM25_WEIGHT, TERM_MATCH_WEIGHT, TOP_K,
)
from data_loader import KnowledgeBase
from indexer import COLLECTION_NAME, _mock_embedding


@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    content: str
    score: float
    article: str
    contained_terms: tuple[str, ...]
    is_definition_chunk: bool
    match_sources: tuple[str, ...]  # which search routes contributed


def rewrite_query(query: str, kb: KnowledgeBase) -> str:
    """Rewrite query by replacing prohibited alternatives with correct terms.

    Simulates Azure AI Search Synonym Maps applied at query time.
    """
    rewritten = query
    replacements = []
    for alt, correct in kb.synonym_map.items():
        if alt in rewritten:
            rewritten = rewritten.replace(alt, correct)
            replacements.append(f"'{alt}' → '{correct}'")
    if replacements:
        print(f"  Query rewriting: {', '.join(replacements)}")
    return rewritten


def detect_query_terms(query: str, kb: KnowledgeBase) -> list[str]:
    """Detect known terms in the query string.

    Returns list of term IDs found.
    """
    found = []
    for term_name, term_id in kb.term_name_index.items():
        if term_name in query:
            found.append(term_id)
    return found


def _reciprocal_rank(rank: int, k: int = 60) -> float:
    """RRF score: 1 / (k + rank). Azure AI Search uses k=60 by default."""
    return 1.0 / (k + rank)


def hybrid_search(
    query: str,
    kb: KnowledgeBase,
    openai_client: OpenAI | None = None,
    top_k: int = TOP_K,
    mock: bool = False,
) -> list[SearchResult]:
    """Execute hybrid search combining vector + keyword + term metadata.

    Simulates Azure AI Search hybrid query with RRF fusion:
    1. Vector search (dense embedding cosine similarity)
    2. Full-text search (ChromaDB document search ≈ BM25)
    3. Term metadata exact match ($filter on contained_terms)

    Results are fused using Reciprocal Rank Fusion (RRF).
    """
    chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = chroma.get_collection(COLLECTION_NAME)

    # --- Rewrite query ---
    rewritten = rewrite_query(query, kb)

    # --- Route 1: Vector search ---
    if mock or openai_client is None:
        query_embedding = _mock_embedding(rewritten)
    else:
        query_embedding = openai_client.embeddings.create(
            input=[rewritten], model=EMBEDDING_MODEL
        ).data[0].embedding

    vector_results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k * 2, 20),
        include=["documents", "metadatas", "distances"],
    )

    vector_scores: dict[str, float] = {}
    for rank, chunk_id in enumerate(vector_results["ids"][0], start=1):
        vector_scores[chunk_id] = _reciprocal_rank(rank)

    # --- Route 2: Keyword search (BM25-like term frequency scoring) ---
    # Simple keyword matching instead of ChromaDB query_texts
    # (avoids ChromaDB's built-in model download)
    all_data = collection.get(include=["documents", "metadatas"])
    query_terms = list(set(rewritten))  # character-level for Chinese
    query_words = rewritten.split()  # word-level for any English terms

    keyword_scores_raw: list[tuple[str, float]] = []
    for idx, chunk_id in enumerate(all_data["ids"]):
        doc = all_data["documents"][idx]
        # Count character overlap (effective for Chinese)
        char_hits = sum(1 for c in query_terms if c in doc)
        # Count word/phrase overlap
        phrase_hits = sum(2 for w in query_words if len(w) > 1 and w in doc)
        score = char_hits + phrase_hits
        if score > 0:
            keyword_scores_raw.append((chunk_id, score))

    keyword_scores_raw.sort(key=lambda x: -x[1])
    text_scores: dict[str, float] = {}
    for rank, (chunk_id, _) in enumerate(keyword_scores_raw[:top_k * 2], start=1):
        text_scores[chunk_id] = _reciprocal_rank(rank)

    # --- Route 3: Term metadata exact match ---
    query_term_ids = detect_query_terms(rewritten, kb)
    term_scores: dict[str, float] = {}

    if query_term_ids:
        # Simulate Azure AI Search $filter on metadata
        all_data = collection.get(include=["metadatas"])
        for idx, chunk_id in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][idx]
            chunk_terms = set(meta.get("contained_terms", "").split(","))
            overlap = len(set(query_term_ids) & chunk_terms)
            if overlap > 0:
                # Boost definition chunks (simulates definitionChunkBoost: 1.5)
                boost = 1.5 if meta.get("is_definition_chunk") else 1.0
                term_scores[chunk_id] = overlap * boost

        # Convert to RRF ranks
        sorted_term = sorted(term_scores.items(), key=lambda x: -x[1])
        term_scores = {
            cid: _reciprocal_rank(rank)
            for rank, (cid, _) in enumerate(sorted_term, start=1)
        }

    # --- RRF Fusion ---
    all_chunk_ids = set(vector_scores) | set(text_scores) | set(term_scores)
    fused: dict[str, float] = {}
    match_sources: dict[str, list[str]] = {}

    for cid in all_chunk_ids:
        score = 0.0
        sources = []
        if cid in vector_scores:
            score += VECTOR_WEIGHT * vector_scores[cid]
            sources.append("vector")
        if cid in text_scores:
            score += BM25_WEIGHT * text_scores[cid]
            sources.append("keyword")
        if cid in term_scores:
            score += TERM_MATCH_WEIGHT * term_scores[cid]
            sources.append("term_match")
        fused[cid] = score
        match_sources[cid] = sources

    # Sort by fused score, take top_k
    ranked = sorted(fused.items(), key=lambda x: -x[1])[:top_k]

    # Build results with full metadata
    results = []
    # Fetch all needed chunk data
    if ranked:
        fetched = collection.get(
            ids=[cid for cid, _ in ranked],
            include=["documents", "metadatas"],
        )
        id_to_idx = {cid: i for i, cid in enumerate(fetched["ids"])}

        for cid, score in ranked:
            idx = id_to_idx[cid]
            meta = fetched["metadatas"][idx]
            results.append(SearchResult(
                chunk_id=cid,
                content=fetched["documents"][idx],
                score=score,
                article=meta.get("article", ""),
                contained_terms=tuple(meta.get("contained_terms", "").split(",")),
                is_definition_chunk=meta.get("is_definition_chunk", False),
                match_sources=tuple(match_sources.get(cid, [])),
            ))

    return results
