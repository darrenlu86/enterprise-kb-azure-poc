"""Azure Functions — Enterprise Knowledge Base API.

Endpoints:
  POST /api/query   — Query the knowledge base
  GET  /api/health  — Health check
  GET  /api/stats   — KB statistics
"""

import json
import logging
import os
from datetime import datetime, timezone

import azure.functions as func


# ============================================================
# Monthly query budget (hard stop)
# ============================================================
MONTHLY_QUERY_LIMIT = 100  # ~$3 USD at ~$0.03/query
RATE_LIMIT_SECONDS = 10    # minimum seconds between queries
_query_count = {"month": "", "count": 0}
_last_query_time = {"ts": 0.0}


def _check_budget() -> tuple[bool, int]:
    """Check if monthly query budget is exhausted. Returns (allowed, remaining)."""
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    if _query_count["month"] != current_month:
        _query_count["month"] = current_month
        _query_count["count"] = 0
    remaining = MONTHLY_QUERY_LIMIT - _query_count["count"]
    return remaining > 0, remaining


def _check_rate_limit() -> tuple[bool, float]:
    """Check if rate limit is exceeded. Returns (allowed, wait_seconds)."""
    import time
    now = time.time()
    elapsed = now - _last_query_time["ts"]
    if elapsed < RATE_LIMIT_SECONDS:
        return False, RATE_LIMIT_SECONDS - elapsed
    return True, 0.0


def _increment_budget():
    """Increment query counter and update rate limit timestamp."""
    import time
    _query_count["count"] += 1
    _last_query_time["ts"] = time.time()
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from azure.cosmos import CosmosClient
from openai import AzureOpenAI

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# ============================================================
# Clients (initialized once, reused across invocations)
# ============================================================

_search_client = None
_cosmos_glossary = None
_cosmos_relations = None
_openai_client = None


def _get_search_client() -> SearchClient:
    global _search_client
    if _search_client is None:
        _search_client = SearchClient(
            endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
            index_name="financial-ebanking-chunks",
            credential=AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
        )
    return _search_client


def _get_cosmos_containers():
    global _cosmos_glossary, _cosmos_relations
    if _cosmos_glossary is None:
        client = CosmosClient(
            os.environ["AZURE_COSMOS_ENDPOINT"],
            os.environ["AZURE_COSMOS_KEY"],
        )
        db = client.get_database_client("enterprise-kb")
        _cosmos_glossary = db.get_container_client("glossary")
        _cosmos_relations = db.get_container_client("term-relations")
    return _cosmos_glossary, _cosmos_relations


def _get_openai_client() -> AzureOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version="2024-10-21",
        )
    return _openai_client


# ============================================================
# Synonym Map (loaded from Cosmos DB glossary)
# ============================================================

_synonym_map: dict[str, str] | None = None


def _get_synonym_map() -> dict[str, str]:
    """Build prohibited alternative -> correct term mapping."""
    global _synonym_map
    if _synonym_map is None:
        glossary, _ = _get_cosmos_containers()
        _synonym_map = {}
        for item in glossary.query_items(
            "SELECT c.term, c.prohibitedAlternatives FROM c WHERE ARRAY_LENGTH(c.prohibitedAlternatives) > 0",
            enable_cross_partition_query=True,
        ):
            for alt in item.get("prohibitedAlternatives", []):
                _synonym_map[alt] = item["term"]
    return _synonym_map


# ============================================================
# Pipeline Functions
# ============================================================

def rewrite_query(query: str) -> tuple[str, list[str]]:
    """Rewrite query using synonym map. Returns (rewritten_query, replacements)."""
    synonym_map = _get_synonym_map()
    rewritten = query
    replacements = []
    for alt, correct in synonym_map.items():
        if alt in rewritten:
            rewritten = rewritten.replace(alt, correct)
            replacements.append(f"'{alt}' → '{correct}'")
    return rewritten, replacements


def hybrid_search(query: str, top_k: int = 5) -> list[dict]:
    """Execute hybrid search on Azure AI Search."""
    client = _get_search_client()
    openai = _get_openai_client()

    # Generate query embedding
    embedding = openai.embeddings.create(
        input=[query], model="text-embedding-3-large"
    ).data[0].embedding

    results = client.search(
        search_text=query,
        vector_queries=[
            VectorizedQuery(
                vector=embedding,
                k_nearest_neighbors=top_k,
                fields="content_vector",
            )
        ],
        select=["chunk_id", "content", "article", "contained_terms", "is_definition_chunk", "topic_tags"],
        top=top_k,
        query_type="semantic",
        semantic_configuration_name="default-semantic",
    )

    return [
        {
            "chunk_id": r["chunk_id"],
            "content": r["content"],
            "article": r["article"],
            "contained_terms": r.get("contained_terms", []),
            "is_definition_chunk": r.get("is_definition_chunk", False),
            "score": r.get("@search.score", 0),
            "reranker_score": r.get("@search.reranker_score", 0),
        }
        for r in results
    ]


