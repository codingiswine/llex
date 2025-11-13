#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
routes_async_v6.6_dualpath.py
────────────────────────────────────────────
✅ 개선 사항
1️⃣ Fast Path → Deep Path 구조 대응
2️⃣ law_rag_tool 실행 후 Web fallback 자동 연결
3️⃣ DB 저장 시 tool 명 오염 방지
4️⃣ MLOps 메트릭 수집 통합
────────────────────────────────────────────
"""
import re, json, asyncio, time
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from typing import AsyncGenerator, List
from sqlalchemy import text

# ✅ Docker 기준으로 경로 수정
from app.config import settings
from app.api.models import QueryRequest
from app.services.question_router import question_router
from app.services.langgraph_multi_agent import run_multi_agent
from app.services.metrics_service import metrics_collector, get_prometheus_metrics, CONTENT_TYPE_LATEST
from core.logger import llex_logger as logger
from core.stream import ToolChunk

# ✅ 비동기 엔진
async_engine = settings.async_engine

# ✅ Tool 모듈 로드
from app.tools import (
    law_rag_tool,
    news_tool,
    blog_tool,
    general_tool,
    db_query_tool_async,
    websearch_tool,
)

router = APIRouter()

# ─────────────────────────────
# ⚙️ 품질 평가
# ─────────────────────────────
def evaluate_answer_quality(answer: str) -> dict:
    law_refs = re.findall(r"「.*?」", answer)
    article_refs = re.findall(r"제\d+조", answer)
    score = min(len(law_refs) * 10 + len(article_refs) * 5 + 35, 100)
    return {"score": score, "law_ref_count": len(law_refs)}


# ─────────────────────────────
# 💾 비동기 DB 저장
# ─────────────────────────────
async def save_chat_history(user_id: str, question: str, answer: str, tool: str):
    eval_ = evaluate_answer_quality(answer)
    session_id = "llex_session"
    turn_index = int(time.time())
    metadata_json = json.dumps({"tool": tool})

    insert = text("""
        INSERT INTO chat_history (session_id, turn_index, role, content, user_id, metadata, score)
        VALUES (:session_id, :turn_index, :role, :content, :user_id, :metadata, :score)
    """)

    try:
        async with async_engine.begin() as conn:
            await conn.execute(insert, {
                "session_id": session_id, "turn_index": turn_index,
                "role": "user", "content": question, "user_id": user_id,
                "metadata": metadata_json, "score": eval_["score"]
            })
            await conn.execute(insert, {
                "session_id": session_id, "turn_index": turn_index + 1,
                "role": "assistant", "content": answer, "user_id": user_id,
                "metadata": metadata_json, "score": eval_["score"]
            })
        logger.info(f"💾 [DB 저장 완료] {tool} ({eval_['score']}점)")
    except Exception as e:
        logger.error(f"⚠️ [DB 저장 실패] {e}")
        raise


# ─────────────────────────────
# 🧠 Tool 실행기 (비동기)
# ─────────────────────────────
async def run_tool(plan) -> AsyncGenerator[ToolChunk, None]:
    tool = plan.tool
    args = plan.args
    print(f"🔧 [Tool 실행] {tool} ← {args}")

    tool_map = {
        "law_rag_tool": law_rag_tool,
        "news_tool": news_tool,
        "blog_tool": blog_tool,
        "websearch_tool": websearch_tool,
        "db_query_tool_async": db_query_tool_async,
        "general_tool": general_tool,
    }

    # ✅ Tool 존재 여부 확인
    if tool not in tool_map:
        yield ToolChunk(type="error", payload=f"Unknown tool: {tool}")
        return

    # ✅ 1차 Tool 실행
    collected_chunks = []
    try:
        async for chunk in tool_map[tool].run(plan):
            collected_chunks.append(chunk)
            yield chunk
    
    except Exception as e:
        yield ToolChunk(type="error", payload=f"❌ Tool 실행 중 오류: {str(e)}")
        logger.error(f"[Tool 오류] {tool}: {e}")
        return

    # ✅ 2차 Web fallback (법령 미발견 시)
    # text 내용이 “조문 없음”, “법령 없음” 등일 때 자동 보완
    full_text = "".join(c.payload for c in collected_chunks if c.type == "text")
    if tool == "law_rag_tool" and (
        ("조문" in full_text and "없" in full_text) 
        or ("법령" in full_text and "없" in full_text)
    ):
        print("🔁 [Fallback] law_rag_tool → websearch_tool")
        yield ToolChunk(type="status", payload="⚠️ 법령 조문 없음 → Web 보완 검색 중...")
        plan.tool = "websearch_tool"
        async for chunk in websearch_tool.run(plan):
            yield chunk


# ─────────────────────────────
# 🚀 FastAPI 엔드포인트 (완전 async)
# ─────────────────────────────
# 🚀 FastAPI 엔드포인트 (완전 async)
@router.post("/ask")
async def ask_llex(request: QueryRequest):
    """질문 → Router → ToolPlan → Tool 실행 → Stream"""
    user_id = "linkcampus"
    print(f"🚀 [요청 수신] {request.question}")

    try:
        # ① ToolPlan 생성
        plan = await question_router.detect_tool(user_id, request.question)
        full_answer_parts: List[str] = []

        # ✅ 내부 event_stream 정의
        async def event_stream():
            print(f"🌊 [스트리밍 시작] {plan.summary()}")
            counter = 0

            async for chunk in run_tool(plan):
                # ✅ 항상 JSON 포맷으로 전송
                yield f"data: {json.dumps({'event': chunk.type, 'payload': chunk.payload})}\n\n"

                if chunk.type == "text":
                    full_answer_parts.append(chunk.payload)
                    counter += 1
                    # 🔹 CPU 부하 완화
                    if counter % 20 == 0:
                        await asyncio.sleep(0)

            # ✅ DB 저장
            final_tool_name = plan.tool.split("_")[0]
            full_answer = "".join(full_answer_parts)
            try:
                await save_chat_history(user_id, request.question, full_answer, final_tool_name)
                yield f"data: {ToolChunk(type='status', payload='✅ 대화 저장 완료').to_json()}\n\n"
            except Exception as e:
                logger.error(f"⚠️ [DB 저장 중 오류] {e}")
                yield f"data: {ToolChunk(type='warning', payload='⚠️ 대화 저장 실패 (DB 연결 문제)').to_json()}\n\n"

        # ✅ 스트리밍 반환
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"❌ [백엔드 에러] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────
# 📜 대화 기록 조회 API
# ─────────────────────────────

@router.get("/history")
async def get_chat_history(
    user_id: str = "linkcampus",
    limit: int = 50
):
    """대화 기록 조회"""
    sql = text("""
        SELECT
            id,
            role,
            content,
            metadata,
            score,
            created_at
        FROM chat_history
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit
    """)

    try:
        async with async_engine.begin() as conn:
            result = await conn.execute(sql, {"user_id": user_id, "limit": limit})
            rows = result.fetchall()

            history = []
            for row in rows:
                history.append({
                    "id": row.id,
                    "role": row.role,
                    "content": row.content,
                    "tool": row.metadata.get("tool") if row.metadata else None,
                    "score": row.score,
                    "created_at": row.created_at.isoformat()
                })

            return {"total": len(history), "history": history}
    except Exception as e:
        logger.error(f"⚠️ [History 조회 실패] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/stats")
async def get_history_stats():
    """대화 통계"""
    sql = text("""
        SELECT
            metadata->>'tool' as tool,
            COUNT(*) as count,
            AVG(score) as avg_score,
            MAX(created_at) as last_used
        FROM chat_history
        WHERE role = 'assistant'
        GROUP BY metadata->>'tool'
        ORDER BY count DESC
    """)

    try:
        async with async_engine.begin() as conn:
            result = await conn.execute(sql)
            rows = result.fetchall()

            stats = []
            for row in rows:
                stats.append({
                    "tool": row.tool,
                    "count": row.count,
                    "avg_score": round(row.avg_score, 1) if row.avg_score else 0,
                    "last_used": row.last_used.isoformat() if row.last_used else None
                })

            return {"stats": stats}
    except Exception as e:
        logger.error(f"⚠️ [Stats 조회 실패] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """대화 기록 대시보드 (HTML)"""
    return """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LLeX 대화 기록 대시보드</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <!-- Header -->
        <div class="bg-white rounded-lg shadow-md p-6 mb-8">
            <h1 class="text-4xl font-bold text-gray-800 mb-2">💬 LLeX 대화 기록</h1>
            <p class="text-gray-600">실시간 대화 분석 및 품질 모니터링</p>
        </div>

        <!-- Stats Cards -->
        <div class="mb-8">
            <h2 class="text-2xl font-bold text-gray-800 mb-4">📊 Tool 사용 통계</h2>
            <div id="stats" class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
                <div class="bg-white p-6 rounded-lg shadow-md animate-pulse">
                    <div class="h-4 bg-gray-200 rounded w-3/4 mb-4"></div>
                    <div class="h-8 bg-gray-200 rounded w-1/2"></div>
                </div>
            </div>
        </div>

        <!-- Chat History -->
        <div>
            <h2 class="text-2xl font-bold text-gray-800 mb-4">💭 최근 대화</h2>
            <div id="history" class="space-y-4">
                <div class="bg-white p-6 rounded-lg shadow-md animate-pulse">
                    <div class="h-4 bg-gray-200 rounded w-full mb-2"></div>
                    <div class="h-4 bg-gray-200 rounded w-5/6"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Tool 색상 매핑
        const toolColors = {
            'law': 'bg-blue-100 text-blue-800',
            'general': 'bg-green-100 text-green-800',
            'news': 'bg-purple-100 text-purple-800',
            'blog': 'bg-yellow-100 text-yellow-800',
            'websearch': 'bg-red-100 text-red-800',
            'db': 'bg-gray-100 text-gray-800'
        };

        // 통계 로드
        fetch('/api/history/stats')
            .then(r => r.json())
            .then(data => {
                document.getElementById('stats').innerHTML = data.stats.map(s => {
                    const colorClass = toolColors[s.tool] || 'bg-gray-100 text-gray-800';
                    const lastUsed = s.last_used ? new Date(s.last_used).toLocaleString('ko-KR') : 'N/A';
                    return `
                        <div class="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition-shadow">
                            <div class="flex items-center justify-between mb-4">
                                <span class="inline-block px-3 py-1 rounded-full text-sm font-semibold ${colorClass}">
                                    ${s.tool || 'unknown'}
                                </span>
                            </div>
                            <div class="text-3xl font-bold text-gray-800 mb-2">${s.count}회</div>
                            <div class="text-sm text-gray-600 mb-1">평균 품질: ${s.avg_score}점</div>
                            <div class="text-xs text-gray-500">마지막: ${lastUsed}</div>
                        </div>
                    `;
                }).join('');
            })
            .catch(err => {
                document.getElementById('stats').innerHTML = `
                    <div class="col-span-full bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
                        ⚠️ 통계 로드 실패: ${err.message}
                    </div>
                `;
            });

        // 대화 기록 로드
        fetch('/api/history?limit=50')
            .then(r => r.json())
            .then(data => {
                if (data.history.length === 0) {
                    document.getElementById('history').innerHTML = `
                        <div class="bg-white p-8 rounded-lg shadow-md text-center text-gray-500">
                            아직 대화 기록이 없습니다.
                        </div>
                    `;
                    return;
                }

                document.getElementById('history').innerHTML = data.history.map(h => {
                    const isUser = h.role === 'user';
                    const bgColor = isUser ? 'bg-blue-50 border-blue-200' : 'bg-white';
                    const icon = isUser ? '👤' : '🤖';
                    const roleText = isUser ? '사용자' : 'AI 어시스턴트';
                    const toolColorClass = toolColors[h.tool] || 'bg-gray-100 text-gray-800';
                    const timestamp = new Date(h.created_at).toLocaleString('ko-KR');

                    // 내용 미리보기 (200자 제한)
                    const preview = h.content.length > 200
                        ? h.content.substring(0, 200) + '...'
                        : h.content;

                    return `
                        <div class="bg-white rounded-lg shadow-md overflow-hidden border-l-4 ${isUser ? 'border-blue-500' : 'border-green-500'}">
                            <div class="p-6">
                                <div class="flex items-center justify-between mb-3">
                                    <div class="flex items-center space-x-2">
                                        <span class="text-2xl">${icon}</span>
                                        <span class="font-bold text-gray-800">${roleText}</span>
                                    </div>
                                    <div class="flex items-center space-x-2 text-sm text-gray-500">
                                        ${h.tool ? `<span class="px-2 py-1 rounded-full ${toolColorClass} font-semibold">${h.tool}</span>` : ''}
                                        ${h.score ? `<span class="px-2 py-1 rounded-full bg-gray-100 text-gray-700">📊 ${h.score}점</span>` : ''}
                                        <span>🕐 ${timestamp}</span>
                                    </div>
                                </div>
                                <div class="text-gray-700 whitespace-pre-wrap leading-relaxed">${preview}</div>
                            </div>
                        </div>
                    `;
                }).join('');
            })
            .catch(err => {
                document.getElementById('history').innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
                        ⚠️ 대화 기록 로드 실패: ${err.message}
                    </div>
                `;
            });
    </script>
</body>
</html>
    """


# ─────────────────────────────
# 🤖 LangGraph Multi-Agent 엔드포인트
# ─────────────────────────────
@router.post("/ask-multi")
async def ask_llex_multi_agent(request: QueryRequest):
    """LangGraph Multi-Agent 시스템을 활용한 질문 응답 (메트릭 수집 포함)"""
    user_id = "linkcampus"
    logger.info(f"🤖 [Multi-Agent] 요청 수신: {request.question}")

    # 메트릭 추적 시작
    start_time = time.time()
    selected_agent = "unknown"

    try:
        full_answer_parts: List[str] = []

        async def event_stream():
            nonlocal selected_agent
            """Multi-Agent 실행 및 스트리밍"""

            # Multi-Agent 실행
            final_state = await run_multi_agent(user_id, request.question)

            # 답변을 chunk로 나눠서 스트리밍
            answer = final_state.get("final_answer", "")

            # Agent 정보 전송
            selected_tool = final_state.get("selected_tool", "unknown")
            selected_agent = selected_tool

            # Agent 사용 메트릭 기록
            metrics_collector.record_agent_usage(selected_agent)

            status_msg = f"🤖 [{selected_tool}] 처리 완료"
            yield f"data: {json.dumps({'event': 'status', 'payload': status_msg})}\n\n"

            # 답변을 chunk로 나눠서 전송 (20자씩)
            chunk_size = 20
            for i in range(0, len(answer), chunk_size):
                chunk_text = answer[i:i+chunk_size]
                full_answer_parts.append(chunk_text)
                yield f"data: {json.dumps({'event': 'text', 'payload': chunk_text})}\n\n"
                await asyncio.sleep(0.01)  # 자연스러운 스트리밍

            # DB 저장
            full_answer = "".join(full_answer_parts)
            tool_name = final_state.get("selected_tool", "").split("_")[0]

            try:
                await save_chat_history(user_id, request.question, full_answer, tool_name)
                yield f"data: {json.dumps({'event': 'status', 'payload': '✅ Multi-Agent 처리 완료'})}\n\n"
            except Exception as e:
                logger.error(f"⚠️ [DB 저장 실패] {e}")
                yield f"data: {json.dumps({'event': 'warning', 'payload': '⚠️ DB 저장 실패'})}\n\n"

        response = StreamingResponse(event_stream(), media_type="text/event-stream")

        # 응답 완료 후 메트릭 기록
        duration = time.time() - start_time
        metrics_collector.record_response_time("/ask-multi", selected_agent, duration)
        metrics_collector.record_request("/ask-multi", selected_agent, "success")

        return response

    except Exception as e:
        # 에러 메트릭 기록
        duration = time.time() - start_time
        metrics_collector.record_response_time("/ask-multi", selected_agent, duration)
        metrics_collector.record_error("/ask-multi", type(e).__name__)
        metrics_collector.record_request("/ask-multi", selected_agent, "error")

        logger.error(f"❌ [Multi-Agent 에러] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────
# 📊 MLOps 모니터링 엔드포인트
# ─────────────────────────────
@router.get("/metrics")
async def get_metrics():
    """Prometheus 메트릭 엔드포인트"""
    return Response(content=get_prometheus_metrics(), media_type=CONTENT_TYPE_LATEST)


@router.get("/metrics/summary")
async def get_metrics_summary():
    """메트릭 요약 정보 (사람이 읽을 수 있는 형태)"""
    summary = metrics_collector.get_summary()

    return {
        "status": "ok",
        "service": "LLeX Multi-Agent System",
        "metrics": summary,
        "endpoints": {
            "prometheus_metrics": "/api/metrics",
            "summary": "/api/metrics/summary"
        }
    }


@router.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {
        "status": "healthy",
        "service": "LLeX Backend",
        "timestamp": time.time()
    }


