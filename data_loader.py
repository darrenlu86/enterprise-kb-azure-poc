"""Load chunks, glossary, and knowledge graph from the existing KB methodology project."""

import json
from pathlib import Path
from dataclasses import dataclass

from config import CHUNKS_MAIN, CHUNKS_APPENDICES, GLOSSARY_PATH, KNOWLEDGE_GRAPH_PATH


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    content: str
    article: str
    section: str | None
    version: str
    contained_terms: tuple[str, ...]
    is_definition_chunk: bool
    topic_tags: tuple[str, ...]
    priority: str


@dataclass(frozen=True)
class Term:
    id: str
    term: str
    enterprise_definition: str
    common_definition: str
    definition_difference: str
    category: str
    prohibited_alternatives: tuple[str, ...]
    accepted_synonyms: tuple[str, ...]
    related_terms: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class Relation:
    from_id: str
    to_id: str
    relation_type: str
    note: str


@dataclass(frozen=True)
class KnowledgeBase:
    chunks: tuple[Chunk, ...]
    terms: dict[str, Term]  # id -> Term
    relations: tuple[Relation, ...]
    term_name_index: dict[str, str]  # term name -> term id
    synonym_map: dict[str, str]  # prohibited alt -> correct term name


def load_chunks() -> list[Chunk]:
    chunks = []
    for chunk_dir in (CHUNKS_MAIN, CHUNKS_APPENDICES):
        if not chunk_dir.exists():
            continue
        for f in sorted(chunk_dir.glob("*.json")):
            raw = json.loads(f.read_text(encoding="utf-8"))
            meta = raw.get("metadata", {})
            source = meta.get("source", {})
            terms_meta = meta.get("terms", {})
            classification = meta.get("classification", {})
            chunks.append(Chunk(
                chunk_id=raw["chunk_id"],
                content=raw["content"],
                article=source.get("article", ""),
                section=source.get("section"),
                version=source.get("version", ""),
                contained_terms=tuple(terms_meta.get("contained_terms", [])),
                is_definition_chunk=terms_meta.get("is_definition_chunk", False),
                topic_tags=tuple(classification.get("topic_tags", [])),
                priority=classification.get("priority", "P2"),
            ))
    return chunks


def load_glossary() -> dict[str, Term]:
    raw = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
    terms = {}
    for t in raw.get("terms", []):
        prohibited = tuple(
            p["term"] for p in t.get("prohibitedAlternatives", [])
        )
        terms[t["id"]] = Term(
            id=t["id"],
            term=t.get("term", ""),
            enterprise_definition=t.get("enterpriseDefinition", ""),
            common_definition=t.get("commonDefinition", ""),
            definition_difference=t.get("definitionDifference", ""),
            category=t.get("category", ""),
            prohibited_alternatives=prohibited,
            accepted_synonyms=tuple(t.get("acceptedSynonyms", [])),
            related_terms=tuple(t.get("relatedTerms", [])),
            status=t.get("status", "draft"),
        )
    return terms


def load_relations() -> list[Relation]:
    raw = json.loads(KNOWLEDGE_GRAPH_PATH.read_text(encoding="utf-8"))
    return [
        Relation(
            from_id=r["from"],
            to_id=r["to"],
            relation_type=r["type"],
            note=r.get("note", ""),
        )
        for r in raw.get("relations", [])
    ]


def build_synonym_map(terms: dict[str, Term]) -> dict[str, str]:
    """Build prohibited alternative -> correct term name mapping.

    Simulates Azure AI Search Synonym Maps.
    """
    synonym_map: dict[str, str] = {}
    for term in terms.values():
        for alt in term.prohibited_alternatives:
            synonym_map[alt] = term.term
    return synonym_map


def build_term_name_index(terms: dict[str, Term]) -> dict[str, str]:
    """Build term name -> term id index for fast lookup."""
    index: dict[str, str] = {}
    for term in terms.values():
        index[term.term] = term.id
        for syn in term.accepted_synonyms:
            index[syn] = term.id
    return index


def load_knowledge_base() -> KnowledgeBase:
    chunks = load_chunks()
    terms = load_glossary()
    relations = load_relations()
    term_name_index = build_term_name_index(terms)
    synonym_map = build_synonym_map(terms)

    print(f"Loaded: {len(chunks)} chunks, {len(terms)} terms, "
          f"{len(relations)} relations, {len(synonym_map)} synonym mappings")

    return KnowledgeBase(
        chunks=tuple(chunks),
        terms=terms,
        relations=tuple(relations),
        term_name_index=term_name_index,
        synonym_map=synonym_map,
    )
