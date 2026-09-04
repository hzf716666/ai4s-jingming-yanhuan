#!/usr/bin/env python3
"""econ 体系技能路由器：路由表 + 技能分值（照抄 ui-ux-pro-max 的机制）。

机制（与 ui-ux-pro-max/src/ui-ux-pro-max/scripts/core.py 一致，内容改为经管技能路由）：
1. 关键词加权打分：每个命中关键词 + max(1, 词数)（多词词组长于/更具体 → 分更高）；
2. 固定优先级拉平：同分按 ROUTE_TABLE 的 tiebreak 顺序（P0 评审 → P1 拆解 … → 通用工具）；
3. BM25 二次排序：对全部技能 description 建 BM25 索引，score(query) 归一化后
   与关键词分融合（KEYWORD_W=0.6 / BM25_W=0.4）；
4. 领域路由：先 detect_domain（经管实证任务默认走 econ 链），命中"通用通道"词的
   任务（训练/推理/远程作业等）路由到云端计算 / econ-run 的模型通道。

用法：
    python skill_router.py "<用户任务>" [--top 5] [--json]
输出：带分值排序的技能列表（stdout 单行 JSON 便于编排层解析）。
"""
import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

KEYWORD_W = 0.6
BM25_W = 0.4
K1 = 1.5
B = 0.75
TABLE_PATH = Path(__file__).parent.parent / "ROUTE_TABLE.json"


class BM25:
    """BM25 检索器（同 ui-ux-pro-max core.py 的 BM25）。"""

    def __init__(self):
        self.k1, self.b = K1, B
        self.corpus, self.N = [], 0
        self.doc_lengths, self.avgdl = [], 0.0
        self._term_freqs, self.idf = [], {}
        self.doc_freqs = defaultdict(int)

    def fit(self, documents):
        self.corpus = [self.tokenize(d) for d in documents]
        self.N = len(self.corpus)
        if self.N == 0:
            return
        self.doc_lengths = [len(d) for d in self.corpus]
        self.avgdl = sum(self.doc_lengths) / self.N
        self._term_freqs = []
        for doc in self.corpus:
            tf = defaultdict(int)
            for word in doc:
                tf[word] += 1
            self._term_freqs.append(tf)
            for word in tf:
                self.doc_freqs[word] += 1
        for word, freq in self.doc_freqs.items():
            self.idf[word] = math.log((self.N - freq + 0.5) / (freq + 0.5) + 1)

    @staticmethod
    def tokenize(text):
        # 中英文混合切词：英文按词，中文按 2~4 字滑窗（关键词匹配用全词即可，这里供 BM25 检索）
        text = text.lower()
        words = re.findall(r"[a-z0-9_]+", text)
        han = re.sub(r"[^\u4e00-\u9fff]", " ", text)
        for seg in han.split():
            for n in (2, 3, 4):
                if len(seg) >= n:
                    words += [seg[i:i + n] for i in range(len(seg) - n + 1)]
        return words

    def score(self, query):
        """对全部文档打分，返回 [(idx, score)] 降序。"""
        query_tokens = self.tokenize(query)
        scores = []
        for idx in range(self.N):
            score = 0.0
            doc_len = self.doc_lengths[idx]
            term_freqs = self._term_freqs[idx]
            for token in query_tokens:
                if token in self.idf:
                    tf = term_freqs.get(token, 0)
                    idf = self.idf[token]
                    numerator = tf * (self.k1 + 1)
                    denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                    score += idf * numerator / denominator
            scores.append((idx, score))
        return sorted(scores, key=lambda x: x[1], reverse=True)


def detect_domain(query):
    """经管实证任务默认走 econ 链；命中通用通道词的任务走通用技能（受控加权）。"""
    econ_kw = ["假设", "评审", "拆解", "子问题", "文献", "综述", "回归", "面板", "数据盘点",
               "实证", "论文", "统计", "因果", "识别", "变量", "检验", "论文写作"]
    generic_kw = ["训练", "推理", "模型", "checkpoint", "分布式", "并行", "gpu", "超算",
                  "scnet", "作业提交", "复现", "数据集构建", "fastq", "分子", "自动机"]
    score = lambda kws: sum(1 for k in kws if k in query.lower())
    econ, gen = score(econ_kw), score(generic_kw)
    if gen > econ:
        return "generic"
    return "econ"


def load_table():
    data = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    return data["skills"], data.get("tiebreak", [])


def route(query, top=5):
    """返回 [{name, cn, dir, type, stage, score, matched}] 按分值降序。"""
    skills, tiebreak = load_table()
    # 领域路由：通用通道任务把 econ 全链压后（分值乘 0.15），避免误路由
    domain = detect_domain(query)
    q = query.lower()

    # 1) 关键词加权分
    kw_scores = []
    for sk in skills:
        total = 0.0
        matched = []
        for kw in sk.get("keywords", []):
            if kw.lower() in q:
                total += max(1, len(kw.split()))
                matched.append(kw)
        if domain == "generic" and sk.get("domain", "econ") == "econ":
            total *= 0.15
        kw_scores.append((total, matched))

    # 2) BM25 分
    docs = [sk["description"] for sk in skills]
    bm25 = BM25()
    bm25.fit(docs)
    raw = {idx: sc for idx, sc in bm25.score(query)}
    maxr = max(raw.values()) if raw and max(raw.values()) > 0 else 1.0
    maxk = max((s for s, _ in kw_scores), default=0.0)

    # 3) 融合 + 拉平
    def norm(v, m):
        return v / m if m > 0 else 0.0

    results = []
    for i, sk in enumerate(skills):
        kscore = kw_scores[i][0]
        bscore = raw.get(i, 0.0)
        score = KEYWORD_W * norm(kscore, maxk) + BM25_W * norm(bscore, maxr)
        results.append({
            "name": sk["name"], "cn": sk.get("cn", sk["name"]), "dir": sk["dir"],
            "type": sk.get("type", "executor"), "stage": sk.get("stage", 99),
            "domain": sk.get("domain", "econ"),
            "score": round(score, 4), "matched": kw_scores[i][1],
        })
    results.sort(key=lambda r: (-r["score"], tiebreak_r(r, tiebreak)))
    return results[:top]


def tiebreak_r(r, tiebreak):
    """同分时按 stage 顺序拉平（P0 优先），未入序者排最后。"""
    idx = tiebreak.index(r["stage"]) if r["stage"] in tiebreak else 999
    return idx


def main():
    ap = argparse.ArgumentParser(description="econ 技能路由：关键词加权 + 优先级拉平 + BM25")
    ap.add_argument("query", help="用户任务描述")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()
    out = {"domain": detect_domain(args.query), "skills": route(args.query, args.top)}
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
