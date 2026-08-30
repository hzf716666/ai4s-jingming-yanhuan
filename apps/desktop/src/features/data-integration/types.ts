export type ExtractionTaskStatus = "pending" | "running" | "completed" | "failed";

export type ExtractionTask = {
  id: string;
  name: string;
  status: ExtractionTaskStatus;
  fileCount: number;
  recordCount?: number;
  progress?: number;
  qualityScore?: number;
  currentStep?: string;
  errorMessage?: string;
  createdAt: number;
  updatedAt: number;
  files: SourceFile[];
};

export type SourceFile = {
  id: string;
  name: string;
  size: number;
  type: "xlsx" | "csv" | "pdf" | "docx" | "pptx";
  status: "pending" | "parsing" | "parsed" | "failed";
  recordCount?: number;
};

export type PipelineStep = {
  key: string;
  label: string;
  status: "done" | "active" | "pending";
  progress?: number;
};

export type QualityMetrics = {
  overallScore: number;
  completeness: number;
  conflictRate: number;
  anomalyPoints: number;
  structuralBreaks: number;
};

export type ResultSummary = {
  sourceCount: number;
  recordCount: number;
  spatialCoverage: string;
  timeRange: string;
};

export type AnomalyItem = {
  id: string;
  type: "outlier" | "missing" | "conflict" | "structural";
  description: string;
  location: string;
  severity: "low" | "medium" | "high";
};
