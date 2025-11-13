#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
news_tool_v5.4_aiohttp (LLeX GPT-5 구조 완전 비동기판)
────────────────────────────────────────────
✅ 주요 개선
1️⃣ requests → aiohttp 완전 비동기화
2️⃣ Google/Naver 뉴스 동시 요청
3️⃣ ToolChunk 기반 스트리밍 구조 유지
────────────────────────────────────────────
"""

import os, re, html, datetime, asyncio, aiohttp
from typing import List, Dict, AsyncGenerator
from urllib.parse import urlparse
from app.config import settings
from core.stream import ToolChunk


NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36"
)


# ─────────────────────────────
# 🔧 공통 유틸
# ─────────────────────────────
def strip_tags(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()

def brand_from_link(link: str) -> str:
    try:
        host = urlparse(link).netloc.lower()
        if "naver" in host: return "NAVER"
        if "daum" in host: return "DAUM"
        if "google" in host: return "GOOGLE"
        if "yonhap" in host: return "YONHAP"
        parts = [p for p in host.split(".") if p not in {"www", "m", "co", "kr", "com", "net"}]
        return parts[-1].upper() if parts else "출처 미상"
    except:
        return "출처 미상"

def unique_preserve_order(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen, result = set(), []
    for it in items:
        title = it.get("title")
        if title and title not in seen:
            seen.add(title)
            result.append(it)
    return result


# ─────────────────────────────
# 🌐 Naver 뉴스 (aiohttp)
# ─────────────────────────────
async def get_naver_news(session: aiohttp.ClientSession, query: str, max_results: int = 5) -> List[Dict[str, str]]:
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID or "",
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET or "",
        "User-Agent": DEFAULT_UA,
    }
    params = {"query": query, "display": max_results, "sort": "sim"}

    async with session.get(url, headers=headers, params=params, timeout=8) as res:
        data = await res.json()
        items = data.get("items", [])
        results = []
        for it in items:
            title = strip_tags(it.get("title", ""))
            desc = strip_tags(it.get("description", ""))
            link = it.get("originallink") or it.get("link", "")
            pub = it.get("pubDate", "")
            try:
                pub = datetime.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z").strftime("%Y-%m-%d")
            except Exception:
                pub = "정보 없음"
            results.append({
                "title": title,
                "description": desc,
                "link": link,
                "source": brand_from_link(link),
                "pubDate": pub,
            })
        return results


# ─────────────────────────────
# 🌍 Google 뉴스 (aiohttp)
# ─────────────────────────────
async def get_google_news(session: aiohttp.ClientSession, query: str, max_results: int = 5) -> List[Dict[str, str]]:
    params = {"q": query, "tbm": "nws", "hl": "ko", "gl": "kr"}
    headers = {"User-Agent": DEFAULT_UA}

    async with session.get("https://www.google.com/search", params=params, headers=headers, timeout=8) as res:
        res_text = await res.text()

    blocks = re.findall(
        r'<a href="/url\?q=(.*?)&amp.*?<div[^>]*class="BNeawe vvjwJb[^"]*">(.*?)</div>.*?<div[^>]*class="BNeawe s3v9rd AP7Wnd">(.*?)</div>',
        res_text, re.S,
    )
    articles = []
    for link, title, source in blocks[:max_results]:
        clean_link = strip_tags(link)
        articles.append({
            "title": strip_tags(title),
            "link": clean_link,
            "source": brand_from_link(clean_link),
            "pubDate": "정보 없음",
            "description": "",
        })
    return articles


# ─────────────────────────────
# 🧠 GPT 프롬프트
# ─────────────────────────────
def build_prompt(query: str, items: List[Dict[str, str]]) -> str:
    header = (
        f"'{query}' 관련 최신 뉴스를 3건 요약하세요.\n"
        "출력 형식:\n"
        "1️⃣ 제목  \n"
        "출처 : 매체명(링크) · 날짜  \n"
        "요약 (2~3줄, 자연스러운 문체)\n"
        "---\n\n"
        "주의:\n"
        "- 제목은 굵게(**제목**)\n"
        "- Markdown 링크는 (링크) 형식으로 유지\n"
        "- 각 뉴스는 3줄 이하\n"
    )
    context = "\n".join([
        f"- 제목: {i['title']}\n  매체: {i['source']}\n  날짜: {i.get('pubDate','')}\n  링크: {i['link']}\n  내용: {i.get('description','')}"
        for i in items
    ])
    return header + "\n[기사 데이터]\n" + context


# ─────────────────────────────
# 🚀 메인 실행 (비동기 Stream)
# ─────────────────────────────
async def run(plan) -> AsyncGenerator[ToolChunk, None]:
    query = plan.args.get("query", "")
    yield ToolChunk(type="status", payload=f"🗞️ '{query}' 관련 뉴스 검색 중...")

    async with aiohttp.ClientSession() as session:
        google_task = asyncio.create_task(get_google_news(session, query))
        naver_task = asyncio.create_task(get_naver_news(session, query))
        google, naver = await asyncio.gather(google_task, naver_task)

    items = unique_preserve_order(google + naver)
    if not items:
        yield ToolChunk(type="error", payload="❌ 관련 뉴스 기사를 찾지 못했습니다.")
        return

    yield ToolChunk(type="status", payload=f"🧠 GPT가 {len(items)}건 요약 중...")

    prompt = build_prompt(query, items)
    stream = await settings.openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        stream=True,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield ToolChunk(type="text", payload=delta)

    yield ToolChunk(
        type="source",
        payload=[{"title": i["title"], "link": i["link"], "source": i["source"]} for i in items[:5]],
    )
    yield ToolChunk(type="status", payload="✅ 뉴스 요약 완료")
