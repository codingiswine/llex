# LLeX.Ai FastAPI Backend

비동기 FastAPI + OpenAI + Qdrant 기반의 한국 법령 전문 챗봇 백엔드입니다.  
Router → ToolPlan → ToolChunk 스트리밍 파이프라인으로 구성되어, GPT 스타일의 실시간 응답과 법령/뉴스/블로그/DB 조회를 조합할 수 있습니다.

---

## 🚀 Quick start

```bash
cd llex_backend
python -m venv .venv
source .venv/bin/activate        # Windows 는 .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

cp env.example .env              # 환경 변수 템플릿 복사
# .env 파일을 편집해 OpenAI, Qdrant, DB 정보를 입력

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API 문서: http://localhost:8000/docs  
- 헬스체크: http://localhost:8000/health

---

## 🧱 Architecture

```
app/
├── main.py                  # FastAPI 엔트리포인트, SSE 라우터 등록
├── config/                  # 환경설정 및 클라이언트 풀
│   └── settings.py
├── api/                     # FastAPI 라우터 & Pydantic 모델
│   ├── models.py
│   └── routes.py
├── core/                    # 공통 유틸
│   ├── logger.py
│   ├── plan.py              # ToolPlan dataclass
│   └── stream.py            # ToolChunk 정의
├── services/                # 비즈니스 로직
│   ├── gpt_service.py
│   ├── question_router.py
│   └── rag_service.py
└── tools/                   # Tool 실행기 (law/news/blog/web/db/general)
```

핵심 디자인
- `question_router.detect_tool` → ToolPlan 생성  
- `routes.run_tool` → Tool 모듈 실행, ToolChunk 스트리밍  
- `save_chat_history` → Async PostgreSQL 기록 (score 포함)

---

## 🔐 Environment variables

`.env` 예시 (`env.example` 참고):

```env
OPENAI_API_KEY=sk-...
OPENAI_PROJECT_ID=llex

DB_NAME=law_chatbot
DB_USER=linkcampus
DB_PASS=changeme
DB_HOST=localhost
DB_PORT=5432

QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME=laws

LAW_OC_ID=your_law_go_drf_key
GOOGLE_SEARCH_API_KEY=your_cse_key
GOOGLE_SEARCH_ENGINE_ID=your_cx_id
NAVER_CLIENT_ID=optional
NAVER_CLIENT_SECRET=optional
```

기본 설정은 `app/config/settings.py` 에서 관리되며, AsyncOpenAI / AsyncQdrant / SQLAlchemy AsyncEngine 인스턴스를 재사용합니다.

---

## 📡 API surface

| Method | Path         | Description                     |
| ------ | ------------ | -------------------------------- |
| POST   | `/api/ask`   | SSE 스트리밍으로 답변 반환       |
| GET    | `/health`    | 서버 상태 확인 (`{"status":"ok"}`) |

`POST /api/ask` 요청 본문:
```json
{
  "question": "소화기 점검 주기는 어떻게 되나요?",
  "search_mode": "general"
}
```

응답은 `text/event-stream` 으로 전송되며, 각 라인은 JSON 직렬화된 `ToolChunk` 입니다:
```json
{"event":"text","payload":"첫 문장..."}
{"event":"status","payload":"🧠 GPT 요약 중..."}
{"event":"source","payload":{"title":"산업안전보건법 ..."}}
```

---

## 🧰 Tool overview

| Tool 이름             | 역할                               | 비동기 여부 |
| --------------------- | ----------------------------------- | ----------- |
| `law_rag_tool`        | Postgres → Qdrant → Web fallback    | ✅ |
| `news_tool`           | Google/Naver 뉴스 요약              | ✅ (`asyncio.to_thread`) |
| `blog_tool`           | 블로그 후기 검색/요약              | ✅ (`asyncio.to_thread`) |
| `websearch_tool`      | Google CSE + Naver API (aiohttp)    | ✅ |
| `db_query_tool_async` | chat_history / law_test 직접 조회   | ✅ |
| `general_tool`        | 일반 GPT 대화                       | ✅ |

각 Tool 은 `ToolChunk`를 `yield` 하며 `routes.run_tool`이 스트리밍 응답으로 변환합니다.

---

## 🧪 Development tips

- **가상환경**: Python 3.11+ 권장  
- **테스트**: 임시로 `curl` 또는 `loadtest.js` (k6 스타일) 활용  
- **로그 위치**: `logs/<YYYY-MM-DD>/` 에 chat/server/error 로그가 생성됩니다.  
- **핫리로드**: `uvicorn app.main:app --reload` 사용  
- **동시성**: SQLAlchemy 풀 (`pool_size=10, max_overflow=20`), SSE 비동기 루프, Tool 별 async 호출로 10명 동시 접속을 목표로 설계되었습니다.

---

## 🧯 Troubleshooting

| 증상 | 확인 사항 |
| ---- | -------- |
| OpenAI 관련 에러 | `OPENAI_API_KEY`, 프로젝트 권한, 네트워크 방화벽 |
| Qdrant 검색 실패 | `QDRANT_HOST`, 포트, 컬렉션 이름, 임베딩 차원 |
| DB 연결 오류 | PostgreSQL 접속 정보 및 권한, `asyncpg` 설치 여부 |
| SSE 끊김 | 브라우저 콘솔, FastAPI 로그, 프록시 서버에서 헤더가 잘 전달되는지 확인 |

---

## 📦 배포

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

필요 시 `ENV` 지표를 Docker Secret / Vault 등으로 주입하고, Reverse proxy (Nginx, Caddy) 에서 `/api/ask` 경로는 SSE 헤더(`Cache-Control: no-cache`, `Connection: keep-alive`)를 유지하도록 설정하세요.

### 헬스체크

```bash
curl http://localhost:8000/health
```

### 성능 메트릭

- 임베딩 생성 시간
- Qdrant 검색 시간
- GPT 응답 시간
- 전체 응답 시간

## 🔧 문제 해결

### 일반적인 문제

1. **Qdrant 연결 실패**
   - Qdrant 서버가 실행 중인지 확인
   - `QDRANT_HOST`, `QDRANT_PORT` 설정 확인

2. **OpenAI API 오류**
   - `OPENAI_API_KEY` 유효성 확인
   - API 사용량 한도 확인

3. **임베딩 캐시 오류**
   - `.cache` 폴더 권한 확인
   - SQLite 데이터베이스 파일 권한 확인

### 로그 확인

```bash
# 실시간 로그 확인
tail -f logs/app.log

# 특정 에러 로그 필터링
grep "ERROR" logs/app.log
```

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.
