#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gpt_service.py (LLeX v5.2 - Async Stable)
────────────────────────────────────────────
- 모든 async 함수에 await 적용
- summarize_web 비동기 호출 보완
- DB / Memory 완전 비동기 호환
"""

import logging
import asyncio
import warnings
from typing import AsyncGenerator
from openai import AsyncOpenAI

# Suppress all LangChain warnings (including deprecation)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*LangChain.*")

from langchain.memory import ConversationBufferMemory

try:
    # ✅ Docker 내부 기준 (WORKDIR /app)
    from app.config import settings
    from app.services.rag_service import get_embedding_async, search_qdrant_async
    from app.tools.websearch_tool import summarize_web
    from app.tools.db_query_tool_async import get_recent_history
except ModuleNotFoundError:
    # ✅ 로컬 실행 기준 (Cursor, VSCode)
    from app.config import settings
    from app.services.rag_service import get_embedding_async, search_qdrant_async
    from app.tools.websearch_tool import summarize_web
    from app.tools.db_query_tool_async import get_recent_history



logger = logging.getLogger("GPTService")
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# ─────────────────────────────
# 고정 응답 캐시
# ─────────────────────────────
FIXED_RESPONSES = {
    "용산구 재난안전관리팀이 알아야 할 법": """\
#### 🏛️ 재난안전관리팀 핵심 9개 법령
1️⃣ 산업안전보건기준에 관한 규칙  
2️⃣ 산업안전보건법 시행규칙  
3️⃣ 재난 및 안전관리 기본법 시행령  
4️⃣ 산업안전보건법  
5️⃣ 재난 및 안전관리 기본법  
6️⃣ 산업안전보건법 시행령  
7️⃣ 재난 및 안전관리 기본법 시행규칙  
8️⃣ 중대재해 처벌 등에 관한 법률  
9️⃣ 중대재해 처벌 등에 관한 법률 시행령  
> 💬 이 중 가장 실무에서 중요한 법은  
> **산업안전보건기준에 관한 규칙**이야.
"""
}

# ✅ 사용자별 Memory 관리
USER_MEMORIES = {}

def get_user_memory(user_id: str):
    """사용자별 Memory 객체 반환"""
    if user_id not in USER_MEMORIES:
        USER_MEMORIES[user_id] = ConversationBufferMemory(
            memory_key="chat_history",
            input_key="input",
            return_messages=False
        )
        print(f"🧠 [init] {user_id} Memory 생성 완료")
    return USER_MEMORIES[user_id]

def check_fixed_response(query: str) -> str | None:
    for key, value in FIXED_RESPONSES.items():
        if key in query or key.replace(" ", "") in query.replace(" ", ""):
            return value
    return None

# ─────────────────────────────
# ✅ Memory-aware GPT 답변 생성기
# ─────────────────────────────
async def generate_answer_async(user_id: str, full_prompt: str) -> AsyncGenerator[str, None]:
    fixed = check_fixed_response(full_prompt)
    if fixed:
        yield fixed
        return

    user_memory = get_user_memory(user_id)

    # 🔧 await 추가: DB Memory는 비동기 함수
    history_records = await get_recent_history(user_id, limit=10)
    history_text = "\n".join(
        f"사용자: {h['question']}\nLLeX.Ai: {h['answer']}"
        for h in history_records
    )

    past_context = user_memory.load_memory_variables({})
    chain_history = past_context.get("chat_history", "")

    merged_prompt = f"{history_text}\n{chain_history}\n사용자: {full_prompt}"

    messages = [
        {"role": "system", "content": "너는 LinkCampus 재난안전관리팀의 법령·안전 어시스턴트 LLeX.Ai야."},
        {"role": "user", "content": merged_prompt},
    ]

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.5,
        max_tokens=1000,
        stream=True,
    )

    full_answer = ""
    async for chunk in response:
        token = chunk.choices[0].delta.content
        if token:
            full_answer += token
            yield token

    user_memory.save_context({"input": full_prompt}, {"output": full_answer})
    print(f"🧠 [Memory] {user_id} 대화 저장 완료")

# ─────────────────────────────
# ⚖️ Hybrid RAG + Web 통합 (비동기 완전화)
# ─────────────────────────────
async def hybrid_merge(user_id: str, question: str):
    print("⚖️ [hybrid_merge] 실행 시작")

    fixed = check_fixed_response(question)
    if fixed:
        yield fixed
        return

    user_memory = get_user_memory(user_id)

    # 🔧 await 추가
    history_records = await get_recent_history(user_id, limit=10)
    history_text = "\n".join(
        f"사용자: {h['question']}\nLLeX.Ai: {h['answer']}"
        for h in history_records
    )

    past_context = user_memory.load_memory_variables({})
    chain_history = past_context.get("chat_history", "")

    # 🔧 비동기 작업 병렬 처리
    rag_task = asyncio.create_task(_rag_search(question))
    web_task = asyncio.create_task(_web_search(question))
    rag_results, web_results = await asyncio.gather(rag_task, web_task)

    merged_prompt = f"""
{history_text}
{chain_history}

### 사용자 질문
{question}

### 내부 법령 근거 (RAG 결과)
{_format_rag_results(rag_results)}

### 외부 웹 검색 결과
{_format_web_results(web_results)}

💡 위의 내용을 참고해 정확하고 근거 있는 답변을 작성해줘.
"""

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 LinkCampus의 재난안전관리팀을 위한 법령·안전 어시스턴트 LLeX.Ai야."},
            {"role": "user", "content": merged_prompt},
        ],
        temperature=0.3,
        stream=True,
    )

    full_answer = ""
    async for chunk in response:
        token = chunk.choices[0].delta.content
        if token:
            full_answer += token
            yield token

    print("✅ [hybrid_merge] 스트리밍 완료")

    try:
        user_memory.save_context({"input": question}, {"output": full_answer})
        print(f"🧠 [Memory] hybrid_merge 대화 내용 저장 완료 (user={user_id})")
    except Exception as e:
        print(f"⚠️ [Memory] 저장 실패: {e}")

# ─────────────────────────────
# 내부 유틸 함수들 (비동기 수정)
# ─────────────────────────────
async def _rag_search(question: str):
    try:
        embedding = await get_embedding_async(question)
        results = await search_qdrant_async(embedding, limit=3)
        print(f"📚 [RAG] 검색 완료 ({len(results)}건)")
        return results
    except Exception as e:
        print(f"⚠️ [RAG] 검색 오류: {e}")
        return []

async def _web_search(question: str):
    try:
        # 🔧 summarize_web은 비동기 함수로 호출
        result = await summarize_web(question)
        print(f"🌐 [Web] 검색 완료")
        return result
    except Exception as e:
        print(f"⚠️ [Web] 검색 오류: {e}")
        return {}

def _format_rag_results(results):
    if not results:
        return "없음"
    return "\n".join(
        f"- **{r.get('payload', {}).get('title', '제목 없음')}** "
        f"(score={r.get('score', 0):.2f})\n  {r.get('payload', {}).get('content', '')[:200]}"
        for r in results
    )

def _format_web_results(results):
    if not results or "summaries" not in results:
        return "없음"
    return results.get("summaries", "").strip()

__all__ = ["generate_answer_async", "hybrid_merge", "check_fixed_response", "get_user_memory"]

print("✅ [init] gpt_service.py 로드 완료 (Async Stable)")
