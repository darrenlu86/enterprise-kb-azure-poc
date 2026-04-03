"""Migrate local KB data to Azure services.

Uploads:
  1. 63 chunks → Azure AI Search index (with embeddings + metadata)
  2. 99 terms → Cosmos DB glossary container
  3. 47 relations → Cosmos DB term-relations container
  4. Synonym map → Azure AI Search synonym map
"""

import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SearchField,
    SearchFieldDataType,
    SimpleField,
    SearchableField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile,
    SearchIndex,
    SemanticConfiguration,
    SemanticSearch,
    SemanticPrioritizedFields,
    SemanticField,
    SynonymMap,
)
from azure.core.credentials import AzureKeyCredential
from azure.cosmos import CosmosClient
from openai import AzureOpenAI

from data_loader import load_knowledge_base


def get_azure_clients():
    search_endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    search_key = os.environ["AZURE_SEARCH_KEY"]
    cosmos_endpoint = os.environ["AZURE_COSMOS_ENDPOINT"]
    cosmos_key = os.environ["AZURE_COSMOS_KEY"]
    openai_endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    openai_key = os.environ["AZURE_OPENAI_API_KEY"]

    search_index_client = SearchIndexClient(
        endpoint=search_endpoint,
        credential=AzureKeyCredential(search_key),
    )
    cosmos_client = CosmosClient(cosmos_endpoint, cosmos_key)
    openai_client = AzureOpenAI(
        azure_endpoint=openai_endpoint,
        api_key=openai_key,
        api_version="2024-10-21",
    )
    return search_index_client, cosmos_client, openai_client


INDEX_NAME = "financial-ebanking-chunks"


def create_search_index(index_client: SearchIndexClient):
    """Create Azure AI Search index with vector + text + metadata fields."""
    fields = [
        SimpleField(name="chunk_id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="zh-Hant.lucene"),
        SimpleField(name="article", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="section", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="version", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="contained_terms", type="Collection(Edm.String)", filterable=True),
        SimpleField(name="is_definition_chunk", type=SearchFieldDataType.Boolean, filterable=True),
        SimpleField(name="topic_tags", type="Collection(Edm.String)", filterable=True, facetable=True),
        SimpleField(name="priority", type=SearchFieldDataType.String, filterable=True),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=3072,
            vector_search_profile_name="default-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="default-algo", parameters={"metric": "cosine"})],
        profiles=[VectorSearchProfile(name="default-profile", algorithm_configuration_name="default-algo")],
    )

    semantic_config = SemanticConfiguration(
        name="default-semantic",
        prioritized_fields=SemanticPrioritizedFields(
            content_fields=[SemanticField(field_name="content")],
        ),
    )

    index = SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
        semantic_search=SemanticSearch(configurations=[semantic_config]),
    )

    index_client.create_or_update_index(index)
    print(f"  Created search index: {INDEX_NAME}")


def create_synonym_map(index_client: SearchIndexClient, kb):
    """Create Azure AI Search Synonym Map from glossary prohibited alternatives."""
    rules = []
    for term in kb.terms.values():
        for alt in term.prohibited_alternatives:
            # Solr format: "alt => correct"
            rules.append(f"{alt} => {term.term}")

    if rules:
        synonym_map = SynonymMap(name="term-synonyms", synonyms="\n".join(rules))
        index_client.create_or_update_synonym_map(synonym_map)
        print(f"  Created synonym map: {len(rules)} rules")


def upload_chunks(index_client: SearchIndexClient, openai_client: AzureOpenAI, kb):
    """Upload chunks with embeddings to Azure AI Search."""
    search_client = SearchClient(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        index_name=INDEX_NAME,
        credential=AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]),
    )

    # Generate embeddings in batches
    batch_size = 16
    all_chunks = list(kb.chunks)
    documents = []

    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        texts = [c.content for c in batch]

        response = openai_client.embeddings.create(
            input=texts,
            model="text-embedding-3-large",
        )
        embeddings = [item.embedding for item in response.data]

        for chunk, embedding in zip(batch, embeddings):
            documents.append({
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "article": chunk.article,
                "section": chunk.section or "",
                "version": chunk.version,
                "contained_terms": list(chunk.contained_terms),
                "is_definition_chunk": chunk.is_definition_chunk,
                "topic_tags": list(chunk.topic_tags),
                "priority": chunk.priority,
                "content_vector": embedding,
            })

        print(f"  Embedded {min(i + batch_size, len(all_chunks))}/{len(all_chunks)} chunks")

    # Upload to search index
    result = search_client.upload_documents(documents)
    succeeded = sum(1 for r in result if r.succeeded)
    print(f"  Uploaded {succeeded}/{len(documents)} chunks to Azure AI Search")


def upload_glossary(cosmos_client: CosmosClient, kb):
    """Upload glossary terms to Cosmos DB."""
    db = cosmos_client.get_database_client("enterprise-kb")
    container = db.get_container_client("glossary")

    count = 0
    for term in kb.terms.values():
        doc = {
            "id": term.id,
            "term": term.term,
            "enterpriseDefinition": term.enterprise_definition,
            "commonDefinition": term.common_definition,
            "definitionDifference": term.definition_difference,
            "category": term.category,
            "prohibitedAlternatives": list(term.prohibited_alternatives),
            "acceptedSynonyms": list(term.accepted_synonyms),
            "relatedTerms": list(term.related_terms),
            "status": term.status,
        }
        container.upsert_item(doc)
        count += 1

    print(f"  Uploaded {count} terms to Cosmos DB")


def upload_relations(cosmos_client: CosmosClient, kb):
    """Upload knowledge graph relations to Cosmos DB."""
    db = cosmos_client.get_database_client("enterprise-kb")
    container = db.get_container_client("term-relations")

    count = 0
    for i, rel in enumerate(kb.relations):
        doc = {
            "id": f"rel-{i:04d}",
            "from_id": rel.from_id,
            "to_id": rel.to_id,
            "relation_type": rel.relation_type,
            "note": rel.note,
        }
        container.upsert_item(doc)
        count += 1

    print(f"  Uploaded {count} relations to Cosmos DB")


def main():
    print("=== Migrating KB data to Azure ===\n")

    kb = load_knowledge_base()
    index_client, cosmos_client, openai_client = get_azure_clients()

    print("\n[1/5] Creating search index...")
    create_search_index(index_client)

    print("\n[2/5] Creating synonym map...")
    create_synonym_map(index_client, kb)

    print("\n[3/5] Uploading chunks with embeddings...")
    upload_chunks(index_client, openai_client, kb)

    print("\n[4/5] Uploading glossary to Cosmos DB...")
    upload_glossary(cosmos_client, kb)

    print("\n[5/5] Uploading relations to Cosmos DB...")
    upload_relations(cosmos_client, kb)

    print("\n=== Migration complete! ===")
    print("Run: python deploy/test_azure.py  to verify")


if __name__ == "__main__":
    main()
