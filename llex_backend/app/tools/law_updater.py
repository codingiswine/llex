#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLeX — DRF 매일 최신화 & Postgres/Qdrant 동기화 스크립트
================================================================
목적
- 법제처 DRF(JSON)에서 지정된 법령들을 매일 받아 최신 조문 단위로 정규화
- PostgreSQL(law_chunks)와 Qdrant(laws 컬렉션)에 Upsert(동기화)
- 검색 정확도 향상: '조문여부=조문' 본문만 저장, 편/장 제목('전문') 필터링

사용 방법(요약)
1) .env 설정(아래 샘플 참고)
2) python law_updater.py --all  # 모든 법령 최신화
3) (권장) 크론/launchd/pm2 등으로 매일 1회 자동 실행

필수 .env 키
- OPENAI_API_KEY
- DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME
- QDRANT_HOST, QDRANT_PORT
- LAW_OC_ID (법제처 DRF OC 키)

테이블 요구사항 (자동 생성)
- law_chunks(law_name_norm, article_number_norm, text, enforcement_date)
  * (law_name_norm, article_number_norm) UNIQUE 인덱스

Qdrant 요구사항 (자동 생성)
- 컬렉션명: laws
- vector size: OpenAI text-embedding-3-large(3072)

스케줄링 예시
- 크론:  매일 새벽 3시 → 0 3 * * * /usr/bin/python3 /path/to/law_updater.py --all >> /var/log/llex_law_updater.log 2>&1

