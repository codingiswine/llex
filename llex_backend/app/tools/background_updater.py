#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
background_updater_v5.1_stable.py (LLeX.Ai, 2025-10-24)
✅ 로그 강화판 (law.go.kr 최신 JSON 구조 완전 대응)
────────────────────────────────────────────
- 조문 본문 + 항/호 병합
- 시행일자 타입(list/dict/str) 완전 대응
- PostgreSQL + Qdrant 초기화 후 자동 임베딩
- 실행 로그 및 진행률 출력 개선
────────────────────────────────────────────
"""

import os, uuid, re, sys, asyncio, requests, time
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from qdrant_client import QdrantClient
from openai import OpenAI

# ─────────────────────────────
# 환경 설정
# ─────────────────────────────
load_dotenv()
LAW_OC_ID = os.getenv("LAW_OC_ID", "drsgh1")
BASE_DETAIL_URL = "https://www.law.go.kr/DRF/lawService.do"

DB_USER = os.getenv("DB_USER", "linkcampus")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", 5432)
DB_NAME = os.getenv("DB_NAME", "law_chatbot")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=300)
pg_engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=300)

# ─────────────────────────────
# 핵심 법령 목록
# ─────────────────────────────
CORE_LAWS = [
    "산업안전보건법",
    "산업안전보건법 시행령",
    "산업안전보건법 시행규칙",
    "산업안전보건기준에 관한 규칙",
    "재난 및 안전관리 기본법",
    "재난 및 안전관리 기본법 시행령",
    "재난 및 안전관리 기본법 시행규칙",
    "중대재해 처벌 등에 관한 법률",
    "중대재해 처벌 등에 관한 법률 시행령",
]

# ─────────────────────────────
# 고정 ID 매핑
# ─────────────────────────────
LAW_ID_MAP = {
    "산업안전보건법": "001766",
    "산업안전보건법 시행령": "003786",
    "산업안전보건법 시행규칙": "007364",
    "산업안전보건기준에 관한 규칙": "007363",
    "재난 및 안전관리 기본법": "009640",
    "재난 및 안전관리 기본법 시행령": "009708",
    "재난 및 안전관리 기본법 시행규칙": "009717",
    "중대재해 처벌 등에 관한 법률": "013993",
    "중대재해 처벌 등에 관한 법률 시행령": "014159",
}

# ─────────────────────────────
# 고정 ID 매핑 조회
# ─────────────────────────────
def get_latest_law_id(law_name: str):
    if law_name in LAW_ID_MAP:
        law_id = LAW_ID_MAP[law_name]
        print(f"🧩 {law_name} → 고정 ID 매핑 성공 (ID={law_id})")
        return law_id
    raise RuntimeError(f"❌ {law_name}: ID 미등록")

# ─────────────────────────────
# DB 및 Qdrant 초기화
# ─────────────────────────────
def reset_databases():
    print("\n🧹 [Init] PostgreSQL + Qdrant 초기화 시작...")
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE law_chunks RESTART IDENTITY;"))
    print("✅ PostgreSQL 초기화 완료")

    if qdrant.collection_exists("laws"):
        qdrant.delete_collection("laws")
        print("🧠 기존 Qdrant 컬렉션 삭제 완료")

    qdrant.create_collection(
        collection_name="laws",
        vectors_config={"size": 3072, "distance": "Cosine"},
    )
    print("✅ Qdrant 컬렉션 재생성 완료\n")

# ─────────────────────────────
# 법령 수집 함수
# ─────────────────────────────
async def fetch_law(law_name: str):
    """law.go.kr DRF JSON에서 조문 + 시행일자 수집"""
    def extract_article_text(art):
        parts = []
        if art.get("조문내용"):
            parts.append(str(art["조문내용"]).strip())
        paras = art.get("항") or []
        if isinstance(paras, dict): paras = [paras]
        for p in paras:
            if p.get("항내용"): parts.append(str(p["항내용"]).strip())
            hos = p.get("호") or []
            if isinstance(hos, dict): hos = [hos]
            for h in hos:
                if h.get("호내용"): parts.append(str(h["호내용"]).strip())
        return "\n".join([p for p in parts if p.strip()])

    try:
        law_id = get_latest_law_id(law_name)
        res = requests.get(
            BASE_DETAIL_URL,
            params={"OC": LAW_OC_ID, "target": "law", "ID": law_id, "type": "JSON"},
            timeout=20,
        )
        data = res.json().get("법령", {})
        articles = data.get("조문", [])
        if isinstance(articles, dict):
            articles = articles.get("조문단위", [articles])

        raw_enf = data.get("시행일자") or data.get("시행일") or data.get("기본정보", {}).get("시행일자")
        enforcement_date = None
        if isinstance(raw_enf, str):
            enforcement_date = raw_enf.strip()
        elif isinstance(raw_enf, dict):
            enforcement_date = raw_enf.get("@시행일자") or raw_enf.get("#text")
        elif isinstance(raw_enf, list):
            for item in raw_enf:
                if isinstance(item, dict):
                    enforcement_date = item.get("@시행일자") or item.get("#text")
            enforcement_date = enforcement_date or str(raw_enf[-1]) if raw_enf else None
        enforcement_date = enforcement_date or "시행일자 정보 없음"

        print(f"📜 [{law_name}] {len(articles)}개 조문 로드 완료 (시행일={enforcement_date})")

        unique_articles = {}
        for art in articles:
            num = re.sub(r"[^\d]", "", art.get("조문번호") or "")
            if not num or num in unique_articles:
                continue
            text_val = extract_article_text(art)
            unique_articles[num] = (
                str(uuid.uuid4()),
                law_name,
                law_name.replace(" ", ""),
                art.get("조문번호"),
                num,
                text_val,
                enforcement_date,
            )

        if unique_articles:
            preview_text = list(unique_articles.values())[0][5][:80].replace("\n", " ")
            print(f"   └ 예시: {preview_text}...")
        return list(unique_articles.values())

    except Exception as e:
        print(f"❌ [{law_name}] 수집 실패: {e}")
        raise

# ─────────────────────────────
# 메인 실행
# ─────────────────────────────
async def main():
    start_time = time.time()
    print(f"\n🕖 [{datetime.now():%Y-%m-%d %H:%M:%S}] 법령 최신화 프로세스 시작\n")
    reset_databases()
    all_records = []

    try:
        results = await asyncio.gather(*[fetch_law(law) for law in CORE_LAWS])
        for r in results:
            all_records.extend(r)

        print(f"\n✅ 총 {len(all_records)}개 조문 수집 완료 → 임베딩 생성 중...\n")

        texts = [f"{r[1]} 제{r[3]}조 {r[5]}" for r in all_records]
        vectors = []
        batch_size = 100

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            pct = round(((i + len(batch)) / len(texts)) * 100, 1)
            print(f"🧠 임베딩 생성 중... {i + 1} ~ {i + len(batch)} / {len(texts)} ({pct}%)")
            try:
                response = openai_client.embeddings.create(model="text-embedding-3-large", input=batch)
                batch_vectors = [item.embedding for item in response.data]
                vectors.extend(batch_vectors)
            except Exception as e:
                print(f"⚠️ 임베딩 배치 {i // batch_size + 1} 실패: {e}")
                continue

        with pg_engine.begin() as conn:
            for r in all_records:
                conn.execute(text("""
                    INSERT INTO law_chunks 
                    (chunk_id, law_name, law_name_norm, article_number, article_number_norm, text, enforcement_date)
                    VALUES (:chunk_id, :law_name, :law_name_norm, :article_number, :article_number_norm, :text, :enf)
                    ON CONFLICT (law_name, article_number) DO NOTHING;
                """), {
                    "chunk_id": r[0], "law_name": r[1], "law_name_norm": r[2],
                    "article_number": r[3], "article_number_norm": r[4],
                    "text": r[5], "enf": r[6],
                })
        print(f"\n✅ [PostgreSQL] {len(all_records)}개 조문 저장 완료")

        batch_size_qdrant = 50
        print(f"\n🧠 [Qdrant] 업로드 시작 (총 {len(vectors)}개, 배치={batch_size_qdrant})")

        for i in range(0, len(vectors), batch_size_qdrant):
            batch_points = [
                {
                    "id": i + j + 1,
                    "vector": vectors[i + j],
                    "payload": {
                        "law_name": all_records[i + j][1],
                        "law_name_norm": all_records[i + j][2],
                        "article_number": all_records[i + j][3],
                        "article_number_norm": all_records[i + j][4],
                        "text": all_records[i + j][5],
                        "enforcement_date": all_records[i + j][6],
                    },
                }
                for j in range(min(batch_size_qdrant, len(vectors) - i))
            ]
            qdrant.upsert(collection_name="laws", points=batch_points)
            pct = round(((i + len(batch_points)) / len(vectors)) * 100, 1)
            print(f"   └ 업로드 진행률: {pct}%")

        elapsed = round(time.time() - start_time, 1)
        print(f"\n🎉 모든 법령 최신화 완료! (총 {len(all_records)}개, 소요시간: {elapsed}s)\n")

    except Exception as e:
        print(f"\n❌ 전체 프로세스 오류 발생: {e}")
        sys.exit(1)

# ─────────────────────────────
# 실행 엔트리
# ─────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
