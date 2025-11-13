#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
websearch_tool.py (v3.1, Async Parallel)
────────────────────────────────────────────
✅ 개선 요약
1️⃣ requests → aiohttp (완전 비동기화)
2️⃣ Google + Naver 뉴스/블로그 병렬 실행 (asyncio.gather)
3️⃣ summarize_web() 호출 시 완전 async-safe
4️⃣ 결과 구조 유지 (summaries + raw_results)
"""

import aiohttp
import asyncio
from typing import List, Dict
try:
    from app.config import settings   # ✅ Docker 실행 시
except ModuleNotFoundError:
    from app.config import settings  # ✅ 로컬 실행 시



# --------------------------
# 🔍 비동기 Naver 검색
# --------------------------
async def naver_search(session, query: str, search_type: str = "news", display: int = 5) -> List[Dict]:
    url = f"https://openapi.naver.com/v1/search/{search_type}.json"
    headers = {
        "X-Naver-Client-Id": settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": "date"}

    try:
        async with session.get(url, headers=headers, params=params, timeout=10) as res:
            if res.status != 200:
                print(f"⚠️ Naver {search_type} HTTP {res.status}")
                return []
            data = await res.json()
            items = data.get("items", [])
            return [
                {
                    "title": i.get("title"),
                    "link": i.get("link"),
                    "snippet": i.get("description"),
                    "source": f"naver_{search_type}",
                }
                for i in items
            ]
    except Exception as e:
        print(f"⚠️ Naver {search_type} 검색 실패: {e}")
        return []


# --------------------------
# 🔍 비동기 Google 검색
# --------------------------
async def google_search(session, query: str, num: int = 5) -> List[Dict]:
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": settings.GOOGLE_SEARCH_API_KEY,
        "cx": settings.GOOGLE_SEARCH_ENGINE_ID,
        "q": f"{query} site:news.naver.com OR site:yna.co.kr OR site:kbs.co.kr OR site:sbs.co.kr OR site:mbc.co.kr OR site:chosun.com OR site:joongang.co.kr OR site:donga.com",
        "num": num,
    }
    try:
        async with session.get(url, params=params, timeout=10) as res:
            if res.status != 200:
                print(f"⚠️ Google HTTP {res.status}")
                return []
            data = await res.json()
            items = data.get("items", [])
            return [
                {
                    "title": i.get("title"),
                    "link": i.get("link"),
                    "snippet": i.get("snippet"),
                    "source": "google_news",
                }
                for i in items
            ]
    except Exception as e:
        print(f"⚠️ Google 검색 실패: {e}")
        return []


# --------------------------
# 🌐 통합 웹검색 (병렬)
# --------------------------
async def get_web_results(query: str) -> List[Dict]:
    """Google + Naver 뉴스/블로그 비동기 병렬"""
    async with aiohttp.ClientSession() as session:
        naver_news, naver_blog, google_news = await asyncio.gather(
            naver_search(session, query, "news"),
            naver_search(session, query, "blog"),
            google_search(session, query),
        )
    all_results = naver_news + naver_blog + google_news

    # 중복 제거
    seen, unique_results = set(), []
    for r in all_results:
        if r["link"] not in seen:
            unique_results.append(r)
            seen.add(r["link"])
    return unique_results


# --------------------------
# 🧠 GPT 요약 (비동기)
# --------------------------
async def summarize_web(query: str, max_results: int = 8) -> Dict:
    """검색 결과를 GPT로 요약 (비동기, 법령 제외)"""
    if len(query) > 500:
        query = query[:500] + " ..."

    results = await get_web_results(query)
    results = results[:max_results]

    if not results:
        return {"summaries": "📰 관련 뉴스/블로그 검색 결과가 없습니다.", "raw_results": []}

    # 뉴스/블로그 구분
    context = "\n\n".join(
        [f"[{i+1}] {r['title']}\n{r['snippet']}\n{r['link']}" for i, r in enumerate(results)]
    )

    messages = [
        {"role": "system", "content": (
            "너는 한국 뉴스·블로그 요약 전문가야.\n"
            "법조문 언급 없이 현실적인 뉴스·블로그 요약만 제시해.\n"
            "[뉴스]\n1. 제목 / 핵심 요약\n[블로그]\n1. 작성자 / 주요 관점 요약"
        )},
        {"role": "user", "content": f"질문: {query}\n\n검색 결과:\n{context}"}
    ]

    try:
        completion = await settings.openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.4,
            max_tokens=700,
        )
        summary = completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ GPT 요약 실패: {e}")
        summary = "요약 중 오류가 발생했습니다."

    return {"summaries": summary, "raw_results": results}


# --------------------------
# 🧪 단독 테스트
# --------------------------
if __name__ == "__main__":
    async def _test():
        q = "소화기 설치 기준"
        result = await summarize_web(q)
        print("✅ 요약 결과:\n", result["summaries"])
        print("\n🧩 원문 링크:")
        for r in result["raw_results"]:
            print(f"- {r['title']} ({r['source']}) → {r['link']}")

    asyncio.run(_test())
