# CLAUDE.md — enterprise-kb-azure-poc（中文版）

## 專案概述

政府法規 AI 知識庫 PoC，全雲端 RAG 架構，保證術語保真度。

## 部署資訊

- **平台**：Azure Functions (Consumption Plan)
- **區域**：East US
- **Resource Group**：ekb-poc-rg
- **API Endpoint**：ekb-poc-api.azurewebsites.net
- **認證方式**：Function Key
- **預算控制**：每月 NT$100，超過自動停機（Automation Runbook）

## 關鍵檔案

- `functions/function_app.py` — 主要 API：/api/query（RAG Pipeline）、/api/health、/api/messages（Teams Bot）
- `search.py` — Azure AI Search 混合檢索（Vector + BM25 + Metadata + RRF + Semantic Ranker）
- `term_injection.py` — Cosmos DB 術語查詢、知識圖譜 1-hop 擴展、三級格式注入
- `prompt_builder.py` — System Prompt 組裝（含 8 條術語保真規則）
- `config.py` — 設定檔、路徑、檢索參數

## Azure 服務對照

| 服務 | 資源名稱 | 用途 |
|------|--------|------|
| Azure Functions | ekb-poc-api | Serverless API |
| Azure AI Search | (ekb-poc-rg 內) | 混合檢索 + Semantic Ranker |
| Azure Cosmos DB | (ekb-poc-rg 內) | 術語詞典 (99 個) + 知識圖譜 (47 條關係) |
| Azure OpenAI | ekb-poc-openai | GPT-4o + text-embedding-3-large |
| Automation Account | ekb-poc-automation | 預算超限自動停機 Runbook |

## 資料來源

試點法規：金融機構辦理電子銀行業務安全控管作業基準
- Chunks 存於 Azure AI Search index
- 詞典與圖譜存於 Cosmos DB containers
- 原始資料在 ../Research/enterprise-kb-methodology/financial-ebanking/

## 開發規範

- Commit message 一律使用英文（中文會導致 Cloudflare Pages 部署失敗）
- Function Key 不存於程式碼中 — 透過 `az functionapp keys list` 取得
- 查詢計數器為記憶體變數（cold start 重置）— 真正的費用控制靠 Azure Budget + Automation Runbook
