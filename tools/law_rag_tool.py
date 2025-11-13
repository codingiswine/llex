#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
law_rag_tool_v5.py (LLeX v5.0, GPT-5 스타일)
────────────────────────────────────────────
RAG 기반 법령 검색 + DRF 복구 감지 + 실제 시행일자 표시
- PostgreSQL(law_test) → Qdrant → DRF 순서 탐색
- 정확 매칭(정규화 필드) + 자동 하이퍼링크 + 시행일 표시
"""

import os, re, requests
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
from openai import OpenAI

# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
# COLLECTION = "laws"
COLLECTION = os.getenv("QDRANT_COLLECTION", "laws")
LAW_OC_ID = os.getenv("law_oc_id", "drsgh1")

DB_USER = os.getenv("DB_USER", "linkcampus")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", 5432)
DB_NAME = os.getenv("DB_NAME", "law_chatbot")

BASE_URL = "http://www.law.go.kr/DRF/lawService.do"

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
pg_engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# ─────────────────────────────
# DRF 상태 감지
# ─────────────────────────────
def drf_is_alive() -> bool:
    try:
        res = requests.get(BASE_URL, params={"OC": LAW_OC_ID, "target": "law", "query": "산업안전보건법", "type": "json"}, timeout=5)
        return res.status_code == 200 and "법령" in res.text
    except:
        return False

# ─────────────────────────────
# PostgreSQL 검색 (law_test)
# ─────────────────────────────
def get_law_from_postgres(law_name: str, article_num: str) -> Optional[str]:
    """law_test 테이블에서 법령 조문 조회"""
    try:
        query = text("""
            SELECT text
            FROM law_test
            WHERE REPLACE(law_name_norm, ' ', '') = :law_name
              AND article_number_norm = :article_num
            LIMIT 1;
        """)
        with pg_engine.connect() as conn:
            row = conn.execute(query, {"law_name": law_name.replace(" ", ""), "article_num": article_num}).fetchone()
            if row:
                print(f"✅ [Postgres] '{law_name}' 제{article_num}조 로드 완료")
                return row[0]
    except Exception as e:
        print(f"⚠️ [Postgres] 조회 실패: {e}")
    return None

# ─────────────────────────────
# DRF 복구 조회
# ─────────────────────────────
def get_law_from_drf(law_name: str) -> Optional[dict]:
    print(f"🌐 [DRF] API 요청: {law_name}")
    try:
        params = {"OC": LAW_OC_ID, "target": "law", "query": law_name, "type": "json"}
        res = requests.get(BASE_URL, params=params, timeout=10)
        if res.status_code != 200:
            return None
        data = res.json().get("법령", {})
        enforcement_date = data.get("시행일자") or data.get("시행일") or "시행일자 정보 없음"
        articles = data.get("조문", [])
        print(f"✅ [DRF] '{law_name}' 조문 {len(articles)}개 로드 + 시행일자 {enforcement_date}")
        return {"articles": articles, "enforcement_date": enforcement_date}
    except Exception as e:
        print(f"❌ [DRF] 오류: {e}")
        return None

# ─────────────────────────────
# 핵심 RAG 함수
# ─────────────────────────────
def get_law_rag_answer(query: str, top_k: int = 3) -> str:
    """PostgreSQL → Qdrant → DRF → GPT 요약"""
    print(f"🔍 [LawRAG] 검색 시작: {query}")

    def extract_law_name(q: str) -> str:
        m = re.search(
            r"([가-힣]+(?:법|기준|규칙|처벌법|시행령|시행규칙))", q
        )
        return m.group(1) if m else ""


    def extract_article_num(q: str) -> str:
        m = re.search(r"(\d+)\s*조", q)
        return m.group(1) if m else ""

    law_name = extract_law_name(query)
    article_number = extract_article_num(query)
    print(f"📘 [LawRAG] 질의 법령명: {law_name}, 조문번호: {article_number}")

    full_text = get_law_from_postgres(law_name, article_number)
    found_law = law_name
    enforcement_date = None

    # PostgreSQL 실패 → Qdrant fallback
    if not full_text:
        print(f"⚠️ [LawRAG] PostgreSQL '{law_name}' 없음 → Qdrant로 전환")
        embedding = openai_client.embeddings.create(model="text-embedding-3-large", input=query).data[0].embedding

        q_filter = Filter(
            must=[FieldCondition(key="law_name_norm", match=MatchValue(value=law_name.replace(" ", "")))]
        )

        results = qdrant.search(collection_name=COLLECTION, query_vector=embedding, limit=top_k, with_payload=True, query_filter=q_filter)
        if results:
            best = results[0]
            found_law = best.payload.get("law_name", law_name)
            full_text = best.payload.get("text", "")
            enforcement_date = best.payload.get("enforcement_date", None)
            print(f"✅ [LawRAG] Qdrant에서 '{found_law}' 검색 성공")
        else:
            drf_data = get_law_from_drf(law_name)
            if drf_data:
                enforcement_date = drf_data["enforcement_date"]
                full_text = "\n\n".join(f"제{a.get('조문번호')}조 {a.get('조문내용')}" for a in drf_data["articles"])
                print("🟢 [LawRAG] DRF 복구 데이터 사용")
            else:
                return f"❌ '{law_name}' 제{article_number}조를 찾을 수 없습니다."

    # GPT 요약
    prompt = f"""
    너는 대한민국 재난·안전·산업안전 법령 전문가야.
    아래 조문을 참고하여 사용자 질문에 정확히 설명해줘.

    [질문]
    {query}

    [법령명] {found_law}
    [조문번호] 제{article_number}조
    [조문내용]
    {full_text}
    """

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1200
    )
    summary = response.choices[0].message.content.strip()

    # 시행일자
    enforcement_info = enforcement_date or "시행일자 정보 없음"

    # 출처
    if drf_is_alive():
        law_url = f"http://www.law.go.kr/법령/{found_law}/제{article_number}조"
        source = f"[{found_law} 제{article_number}조]({law_url}) (법제처 DRF)"
        notice = ""
    else:
        source = "PostgreSQL → Qdrant (DRF 임시 차단 중)"
        notice = "\n\n⚠️ **국가정보자원관리원 전산시설 화재** 로 현재 서비스가 중단되고 있습니다. 조속한 서비스 정상화를 위하여 최선을 다하겠습니다. 감사합니다"

    return f"""
🧾 **{found_law} 제{article_number}조**

{summary}

📜 **조문 전문**

{full_text.strip()}

---

**시행일자:** {enforcement_info}  
**출처:** {source}{notice}
""".strip()
