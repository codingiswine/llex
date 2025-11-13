#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
answer_tool.py (LLeX v3.0)
───────────────────────────────
목적:
    - 질문 유형별 전용 프롬프트 분리
    - 법령(RAG)은 "설명 + 조문 원문" 2단 구조
    - 일반/웹/DB는 기존 Perplexity 스타일 유지
"""

import re
import asyncio
import datetime
from typing import Optional, Dict, Any
from openai import OpenAI
from openai import OpenAIError
from app.config import settings


# ─────────────────────────────
# 🔧 초기 설정
# ─────────────────────────────
client = OpenAI(api_key=settings.OPENAI_API_KEY)
LOG_PATH = "logs/answer_history.log"

# ─────────────────────────────
# 🔗 하이퍼링크 변환 유틸
# ─────────────────────────────
def make_law_link(text: str) -> str:
    """'「법령명」 제n조' → 링크 자동 변환"""
    pattern = r'「(.+?)」\s*제(\d+)조'
    def _repl(match: re.Match) -> str:
        law_name, article = match.groups()
        law_clean = law_name.replace(" ", "")
        link = f"https://www.law.go.kr/법령/{law_clean}/제{article}조"
        return f"[{match.group(0)}]({link})"
    return re.sub(pattern, _repl, text)

# ─────────────────────────────
# 🪵 로깅 유틸
# ─────────────────────────────
def log_answer(query: str, context_type: str, answer: str) -> None:
    """질문·답변 로그 저장"""
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] ({context_type})\n")
            f.write(f"Q: {query}\nA: {answer}\n{'-'*60}\n")
    except Exception:
        pass

# ─────────────────────────────
# 🧠 AnswerTool 클래스
# ─────────────────────────────
class AnswerTool:
    """법령/웹/DB/일반 질문 통합 답변 생성기"""

    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.client = client

    # -----------------------------
    # 🧩 일반/웹/DB용 프롬프트
    # -----------------------------
    def _build_general_prompt(self, query: str, context: str, context_type: str) -> str:
        return f"""
        당신은 대한민국의 재난·안전·소방 관련 법령 전문가입니다.
        아래 질문과 참고자료를 기반으로 **법적 근거와 구체적 수치 기준**을 포함해 답변하세요.

        [질문]
        {query}

        [검색결과유형]
        {context_type}

        [참고자료]
        {context or '관련 자료 없음'}

        ---
        ⚙️ 답변 작성 규칙
        1️⃣ **결론 → 수치 기준 → 법적 근거 → 설명** 순서로 작성
        2️⃣ 법령은 「법령명 제n조」 형식으로 인용하고 하이퍼링크로 연결
        3️⃣ 수치(예: 20m, 30m, 100㎡, 6개월 등)는 명확히 표시
        4️⃣ 웹 자료만 있을 경우 "법령 근거 없음" 명시
        5️⃣ 사실 기반으로 작성, 추측성 문장 금지
        6️⃣ 마지막 줄에 "[사용된 도구: {context_type}]" 추가
        """

    # -----------------------------
    # ⚖️ 법령용 프롬프트
    # -----------------------------
    def _build_law_prompt(self, query: str, law_context: str) -> str:
        return f"""
        너는 대한민국 법령 전문 AI 어시스턴트야.
        사용자가 특정 법령(예: '산업안전보건법 제22조')을 물어보면 아래 형식으로 정확히 답변해.

        📘 출력 형식 (Markdown)
        1️⃣ **법령 설명 요약**
        - 해당 조항의 목적, 의미, 실무상 해석을 간결히 설명
        - 필요 시 법적 의무, 적용 범위 언급

        2️⃣ **조문 원문 전체**
        - 반드시 아래 원문을 그대로 보여줌 (문장 수정 금지)
        - 줄바꿈, 번호 등 형식을 유지

        [사용자 질문]
        {query}

        [법령 원문]
        {law_context}
        """

    # -----------------------------
    # 🔮 GPT 호출
    # -----------------------------
    def _generate_answer(self, prompt: str) -> str:
        try:
            res = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1800,
            )
            return make_law_link(res.choices[0].message.content.strip())
        except OpenAIError as e:
            return f"⚠️ 모델 응답 오류가 발생했습니다: {str(e)}"

    # -----------------------------
    # 🧠 통합 실행
    # -----------------------------
    def run(
        self,
        query: str,
        law_context: Optional[str] = None,
        web_summary: Optional[str] = None,
        db_context: Optional[str] = None,
    ) -> str:
        if law_context:
            context_type, prompt = "law_rag", self._build_law_prompt(query, law_context)
        elif web_summary:
            context_type, prompt = "websearch", self._build_general_prompt(query, web_summary, "웹검색 기반")
        elif db_context:
            context_type, prompt = "db_query", self._build_general_prompt(query, db_context, "DB 기반")
        else:
            context_type, prompt = "general", self._build_general_prompt(query, "", "일반")

        answer = self._generate_answer(prompt)
        log_answer(query, context_type, answer)
        return answer

    async def run_async(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.run, *args, **kwargs)

# ─────────────────────────────
# 🌐 전역 인스턴스
# ─────────────────────────────
answer_tool = AnswerTool()
