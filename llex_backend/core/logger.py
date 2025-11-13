import logging
import os
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime

# ─────────────────────────────────────────────
# 📁 1. 날짜별 로그 폴더 자동 생성
# ─────────────────────────────────────────────
# Docker 환경 고려: /app/logs
BASE_LOG_DIR = Path("/app/logs") if os.path.exists("/app") else Path("logs")
BASE_LOG_DIR.mkdir(parents=True, exist_ok=True)

today = datetime.now().strftime("%Y-%m-%d")
LOG_DIR = BASE_LOG_DIR / today
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# 📄 2. 로그 파일 경로 설정
# ─────────────────────────────────────────────
CHAT_LOG = LOG_DIR / "chat_history.log"
SERVER_LOG = LOG_DIR / "server.log"
ERROR_LOG = LOG_DIR / "error.log"

# ─────────────────────────────────────────────
# 🎨 3. 로그 포맷터 (프로덕션 버전)
# ─────────────────────────────────────────────
# 포맷 예시:
# 2025-11-06 15:02:11.123 [INFO] [LLeXLogger] {file.py:42} 🚀 [요청 수신] question=소화기 점검 주기
formatter = logging.Formatter(
    "%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] {%(filename)s:%(lineno)d} %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 간단한 콘솔용 포맷터
console_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

# ─────────────────────────────────────────────
# 🧠 4. LLeX 내부 로거 (GPT / DB / 품질평가 등)
# ─────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

llex_logger = logging.getLogger("LLeXLogger")
llex_logger.setLevel(LOG_LEVEL)
llex_logger.propagate = False  # 중복 로깅 방지

# 파일 핸들러 (상세 로그)
chat_handler = RotatingFileHandler(
    str(CHAT_LOG),
    maxBytes=10_000_000,  # 10MB
    backupCount=10,
    encoding="utf-8"
)
chat_handler.setLevel(logging.DEBUG)
chat_handler.setFormatter(formatter)

# 콘솔 핸들러 (간단한 로그)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(console_formatter)

llex_logger.addHandler(chat_handler)
llex_logger.addHandler(console_handler)

# ─────────────────────────────────────────────
# 🌐 5. FastAPI 서버 요청 로그 (uvicorn.access)
# ─────────────────────────────────────────────
uvicorn_access = logging.getLogger("uvicorn.access")
uvicorn_access.setLevel(logging.INFO)
uvicorn_access.propagate = False

server_handler = RotatingFileHandler(
    str(SERVER_LOG),
    maxBytes=20_000_000,  # 20MB
    backupCount=5,
    encoding="utf-8"
)
server_handler.setLevel(logging.INFO)
server_handler.setFormatter(formatter)

uvicorn_access.addHandler(server_handler)

# ─────────────────────────────────────────────
# ⚠️ 6. Uvicorn 에러 로그 (uvicorn.error)
# ─────────────────────────────────────────────
uvicorn_error = logging.getLogger("uvicorn.error")
uvicorn_error.setLevel(logging.ERROR)
uvicorn_error.propagate = False

error_handler = RotatingFileHandler(
    str(ERROR_LOG),
    maxBytes=20_000_000,  # 20MB
    backupCount=10,
    encoding="utf-8"
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)

# 에러는 콘솔에도 출력
error_console = logging.StreamHandler(sys.stderr)
error_console.setLevel(logging.ERROR)
error_console.setFormatter(console_formatter)

uvicorn_error.addHandler(error_handler)
uvicorn_error.addHandler(error_console)

# ─────────────────────────────────────────────
# 🧩 7. Alias (다른 파일에서 import logger 가능)
# ─────────────────────────────────────────────
logger = llex_logger

# ─────────────────────────────────────────────
# ✅ 8. 초기화 확인 메시지
# ─────────────────────────────────────────────
print(f"✅ [init] LLeX Logger initialized → {LOG_DIR}")
print(f"📄 chat_history.log / server.log / error.log 활성화 완료")
