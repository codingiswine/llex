import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from openai import AsyncOpenAI

from app.config import settings


logger = logging.getLogger("QdrantService")

qdrant_client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=60.0)
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) # Embedding generation

async def get_embedding(text: str) -> List[float]:
    """텍스트에 대한 임베딩을 생성합니다."""
    response = await openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=text
    )
    return response.data[0].embedding

async def search_qdrant(vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
    """Qdrant에서 벡터 검색을 수행합니다."""
    import asyncio
    results = await asyncio.to_thread(
        qdrant_client.search,
        collection_name=settings.QDRANT_COLLECTION_NAME,
        query_vector=vector,
        limit=limit,
        append_payload=True
    )
    return [
        {
            "id": hit.id,
            "score": hit.score,
            "payload": hit.payload
        } for hit in results
    ]

async def get_law_sources(query: str) -> List[Dict[str, Any]]:
    """주어진 쿼리에 대한 법령 출처를 Qdrant에서 검색합니다."""
    embedding = await get_embedding(query)
    qdrant_results = await search_qdrant(embedding, limit=10) # 더 많은 출처를 위해 limit 증가
    
    sources = []
    for result in qdrant_results:
        payload = result.get("payload", {})
        law_name = payload.get("law_name", "알 수 없는 법령")
        article_num = payload.get("article_number", "")
        article_title = payload.get("article_title", "")
        text_content = payload.get("text", "")
        
        # 요약 생성 (본문이 있으면 사용, 없으면 제목 사용)
        content_summary = text_content[:150] + "..." if text_content else article_title
        
        full_article_ref = f"제{article_num}조"
        if article_title:
            full_article_ref += f" ({article_title})"

        sources.append({
            "domain": "law.go.kr", # 법제처 고정
            "title": f"{law_name} {full_article_ref}",
            "summary": content_summary,
            "link": f"http://www.law.go.kr/법령/{law_name}#{article_num}", # 실제 법제처 링크 형식에 맞게 수정 필요
            "relevance": round(result.get("score", 0.0), 2)
        })
    return sources
