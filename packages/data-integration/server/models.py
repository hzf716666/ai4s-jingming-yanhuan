"""Data extraction task models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PipelineStage(str, Enum):
    M1_REQUIREMENT = "m1_requirement"
    M2_SOURCE_QUALITY = "m2_source_quality"
    M3_PARSING = "m3_parsing"
    M4_INTEGRATION = "m4_integration"
    M5_QUALITY = "m5_quality"
    M6_OUTPUT = "m6_output"
    M7_GIS = "m7_gis"


STAGE_ORDER = [
    PipelineStage.M1_REQUIREMENT,
    PipelineStage.M2_SOURCE_QUALITY,
    PipelineStage.M3_PARSING,
    PipelineStage.M4_INTEGRATION,
    PipelineStage.M5_QUALITY,
    PipelineStage.M6_OUTPUT,
    PipelineStage.M7_GIS,
]

STAGE_LABELS: dict[PipelineStage, str] = {
    PipelineStage.M1_REQUIREMENT: "需求理解",
    PipelineStage.M2_SOURCE_QUALITY: "来源质量评估",
    PipelineStage.M3_PARSING: "多格式解析",
    PipelineStage.M4_INTEGRATION: "字段对齐与整合",
    PipelineStage.M5_QUALITY: "质量检查",
    PipelineStage.M6_OUTPUT: "结构化输出",
    PipelineStage.M7_GIS: "GIS 关联",
}


class SourceFile(BaseModel):
    name: str
    size: int
    type: str
    quality_score: Optional[float] = None
    record_count: Optional[int] = None


class StageProgress(BaseModel):
    stage: PipelineStage
    label: str
    status: str = "pending"  # pending | running | completed | failed
    progress: float = 0.0  # 0-100
    detail: str = ""


class TaskCreateRequest(BaseModel):
    name: str = Field(description="任务名称")
    description: str = ""
    research_question: str = ""
    indicator_hints: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    task_id: str
    name: str
    description: str = ""
    status: TaskStatus
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    source_files: list[SourceFile] = Field(default_factory=list)
    current_stage: Optional[PipelineStage] = None
    stages: list[StageProgress] = Field(default_factory=list)
    total_records: int = 0
    error: Optional[str] = None


class QualityMetrics(BaseModel):
    completeness: float
    accuracy: float
    consistency: float
    overall: float
    total_records: int
    unique_indicators: int
    unique_spaces: int
    anomalies: int = 0
    structural_breaks: int = 0
    summarizability_violations: int = 0


class ResultResponse(BaseModel):
    task_id: str
    summary: dict[str, Any] = Field(default_factory=dict)
    quality: QualityMetrics
    records_preview: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    source_quality: list[dict[str, Any]] = Field(default_factory=list)
    output_files: list[dict[str, Any]] = Field(default_factory=list)


class LLMConfig(BaseModel):
    provider: str = "dashscope"
    api_key: str = ""
    model: str = "qwen-plus"
    enabled: bool = False


class LLMConfigResponse(BaseModel):
    provider: str
    model: str
    enabled: bool
    has_api_key: bool
