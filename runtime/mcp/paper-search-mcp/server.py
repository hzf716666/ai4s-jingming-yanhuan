#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paper-search-mcp — 文献检索 MCP 服务器(OpenAlex 直连)

提供工具:
- search_papers(query, max_results=10)         全文/标题检索论文(OpenAlex)
- search_papers_by_title(title, max_results=5)  标题精确检索(找已知文献)
- get_paper_authors(paper_id)                   获取作者列表
按 MCP 协议 stdio JSON-RPC 实现(与 Claude/OpenCode 兼容)。
OpenAlex 接口参考: https://docs.openalex.org/  (免费直连, 已验证稳定)
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
import urllib.error as _urlerr
import os

API = "https://api.openalex.org/works"
HEADERS = {"User-Agent": "jingming-yanhuan-paper-search/1.0 (research assistant)"}
TIMEOUT = 20
import time as _time
_last_request = 0.0


def _get(url: str) -> dict:
    """带速率限制与重试的 GET(OpenAlex 免费 API 约 10 请求/秒, 加延迟防 429)"""
    global _last_request
    for attempt in range(3):
        gap = _time.time() - _last_request
        if gap < 1.4:
            _time.sleep(1.4 - gap)
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                _last_request = _time.time()
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                _time.sleep(3 * (attempt + 1))
                continue
            raise
    raise RuntimeError("OpenAlex rate limited after retries")


def search_papers(query: str, max_results: int = 10) -> dict:
    """按全文/标题检索文献,返回结构化论文列表(标题/作者/年份/期刊/DOI/被引)。"""
    params = {
        "search": query,
        "per_page": max_results,
        "sort": "relevance_score:desc",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    try:
        data = _get(url)
    except Exception as e:
        return {"error": str(e), "works": []}
    works = []
    for w in data.get("results", []):
        authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])][:5]
        primary = w.get("primary_location") or {}
        src = (primary.get("source") or {}).get("display_name", "")
        works.append({
            "id": w.get("id", "").split("/")[-1],
            "title": w.get("title", ""),
            "authors": authors,
            "year": w.get("publication_year"),
            "journal": src,
            "doi": w.get("doi", ""),
            "cited_by": w.get("cited_by_count", 0),
            "type": w.get("type", ""),
        })
    return {"query": query, "count": len(works), "works": works}


def search_papers_by_title(title: str, max_results: int = 5) -> dict:
    """标题模糊检索(找已知文献),返回候选列表。"""
    params = {"filter": f"title.search:{title}", "per_page": max_results}
    url = API + "?" + urllib.parse.urlencode(params)
    try:
        data = _get(url)
    except Exception as e:
        return {"error": str(e), "works": []}
    works = []
    for w in data.get("results", []):
        authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])][:5]
        primary = w.get("primary_location") or {}
        src = (primary.get("source") or {}).get("display_name", "")
        works.append({
            "id": w.get("id", "").split("/")[-1],
            "title": w.get("title", ""),
            "authors": authors,
            "year": w.get("publication_year"),
            "journal": src,
            "doi": w.get("doi", ""),
            "cited_by": w.get("cited_by_count", 0),
        })
    return {"title": title, "count": len(works), "works": works}


def get_paper_authors(paper_id: str) -> dict:
    """获取一篇论文的作者与引用信息。"""
    url = f"https://api.openalex.org/works/{urllib.parse.quote(paper_id)}"
    try:
        w = _get(url)
    except Exception as e:
        return {"error": str(e)}
    authors = [a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])]
    return {
        "id": w.get("id", "").split("/")[-1],
        "title": w.get("title", ""),
        "authors": authors,
        "year": w.get("publication_year"),
        "cited_by": w.get("cited_by_count", 0),
        "concepts": [c.get("display_name", "") for c in w.get("concepts", [])][:5],
    }


# ────────────────────────── MCP 协议 ──────────────────────────
TOOLS = [
    {"name": "search_papers", "description": "检索学术文献(OpenAlex 全文检索),返回标题/作者/年份/期刊/DOI/被引。输入 query 和 max_results。",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "default": 10}},
                     "required": ["query"]}},
    {"name": "search_papers_by_title", "description": "按标题检索已知文献(OpenAlex title.search),用于确认某篇论文是否存在及其元数据。",
     "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "max_results": {"type": "integer", "default": 5}},
                     "required": ["title"]}},
    {"name": "get_paper_authors", "description": "获取一篇论文的作者与引用信息(输入 OpenAlex work id 或简写)。",
     "inputSchema": {"type": "object", "properties": {"paper_id": {"type": "string"}}, "required": ["paper_id"]}},
]

HANDLERS = {
    "search_papers": lambda a: search_papers(a.get("query", ""), a.get("max_results", 10)),
    "search_papers_by_title": lambda a: search_papers_by_title(a.get("title", ""), a.get("max_results", 5)),
    "get_paper_authors": lambda a: get_paper_authors(a.get("paper_id", "")),
}


def log(msg: str):
    sys.stderr.write(f"[paper-search-mcp] {msg}\n")


def main():
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get("id")
        method = msg.get("method", "")
        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                "serverInfo": {"name": "paper-search-mcp", "version": "1.0.0"}}}
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
        elif method == "tools/call":
            name = (msg.get("params") or {}).get("name", "")
            args = (msg.get("params") or {}).get("arguments", {})
            try:
                result = HANDLERS[name](args)
            except Exception as e:
                result = {"error": str(e)}
            resp = {"jsonrpc": "2.0", "id": mid,
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}}
        elif method == "notifications/initialized" or method.startswith("notifications/"):
            continue
        elif method == "shutdown":
            resp = {"jsonrpc": "2.0", "id": mid, "result": {}}
        else:
            resp = {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method {method} not found"}}
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
