import type { ExtractionTask, PipelineStep, QualityMetrics, ResultSummary, AnomalyItem } from "./types";

const now = Date.now();

export const mockTasks: ExtractionTask[] = [
  {
    id: "task-001",
    name: "省级GDP数据整合",
    status: "completed",
    fileCount: 5,
    recordCount: 186,
    qualityScore: 92,
    createdAt: now - 2 * 24 * 3600 * 1000,
    updatedAt: now - 2 * 24 * 3600 * 1000 + 3600 * 1000,
    files: [
      { id: "f1", name: "gdp_2018_2023.xlsx", size: 45056, type: "xlsx", status: "parsed", recordCount: 186 },
      { id: "f2", name: "gdp_province_2022.csv", size: 12288, type: "csv", status: "parsed", recordCount: 31 },
      { id: "f3", name: "statistical_yearbook_2023.pdf", size: 2516582, type: "pdf", status: "parsed", recordCount: 93 },
      { id: "f4", name: "regional_economy.docx", size: 307200, type: "docx", status: "parsed", recordCount: 24 },
      { id: "f5", name: "quarterly_gdp.pptx", size: 1258291, type: "pptx", status: "parsed", recordCount: 48 },
    ],
  },
  {
    id: "task-002",
    name: "人口与就业数据抽取",
    status: "running",
    fileCount: 5,
    progress: 65,
    currentStep: "多源融合",
    createdAt: now - 30 * 60 * 1000,
    updatedAt: now - 5 * 60 * 1000,
    files: [
      { id: "f6", name: "population_2018_2023.xlsx", size: 52224, type: "xlsx", status: "parsed", recordCount: 186 },
      { id: "f7", name: "employment_data.csv", size: 8192, type: "csv", status: "parsed", recordCount: 62 },
      { id: "f8", name: "statistical_yearbook_2023.pdf", size: 2516582, type: "pdf", status: "parsing" },
      { id: "f9", name: "labor_report.docx", size: 204800, type: "docx", status: "pending" },
      { id: "f10", name: "unemployment_stats.pptx", size: 800000, type: "pptx", status: "pending" },
    ],
  },
  {
    id: "task-003",
    name: "固定资产投资统计",
    status: "pending",
    fileCount: 3,
    createdAt: now - 60 * 60 * 1000,
    updatedAt: now - 60 * 60 * 1000,
    files: [
      { id: "f11", name: "investment_2023.xlsx", size: 38912, type: "xlsx", status: "pending" },
      { id: "f12", name: "fixed_assets.pdf", size: 1048576, type: "pdf", status: "pending" },
      { id: "f13", name: "infra_report.docx", size: 256000, type: "docx", status: "pending" },
    ],
  },
  {
    id: "task-004",
    name: "R&D经费投入整合",
    status: "failed",
    fileCount: 2,
    errorMessage: "PDF解析失败：文件可能已损坏或为扫描件",
    createdAt: now - 24 * 3600 * 1000,
    updatedAt: now - 22 * 3600 * 1000,
    files: [
      { id: "f14", name: "rd_expenditure.xlsx", size: 22528, type: "xlsx", status: "parsed", recordCount: 45 },
      { id: "f15", name: "rd_survey.pdf", size: 524288, type: "pdf", status: "failed" },
    ],
  },
];

export const mockPipelineSteps: PipelineStep[] = [
  { key: "upload", label: "数据上传", status: "done" },
  { key: "parse", label: "格式解析", status: "done" },
  { key: "clean", label: "清洗标准化", status: "done" },
  { key: "align", label: "字段对齐", status: "done" },
  { key: "fuse", label: "多源融合", status: "active", progress: 45 },
  { key: "quality", label: "质量检查", status: "pending" },
  { key: "output", label: "结构化输出", status: "pending" },
];

export const mockQualityMetrics: QualityMetrics = {
  overallScore: 92,
  completeness: 96.8,
  conflictRate: 3.2,
  anomalyPoints: 7,
  structuralBreaks: 3,
};

export const mockResultSummary: ResultSummary = {
  sourceCount: 5,
  recordCount: 186,
  spatialCoverage: "31 个省份",
  timeRange: "2018-2023",
};

export const mockAnomalies: AnomalyItem[] = [
  {
    id: "a1",
    type: "conflict",
    description: "2022年某省GDP数值在两个来源中差异超过5%",
    location: "GDP_2022 / 广东省",
    severity: "high",
  },
  {
    id: "a2",
    type: "outlier",
    description: "某省2021年增长率明显偏离历史趋势",
    location: "增长率 / 湖北省 2021",
    severity: "medium",
  },
  {
    id: "a3",
    type: "missing",
    description: "西藏自治区2020年数据缺失",
    location: "GDP_2020 / 西藏",
    severity: "medium",
  },
  {
    id: "a4",
    type: "structural",
    description: "2019年统计口径发生变化，第三产业分类调整",
    location: "产业结构 / 2019",
    severity: "low",
  },
];

export const mockDataPreview = [
  {
    province: "北京市",
    year: 2023,
    gdp: 43760.7,
    population: 2184.3,
    source: "多源融合",
    confidence: 0.97,
  },
  {
    province: "上海市",
    year: 2023,
    gdp: 47218.7,
    population: 2487.1,
    source: "多源融合",
    confidence: 0.98,
  },
  {
    province: "广东省",
    year: 2023,
    gdp: 135673.2,
    population: 12684.0,
    source: "多源融合",
    confidence: 0.96,
  },
  {
    province: "江苏省",
    year: 2023,
    gdp: 128222.2,
    population: 8515.0,
    source: "多源融合",
    confidence: 0.97,
  },
  {
    province: "浙江省",
    year: 2023,
    gdp: 82553.0,
    population: 6577.0,
    source: "单源",
    confidence: 0.89,
  },
];

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

export function formatTimeAgo(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "刚刚";
  if (mins < 60) return mins + " 分钟前";
  const hours = Math.floor(mins / 60);
  if (hours < 24) return hours + " 小时前";
  const days = Math.floor(hours / 24);
  return days + " 天前";
}
