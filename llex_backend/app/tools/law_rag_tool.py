#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
law_rag_tool_async_v6.11_direct_article_linked.py
────────────────────────────────────────────
✅ 주요 개선
1️⃣ "법령명 + 조문번호" 질의 시 단순 포맷 출력
   → 법 설명 / 조문 전문 / 법령 정보(하이퍼링크 포함)
2️⃣ 시행일자는 DB 값만 표시 (GPT 생성 금지)
3️⃣ 출처는 [법령명 제n조](링크) 하이퍼링크로 표시
────────────────────────────────────────────
"""

import re, urllib.parse, aiohttp
from datetime import datetime
from typing import Optional, Dict
from sqlalchemy import text
from qdrant_client.http.models import FieldCondition, MatchValue, Filter
from core.stream import ToolChunk
from app.tools.websearch_tool import summarize_web
try:
    from app.config import settings   # ✅ Docker 실행 시
except ModuleNotFoundError:
    from app.config import settings  # ✅ 로컬 실행 시



# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
qdrant = settings.qdrant_client
async_engine = settings.async_engine
COLLECTION = settings.QDRANT_COLLECTION_NAME


# ─────────────────────────────
# 유틸 함수
# ─────────────────────────────
def normalize_law_name(name: str) -> str:
    import unicodedata
    return re.sub(r"[\s·]", "", unicodedata.normalize("NFC", name.strip()))

def normalize_article(article: str) -> str:
    return re.sub(r"[^\d]", "", article or "")

def detect_law_name(query: str) -> Optional[str]:
    """질문 내에서 법령명 자동 감지"""
    LAWS = [
        "산업안전보건기준에관한규칙", "산업안전보건법시행규칙", "산업안전보건법시행령", "산업안전보건법",
        "재난및안전관리기본법시행규칙", "재난및안전관리기본법시행령", "재난및안전관리기본법",
        "중대재해처벌등에관한법률시행령", "중대재해처벌등에관한법률"
    ]
    q = re.sub(r"\s+", "", query)
    for law in LAWS:
        if law in q:
            return normalize_law_name(law)
    return None


# ─────────────────────────────
# 핵심 실행 (Async)
# ─────────────────────────────
async def run(plan):
    query = plan.args.get("query", "")
    yield ToolChunk(type="status", payload="⚖️ 법령 검색 시작...")

    law_name = detect_law_name(query)
    article_match = re.search(r"(?:제)?\s*(\d+)\s*조", query)
    article_number = article_match.group(1) if article_match else ""

    is_direct_article_query = bool(law_name and article_number)

    # ① 법령명 미인식 시 Web fallback
    if not law_name:
        yield ToolChunk(type="status", payload="⚠️ 법령명을 인식하지 못했습니다 → Web 검색으로 전환")
        web_result = await summarize_web(query)
        web_summary = web_result.get("summaries", "")
        resp = await settings.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"""
                대한민국 법령 해설 전문가로서 답변하세요.
                질문: {query}
                ---
                {web_summary}
                ---
                🔹 **결론**
                🔹 **설치 또는 적용 기준**
                🔹 **법적 근거**
                🔹 **출처**
                """
            }],
            temperature=0.3,
        )
        answer = resp.choices[0].message.content.strip()
        yield ToolChunk(type="text", payload=answer)
        yield ToolChunk(type="status", payload="✅ Web 보완 검색 완료")
        return

    # ② PostgreSQL 검색 (1차: 정확한 조문 검색)
    text_val, enforcement_date = None, None
    search_law_norm = normalize_law_name(law_name)
    search_article_norm = normalize_article(article_number)

    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("""
                    SELECT text, enforcement_date
                    FROM law_chunks
                    WHERE law_name_norm = :law AND article_number_norm = :num
                    LIMIT 1;
                """),
                {"law": search_law_norm, "num": search_article_norm}
            )
            row = result.fetchone()
            if row:
                text_val, enforcement_date = row
                yield ToolChunk(type="status", payload="✅ [PostgreSQL] 조문 발견")
            else:
                yield ToolChunk(type="status", payload="🔍 [Qdrant] 벡터 검색으로 전환...")
    except Exception as e:
        yield ToolChunk(type="status", payload=f"⚠️ [PostgreSQL] 오류 → Qdrant 검색")

    # ③ Qdrant (2차: 벡터 유사도 검색)
    if not text_val:
        yield ToolChunk(type="status", payload="🧠 [Qdrant] 벡터 검색 중...")
        try:
            emb = await settings.openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=query
            )
            embedding = emb.data[0].embedding
            q_filter = Filter(
                must=[
                    FieldCondition(key="law_name_norm", match=MatchValue(value=search_law_norm)),
                    FieldCondition(key="article_number_norm", match=MatchValue(value=search_article_norm)),
                ]
            )
            results = await qdrant.search(
                COLLECTION,
                embedding,
                query_filter=q_filter,
                limit=1,
                with_payload=True
            )
            if results and results[0].score >= 0.7:
                best = results[0]
                text_val = best.payload.get("text", "")
                enforcement_date = best.payload.get("enforcement_date", "")
                yield ToolChunk(type="status", payload=f"✅ [Qdrant] 유사도 {best.score:.2f} 조문 발견")
        except Exception as e:
            yield ToolChunk(type="status", payload=f"⚠️ Qdrant 검색 실패")

    # ④ Web fallback (모든 조문 검색 실패)
    if not text_val or str(text_val).strip() == "":
        yield ToolChunk(type="status", payload="⚠️ 조문 없음 → Web fallback 실행")
        web_result = await summarize_web(query)
        web_summary = web_result.get("summaries", "")
        resp = await settings.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"""
                질문: {query}
                ---
                {web_summary}
                ---
                🔹 **결론**
                🔹 **설치 또는 적용 기준**
                🔹 **법적 근거**
                🔹 **출처**
                """
            }],
            temperature=0.3,
        )
        answer = resp.choices[0].message.content.strip()
        yield ToolChunk(type="text", payload=answer)
        yield ToolChunk(type="status", payload="✅ Web fallback 완료")
        return

    # ⑤ 조문 발견 시 GPT 요약
    yield ToolChunk(type="status", payload="🧠 GPT 요약 중...")

    # ✅ 포맷 분기
    if is_direct_article_query:
        prompt = f"""
        너는 대한민국 법령 해설 전문가야.
        아래 조문을 기반으로 법의 취지와 목적만 설명해.
        ⚠️ 시행일자나 출처를 절대 출력하지 마.

        출력 형식:
        🔹 **법 설명**
        - 법의 취지를 한 문단으로 요약
        📜 **조문 전문**
        - 원문 그대로 표시 (조문 내 개정일은 그대로 둬도 됨)
        ---
        [조문 전문]
        {text_val}
        """
    else:
        prompt = f"""
        너는 대한민국 법령 해설 전문가야.
        사용자 질문: "{query}"
        아래 조문을 참고해 실무 중심으로 설명해.
        ---
        🔹 **결론**
        🔹 **설치 또는 적용 기준**
        🔹 **법적 근거**
        🔹 **출처**
        [조문 전문]
        {text_val}
        """

    try:
        # ✅ GPT 호출을 스트리밍 모드로 변경
        stream = await settings.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            stream=True,  # ← 이게 핵심!
        )
    
        summary_parts = []
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                summary_parts.append(delta)
                # ✅ 스트리밍 중간에도 바로 전송
                yield ToolChunk(type="text", payload=delta)
        
        # ✅ 스트림 끝나면 전체 텍스트 조합
        summary = "".join(summary_parts).strip()
        law_url = f"https://www.law.go.kr/법령/{urllib.parse.quote(law_name)}/제{article_number}조"

        # ✅ 출력 포맷 (Markdown 하이퍼링크 적용)
        if is_direct_article_query:
            # ⚙️ 스트리밍 중에는 이미 본문을 보냈으므로
            # 여기서는 법령 정보(시행일자, 출처)만 추가 출력
            footer = (
                f"\n\n📘 **법령 정보**  \n"
                f"시행일자: {enforcement_date or '정보 없음'}  \n"
                f"출처: [{law_name} 제{article_number}조]({law_url})"
            )
            yield ToolChunk(type="text", payload=footer)
        else:
            # 일반 질문일 경우 전체 출력 필요
            final_text = (
                f"{summary}\n\n"
                f"📜 **조문 전문**\n{text_val}\n\n"
                f"**시행일자:** {enforcement_date or '정보 없음'}"
            )
            yield ToolChunk(type="text", payload=final_text)

        # ✅ 마지막에 출처 정보만 별도로 전송
        yield ToolChunk(type="source", payload={"law_url": law_url})

    except Exception as e:
        yield ToolChunk(type="error", payload=f"❌ GPT 요약 실패: {e}")

    yield ToolChunk(type="status", payload="✅ 법령 검색 완료")

