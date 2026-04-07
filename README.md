# Government Regulation AI Knowledge Base — Azure PoC

> [中文版 README](README.zh-TW.md)

Full-cloud RAG system for government regulation knowledge base, ensuring **terminology fidelity** in AI responses.

## Architecture

All components deployed on Azure (East US region), zero on-premises dependency.

```
Browser / Teams Bot
       │
       ▼
Azure Functions (Consumption Plan, Python 3.11)
  ├── Azure AI Search (Hybrid: Vector + BM25 + Metadata + RRF + Semantic Ranker)
  ├── Azure Cosmos DB (Glossary: 99 terms, Knowledge Graph: 47 relations)
  └── Azure OpenAI (GPT-4o + text-embedding-3-large)
```

## Pipeline (4 Steps)

1. **Synonym Map Query Rewrite** — Intercepts prohibited alternative terms (e.g., "online banking" → "electronic banking") via Azure AI Search Synonym Maps
2. **Hybrid Search** — 3-route retrieval (vector + BM25 + metadata term match) fused with RRF (k=60), reranked by Semantic Ranker
3. **Term Injection + Knowledge Graph** — Detects terms from query and chunks, expands via 1-hop graph traversal, injects into System Prompt with 3-tier format (Full/Medium/Short) within 6,000 token budget
4. **LLM Generation** — Azure OpenAI GPT-4o with 8 term-fidelity rules in System Prompt

## Data

- **Pilot regulation**: 金融機構辦理電子銀行業務安全控管作業基準 (Financial Institution E-Banking Security Controls)
- 63 chunks indexed
- 99 terminology definitions
- 47 knowledge graph relations
- 5 synonym map rules

## Project Structure

```
├── functions/          # Azure Functions app (API endpoints)
│   └── function_app.py # /api/query, /api/health, /api/messages (Teams Bot)
├── teams-bot/          # Teams Bot integration (Adaptive Cards)
├── scripts/            # Automation scripts (budget stop runbook)
├── deploy/             # Deployment scripts
├── config.py           # Configuration and paths
├── search.py           # Hybrid search implementation
├── term_injection.py   # Term detection, graph expansion, injection
├── prompt_builder.py   # System prompt assembly
├── data_loader.py      # Data loading utilities
├── indexer.py          # Azure AI Search index creation
├── generate.py         # LLM answer generation
├── demo.html           # Interactive demo page with pipeline visualization
└── demo.js             # Demo page logic
```

## Security & Cost Control

- **Authentication**: Azure Function Key
- **Rate Limiting**: 1 query per 10 seconds (in-memory)
- **Budget**: NT$100/month Azure Budget with auto-stop (Automation Runbook stops Function App at 100%)
- **Query Cap**: 100 queries/month soft cap

## Live Demo

- **Resume site**: [resume.darrenlu.com](https://resume.darrenlu.com)
- **Demo page**: Available via resume site with API key parameter

## Methodology

Based on **Enterprise Knowledge Base Terminology Fidelity Methodology v2.1**.

Academic references: HalluGraph (arxiv 2512.01659), CRAG (arxiv 2401.15884), SAT-Graph RAG (arxiv 2505.00039).

Validated with financial e-banking regulation pilot — 6/6 term fidelity tests passed.
