# llex_backend/app/services/question_router.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
────────────────────────────────────────────
question_router_v4.5_dualpath.py
────────────────────────────────────────────
✅ 개선사항
1️⃣ "법적 근거", "조문", "기준" 포함 시 자동 LAW_RAG_TOOL 분기
2️⃣ 일반 실무형 질문은 GENERAL_TOOL (Fast Path)
3️⃣ 불필요한 websearch 오탐 제거
"""

import re
import unicodedata
from enum import Enum
from typing import Dict, Any
from openai import OpenAI

from app.config import settings
from app.services.gpt_service import get_user_memory
from core.plan import ToolPlan



# ───────────────────────────────
# ⚙️ 기본 설정
# ───────────────────────────────
client = OpenAI(api_key=settings.OPENAI_API_KEY)


# ───────────────────────────────
# 🧠 QuestionRouter
# ───────────────────────────────
class QuestionRouter:
    def __init__(self):
        # 📚 핵심 키워드
        self.law_keywords = [
            "법적근거", "법령", "법조문", "조문", "근거", "기준", "조항", "법률", "시행령", "시행규칙"
        ]
        self.news_keywords = ["뉴스", "보도", "이슈", "사건", "사고", "기사", "속보"]
        self.blog_keywords = ["블로그", "포스팅", "후기", "리뷰", "경험담"]
        self.db_keywords = ["데이터에서", "기록에서", "db에서", "데이터 확인", "기록 확인"]
        self.general_keywords = [
            "힘들", "피곤", "기분", "고마워", "감사", "사랑", "재밌",
            "화나", "짜증", "슬퍼", "걱정", "무서워", "불안", "외로워"
        ]

        # 🧾 핵심 법령 목록
        raw_laws = [
            "산업안전보건법", "산업안전보건법 시행령", "산업안전보건법 시행규칙",
            "산업안전보건기준에 관한 규칙", "재난 및 안전관리 기본법",
            "재난 및 안전관리 기본법 시행령", "재난 및 안전관리 기본법 시행규칙",
            "중대재해 처벌 등에 관한 법률", "중대재해 처벌 등에 관한 법률 시행령"
        ]
        self.core_laws = [
            unicodedata.normalize("NFC", law.replace(" ", "")) for law in raw_laws
        ]

    # ───────────────────────────────
    # 🧩 Tool 자동 감지
    # ───────────────────────────────
    async def detect_tool(self, user_id: str, text: str) -> ToolPlan:
        """문맥 인식 기반 Tool 자동 선택"""
        user_memory = get_user_memory(user_id)
        past_context = user_memory.load_memory_variables({})
        history = past_context.get("chat_history", "")
        full_query = f"{history}\n{text}".strip().lower()
        normalized_q = unicodedata.normalize("NFC", full_query.replace(" ", ""))

        # ✅ 1️⃣ 법령 관련 키워드 (Deep Path)
        if any(k in normalized_q for k in self.law_keywords):
            print("🏛️ [Router] 법적 근거/조문/기준 감지 → LAW_RAG_TOOL")
            return ToolPlan(tool="law_rag_tool", args={"query": text})

        # ✅ 2️⃣ 핵심 법령명 포함
        for law in self.core_laws:
            if law in normalized_q:
                print(f"🏛️ [Router] 핵심 법령명 감지 → LAW_RAG_TOOL ({law})")
                return ToolPlan(tool="law_rag_tool", args={"query": text})

        # ✅ 3️⃣ 뉴스
        if any(k in normalized_q for k in self.news_keywords):
            print("🗞️ [Router] 뉴스 감지 → NEWS_TOOL")
            return ToolPlan(tool="news_tool", args={"query": text})

        # ✅ 4️⃣ 블로그
        if any(k in normalized_q for k in self.blog_keywords):
            print("📝 [Router] 블로그 감지 → BLOG_TOOL")
            return ToolPlan(tool="blog_tool", args={"query": text})

        # ✅ 5️⃣ DB 감지
        if any(k in normalized_q for k in self.db_keywords):
            print("💾 [Router] 명시적 DB 조회 감지 → DB_QUERY_TOOL_ASYNC")
            return ToolPlan(tool="db_query_tool_async", args={"query": text})

        # ✅ 6️⃣ 감정/일상 대화
        if any(k in normalized_q for k in self.general_keywords):
            print("💬 [Router] 감정형 대화 감지 → GENERAL_TOOL")
            return ToolPlan(tool="general_tool", args={"query": text})

        # ✅ 7️⃣ 기본 실무형 질문 (Fast Path)
        print("💬 [Router] 일반 실무형 질문 → GENERAL_TOOL")
        return ToolPlan(tool="general_tool", args={"query": text})


# 전역 인스턴스
question_router = QuestionRouter()
