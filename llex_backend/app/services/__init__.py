# services/__init__.py
"""
services 패키지 초기화
- LLeX Backend 서비스 모듈 로드
- GPT / RAG / NEWS / LAW 등 주요 함수에 대한 lazy import 지원
"""

def __getattr__(name):
    if name in {"generate_answer_async", "hybrid_merge"}:
        from . import gpt_service
        return getattr(gpt_service, name)
    raise AttributeError(f"module {__name__} has no attribute {name}")
