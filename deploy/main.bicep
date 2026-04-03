// Enterprise Knowledge Base PoC — Azure Infrastructure
// Deploys: AI Search (Free) + OpenAI + Cosmos DB (Serverless)
//
// Cost estimate (demo usage, tear down after testing):
//   AI Search Free tier:     $0
//   OpenAI pay-as-you-go:    ~$0.50 (a few queries)
//   Cosmos DB serverless:    ~$0.10 (small data)
//   Total:                   < $1 if torn down within 1 hour

targetScope = 'resourceGroup'

@description('Resource name prefix')
param prefix string = 'ekb-poc'

@description('Location')
param location string = 'eastasia'

// ============================================================
// 1. Azure AI Search (Free tier) — hybrid search + RRF
// ============================================================
resource searchService 'Microsoft.Search/searchServices@2023-11-01' = {
  name: '${prefix}-search'
  location: location
  sku: {
    name: 'free'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
  }
}

// ============================================================
// 2. Azure OpenAI — embeddings + GPT-4o
// ============================================================
resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: '${prefix}-openai'
  location: location
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: '${prefix}-openai'
    publicNetworkAccess: 'Enabled'
  }
}

// Deploy text-embedding-3-large
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'text-embedding-3-large'
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
  }
}

// Deploy GPT-4o
resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
  }
  dependsOn: [embeddingDeployment]
}

// ============================================================
// 3. Cosmos DB (Serverless) — glossary + knowledge graph
// ============================================================
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: '${prefix}-cosmos'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [
      { name: 'EnableServerless' }
    ]
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: 'enterprise-kb'
  properties: {
    resource: {
      id: 'enterprise-kb'
    }
  }
}

resource glossaryContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDb
  name: 'glossary'
  properties: {
    resource: {
      id: 'glossary'
      partitionKey: {
        paths: ['/category']
        kind: 'Hash'
      }
    }
  }
}

resource relationsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDb
  name: 'term-relations'
  properties: {
    resource: {
      id: 'term-relations'
      partitionKey: {
        paths: ['/relation_type']
        kind: 'Hash'
      }
    }
  }
}

// ============================================================
// Outputs — used by deployment scripts
// ============================================================
output searchServiceName string = searchService.name
output searchAdminKey string = listAdminKeys(searchService.id, '2023-11-01').primaryKey
output openaiEndpoint string = openai.properties.endpoint
output openaiKey string = listKeys(openai.id, '2024-10-01').key1
output cosmosEndpoint string = cosmosAccount.properties.documentEndpoint
output cosmosKey string = cosmosAccount.listKeys().primaryMasterKey