주의
- DRF 응답 구조가 법령마다 다르므로, 본문 추출은 딥 파서 사용(조문/항/호 + #text/전문 대응)
- 저장 시 조문번호가 동일하고 '조문여부=전문'인 항목은 건너뜀
"""

import os
import re
import sys
import json
import time
import argparse
import uuid
from typing import Dict, List, Optional
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from openai import OpenAI

# ────────────────────────────────────────────────────────────────
# 환경설정
# ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(os.path.abspath(os.path.join(BASE_DIR, "..", "..")), ".env")
load_dotenv(ENV_PATH) if os.path.exists(ENV_PATH) else load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DB_USER = os.getenv("DB_USER", "linkcampus")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "law_chatbot")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
LAW_OC_ID = os.getenv("LAW_OC_ID", "drsgh1")

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072  # 모델 차원(2025-10 기준)
COLLECTION = "laws"

BASE_URL = "https://www.law.go.kr/DRF/lawService.do"
LAW_ID_MAP: Dict[str, str] = {
    "산업안전보건법": "001766",
    "산업안전보건법시행령": "003786",
    "산업안전보건법시행규칙": "007364",
    "산업안전보건기준에관한규칙": "007363",
    "재난및안전관리기본법": "009640",
    "재난및안전관리기본법시행령": "009708",
    "재난및안전관리기본법시행규칙": "009717",
    "중대재해처벌등에관한법률": "013993",
    "중대재해처벌등에관한법률시행령": "014159",
}

# ────────────────────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────────────────────

def normalize_law_name(name: str) -> str:
    import unicodedata
    name = unicodedata.normalize("NFC", name or "")
    name = re.sub(r"[\s·]", "", name)
    return name.strip()


def normalize_article(article: str) -> str:
    return re.sub(r"[^\d]", "", article or "")


def deep_extract_text(value) -> List[str]:
    """DRF JSON의 모든 중첩 구조에서 문자열을 수집 (#text/전문/조문내용/항내용/호내용 포함)."""
    out = []
    if isinstance(value, list):
        for v in value:
            out.extend(deep_extract_text(v))
    elif isinstance(value, dict):
        for k, v in value.items():
            if k in ["조문내용", "조문단위", "항내용", "호내용", "전문", "#text", "content"]:
                out.extend(deep_extract_text(v))
            else:
                out.extend(deep_extract_text(v))
    elif isinstance(value, str):
        t = value.strip()
        if t:
            out.append(t)
    return out


def extract_article_payloads(law_name: str, drf_json: dict) -> List[dict]:
    """DRF JSON → 조문(본문) 리스트로 표준화.
    - '조문여부' == '조문' 인 항목만 대상
    - 텍스트: 조문내용 + 항/호까지 통합
    - 조문번호는 숫자만(article_number_norm)
    - 시행일자 추출(가능 시)
    """
    articles = drf_json.get("법령", {}).get("조문", {})
    if isinstance(articles, dict):
        articles = articles.get("조문단위", [articles])

    payloads = []
    for a in articles or []:
        if a.get("조문여부") != "조문":
            continue  # 편/장 제목('전문') 제외

        art_no = normalize_article(str(a.get("조문번호", "")))
        if not art_no:
            continue

        # 텍스트 추출
        text_candidates = []
        if a.get("조문내용"):
            text_candidates.extend(deep_extract_text(a.get("조문내용")))
        if a.get("항"):
            text_candidates.extend(deep_extract_text(a.get("항")))
        # 보정: 일부 법령은 조문단위 아래에 본문이 있는 형태
        if a.get("조문단위"):
            text_candidates.extend(deep_extract_text(a.get("조문단위")))

        full_text = "\n".join([t for t in text_candidates if t]).strip()
        if not full_text:
            # 최후 보정: 조문제목 + 조문내용 단일 문자열 조합 시도
            title = a.get("조문제목") or ""
            body = a.get("조문내용") or ""
            body_str = " ".join(deep_extract_text(body)) if body else ""
            full_text = (f"{title} {body_str}").strip()

        # 시행일자
        enf = a.get("조문시행일자") or drf_json.get("법령", {}).get("시행일자") or drf_json.get("법령", {}).get("시행일")
        if isinstance(enf, list):
            enf = enf[-1]
        if isinstance(enf, dict):
            enf = enf.get("@시행일자") or enf.get("#text")
        enforcement_date = (str(enf).strip() if enf else None) or ""

        if enforcement_date:
            enforcement_date = enforcement_date[:10]  # 'YYYY-MM-DD' 형식 보정


        if full_text:
            payloads.append({
                "chunk_id": str(uuid.uuid4()), # ✅ uuid 추가
                "law_name": law_name,          # ✅ 원본 법령명 추가
                "law_name_norm": normalize_law_name(law_name),
                "article_number_norm": art_no,
                "text": full_text,
                "enforcement_date": enforcement_date,
            })
    return payloads


# ────────────────────────────────────────────────────────────────
# 외부 클라이언트
# ────────────────────────────────────────────────────────────────

def init_clients():
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing in environment")
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    engine: Engine = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=120) # QdrantClient 생성 시 느려질 경우 대비 timeout 추가
    return openai_client, engine, qdrant


def ensure_pg_schema(engine: Engine):
    ddl = text(
        """
        CREATE TABLE IF NOT EXISTS law_chunks (
            id SERIAL PRIMARY KEY,
            law_name_norm TEXT NOT NULL,
            article_number_norm TEXT NOT NULL,
            text TEXT NOT NULL,
            enforcement_date TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_law_chunks_unique
            ON law_chunks (law_name_norm, article_number_norm);
        """
    )
    with engine.begin() as conn:
        conn.execute(ddl)


def ensure_qdrant_schema(qdrant: QdrantClient):
    try:
        qdrant.get_collection(COLLECTION)
    except Exception:
        qdrant.recreate_collection(
            collection_name=COLLECTION,
            vectors_config=qmodels.VectorParams(size=EMBED_DIM, distance=qmodels.Distance.COSINE),
        )


# ────────────────────────────────────────────────────────────────
# DRF Fetch
# ────────────────────────────────────────────────────────────────

def fetch_drf_json(law_name: str) -> dict:
    law_id = LAW_ID_MAP.get(law_name, law_name)
    r = requests.get(
        BASE_URL,
        params={"OC": LAW_OC_ID, "target": "law", "ID": law_id, "type": "JSON"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


# ────────────────────────────────────────────────────────────────
# Upsert to PG & Qdrant
# ────────────────────────────────────────────────────────────────

def upsert_pg(engine: Engine, rows: List[dict]):
    if not rows:
        return
    sql = text(
        """
        INSERT INTO law_chunks (chunk_id, law_name, law_name_norm, article_number_norm, text, enforcement_date)
        VALUES (:chunk_id, :law_name, :law_name_norm, :article_number_norm, :text, :enforcement_date)
        ON CONFLICT (law_name_norm, article_number_norm)
        DO UPDATE SET text = EXCLUDED.text,
                      enforcement_date = EXCLUDED.enforcement_date;
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, rows)



def upsert_qdrant(qdrant: QdrantClient, openai_client: OpenAI, rows: List[dict]):
    if not rows:
        return

    batch_size = 100  # ✅ 한번에 처리할 벡터 수
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        print(f"📤 Qdrant 업로드 중... {i+1} ~ {i+len(batch)} / {len(rows)}")

        texts = [r["text"] for r in batch]
        embeds = openai_client.embeddings.create(model=EMBED_MODEL, input=texts).data
        vectors = [e.embedding for e in embeds]

        points = []
        for r, vec in zip(batch, vectors):
            pid = int(f"{abs(hash(r['law_name_norm'])) % 10_000}{r['article_number_norm']:0>4}")
            payload = {
                "law_name_norm": r["law_name_norm"],
                "article_number_norm": r["article_number_norm"],
                "text": r["text"],
                "enforcement_date": r["enforcement_date"],
            }
            points.append(qmodels.PointStruct(id=pid, vector=vec, payload=payload))

        qdrant.upsert(collection_name=COLLECTION, points=points)
        time.sleep(0.3)  # 과부하 방지

    print("✅ Qdrant 업로드 완료")


# ────────────────────────────────────────────────────────────────
# 메인 루틴
# ────────────────────────────────────────────────────────────────

def update_one_law(law_name: str):
    print(f"\n🔄 [Update] {law_name} — DRF fetch")
    drf_json = fetch_drf_json(law_name)
    rows = extract_article_payloads(law_name, drf_json)
    if not rows:
        print(f"⚠️  {law_name}: 추출된 조문이 없습니다(조문여부='조문' 없음).")
        return 0

    openai_client, engine, qdrant = init_clients()
    ensure_pg_schema(engine)
    ensure_qdrant_schema(qdrant)

    print(f"🗄️  PG upsert: {len(rows)} rows")
    upsert_pg(engine, rows)

    print(f"🧠 Qdrant upsert+embed: {len(rows)} points")
    upsert_qdrant(qdrant, openai_client, rows)

    print(f"✅ 완료: {law_name} — {len(rows)}개 조문 동기화")
    return len(rows)


def update_all():
    total = 0
    for law in LAW_ID_MAP.keys():
        try:
            total += update_one_law(law)
        except Exception as e:
            print(f"❌ {law} 업데이트 실패: {e}")
            continue
        time.sleep(0.8)  # API 과호출 방지
    print(f"\n🎉 전체 완료: {total}개 조문 동기화")


# ────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLeX DRF→PG/Qdrant 최신화 도구")
    parser.add_argument("--all", action="store_true", help="모든 법령 최신화")
    parser.add_argument("--law", type=str, help="특정 법령명만 최신화 (예: 산업안전보건기준에관한규칙)")
    args = parser.parse_args()

    if args.all:
        update_all()
    elif args.law:
        update_one_law(args.law)
    else:
        print("사용법: --all 또는 --law '법령명'")
