"""Dynamic term injection into System Prompt.

Simulates:
- Azure AI Search term detection on query + retrieved chunks
- Knowledge graph traversal for related term expansion
- Token budget management for prompt assembly
"""

import tiktoken

from config import TERM_TOKEN_BUDGET
from data_loader import KnowledgeBase, Term
from search import SearchResult


def _count_tokens(text: str, model: str = "gpt-4o") -> int:
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


def _format_term_full(term: Term) -> str:
    """Full term entry (~200-500 tokens). Used for direct-hit terms."""
    parts = [
        f"### {term.term}",
        f"**企業定義**：{term.enterprise_definition}",
    ]
    if term.common_definition:
        parts.append(f"**通俗定義**：{term.common_definition}")
    if term.definition_difference:
        parts.append(f"**差異說明**：{term.definition_difference}")
    if term.prohibited_alternatives:
        alts = "、".join(term.prohibited_alternatives)
        parts.append(f"**禁用替代詞**：{alts}")
    return "\n".join(parts)


def _format_term_medium(term: Term) -> str:
    """Medium term entry (~80-120 tokens). Used for indirect terms."""
    definition = term.enterprise_definition[:150]
    if len(term.enterprise_definition) > 150:
        definition += "..."
    return f"- **{term.term}**：{definition}"


def _format_term_short(term: Term) -> str:
    """Short term entry (~20-40 tokens). Used for background terms."""
    definition = term.enterprise_definition[:60]
    if len(term.enterprise_definition) > 60:
        definition += "..."
    return f"- {term.term}：{definition}"


def expand_terms_via_graph(
    term_ids: set[str],
    kb: KnowledgeBase,
    max_hops: int = 1,
) -> set[str]:
    """Expand term IDs using knowledge graph (1-hop neighbors).

    Simulates: query expansion via GraphRAG / Cosmos DB graph traversal.
    """
    expanded = set(term_ids)
    for relation in kb.relations:
        if relation.from_id in term_ids or relation.to_id in term_ids:
            expanded.add(relation.from_id)
            expanded.add(relation.to_id)
    return expanded


def collect_relevant_terms(
    query: str,
    search_results: list[SearchResult],
    kb: KnowledgeBase,
) -> dict[str, str]:
    """Collect and classify relevant terms into priority tiers.

    Returns: {term_id: priority_level} where level is 'direct', 'indirect', 'background'
    """
    term_priority: dict[str, str] = {}

    # Direct hits: terms detected in the query
    for term_name, term_id in kb.term_name_index.items():
        if term_name in query and term_id in kb.terms:
            term_priority[term_id] = "direct"

    # Indirect hits: terms found in retrieved chunks
    for result in search_results:
        for term_id in result.contained_terms:
            if term_id and term_id not in term_priority and term_id in kb.terms:
                term_priority[term_id] = "indirect"

    # Background: 1-hop graph expansion
    direct_and_indirect = set(term_priority.keys())
    expanded = expand_terms_via_graph(direct_and_indirect, kb)
    for term_id in expanded:
        if term_id not in term_priority and term_id in kb.terms:
            term_priority[term_id] = "background"

    return term_priority


def build_term_injection_block(
    term_priority: dict[str, str],
    kb: KnowledgeBase,
    token_budget: int = TERM_TOKEN_BUDGET,
) -> str:
    """Build the dynamic term injection block within token budget.

    Implements the token budget allocation algorithm from the methodology:
    1. Direct-hit terms get full format
    2. Indirect terms get medium format
    3. Background terms get short format
    Stops when budget is exhausted.
    """
    sections: dict[str, list[str]] = {"direct": [], "indirect": [], "background": []}

    for term_id, level in term_priority.items():
        term = kb.terms.get(term_id)
        if not term:
            continue
        if level == "direct":
            sections["direct"].append(_format_term_full(term))
        elif level == "indirect":
            sections["indirect"].append(_format_term_medium(term))
        else:
            sections["background"].append(_format_term_short(term))

    # Assemble within budget, tracking header tokens
    parts = []
    used_tokens = 0

    for section_key, header in [
        ("direct", "## 查詢直接相關術語\n"),
        ("indirect", "\n## 檢索結果相關術語\n"),
        ("background", "\n## 背景相關術語\n"),
    ]:
        entries = sections[section_key]
        if not entries:
            continue
        header_tokens = _count_tokens(header)
        if used_tokens + header_tokens > token_budget:
            break
        added_any = False
        for entry in entries:
            entry_tokens = _count_tokens(entry)
            if used_tokens + header_tokens + entry_tokens > token_budget:
                break
            if not added_any:
                parts.append(header)
                used_tokens += header_tokens
                added_any = True
            parts.append(entry + ("\n" if section_key == "direct" else ""))
            used_tokens += entry_tokens

    block = "\n".join(parts)
    stats = {level: len([v for v in term_priority.values() if v == level])
             for level in ("direct", "indirect", "background")}
    print(f"  Term injection: {stats}, {used_tokens} tokens used / {token_budget} budget")
    return block
