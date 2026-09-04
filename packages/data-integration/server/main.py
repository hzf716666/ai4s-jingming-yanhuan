"""FastAPI server for data extraction module."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# Ensure parent is in path for imports
_PARENT = Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

from .models import LLMConfig, LLMConfigResponse, TaskCreateRequest
from .task_manager import get_manager
from .map_api import router as map_router
from .records_api import router as records_router
from .hypotheses_api import router as hypotheses_router
from .progress_api import router as progress_router
from .impact_api import router as impact_router

app = FastAPI(title="Data Extraction API", version="1.0.0")
app.include_router(map_router)
app.include_router(records_router)
app.include_router(hypotheses_router)
app.include_router(progress_router)
app.include_router(impact_router)

# CORS — allow all for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize task manager on startup
@app.on_event("startup")
def _startup():
    get_manager()
    # 自动同步下载的数据文件(OECD 等下载目录) → fact_records(面板)/zone_facts(地图)
    try:
        import subprocess, sys as _sys, os
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sync = os.path.join(base, "scripts", "sync_oecd_to_panel.py")
        if os.path.exists(sync):
            r = subprocess.run([_sys.executable, sync], capture_output=True, text=True, timeout=300)
            print("[auto-sync]", (r.stdout or r.stderr).strip()[-200:])
        # 各研究项目 data/records.json(工作台 AI 采集产物) → 面板/地图/图谱(幂等增量)
        proj = os.path.join(base, "scripts", "sync_project_data_to_panel.py")
        if os.path.exists(proj):
            r2 = subprocess.run([_sys.executable, proj], capture_output=True, text=True, timeout=300)
            print("[project-ingest]", (r2.stdout or r2.stderr).strip()[-300:])
    except Exception as e:
        print("[auto-sync] skipped:", e)


# ============== Tasks ==============

@app.get("/api/tasks")
def list_tasks():
    mgr = get_manager()
    return [t.to_dict() for t in mgr.list_tasks()]


@app.post("/api/tasks")
def create_task(req: TaskCreateRequest):
    mgr = get_manager()
    task = mgr.create_task(
        name=req.name,
        description=req.description,
        research_question=req.research_question,
        indicator_hints=req.indicator_hints,
    )
    return task.to_dict()


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    mgr = get_manager()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    mgr = get_manager()
    ok = mgr.delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}


@app.post("/api/tasks/{task_id}/start")
def start_task(task_id: str):
    mgr = get_manager()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.source_files:
        raise HTTPException(status_code=400, detail="No source files uploaded")
    ok = mgr.start_task(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot start task")
    return task.to_dict()


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    mgr = get_manager()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.cancel()
    return {"ok": True}


@app.post("/api/tasks/{task_id}/files")
async def upload_file(task_id: str, file: UploadFile = File(...)):
    mgr = get_manager()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    content = await file.read()
    sf = mgr.add_file(task_id, file.filename or "unnamed", content)
    if not sf:
        raise HTTPException(status_code=500, detail="Failed to save file")
    return sf.model_dump()


@app.get("/api/tasks/{task_id}/logs")
def get_logs(task_id: str, after: int = 0):
    mgr = get_manager()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "lines": task.get_logs(after),
        "total": len(task._log_lines),
    }


# SSE stream for real-time progress
@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    mgr = get_manager()
    task = mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        last_log_len = 0
        last_status = None
        while True:
            current = task.to_dict()
            logs = task.get_logs(last_log_len)
            last_log_len += len(logs)

            if current["status"] != last_status or logs:
                data = {
                    "task": current,
                    "new_logs": logs,
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                last_status = current["status"]

            if current["status"] in ("completed", "failed", "cancelled"):
                # Final event
                yield f"data: {json.dumps({'task': current, 'new_logs': [], 'done': True}, ensure_ascii=False)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ============== Result ==============

@app.get("/api/tasks/{task_id}/result")
def get_result(task_id: str):
    mgr = get_manager()
    result = mgr.get_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not available")
    return result


# ============== LLM Config ==============

@app.get("/api/llm-config")
def get_llm_config():
    mgr = get_manager()
    cfg = mgr.get_llm_config()
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        enabled=cfg.enabled,
        has_api_key=bool(cfg.api_key),
    )


@app.post("/api/llm-config")
def set_llm_config(cfg: LLMConfig):
    mgr = get_manager()
    mgr.save_llm_config(cfg)
    return LLMConfigResponse(
        provider=cfg.provider,
        model=cfg.model,
        enabled=cfg.enabled,
        has_api_key=bool(cfg.api_key),
    )


# ============== Health ==============

@app.get("/api/health")
def health():
    return {"status": "ok", "time": time.time()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8787)
