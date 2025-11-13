# app/config.py
# ─────────────────────────────
# LLeX.Ai Backend 환경 설정 (v3.0)
# FastAPI + Pydantic Settings 기반
# .env 경로: /llex/llex_backend/.env
# ─────────────────────────────

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# ─────────────────────────────
# 1️⃣ .env 파일 절대경로 지정
# ─────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[1]  # /llex/llex_backend
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
    print(f"✅ [CONFIG] .env loaded from: {ENV_PATH}")
else:
    print(f"⚠️ [CONFIG] .env file not found at {ENV_PATH}")
    load_dotenv()  # fallback: 시스템 환경변수 사용

# ─────────────────────────────
# 2️⃣ Pydantic Settings 정의
# ─────────────────────────────
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")  # 이미 load_dotenv로 로드됨

    # 🔑 필수 환경변수
    OPENAI_API_KEY: str
    LAW_OC_ID: str

    # 🗄️ DB 기본 설정
    DATABASE_URL: str = "postgresql+psycopg2://linkcampus:비밀번호@localhost:5432/law_chatbot"
    DB_NAME: str = "law_chatbot"
    DB_USER: str = "linkcampus"
    DB_PASS: str = "비밀번호"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432

    # ⚙️ Qdrant 설정
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "laws"

    # 🌐 Naver 검색 (옵션)
    NAVER_CLIENT_ID: str | None = None
    NAVER_CLIENT_SECRET: str | None = None


# ─────────────────────────────
# 3️⃣ 인스턴스 생성
# ─────────────────────────────
settings = Settings()

print(f"📁 [CONFIG] Loaded .env path: {ENV_PATH}")
print(f"🔑 [CONFIG] OPENAI_API_KEY exists: {bool(settings.OPENAI_API_KEY)}")
print(f"⚖️ [CONFIG] LAW_OC_ID = {settings.LAW_OC_ID}")
