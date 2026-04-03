"""Enterprise Knowledge Base PoC — Local simulation of Azure AI stack.

Architecture mapping:
  Azure AI Document Intelligence  →  (pre-processed: existing 63 chunk JSONs)
  Azure AI Search (hybrid)        →  ChromaDB + custom RRF fusion
  Azure AI Search Synonym Maps    →  data_loader.build_synonym_map()
  Azure OpenAI Embeddings         →  OpenAI text-embedding-3-large
  Azure OpenAI GPT-4o             →  OpenAI GPT-4o
  Cosmos DB (glossary store)      →  Local JSON → in-memory dict
  GraphRAG (knowledge graph)      →  Local JSON → in-memory graph traversal
  Prompt Flow (orchestration)     →  This pipeline script

Usage:
  python main.py index       # Index chunks into ChromaDB (run once)
  python main.py query "..." # Single query
  python main.py demo        # Interactive demo

Mock mode (no API key needed):
  python main.py index --mock
  python main.py query "..." --mock
  python main.py demo --mock
"""

import os
import sys

from generate import get_openai_client, generate_answer
from data_loader import load_knowledge_base
from indexer import index_knowledge_base
from search import hybrid_search
from term_injection import collect_relevant_terms, build_term_injection_block
from prompt_builder import build_messages, build_retrieval_context


def _is_mock() -> bool:
    return "--mock" in sys.argv or not os.getenv("OPENAI_API_KEY")


def run_index():
    """Index all chunks into ChromaDB with embeddings."""
    mock = _is_mock()
    mode = "MOCK (hash-based embeddings)" if mock else "LIVE (OpenAI API)"
    print(f"=== Indexing Knowledge Base [{mode}] ===")

    kb = load_knowledge_base()
    client = None if mock else get_openai_client()
    index_knowledge_base(kb, client, mock=mock)
    print("\nDone. Run 'python main.py demo' to start querying.")


def run_query(query: str, verbose: bool = True):
    """Execute a single query through the full pipeline."""
    mock = _is_mock()
    kb = load_knowledge_base()
    client = None if mock else get_openai_client()

    # Step 1: Hybrid search (simulates Azure AI Search)
    if verbose:
        mode = "MOCK" if mock else "LIVE"
        print(f"\n{'='*60}")
        print(f"Query: {query}  [{mode}]")
        print(f"{'='*60}")
        print("\n[1/4] Hybrid Search (Azure AI Search simulation)...")

    results = hybrid_search(query, kb, client, mock=mock)

    if verbose:
        for r in results:
            print(f"  → {r.chunk_id} ({r.article}) "
                  f"score={r.score:.4f} via={','.join(r.match_sources)}")

    # Step 2: Term detection + graph expansion (simulates Cosmos DB + GraphRAG)
    if verbose:
        print("\n[2/4] Term Detection + Graph Expansion (Cosmos DB + GraphRAG simulation)...")

    term_priority = collect_relevant_terms(query, results, kb)
    term_block = build_term_injection_block(term_priority, kb)

    # Step 3: Prompt assembly (simulates Prompt Flow)
    if verbose:
        print("\n[3/4] Prompt Assembly (Prompt Flow simulation)...")

    retrieval_context = build_retrieval_context(results)
    messages = build_messages(query, term_block, retrieval_context)

    if verbose:
        from term_injection import _count_tokens
        total_tokens = sum(_count_tokens(m["content"]) for m in messages)
        print(f"  Total prompt tokens: ~{total_tokens}")

    # Step 4: LLM generation (simulates Azure OpenAI)
    if verbose:
        print("\n[4/4] LLM Generation (Azure OpenAI simulation)...")

    answer = generate_answer(messages, client, mock=mock)

    print(f"\n{'─'*60}")
    print(answer)
    print(f"{'─'*60}")

    return answer


def run_demo():
    """Interactive demo loop."""
    mock = _is_mock()
    mode = "MOCK" if mock else "LIVE"

    print("=" * 60)
    print(f"金融法規知識庫 PoC — Azure AI Stack 本地模擬 [{mode}]")
    print("=" * 60)
    print()
    print("Architecture:")
    print("  ChromaDB          ← Azure AI Search (hybrid search + RRF)")
    print("  OpenAI Embeddings ← Azure OpenAI text-embedding-3-large")
    print("  OpenAI GPT-4o     ← Azure OpenAI GPT-4o")
    print("  Local JSON        ← Cosmos DB (glossary) + GraphRAG (knowledge graph)")
    print("  Pipeline script   ← Azure AI Foundry Prompt Flow")
    print()
    print("範例查詢：")
    print("  1. 什麼是電子銀行？")
    print("  2. 網路銀行和行動銀行有什麼差別？")
    print("  3. 非約定轉帳需要什麼安全設計？")
    print("  4. 端對端加密的要求是什麼？")
    print("  5. 第三類數位存款帳戶的規定為何？")
    print()
    if mock:
        print("⚠ MOCK 模式：embeddings 使用 hash，LLM 回答為模擬輸出")
        print("  設定 OPENAI_API_KEY 環境變數即可切換至正式模式")
        print()
    print("輸入 'quit' 或 'exit' 離開")
    print()

    while True:
        try:
            query = input("查詢 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再見！")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("再見！")
            break

        run_query(query)
        print()


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--mock":
        print("Usage:")
        print("  python main.py index [--mock]    # Index chunks (run once)")
        print("  python main.py query \"...\" [--mock] # Single query")
        print("  python main.py demo [--mock]     # Interactive demo")
        sys.exit(1)

    command = sys.argv[1]

    if command == "index":
        run_index()
    elif command == "query":
        args = [a for a in sys.argv[2:] if a != "--mock"]
        if not args:
            print("Usage: python main.py query \"your question here\" [--mock]")
            sys.exit(1)
        run_query(" ".join(args))
    elif command == "demo":
        run_demo()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
