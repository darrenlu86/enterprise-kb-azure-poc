# CLAUDE.md — enterprise-kb-azure-poc

## Project Overview

Government regulation AI knowledge base PoC on Azure. Full-cloud RAG with terminology fidelity guarantee.

## Deployment

- **Platform**: Azure Functions (Consumption Plan)
- **Region**: East US
- **Resource Group**: ekb-poc-rg
- **API Endpoint**: ekb-poc-api.azurewebsites.net
- **Authentication**: Function Key
- **Budget**: NT$100/month with auto-stop (Automation Runbook)

## Key Files

- `functions/function_app.py` — Main API: /api/query (RAG pipeline), /api/health, /api/messages (Teams Bot)
- `search.py` — Azure AI Search hybrid search (vector + BM25 + metadata + RRF + Semantic Ranker)
- `term_injection.py` — Cosmos DB term lookup, knowledge graph 1-hop expansion, 3-tier injection
- `prompt_builder.py` — System prompt assembly with 8 term-fidelity rules
- `config.py` — Configuration, paths, search parameters

## Azure Services

| Service | Resource Name | Purpose |
|---------|--------------|---------|
| Azure Functions | ekb-poc-api | Serverless API |
| Azure AI Search | (in ekb-poc-rg) | Hybrid search + Semantic Ranker |
| Azure Cosmos DB | (in ekb-poc-rg) | Glossary (99 terms) + Knowledge Graph (47 relations) |
| Azure OpenAI | ekb-poc-openai | GPT-4o + text-embedding-3-large |
| Automation Account | ekb-poc-automation | Budget auto-stop runbook |

## Data Source

Pilot: 金融機構辦理電子銀行業務安全控管作業基準
- Chunks stored in Azure AI Search index
- Glossary and graph stored in Cosmos DB containers
- Source data in ../Research/enterprise-kb-methodology/financial-ebanking/

## Conventions

- Commit messages in English
- Function Key is NOT stored in code — retrieve via `az functionapp keys list`
- Budget counter is in-memory (resets on cold start) — real cost control is via Azure Budget + Automation Runbook
