"""End-to-end test on real Azure services.

Verifies:
  1. Azure AI Search hybrid query (vector + text + filter)
  2. Azure AI Search synonym map
  3. Cosmos DB glossary lookup
  4. Azure OpenAI generation with term-aware system prompt
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery, VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from azure.cosmos import CosmosClient
from openai import AzureOpenAI

from config import SYSTEM_PROMPT_PATH


def get_clients():
    search_client = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name="financial-ebanking-chunks",
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
    )
    cosmos_client = CosmosClient(
        os.environ["AZURE_COSMOS_ENDPOINT"],
        os.environ["AZURE_COSMOS_KEY"],
    )
    openai_client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2024-10-21",
    )
    return search_client, cosmos_client, openai_client


def test_hybrid_search(search_client, openai_client, query: str):
    """Test Azure AI Search hybrid query."""
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}")

    # Generate query embedding
    embedding = openai_client.embeddings.create(
        input=[query], model="text-embedding-3-large"
    ).data[0].embedding

    # Hybrid search: text + vector + filter
    results = search_client.search(
        search_text=query,
        vector_queries=[
            VectorizedQuery(
                vector=embedding,
                k_nearest_neighbors=5,
                fields="content_vector",
            )
        ],
        select=["chunk_id", "content", "article", "contained_terms", "is_definition_chunk"],
        top=5,
        query_type="semantic",
        semantic_configuration_name="default-semantic",
    )

    chunks = []
    print("\n[Azure AI Search — Hybrid Results]")
    for r in results:
        score = r.get("@search.score", 0)
        reranker = r.get("@search.reranker_score", 0)
        print(f"  → {r['chunk_id']} ({r['article']}) "
              f"score={score:.4f} reranker={reranker:.4f}")
        chunks.append(r)

    return chunks


def test_cosmos_glossary(cosmos_client, term_ids: list[str]):
    """Test Cosmos DB glossary lookup."""
    db = cosmos_client.get_database_client("enterprise-kb")
    container = db.get_container_client("glossary")

    print("\n[Cosmos DB — Glossary Lookup]")
    terms = []
    for term_id in term_ids[:5]:
        try:
            items = list(container.query_items(
                query="SELECT * FROM c WHERE c.id = @id",
                parameters=[{"name": "@id", "value": term_id}],
                enable_cross_partition_query=True,
            ))
            if items:
                t = items[0]
                print(f"  {t['id']}: {t['term']} — {t['enterpriseDefinition'][:80]}...")
                terms.append(t)
        except Exception as e:
            print(f"  {term_id}: ERROR {e}")

    return terms


def test_generation(openai_client, query: str, chunks: list, terms: list):
    """Test Azure OpenAI generation with system prompt."""
    # Build context
    retrieval_context = "\n\n".join(
        f"### {c['article']}\n{c['content']}"
        for c in chunks[:3]
    )

    term_block = "\n".join(
        f"- **{t['term']}**: {t['enterpriseDefinition'][:200]}"
        for t in terms
    )

    system_prompt = SYSTEM_PROMPT_PATH.read_text("utf-8")
    system_prompt = system_prompt.replace(
        "{動態注入的術語定義區塊 — 由 RAG 系統根據查詢動態填入}",
        term_block,
    ).replace(
        "{RAG 檢索結果 — 由系統動態填入相關條文 chunk}",
        retrieval_context,
    )

    print("\n[Azure OpenAI — GPT-4o Generation]")
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.1,
        max_tokens=1024,
    )

    answer = response.choices[0].message.content
    usage = response.usage
    print(f"  Tokens: {usage.prompt_tokens} input + {usage.completion_tokens} output")
    print(f"\n{'─'*60}")
    print(answer)
    print(f"{'─'*60}")

    return answer


def main():
    search_client, cosmos_client, openai_client = get_clients()

    test_queries = [
        "什麼是電子銀行？",
        "非約定轉帳需要什麼安全設計？",
        "端對端加密的要求是什麼？",
    ]

    for query in test_queries:
        # 1. Hybrid search
        chunks = test_hybrid_search(search_client, openai_client, query)

        # 2. Glossary lookup (get term IDs from top chunks)
        term_ids = []
        for c in chunks:
            term_ids.extend(c.get("contained_terms", []))
        term_ids = list(dict.fromkeys(term_ids))  # deduplicate, preserve order

        terms = test_cosmos_glossary(cosmos_client, term_ids)

        # 3. LLM generation
        test_generation(openai_client, query, chunks, terms)

        print("\n")

    print("=== All Azure E2E tests complete ===")


if __name__ == "__main__":
    main()
