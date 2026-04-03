"""LLM generation via OpenAI API (Azure OpenAI compatible).

Simulates: Azure OpenAI GPT-4o deployment called from Prompt Flow.
"""

import os
from openai import OpenAI, AzureOpenAI

from config import CHAT_MODEL


def get_openai_client() -> OpenAI | None:
    """Create OpenAI client. Returns None if no API key configured."""
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_endpoint:
        return AzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return OpenAI()
    return None


def _mock_generate(messages: list[dict[str, str]]) -> str:
    """Mock generation: return retrieved context as-is for pipeline testing."""
    # Extract the retrieval context from system prompt
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_q = next((m["content"] for m in messages if m["role"] == "user"), "")

    # Find the retrieval results section
    marker = "### 檢索結果"
    chunks = []
    for line in system.split("\n"):
        if line.startswith("Chunk ID:"):
            chunks.append(line.replace("Chunk ID: ", ""))

    return (
        f"[MOCK 模式 — 未呼叫 LLM，以下為 pipeline 輸出]\n\n"
        f"使用者查詢：{user_q}\n"
        f"檢索到的 chunks：{', '.join(chunks) if chunks else '(none)'}\n\n"
        f"在正式模式下，Azure OpenAI GPT-4o 會根據上述檢索結果\n"
        f"與動態注入的術語定義生成符合術語保真規則的回答。"
    )


def generate_answer(
    messages: list[dict[str, str]],
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
    temperature: float = 0.1,
    mock: bool = False,
) -> str:
    """Call LLM to generate an answer based on assembled prompt."""
    if mock or client is None:
        return _mock_generate(messages)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=2048,
    )
    return response.choices[0].message.content