def lookup_terms(term_ids: list[str], max_terms: int = 10) -> list[dict]:
    """Lookup terms from Cosmos DB glossary."""
    glossary, _ = _get_cosmos_containers()
    unique_ids = list(dict.fromkeys(term_ids))[:max_terms]
    terms = []

    for term_id in unique_ids:
        items = list(glossary.query_items(
            "SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": term_id}],
            enable_cross_partition_query=True,
        ))
        if items:
            terms.append(items[0])

    return terms


def expand_terms_via_graph(term_ids: list[str]) -> list[str]:
    """Expand terms using knowledge graph in Cosmos DB."""
    _, relations = _get_cosmos_containers()
    expanded = set(term_ids)

    for tid in term_ids:
        items = list(relations.query_items(
            "SELECT c.from_id, c.to_id FROM c WHERE c.from_id = @id OR c.to_id = @id",
            parameters=[{"name": "@id", "value": tid}],
            enable_cross_partition_query=True,
        ))
        for item in items:
            expanded.add(item["from_id"])
            expanded.add(item["to_id"])

    return list(expanded)


def build_term_block(terms: list[dict], direct_ids: set[str]) -> str:
    """Build dynamic term injection block with 3-tier formatting."""
    parts = []

    direct = [t for t in terms if t["id"] in direct_ids]
    indirect = [t for t in terms if t["id"] not in direct_ids]

    if direct:
        parts.append("## 查詢直接相關術語\n")
        for t in direct:
            parts.append(f"### {t['term']}")
            parts.append(f"**企業定義**：{t['enterpriseDefinition']}")
            if t.get("commonDefinition"):
                parts.append(f"**通俗定義**：{t['commonDefinition']}")
            if t.get("definitionDifference"):
                parts.append(f"**差異說明**：{t['definitionDifference']}")
            alts = t.get("prohibitedAlternatives", [])
            if alts:
                parts.append(f"**禁用替代詞**：{'、'.join(alts)}")
            parts.append("")

    if indirect:
        parts.append("## 檢索結果相關術語\n")
        for t in indirect[:15]:
            defn = t["enterpriseDefinition"][:150]
            if len(t["enterpriseDefinition"]) > 150:
                defn += "..."
            parts.append(f"- **{t['term']}**：{defn}")

    return "\n".join(parts)


SYSTEM_PROMPT_TEMPLATE = """# 金融法規合規助理 — System Prompt

## 系統角色

你是金融電子銀行法規合規助理，專門協助金融機構從業人員查詢「金融機構辦理電子銀行業務安全控管作業基準（1150107 版）」的法規要求。你的回答必須嚴格基於法規原文，不得臆測或引用法規以外的內容。

## 術語使用規則（最高優先級）

1. 使用企業定義，不得使用通俗定義
2. 不得使用禁用替代詞（如「網路銀行」應為「電子銀行」）
3. 術語首次出現使用「全稱（英文縮寫）」格式
4. 每個回答必須附上法規依據：「依據第 X 條第 Y 款」
5. 不確定時保守回答，不從記憶引入 chunk 外概念

## 當前相關術語

{term_block}

## 檢索到的法規內容

{retrieval_context}

## 回答格式

【回答】
{{基於法規原文的回答}}

【法規依據】
- 第 X 條第 Y 款：{{條文摘要}}

【相關術語】
- {{術語}}：{{簡要定義}}

## 免責聲明

在每次回答末尾附上：
> 本回答僅供參考，係基於「金融機構辦理電子銀行業務安全控管作業基準」（1150107 版）之內容。實際合規判斷應諮詢貴機構法遵/合規部門，以確保符合最新法規要求。
"""


def generate_answer(query: str, term_block: str, chunks: list[dict]) -> tuple[str, dict]:
    """Generate answer using Azure OpenAI GPT-4o."""
    openai = _get_openai_client()

    retrieval_context = "\n\n".join(
        f"### {c['article']}（{c['chunk_id']}）\n{c['content']}"
        for c in chunks
    )

    system_prompt = SYSTEM_PROMPT_TEMPLATE.replace(
        "{term_block}", term_block
    ).replace(
        "{retrieval_context}", retrieval_context
    )

    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.1,
        max_tokens=1500,
    )

    usage = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }

    return response.choices[0].message.content or "", usage


# ============================================================
# HTTP Endpoints
# ============================================================

