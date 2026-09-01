// Curated open-source science MCP connectors (P1-2). These are existing,
// maintained open-source MCP servers — we one-click provision them into a
// shared isolated env (bundled uv) and register them; we do not reimplement
// literature/database access ourselves. Keep this list small and vetted.
import type { McpConfig } from "@jingming/sdk";

export interface ScienceConnector {
  /** MCP server name written into OpenCode's config. */
  id: string;
  label: string;
  /** Short discipline chip, e.g. "materials", "economics". */
  discipline: string;
  description: string;
  /** How this connector is provisioned. `python` (default): installed into the
   *  managed venv via pip. `npx`/`uvx`: launched on demand by the runtime, no
   *  managed venv needed. */
  kind?: "python" | "npx" | "uvx";
  /** PyPI package installed into the shared science-MCP env (kind=python). */
  pkg?: string;
  /** Console script the package installs (resolved next to the managed python).
   *  Preferred when set — many MCP servers ship a script, not a `-m` module. */
  bin?: string;
  /** Fallback: Python `-m` module the server runs as, plus any args. */
  module?: string;
  args?: string[];
  /** npm package for kind=npx (e.g. "@cyanheads/oecd-mcp-server"). */
  npmPkg?: string;
  /** Binary npm installs (kind=npx); defaults to the package's bin. */
  npmBin?: string;
  /** Extra args passed after the bin (kind=npx). */
  npmArgs?: string[];
  /** Env var the server reads its API key from (free keys; never logged). */
  apiKeyEnv?: string;
  /** Where the user gets a free key. */
  apiKeyUrl?: string;
  /** Shown before Enable when the install is large. */
  installNote?: string;
  /** Upstream project, shown so users can vet it before enabling. */
  source: string;
}

export const SCIENCE_CONNECTORS: ScienceConnector[] = [
  {
    id: "paper-search",
    label: "Literature search",
    discipline: "all fields",
    description:
      "arXiv · PubMed · Crossref · Semantic Scholar · bioRxiv/medRxiv — search & fetch papers",
    pkg: "paper-search-mcp",
    module: "paper_search_mcp.server",
    source: "github.com/openags/paper-search-mcp",
  },
  {
    id: "biomcp",
    label: "Biomedical databases",
    discipline: "biology",
    description: "PubMed articles, ClinicalTrials.gov, and genomic variants (MyVariant/ClinVar)",
    pkg: "biomcp-python",
    module: "biomcp",
    args: ["run"],
    source: "github.com/genomoncology/biomcp",
  },
  {
    id: "materials-project",
    label: "Materials Project",
    discipline: "materials",
    description:
      "Query material properties, crystal structures, and phase diagrams from the Materials Project database",
    pkg: "mcp-materials-project",
    bin: "mcp-materials-project",
    apiKeyEnv: "MP_API_KEY",
    apiKeyUrl: "https://next-gen.materialsproject.org/api",
    installNote: "large — installs pymatgen + mp-api on first enable",
    source: "github.com/luffysolution-svg/mcp-materials-project",
  },
  {
    id: "fred",
    label: "FRED economic data",
    discipline: "economics",
    description:
      "Federal Reserve (FRED) economic time series — GDP, inflation, unemployment, rates, and more",
    pkg: "fred-mcp",
    bin: "fred-mcp",
    apiKeyEnv: "FRED_API_KEY",
    apiKeyUrl: "https://fred.stlouisfed.org/docs/api/api_key.html",
    source: "github.com/tosin2013/fred-mcp",
  },
  {
    id: "spaceweather",
    label: "Space weather",
    discipline: "physics",
    description:
      "Solar wind, solar flares, Kp/Dst geomagnetic indices, radiation storms, and aurora forecasts (NOAA SWPC · NASA DONKI · USGS)",
    pkg: "spaceweather-mcp",
    bin: "spaceweather-mcp",
    source: "github.com/hoon1983/spaceweather-mcp",
  },
  {
    id: "open-meteo",
    label: "Weather & climate (Open-Meteo)",
    discipline: "earth/climate",
    description:
      "Current & historical weather, air quality, and timezones from Open-Meteo — free, no key",
    pkg: "mcp-weather-server",
    module: "mcp_weather_server",
    source: "github.com/isdaniel/mcp_weather_server",
  },
  {
    id: "usgs-water",
    label: "USGS water data",
    discipline: "earth/climate",
    description:
      "USGS Water Services — streamflow, flood stages, peak events, and monitoring sites across the US",
    pkg: "usgs-mcp",
    bin: "usgs-mcp",
    source: "github.com/mansurjisan/ocean-mcp",
  },
  {
    id: "cnki",
    label: "CNKI 知网文献检索",
    discipline: "economics",
    description:
      "中国知网 (CNKI) 学术文献与期刊检索、元数据导出 — 需要知网账号登录(Playwright 浏览器)",
    pkg: "cnki-mcp",
    bin: "cnki-mcp",
    installNote: "需要知网账号; 首次启用会安装 Playwright 浏览器",
    source: "github.com/SepineTam/cnki-mcp",
  },
  {
    id: "yahoo-finance",
    label: "Yahoo Finance 金融数据",
    discipline: "economics",
    description:
      "股票、ETF、指数、汇率等金融时间序列(Yahoo Finance) — 免 key",
    pkg: "yahoo-finance-mcp",
    bin: "yahoo-finance-mcp",
    source: "github.com/Alex2Yang97/yahoo-finance-mcp",
  },
  {
    id: "mcp-finance",
    label: "Finance 计算分析工具",
    discipline: "economics",
    description:
      "yfinance 包装器 + 资产收益率/波动率/风险等计算分析工具",
    pkg: "mcp-finance",
    bin: "mcp-finance",
    source: "github.com/JoshCap20/finance-mcp",
  },
  {
    id: "worldbank",
    label: "World Bank 世界银行数据",
    discipline: "economics",
    kind: "npx",
    description:
      "World Bank Open Data — 各国 GDP、人口、贸易、教育、健康等宏观发展指标 (240+ 经济体)",
    npmPkg: "worldbank-mcp",
    npmBin: "worldbank-mcp",
    installNote: "npx 启动 (拉取 npm 包无需额外环境)",
    source: "github.com/tianyuio/worldbank-mcp",
  },
  {
    id: "oecd",
    label: "OECD 经合组织数据",
    discipline: "economics",
    kind: "npx",
    description:
      "OECD 统计数据库 — 1500+ 数据集 (GDP、税收、教育、创新、劳动力市场等)",
    npmPkg: "@cyanheads/oecd-mcp-server",
    npmBin: "oecd-mcp-server",
    installNote: "npx 启动",
    source: "github.com/cyanheads/oecd-mcp-server",
  },
  {
    id: "cnbs",
    label: "中国国家统计局数据",
    discipline: "economics/china",
    kind: "npx",
    description:
      "中国国家统计局 (NBS) 数据查询 — GDP、CPI、人口、工业、固定资产投资等",
    npmPkg: "mcp-cnbs",
    npmBin: "mcp-cnbs",
    installNote: "npx 启动",
    source: "github.com/icen-ai/mcp-cnbs",
  },
];

