# 政府法規 AI 知識庫 — Azure 全雲端 PoC

全雲端 RAG 系統，針對政府法規查詢場景設計，確保 AI 回答中的**術語保真度**接近 100%。

## 架構

所有元件部署於 Azure（East US），零地端依賴。

```
瀏覽器 / Teams Bot
       │
       ▼
Azure Functions (Consumption Plan, Python 3.11)
  ├── Azure AI Search（混合檢索：Vector + BM25 + Metadata + RRF + Semantic Ranker）
  ├── Azure Cosmos DB（術語詞典：99 個定義、知識圖譜：47 條關係）
  └── Azure OpenAI（GPT-4o + text-embedding-3-large）
```

## Pipeline（4 步驟）

1. **Synonym Map 查詢改寫** — 透過 Azure AI Search Synonym Map 攔截禁用替代詞（如「網路銀行」→「電子銀行」）
2. **三路混合檢索** — Vector（語意）+ BM25（關鍵字）+ Metadata（術語 ID 精確匹配），RRF 融合（k=60）後以 Semantic Ranker 重排
3. **術語注入 + 知識圖譜擴展** — 偵測查詢與 chunk 中的術語，1-hop 圖譜擴展，以三級格式（Full/Medium/Short）注入 System Prompt，6,000 token 預算
4. **LLM 生成** — Azure OpenAI GPT-4o，System Prompt 含 8 條術語保真規則

## 試點資料

- **試點法規**：金融機構辦理電子銀行業務安全控管作業基準
- 63 個法規 Chunks
- 99 個術語定義
- 47 條知識圖譜關係
- 5 條 Synonym Map 規則

## 專案結構

```
├── functions/          # Azure Functions（API 端點）
│   └── function_app.py # /api/query、/api/health、/api/messages（Teams Bot）
├── teams-bot/          # Teams Bot 整合（Adaptive Cards）
├── scripts/            # 自動化腳本（預算超限停機 Runbook）
├── deploy/             # 部署腳本
├── config.py           # 設定檔與路徑
├── search.py           # 混合檢索實作
├── term_injection.py   # 術語偵測、圖譜擴展、注入
├── prompt_builder.py   # System Prompt 組裝
├── data_loader.py      # 資料載入工具
├── indexer.py          # Azure AI Search 索引建立
├── generate.py         # LLM 回答生成
├── demo.html           # 互動式 Demo 頁面（含 Pipeline 視覺化）
└── demo.js             # Demo 頁面邏輯
```

## 安全與費用控制

- **認證**：Azure Function Key
- **限速**：每 10 秒 1 次查詢（記憶體計數）
- **預算**：每月 NT$100 Azure Budget，超過自動停機（Automation Runbook 停用 Function App）
- **查詢上限**：每月 100 次軟限制

## Live Demo

- **履歷網站**：[resume.darrenlu.com](https://resume.darrenlu.com)
- **Demo 頁面**：透過履歷網站連結，含 API Key 參數

## 方法論

基於自研的**「企業知識庫術語保真方法論 v2.1」**。

學術參考：HalluGraph (arxiv 2512.01659)、CRAG (arxiv 2401.15884)、SAT-Graph RAG (arxiv 2505.00039)。

已通過金融法規試點驗證 — 6 題術語保真測試全數通過。
