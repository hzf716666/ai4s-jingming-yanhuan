---
name: econ-literature
type: executor
description: 经管文献检索:通过 paper-search MCP 工具(OpenAlex)自主检索相关文献,为论文写综述与参考文献
version: "1.0.0"
phase: literature
stage: 5
inputs: ["hypotheses.md / sub_problems.json"]
outputs: ["literature_review.md", "references.json"]
dependencies: ["econ-decompose-question"]
natural_next: ["econ-write-paper"]
gate: true
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["文献", "参考文献", "综述", "literature", "找文献"]
source: custom
max_retries: 2
timeout_sec: 1800
---

# econ-literature — 经管文献检索

## 目标
用 **paper-search MCP 工具(OpenAlex)** 自主检索假设相关的学术文献,产出综述与参考文献清单。**必须通过 MCP 检索,禁止凭记忆编造文献。**

## 输入 / 输出
- 输入:`hypotheses.md`(研究问题/假设)或 `sub_problems.json`
- 输出:`literature_review.md` + `references.json`

## 工具
MCP 服务器 `paper-search`(在 opencode.json 的 mcp 配置中),工具:
- `paper-search_search_papers(query, max_results)` — 全文检索(OpenAlex),返回标题/作者/年份/期刊/DOI/被引
- `paper-search_search_papers_by_title(title)` — 标题检索(找已知文献核验)
- `paper-search_get_paper_authors(paper_id)` — 作者/引用信息

## 步骤
1. 从研究问题/假设提炼 2~4 组检索词(中英文各至少 1 组),每组 `max_results=10`
2. 依次调用 `paper-search_search_papers` 检索
3. 按相关性筛选(标题/期刊/被引/年份),保留高质量文献(被引高或权威期刊优先)
4. 输出 `references.json`(数组: title/authors/year/journal/doi/cited_by/topic_tag)
5. 输出 `literature_review.md`:每篇 2~3 句(该文献如何支撑/对比本假设),并标注"与该假设相关的维度"(理论框架/类似方法/政策证据)

## 质量要求(门禁)
- **每篇文献必须有真实 DOI或 OpenAlex id**(来自 MCP 返回),不得虚构 —— 这是 P1.5 gate 通过的条件
- **econ-write-paper 必须引用本环节的文献**;论文正文每节(引言/制度背景/方法)都要有 `[cite]` 标注到 references.json 的条目
- 若 MCP 检索失败(网络/无结果),记录失败并在论文中明确"文献检索受限",不得用记忆的文献冒充
- 文献量:核心假设 ≥5 篇(推荐 8~12 篇),跨检索词去重

## schema(参考文献条目)
```json
{
  "id": "W123...", "title": "...", "authors": ["..."],
  "year": 2018, "journal": "Research Policy", "doi": "https://doi.org/...",
  "cited_by": 500, "topic_tag": "innovation_policy", "relevance": "理论框架"
}
```
