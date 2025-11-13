#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
langgraph_multi_agent.py
────────────────────────────────────────────
✅ LangGraph 기반 Multi-Agent 시스템
- StateGraph를 활용한 6개 Agent 협업
- Conditional Routing으로 질문 의도별 최적 Agent 선택
- 법령/뉴스/블로그/DB/웹검색/일반 대화 전문화
────────────────────────────────────────────
"""
from typing import TypedDict, Annotated, List
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END
import asyncio

from app.services.question_router import question_router
from app.tools import (
    law_rag_tool,
    news_tool,
    blog_tool,
    general_tool,
    db_query_tool_async,
    websearch_tool,
)
from core.logger import llex_logger as logger
from core.plan import ToolPlan


# ─────────────────────────────
# 🧠 Multi-Agent State 정의
# ─────────────────────────────
class AgentState(TypedDict):
    """Multi-Agent 공유 State"""
    question: str  # 사용자 질문
    user_id: str  # 사용자 ID
    selected_tool: str  # 선택된 Tool
    answer_chunks: List[str]  # 답변 조각들
    final_answer: str  # 최종 답변
    metadata: dict  # 메타데이터


# ─────────────────────────────
# 🔀 Router Node (질문 분석 및 Tool 선택)
# ─────────────────────────────
async def router_node(state: AgentState) -> AgentState:
    """질문을 분석해서 최적의 Agent(Tool) 선택"""
    question = state["question"]
    user_id = state["user_id"]

    logger.info(f"🔀 [Router] 질문 분석: {question}")

    # 기존 question_router 활용
    plan: ToolPlan = await question_router.detect_tool(user_id, question)

    logger.info(f"🎯 [Router] 선택된 Tool: {plan.tool}")

    return {
        **state,
        "selected_tool": plan.tool,
        "metadata": {"plan": plan.summary()}
    }


# ─────────────────────────────
# 🏛️ Law RAG Agent Node
# ─────────────────────────────
async def law_agent_node(state: AgentState) -> AgentState:
    """법령 RAG Agent - 법령 검색 및 답변 생성"""
    logger.info("🏛️ [Law Agent] 법령 검색 시작")

    plan = ToolPlan(tool="law_rag_tool", args={"query": state["question"]})
    chunks = []

    async for chunk in law_rag_tool.run(plan):
        if chunk.type == "text":
            chunks.append(chunk.payload)

    final = "".join(chunks)
    logger.info(f"🏛️ [Law Agent] 완료 ({len(final)} chars)")

    return {
        **state,
        "answer_chunks": chunks,
        "final_answer": final
    }


# ─────────────────────────────
# 📰 News Agent Node
# ─────────────────────────────
async def news_agent_node(state: AgentState) -> AgentState:
    """뉴스 Agent - 최신 뉴스 검색"""
    logger.info("📰 [News Agent] 뉴스 검색 시작")

    plan = ToolPlan(tool="news_tool", args={"query": state["question"]})
    chunks = []

    async for chunk in news_tool.run(plan):
        if chunk.type == "text":
            chunks.append(chunk.payload)

    final = "".join(chunks)
    logger.info(f"📰 [News Agent] 완료")

    return {
        **state,
        "answer_chunks": chunks,
        "final_answer": final
    }


# ─────────────────────────────
# 📝 Blog Agent Node
# ─────────────────────────────
async def blog_agent_node(state: AgentState) -> AgentState:
    """블로그 Agent - 블로그 검색"""
    logger.info("📝 [Blog Agent] 블로그 검색 시작")

    plan = ToolPlan(tool="blog_tool", args={"query": state["question"]})
    chunks = []

    async for chunk in blog_tool.run(plan):
        if chunk.type == "text":
            chunks.append(chunk.payload)

    final = "".join(chunks)
    logger.info(f"📝 [Blog Agent] 완료")

    return {
        **state,
        "answer_chunks": chunks,
        "final_answer": final
    }


# ─────────────────────────────
# 💾 Database Agent Node
# ─────────────────────────────
async def db_agent_node(state: AgentState) -> AgentState:
    """DB Agent - 대화 기록 검색"""
    logger.info("💾 [DB Agent] DB 검색 시작")

    plan = ToolPlan(tool="db_query_tool_async", args={"query": state["question"]})
    chunks = []

    async for chunk in db_query_tool_async.run(plan):
        if chunk.type == "text":
            chunks.append(chunk.payload)

    final = "".join(chunks)
    logger.info(f"💾 [DB Agent] 완료")

    return {
        **state,
        "answer_chunks": chunks,
        "final_answer": final
    }


# ─────────────────────────────
# 🌐 Web Search Agent Node
# ─────────────────────────────
async def web_agent_node(state: AgentState) -> AgentState:
    """Web Agent - 웹 검색"""
    logger.info("🌐 [Web Agent] 웹 검색 시작")

    plan = ToolPlan(tool="websearch_tool", args={"query": state["question"]})
    chunks = []

    async for chunk in websearch_tool.run(plan):
        if chunk.type == "text":
            chunks.append(chunk.payload)

    final = "".join(chunks)
    logger.info(f"🌐 [Web Agent] 완료")

    return {
        **state,
        "answer_chunks": chunks,
        "final_answer": final
    }


# ─────────────────────────────
# 💬 General Agent Node
# ─────────────────────────────
async def general_agent_node(state: AgentState) -> AgentState:
    """General Agent - 일반 대화"""
    logger.info("💬 [General Agent] 일반 대화 시작")

    plan = ToolPlan(tool="general_tool", args={"query": state["question"]})
    chunks = []

    async for chunk in general_tool.run(plan):
        if chunk.type == "text":
            chunks.append(chunk.payload)

    final = "".join(chunks)
    logger.info(f"💬 [General Agent] 완료")

    return {
        **state,
        "answer_chunks": chunks,
        "final_answer": final
    }


# ─────────────────────────────
# 🔀 Conditional Router Function
# ─────────────────────────────
def route_to_agent(state: AgentState) -> str:
    """선택된 Tool에 따라 Agent로 라우팅"""
    tool = state["selected_tool"]

    routing_map = {
        "law_rag_tool": "law_agent",
        "news_tool": "news_agent",
        "blog_tool": "blog_agent",
        "db_query_tool_async": "db_agent",
        "websearch_tool": "web_agent",
        "general_tool": "general_agent",
    }

    target = routing_map.get(tool, "general_agent")
    logger.info(f"🔀 [Routing] {tool} → {target}")

    return target


# ─────────────────────────────
# 🏗️ Multi-Agent Graph 생성
# ─────────────────────────────
def create_multi_agent_graph():
    """LangGraph Multi-Agent 시스템 생성"""

    # StateGraph 생성
    workflow = StateGraph(AgentState)

    # 1️⃣ Router Node 추가
    workflow.add_node("router", router_node)

    # 2️⃣ 6개 Agent Node 추가
    workflow.add_node("law_agent", law_agent_node)
    workflow.add_node("news_agent", news_agent_node)
    workflow.add_node("blog_agent", blog_agent_node)
    workflow.add_node("db_agent", db_agent_node)
    workflow.add_node("web_agent", web_agent_node)
    workflow.add_node("general_agent", general_agent_node)

    # 3️⃣ Entry Point 설정 (항상 router부터 시작)
    workflow.set_entry_point("router")

    # 4️⃣ Conditional Routing (router → agents)
    workflow.add_conditional_edges(
        "router",
        route_to_agent,
        {
            "law_agent": "law_agent",
            "news_agent": "news_agent",
            "blog_agent": "blog_agent",
            "db_agent": "db_agent",
            "web_agent": "web_agent",
            "general_agent": "general_agent",
        }
    )

    # 5️⃣ 모든 Agent는 완료 후 종료
    workflow.add_edge("law_agent", END)
    workflow.add_edge("news_agent", END)
    workflow.add_edge("blog_agent", END)
    workflow.add_edge("db_agent", END)
    workflow.add_edge("web_agent", END)
    workflow.add_edge("general_agent", END)

    # Graph Compile
    graph = workflow.compile()

    logger.info("✅ [LangGraph] Multi-Agent Graph 생성 완료")

    return graph


# ─────────────────────────────
# 🎯 Multi-Agent 실행 함수
# ─────────────────────────────
async def run_multi_agent(user_id: str, question: str):
    """Multi-Agent 시스템 실행"""

    # Graph 생성
    graph = create_multi_agent_graph()

    # 초기 State
    initial_state = AgentState(
        question=question,
        user_id=user_id,
        selected_tool="",
        answer_chunks=[],
        final_answer="",
        metadata={}
    )

    # Graph 실행
    logger.info(f"🚀 [Multi-Agent] 시작: {question}")

    final_state = await graph.ainvoke(initial_state)

    logger.info(f"✅ [Multi-Agent] 완료")

    return final_state


# Export
__all__ = ["create_multi_agent_graph", "run_multi_agent", "AgentState"]

print("✅ [init] langgraph_multi_agent.py 로드 완료")
