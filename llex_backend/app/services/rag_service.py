import asyncio
import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, AsyncGenerator
from openai import AsyncOpenAI
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from app.config import settings

logger = logging.getLogger("RAGService")

# SQLite 캐시 설정 (Docker 환경 고려)
CACHE_DIR = Path("/app/.cache") if Path("/app").exists() else Path(".cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
EMBEDDING_CACHE_DB = CACHE_DIR / "embedding_cache.db"

# ✅ 비동기 클라이언트 재사용 (settings에서 가져옴)
openai_client = settings.openai_client
qdrant_client = settings.qdrant_client  # AsyncQdrantClient

# SQLite 캐시 초기화
def init_embedding_cache():
    conn = sqlite3.connect(EMBEDDING_CACHE_DB)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            query_hash TEXT PRIMARY KEY,
            query_text TEXT,
            embedding TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_embedding_cache()

def get_embedding_cached(query: str) -> Optional[List[float]]:
    query_hash = hashlib.sha256(query.encode('utf-8')).hexdigest()
    conn = sqlite3.connect(EMBEDDING_CACHE_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT embedding FROM embeddings WHERE query_hash = ?", (query_hash,))
    result = cursor.fetchone()
    conn.close()
    if result:
        logger.info(f"✅ 임베딩 캐시 히트: {query[:30]}...")
        return json.loads(result[0])
    return None

def save_embedding_cached(query: str, embedding: List[float]):
    query_hash = hashlib.sha256(query.encode('utf-8')).hexdigest()
    conn = sqlite3.connect(EMBEDDING_CACHE_DB)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO embeddings (query_hash, query_text, embedding) VALUES (?, ?, ?)",
        (query_hash, query, json.dumps(embedding))
    )
    conn.commit()
    conn.close()
    logger.info(f"💾 임베딩 캐시 저장: {query[:30]}...")

async def get_embedding_async(query: str) -> List[float]:
    start_time = time.time()
    cached_embedding = get_embedding_cached(query)
    if cached_embedding:
        logger.info(f"⏱️ 임베딩 조회 시간: {time.time() - start_time:.2f}s (캐시)")
        return cached_embedding

    response = await openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=query
    )
    embedding = response.data[0].embedding
    save_embedding_cached(query, embedding)
    logger.info(f"⏱️ 임베딩 생성 시간: {time.time() - start_time:.2f}s (신규)")
    return embedding

async def search_qdrant_async(vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
    start_time = time.time()
    # ✅ AsyncQdrantClient 사용 (더 이상 to_thread 불필요)
    results = await qdrant_client.search(
        collection_name=settings.QDRANT_COLLECTION_NAME,
        query_vector=vector,
        limit=limit,
        with_payload=True
    )
    logger.info(f"⏱️ Qdrant 검색 시간: {time.time() - start_time:.2f}s")
    return [
        {
            "id": hit.id,
            "score": hit.score,
            "payload": hit.payload
        } for hit in results
    ]

def build_context(qdrant_results: List[Dict[str, Any]], max_chunk_length: int = 150) -> str:
    context_chunks = []
    for result in qdrant_results:
        payload = result.get("payload", {})
        law_name = payload.get("법령명", "알 수 없는 법령")
        article_num = payload.get("조문번호", "알 수 없는 조문")
        paragraph_num = payload.get("항번호", "")
        sub_paragraph_num = payload.get("호번호", "")
        content = payload.get("본문", "")
        enforcement_date = payload.get("시행일자", "알 수 없음")

        # 조문번호, 항번호, 호번호를 상세하게 포함
        full_article_ref = f"제{article_num}조"
        if paragraph_num:
            full_article_ref += f" 제{paragraph_num}항"
        if sub_paragraph_num:
            full_article_ref += f" 제{sub_paragraph_num}호"

        chunk = f"법령명: {law_name}, 조항: {full_article_ref}, 시행일자: {enforcement_date}, 내용: {content}"
        
        # 청크 길이 제한
        if len(chunk) > max_chunk_length:
            chunk = chunk[:max_chunk_length] + "..."
        context_chunks.append(chunk)
    return "\n\n".join(context_chunks)

async def run_rag_async(query: str) -> AsyncGenerator[str, None]:
    start_total_time = time.time()

    # 1. 임베딩 생성 및 Qdrant 검색 병렬 실행
    embedding_vector = await get_embedding_async(query)
    qdrant_results = await search_qdrant_async(embedding_vector)

    # 2. 컨텍스트 빌드
    context = build_context(qdrant_results)
    logger.info(f"📚 RAG Context:\n{context[:200]}...")

    # 3. GPT 답변 생성 (스트리밍)
    from app.services.gpt_service import generate_answer_async  # ✅ 내부 지연 import
    async for token in generate_answer_async(query, context):
        yield token
    
    end_total_time = time.time()
    logger.info(f"⏱️ 전체 RAG 응답 시간: {end_total_time - start_total_time:.2f}s")
