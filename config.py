"""Configuration — reads .env or environment variables."""

import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent
KB_ROOT = PROJECT_ROOT.parent / "Research" / "enterprise-kb-methodology" / "financial-ebanking"
CHUNKS_MAIN = KB_ROOT / "chunks" / "main-body"
CHUNKS_APPENDICES = KB_ROOT / "chunks" / "appendices"
GLOSSARY_PATH = KB_ROOT / "glossary" / "ebanking-glossary.json"
KNOWLEDGE_GRAPH_PATH = KB_ROOT / "knowledge-graph" / "term-relations.json"
SYSTEM_PROMPT_PATH = KB_ROOT / "config" / "system-prompt.md"
RETRIEVAL_CONFIG_PATH = KB_ROOT / "config" / "retrieval-config.json"

# ChromaDB
CHROMA_DIR = PROJECT_ROOT / ".chroma"

# Models (Azure OpenAI compatible)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o")

# Search parameters (mirroring Azure AI Search config)
VECTOR_WEIGHT = 0.3
BM25_WEIGHT = 0.3
TERM_MATCH_WEIGHT = 0.4
TOP_K = 5

# Term injection
TERM_TOKEN_BUDGET = 6000