@app.route(route="query", methods=["POST"])
def query_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/query — Full RAG pipeline query."""
    try:
        # Rate limit — 1 query per 10 seconds
        rate_ok, wait_secs = _check_rate_limit()
        if not rate_ok:
            return func.HttpResponse(
                json.dumps({
                    "error": f"Rate limited. Please wait {wait_secs:.0f} seconds before next query.",
                    "retry_after": round(wait_secs)
                }, ensure_ascii=False),
                status_code=429, mimetype="application/json",
                headers={"Retry-After": str(round(wait_secs))}
            )

        # Budget check — hard stop at 100 queries/month (~$3)
        allowed, remaining = _check_budget()
        if not allowed:
            return func.HttpResponse(
                json.dumps({
                    "error": "Monthly query budget exhausted (100 queries / ~$3 USD). Resets next month.",
                    "budget": {"limit": MONTHLY_QUERY_LIMIT, "remaining": 0}
                }, ensure_ascii=False),
                status_code=429, mimetype="application/json",
            )

        body = req.get_json()
        query = body.get("query", "").strip()
        if not query:
            return func.HttpResponse(
                json.dumps({"error": "Missing 'query' field"}, ensure_ascii=False),
                status_code=400, mimetype="application/json",
            )

        # Step 1: Query rewrite (Synonym Map)
        rewritten, replacements = rewrite_query(query)

        # Step 2: Hybrid search (Azure AI Search)
        chunks = hybrid_search(rewritten)

        # Step 3: Term detection + graph expansion (Cosmos DB)
        # Detect terms from query
        glossary, _ = _get_cosmos_containers()
        direct_term_ids = set()
        all_terms_items = list(glossary.query_items(
            "SELECT c.id, c.term FROM c",
            enable_cross_partition_query=True,
        ))
        for item in all_terms_items:
            if item["term"] in rewritten:
                direct_term_ids.add(item["id"])

        # Collect term IDs from chunks
        chunk_term_ids = []
        for c in chunks:
            chunk_term_ids.extend(c.get("contained_terms", []))

        # Expand via knowledge graph
        all_term_ids = list(direct_term_ids) + chunk_term_ids
        expanded_ids = expand_terms_via_graph(all_term_ids)

        # Lookup full term definitions
        terms = lookup_terms(expanded_ids)

        # Build term injection block
        term_block = build_term_block(terms, direct_term_ids)

        # Step 4: LLM generation (Azure OpenAI)
        answer, usage = generate_answer(query, term_block, chunks)

        result = {
            "query": query,
            "rewritten_query": rewritten,
            "replacements": replacements,
            "search_results": [
                {
                    "chunk_id": c["chunk_id"],
                    "article": c["article"],
                    "score": c["score"],
                    "reranker_score": c["reranker_score"],
                }
                for c in chunks
            ],
            "terms_injected": {
                "direct": len(direct_term_ids),
                "total": len(terms),
            },
            "answer": answer,
            "usage": usage,
            "budget": {"limit": MONTHLY_QUERY_LIMIT, "remaining": remaining - 1},
        }

        _increment_budget()

        return func.HttpResponse(
            json.dumps(result, ensure_ascii=False, indent=2),
            mimetype="application/json",
        )

    except Exception as e:
        logging.exception("Query failed")
        return func.HttpResponse(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            status_code=500, mimetype="application/json",
        )


@app.route(route="health", methods=["GET"])
def health_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/health — Health check."""
    checks = {}
    try:
        _get_search_client()
        checks["azure_ai_search"] = "ok"
    except Exception as e:
        checks["azure_ai_search"] = f"error: {e}"

    try:
        _get_cosmos_containers()
        checks["cosmos_db"] = "ok"
    except Exception as e:
        checks["cosmos_db"] = f"error: {e}"

    try:
        _get_openai_client()
        checks["azure_openai"] = "ok"
    except Exception as e:
        checks["azure_openai"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return func.HttpResponse(
        json.dumps({"status": "healthy" if all_ok else "degraded", "checks": checks}, ensure_ascii=False),
        status_code=200 if all_ok else 503,
        mimetype="application/json",
    )


@app.route(route="stats", methods=["GET"])
def stats_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/stats — Knowledge base statistics."""
    glossary, relations = _get_cosmos_containers()

    term_count = list(glossary.query_items(
        "SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True
    ))[0]
    relation_count = list(relations.query_items(
        "SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True
    ))[0]

    return func.HttpResponse(
        json.dumps({
            "terms": term_count,
            "relations": relation_count,
            "chunks": 63,
            "synonym_rules": len(_get_synonym_map()),
            "source_document": "金融機構辦理電子銀行業務安全控管作業基準 (1150107 版)",
        }, ensure_ascii=False, indent=2),
        mimetype="application/json",
    )
