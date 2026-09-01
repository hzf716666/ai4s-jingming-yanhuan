# -*- coding: utf-8 -*-
"""Project research progress API — 研究项目(假设→研究→论文)可视化进度。

GET /api/projects/progress?path=<研究项目绝对路径>
  → { project: name, stages: [...], percent: N, status: "..." }

判定依据: 读项目目录下的流水线产物(与研究流水线 gate 一致):
  sub_problems.json        → P1 拆解完成
  literature_review.md + references.json → P1.5 文献
  filtered_problems.json(含 user_confirmed) → P2 过滤确认
  data_gap_report.md 或 data_supplement.json → P2.5 数据缺口
  data_profile.md + data_inventory.json → P3 盘点
  results/<sid>/run_XX/STATUS == COMPLETED → P4 实验
  per_hypothesis_verdict.md → P5 整合
  paper/main.md → P6 写作
  review_report.md → P7 评审交付
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/projects", tags=["projects"])

STAGES = [
    ("p1", "P1 拆解", ["sub_problems.json"]),
    ("p1_5", "P1.5 文献", ["literature_review.md", "references.json"]),
    ("p2", "P2 过滤确认", ["filtered_problems.json"]),
    ("p2_5", "P2.5 数据缺口", ["data_gap_report.md", "data_supplement.json"]),
    ("p3", "P3 数据盘点", ["data_profile.md", "data_inventory.json"]),
    ("p4", "P4 实验", ["results"]),
    ("p5", "P5 结果整合", ["per_hypothesis_verdict.md"]),
    ("p6", "P6 论文写作", ["paper/main.md"]),
    ("p7", "P7 评审交付", ["review_report.md"]),
]


def _stage_done(proj: Path, stage_id: str, files: list[str]) -> bool:
    if stage_id == "p4":
        # 有任一 COMPLETED run 即实验已执行
        results = proj / "results"
        if not results.is_dir():
            return False
        for run in results.rglob("STATUS"):
            try:
                if run.read_text(encoding="utf-8").strip() == "COMPLETED":
                    return True
            except Exception:
                continue
        return False
    return all((proj / f).is_file() for f in files)


@router.get("/progress")
def project_progress(path: str = Query(...)):
    proj = Path(path)
    if not proj.is_dir():
        raise HTTPException(404, f"project dir not found: {path}")
    # 判定项目是否为研究项目(有 sub_problems 或 PIPELINE.md)
    is_research = (proj / "PIPELINE.md").exists()
    stages = []
    done_count = 0
    for stage_id, label, files in STAGES:
        done = _stage_done(proj, stage_id, files)
        if done:
            done_count += 1
        stages.append({"id": stage_id, "label": label, "done": done})
    total = len(stages)
    percent = round(done_count / total * 100) if total else 0
    status = "已完成" if done_count == total else ("研究进行中" if done_count > 0 else "尚未开始")
    return {
        "project": proj.name,
        "is_research": is_research,
        "stages": stages,
        "percent": percent,
        "status": status,
        "done": done_count,
        "total": total,
    }