/** Resolve a console script that sits next to the managed python interpreter
 *  (unix: `<env>/bin/<script>`; Windows: `<env>/Scripts/<script>.exe`). */
function scriptBeside(python: string, bin: string): string {
  const sep = python.includes("\\") ? "\\" : "/";
  const dir = python.slice(0, python.lastIndexOf(sep));
  const exe = python.toLowerCase().endsWith(".exe") ? ".exe" : "";
  return `${dir}${sep}${bin}${exe}`;
}

/** Local-MCP config for a connector, given the managed interpreter path and an
 *  optional API key (passed via env, never written to provenance/logs). */
export function connectorConfig(
  c: ScienceConnector,
  python: string,
  apiKey?: string,
): McpConfig {
  let command: string[];
  if (c.kind === "npx") {
    // On-demand npm launch: `npx -y <pkg> [bin] [args]`. No managed venv.
    command = ["npx", "-y", c.npmPkg ?? ""];
    if (c.npmBin) command.push(c.npmBin);
    if (c.npmArgs) command.push(...c.npmArgs);
  } else if (c.kind === "uvx") {
    command = ["uvx", "--from", c.npmPkg ?? ""];
    if (c.npmBin) command.push(c.npmBin);
    if (c.npmArgs) command.push(...c.npmArgs);
  } else {
    // Python connector: console script beside the managed interpreter, or -m module.
    command = c.bin
      ? [scriptBeside(python, c.bin)]
      : [python, "-m", c.module ?? "", ...(c.args ?? [])];
  }
  const config: McpConfig = { type: "local", command, enabled: true };
  if (c.apiKeyEnv && apiKey && apiKey.trim()) {
    config.environment = { [c.apiKeyEnv]: apiKey.trim() };
  }
  return config;
}
