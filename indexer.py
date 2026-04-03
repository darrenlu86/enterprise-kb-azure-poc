"""Index chunks into ChromaDB with embeddings.

Simulates: Azure AI Search indexer + AzureOpenAIEmbedding skill + index creation.
"""

import hashlib

import chromadb
from openai import OpenAI

from config import CHROMA_DIR, EMBEDDING_MODEL
from data_loader import KnowledgeBase


COLLECTION_NAME = "financial_ebanking_chunks"
MOCK_DIM = 256  # dimension for mock embeddings


def get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def _mock_embedding(text: str) -> list[float]:
    """Deterministic mock embedding based on text hash. For testing without API."""
    # Generate enough bytes: each float needs 1 byte seed
    needed = MOCK_DIM
    parts = []
    for i in range(needed // 32 + 1):
        parts.append(hashlib.sha256(f"{text}:{i}".encode("utf-8")).digest())
    raw = b"".join(parts)
    values = [((b / 255.0) * 2 - 1) for b in raw[:MOCK_DIM]]
    # Normalize to unit vector
    norm = sum(v * v for v in values) ** 0.5
    return [v / norm if norm > 0 else 0.0 for v in values]


def embed_texts(
    client: OpenAI | None,
    texts: list[str],
    model: str = EMBEDDING_MODEL,
    mock: bool = False,
) -> list[list[float]]:
    """Generate embeddings via OpenAI API (Azure OpenAI compatible), or mock."""
    if mock or client is None:
        return [_mock_embedding(t) for t in texts]
    response = client.embeddings.create(input=texts, model=model)
    return [item.embedding for item in response.data]


def index_knowledge_base(kb: KnowledgeBase, openai_client: OpenAI | None = None, mock: bool = False) -> None:
    """Index all chunks into ChromaDB with embeddings and metadata.

    Simulates Azure AI Search index with:
    - Vector field (embeddings)
    - Full-text content (for BM25-like search via ChromaDB)
    - Filterable metadata fields (article, terms, priority, etc.)
    """
    chroma = get_chroma_client()

    # Delete existing collection if present
    try:
        chroma.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = chroma.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Batch embed (OpenAI supports up to 2048 inputs)
    batch_size = 50
    all_chunks = list(kb.chunks)

    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        texts = [c.content for c in batch]
        embeddings = embed_texts(openai_client, texts, mock=mock)

        ids = [c.chunk_id for c in batch]
        documents = texts
        metadatas = [
            {
                "article": c.article,
                "section": c.section or "",
                "version": c.version,
                "contained_terms": ",".join(c.contained_terms),
                "is_definition_chunk": c.is_definition_chunk,
                "topic_tags": ",".join(c.topic_tags),
                "priority": c.priority,
            }
            for c in batch
        ]

        collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        print(f"  Indexed {min(i + batch_size, len(all_chunks))}/{len(all_chunks)} chunks")

    print(f"Indexing complete: {collection.count()} chunks in ChromaDB")
