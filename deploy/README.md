# Azure 部署指南

## 前置條件

```bash
# 1. 安裝 Azure CLI
brew install azure-cli

# 2. 登入
az login

# 3. 安裝 Azure Python SDKs
pip install azure-search-documents azure-cosmos python-dotenv
```

## 部署流程

```bash
# Step 1: 部署 Azure 資源 (AI Search + OpenAI + Cosmos DB)
./deploy/deploy.sh

# Step 2: 上傳資料 (chunks + glossary + relations + synonym map)
python deploy/migrate.py

# Step 3: 執行 Azure E2E 測試
python deploy/test_azure.py

# Step 4: 測試完成後，立即砍掉所有資源
./deploy/deploy.sh teardown
```

## 費用估算

| 操作 | 預估費用 |
|------|----------|
| AI Search (Free tier) | $0 |
| OpenAI embedding (63 chunks, ~50K tokens) | $0.007 |
| OpenAI GPT-4o (3 queries, ~30K tokens) | $0.10 |
| Cosmos DB (99 docs + 47 docs, serverless) | $0.01 |
| **整個 demo 測完砍掉** | **< $0.20** |

> 注意：以上費用前提是測完就 teardown。如果放著不管，Cosmos DB serverless 和 OpenAI 不會產生閒置費用，但 AI Search Free tier 佔一個免費 quota 名額。
