# EconDataForge — 最终整合方案文档

> **赛道二·方向1A | 科学数据查找解析与整合**
> 场景：计量经济学科研流程中的多源异构数据自动抽取、整合与标准化
> 日期：2026-08-29 | 版本：最终整合版
> 基于 EconDataForge 第一版 + SST-Cube Extractor v3 整合

---

## 一、整合背景与策略

### 1.1 两份方案定位

| 方案 | 定位 | 核心优势 |
|------|------|---------|
| EconDataForge 第一版 | 架构与文献基础 | 7模块全流程架构、56篇论文调研、13维度111字段数据基座、Medallion三层平台、完整技术栈 |
| SST-Cube Extractor v3 | 实践与算法引擎 | 5 Pipeline并行抽取、投票融合4档证据链、结构突变检测、H3时空立方体、F1=0.900实测验证 |

### 1.2 整合策略

**以 EconDataForge 的七模块架构为骨架，注入 SST-Cube 的实战算法和实测参数**，形成"理论完整 + 工程可落地"的统一方案。

| 整合维度 | EconDataForge 贡献 | SST-Cube 贡献 |
|---------|-------------------|---------------|
| 架构 | M1-M7 七模块 + Medallion 三层 | 8 节点流水线映射到七模块 |
| 数据模式 | 宽表 fact_panel_wide (111字段) | 七元组长表 (time,space,value,unit,indicator,source,note) |
| 解析管线 | MinerU/Docling/Unstructured | openpyxl/pdfplumber/camelot/PaddleOCR/OpenCV 图表逆向 |
| 数据整合 | OpenRefine+recordlinkage+SCHEMORA | 投票融合4档证据链+冲突仲裁 |
| 质量检查 | Soda SQL规则+闭环修正 | 多维异常+口径交叉+Chow/Bai-Perron结构突变 |
| GIS | PostGIS+GeoPandas+ECharts | H3 GeoCube+Lloyd区划harmonisation |
| 溯源 | W3C PROV-O对齐 | source字段七元组内置溯源 |
| 验证 | — | 反向真值校验 F1=0.900 |

### 1.3 数据模式统一设计

**双模式存储：长表 + 宽表**

- **长表模式**（七元组）：`output/sst_cube/long_table_fused.csv`，面向时空立方体和OLAP操作
- **宽表模式**（PostgreSQL DDL）：`fact_panel_wide`，面向SQL查询和面板数据分析

两者通过 `indicator` 字段与 `fact_panel_wide` 的列名映射实现互转。

---

## 二、系统总体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EconDataForge 整合架构                                   │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  调度层 (Python pipeline + Celery可选)                             │     │
│  │  └── 一键编排：M1→M2→M3→M4→M5→M6→M7（含闭环回流）               │     │
│  └─┬──────┬──────┬───────┬───────┬───────┬───────┬───────────────────┘     │
│    │      │      │       │       │       │       │                          │
│  ┌─▼──┐ ┌▼───┐ ┌▼────┐ ┌▼────┐ ┌▼────┐ ┌▼────┐ ┌▼─────────┐               │
│  │M1  │ │M2  │ │M3   │ │M4   │ │M5   │ │M6   │ │ M7       │               │
│  │需求│ │来源│ │多格式│ │字段 │ │质量 │ │结构化│ │ GIS关联 │               │
│  │理解│ │发现│ │解析 │ │对齐 │ │检查 │ │输出 │ │ +可视化  │               │
│  └────┘ └────┘ └─────┘ └─────┘ └─────┘ └─────┘ └──────────┘               │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  数据层                                                           │     │
│  │  ├── Bronze: 原始文件存储（多格式原样保存+元数据登记）           │     │
│  │  ├── Silver: 标准化七元组长表（字段对齐+单位转换+来源溯源）       │     │
│  │  └── Gold: 宽表面板数据 + H3 GeoCube + 质量报告                  │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│  基座模型: Qwen系列（Qwen-Plus / Qwen-VL-Max / Qwen-Turbo）               │
│  部署: Docker Compose (可选) / 独立Python包                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 三、七模块详细设计（整合版）

### M1: 科研数据需求理解模块

**功能**：将用户自然语言需求转化为结构化字段字典和检索条件。

| 环节 | 技术选型 | 实现 |
|------|---------|------|
| 自然语言→Schema | Qwen-Plus Function Calling | 输出JSON Schema（字段名、类型、单位、精度、范围） |
| 标准字段字典 | indicator_dict.json | 对齐Frictionless Data Table Schema |
| 检索条件 | Qwen-Plus生成关键词/时间/地理范围 | 输出检索条件模板 |

**输出**：`需求Schema.json` + `检索条件.json`

### M2: 数据源发现与筛选模块

**功能**：根据检索条件发现并筛选数据来源。

| 环节 | 技术选型 | 实现 |
|------|---------|------|
| 本地文件扫描 | os.walk + 文件类型检测 | 识别xlsx/pdf/csv/音频/视频 |
| API接入 | 国家统计局/World Bank API | 结构化数据摄入 |
| 来源质量评估 | Färber 7维度加权 h(g) 公式 | 7维×权重打分 |
| 来源筛选 | Qwen-Turbo评分（覆盖度×权威性×时效性） | 输出候选来源列表 |

**Färber 数据源质量评估公式**：
```
h(g) = ( Σ wᵢ · mᵢ(g) ) / ( Σ wⱼ )
```
7维度权重：accuracy 0.30, reliability 0.15, comparability 0.15, completeness 0.10, consistency 0.10, timeliness 0.10, documentation 0.10

### M3: 多格式内容解析模块

**功能**：将各种格式原始数据解析为结构化七元组记录。五Pipeline并行。

#### Pipeline A: xlsx_robust（主力）
- openpyxl 读取 + 自研多级表头解析
- 中英文双语行 split(`split_cn_en`)
- 单位括号提取(`extract_unit` 支持12种单位)
- 自动检测"地区×指标"截面表 vs "年份×指标"时间序列表

#### Pipeline B: pdfplumber
- `pdfplumber.extract_tables()` 文字型PDF表格抽取

#### Pipeline C: camelot
- `camelot.read_pdf(flavor='stream')` 矢量表格识别

#### Pipeline D: 图表逆向（亮点1）
1. pdfplumber 渲染高分辨率图(200dpi)
2. OpenCV 检测图表ROI（HSV饱和度+形态学）
3. PaddleOCR 识别坐标轴文字→数值
4. 颜色采样按列扫描→反推数据系列

#### Pipeline E: PaddleOCR扫描PDF
- 渲染→OCR→行重组→启发式找数据行（≥2个数字的行）

**M3输出**：每条记录为七元组 `(time, space, value, unit, indicator, source, note)`，保存到Silver层

### M4: 字段对齐与多源整合模块

**功能**：将多源解析的结构化记录统一到标准Schema，处理冲突。七步流程。

#### Step 1: 预处理清洗（张辉§5）
- 单位归一（千元/亿元/百万元→元）
- 行政区划归一（北京市→北京）
- 缺失值标 `[missing]`
- 重复按 `(time, space, indicator, unit)` 去重，保留来源最新

#### Step 2: Schema Matching（经典+LLM混合）
- 按名称匹配：indicator_dict.json的aliases字段映射 [Rahm & Bernstein C1]
- 按结构匹配：表头嵌套关系推断字段语义
- 按实例匹配：数据值分布推测字段对应关系
- LLM语义增强：Qwen-Turbo判断"GDP增长率"≡"经济增速" [SCHEMORA P6]

#### Step 3: Record Linkage — 实体对齐
- recordlinkage库：blocking + 相似度 + 分类 [T2]
- dedupe库：跨源记录去重 [T3]
- LLM辅助：Peeters方法处理名称变体 [C5]

#### Step 4: Unit Standardization
- 规则引擎：unit_rules.json预定义转换
- IMF IFS/SNA 2008汇率换算：内置2003-2024人民币年平均汇率，Atlas法三年平滑

#### Step 5: Truth Discovery — 投票融合（亮点2）
**4档证据链**：
| 档位 | 条件 | 应用 |
|------|------|------|
| HIGH_confidence | 多源完全一致（浮点1%容差） | 直接采纳 |
| outlier_removed | 多数一致，偏离剔除 | 标evidence |
| CONFLICT_avg | 全不一致 | 取均值+列各方证据 |
| MEDIUM_confidence | 单源 | 标evidence |

note字段带 `evidence_count` 供时空立方体加权。

#### Step 6: Provenance — 来源留痕 [W3C PROV-O T6]
- source字段：`火炬年鉴<部分>/<文件名>/sheet=<...>`
- raw_payload：完整原始值
- PROV-O结构：entity(来源) + activity(提取) + agent(处理器)

#### Step 7: Data Reorganization
- 七元组长表写入 `long_table_fused.csv`
- 按指标×时间×地区组织面板结构
- 双螺旋派生（陈杰杰p6）：5个派生公式

**双螺旋派生公式**：
| 派生指标 | 公式 | 论文出处 |
|---------|------|---------|
| 创新链强度_RD占比 | R&D经费 / 营业收入 | 陈杰杰p6 |
| 产业链强度_工业实化率 | 工业总产值 / 营业收入 | 陈杰杰p6 |
| 双螺旋协同度 | (R&D/营收) × (工业/营收) | 陈杰杰p6 |
| 技术转移转化率 | 技术合同成交额 / R&D | 陈杰杰p2+p6 |
| 企业主体地位 | 高企数 / 入统企业数 | 陈杰杰p6 |

### M5: 质量检查与反馈修正模块

#### 5a. 多维异常检测（亮点3）
4种方法综合判定：
1. YoY > 50%（吴廷鑫原方法）
2. z-score > 2σ（滚动窗口）
3. IQR outlier（1.5×IQR外）
4. 绝对值跳跃

#### 5b. 口径交叉识别
三源交叉：
1. OCR主要指标解释PDF
2. 已知规则库（2022基地调整/2018高企认定/2021 R&D调查/2019技术合同/2020孵化器）
3. 时间近邻推断（同年同地区≥3指标同时突变→口径调整）

#### 5c. 结构突变检测（补齐4）
| 算法 | 用途 | 论文 |
|------|------|------|
| Chow test | 普查年(2003/2008/2013/2018/2023)检测 | Casini-Perron §3.1 |
| Bai-Perron多断点 | 未知日期多断点，BIC选择 | Casini-Perron §3.2 |
| AO/LS/TC三分类 | 一次性异常/持续偏移/暂时变化 | X-13ARIMA-SEATS |

#### 5d. Summarizability校验（补齐5）
| 条件 | 检查内容 |
|------|---------|
| Disjointness | 子类别成员互斥 |
| Completeness | 子项之和≈父项 |
| Type Compatibility | stock vs flow类型匹配 |

#### 5e. 闭环修正
- 缺失字段→触发M2补充查找→M3解析→M4整合→M5再检查
- 解析错误→触发M3换解析策略→M4→M5
- 字段错配→触发M4重新对齐→M5
- 低置信度/冲突→人工审核队列
- 最多2轮自动修正

#### 5f. 反向真值校验（亮点5）
- 10个公开可验证真值
- 2个故意陷阱（异常倍数检测）
- 单位换算（千元↔亿元↔美元）
- 时间宽松匹配（精确→±1年→None兜底）
- 评估指标：F1 score

### M6: 结构化输出模块

| 输出 | 格式 | 说明 |
|------|------|------|
| 长表 | CSV | 七元组 (time,space,value,unit,indicator,source,note) |
| 宽表 | PostgreSQL DDL | fact_panel_wide (111字段) |
| H3 GeoCube | JSON | H3 res=5 空间点 |
| 异常报告 | JSON | 83处异常+166处结构突变 |
| 质量报告 | JSON/MD | 106源质量分+summarizability+反向校验F1 |
| 数据字典 | JSON | indicator_dict + unit_rules + quality_rules |
| 溯源文件 | JSON | 完整来源链(W3C PROV-O对齐) |

### M7: GIS关联与可视化模块

#### 行政区划映射（补齐2 - Lloyd）
- 内置70+行政区划GPS字典
- 9位→12位NBS区划码映射
- 跨年cross-walk表（撤县设区/合并）
- H3 res=7区县级网格

#### H3 GeoCube
- 七元组长表→H3 res=5空间点
- 输出 `h3_cube_res5.json` 供前端直接渲染

#### 空间计量分析
| 方法 | 工具 | 输出 |
|------|------|------|
| Global Moran's I | PySAL | 全局空间自相关+散点图 |
| LISA | PySAL | HH/LL/LH/HL聚类图 |
| 空间回归(SAR/SEM/SDM) | PySAL spreg | 回归结果+残差分布 |

---

## 四、数据基座设计

### 4.1 七元组Schema（长表模式）

```python
@dataclass
class Record:
    time: str          # 时间 (年份/季度)
    space: str         # 空间 (行政区划名/adcode)
    value: float      # 数值
    unit: str          # 单位 (元/千元/亿元/万美元...)
    indicator: str     # 指标名 (标准化后)
    source: str        # 来源 (文件名/sheet/API)
    note: str = ""     # 备注 (证据链/异常标记/口径)
```

### 4.2 宽表Schema（111字段，13维度）

详见 EconDataForge 第一版 §5.3-5.5 的 PostgreSQL DDL。

### 4.3 五张规范表

| 规范表 | 文件 | 内容 |
|--------|------|------|
| 指标字典 | indicator_dict.json | 标准码、中/英文名、单位、口径、别名、来源 |
| 单位换算 | unit_rules.json | 原始单位→标准单位换算规则 |
| 口径与别名 | calib_notes.json | 同指标异名、口径变更断点 |
| 维度代码 | dimension_codes.json | 载体类型、地区、行业、园区ID编码 |
| 质量规则 | quality_rules.json | 加总/跨表/时序/单位一致性校验 |

---

## 五、16篇论文/标准溯源表

| # | 模块 | 论文出处 | 段落 |
|---|------|---------|------|
| 1 | 七元组schema | 吴廷鑫(2023) | §2.3.5 |
| 2 | 数据清洗流水线 | 张辉《基于工作流…》 | §5 |
| 3 | Cube Coupling | 吴廷鑫(2023) | §6.4+图6-19 |
| 4 | OLAP多维分析 | 吴廷鑫(2023) | §5.3 |
| 5 | 行政区划生存期 | 吴廷鑫(2023) | §3.1.2 |
| 6 | 数据一致性验证 | 吴廷鑫(2023) | §2.3.6 |
| 7 | 图表识别 | EO-agents+张辉 | §3/§4 |
| 8 | 反向真值校验 | HLER | §4 |
| 9 | 投票融合 | HLER+PIEVO | §3/§4 |
| 10 | 双螺旋协同 | 陈杰杰(2026) | p6 |
| 11 | 数据源质量评估 | Färber et al.(2017) | §3.1 h(g) |
| 12 | 行政区划harmonisation | Lloyd et al.(2019) | §3 cross-walk |
| 13 | 货币单位换算 | IMF IFS+WB Atlas+SNA 2008 | 年平均汇率 |
| 14 | 结构突变检测 | Casini&Perron(2018) | §3 Chow+BP+AO/LS/TC |
| 15 | 数据源漂移 | De Boom&Reusens(2023) | UNECE ML工作坊 |
| 16 | Summarizability校验 | Lenz-Shoshani(1997)+Hurtado(2005) | §3 三条件 |

---

## 六、性能指标（SST-Cube v3实测基准）

| 指标 | 数值 |
|------|------|
| 七元组总数 | 10810 |
| 双螺旋派生 | 4710条 |
| 时序异常 | 83处(HIGH 16) |
| 口径调整识别 | 74处 |
| 结构突变 | 166处 |
| 数据源质量评估 | 106源(平均0.498) |
| 行政区划映射 | 3180命中 |
| Summarizability警告 | 1037处 |
| 反向真值F1 | 0.900 |
| 论文溯源 | 16篇 |
| 综合得分 | 0.778 |
| 总用时 | 17秒 |

---

## 七、技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 基座模型 | Qwen-Plus/Qwen-VL-Max/Qwen-Turbo | 需求理解/Schema匹配/OCR辅助/质量验证 |
| Excel解析 | openpyxl | xlsx读取+多级表头 |
| PDF文本 | pdfplumber | 文字型PDF表格 |
| PDF表格 | camelot | 矢量表格识别 |
| OCR | PaddleOCR | 扫描PDF |
| 图表逆向 | OpenCV+PaddleOCR | 图表→数值 |
| 数据清洗 | Python原生+rapidfuzz | 单位/区划/去重 |
| 投票融合 | Python原生 | 4档证据链 |
| 异常检测 | numpy+scipy | YoY/z-score/IQR |
| 结构突变 | statsmodels | Chow/Bai-Perron |
| 空间网格 | h3 | Uber H3 GeoCube |
| 空间分析 | pysal(可选) | Moran's I/LISA/SAR |
| 输出 | CSV/JSON/Parquet | 长表+GeoCube+报告 |

---

## 八、文件结构

```
packages/data-integration/
├── docs/
│   └── FINAL_INTEGRATED_DESIGN.md   ← 本文档
├── src/
│   ├── __init__.py
│   ├── schema.py                     七元组dataclass + 宽表映射
│   ├── config.py                     配置管理
│   ├── source_quality.py             M2: Färber数据源质量评估
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── xlsx_robust.py            M3 Pipeline A: Excel解析
│   │   ├── pdf_pipelines.py          M3 Pipeline B/C: PDF文本+表格
│   │   ├── chart_reverse.py          M3 Pipeline D: 图表逆向
│   │   └── ocr_pipeline.py           M3 Pipeline E: 扫描PDF OCR
│   ├── cleaning.py                   M4 Step1: 数据清洗(张辉七步法)
│   ├── schema_matching.py            M4 Step2: Schema匹配
│   ├── fusion.py                     M4 Step5: 投票融合(HLER+PIEVO)
│   ├── provenance.py                 M4 Step6: 来源溯源(PROV-O)
│   ├── coupling.py                   M4 Step7: 双螺旋派生(陈杰杰)
│   ├── anomaly.py                    M5: 多维异常检测
│   ├── structural_break.py           M5: 结构突变(Casini-Perron)
│   ├── summarizability.py            M5: Summarizability(Lenz-Shoshani)
│   ├── groundtruth.py                M5: 反向真值校验
│   ├── exchange_rate.py              M4 Step4: IMF汇率换算
│   ├── region_mapping.py             M7: Lloyd行政区划映射
│   ├── cube_api.py                   M6/M7: SSTCube OLAP + H3
│   └── run_pipeline.py               一键运行入口
├── data/
│   ├── indicator_dict.json           指标字典
│   ├── unit_rules.json               单位换算规则
│   ├── dimension_codes.json          维度代码
│   ├── quality_rules.json            质量规则
│   ├── exchange_rates.json           2003-2024人民币汇率
│   └── region_gps.json               70+行政区划GPS
├── tests/
│   └── test_smoke.py                 冒烟测试
├── requirements.txt
└── README.md
```

---

## 九、一键运行

```bash
cd packages/data-integration
pip install -r requirements.txt
python -m src.run_pipeline --input <数据目录> --output output/
```

---

> **本文档为 EconDataForge 最终整合方案，以 EconDataForge 第一版架构为骨架，注入 SST-Cube Extractor v3 的实战算法和实测参数。**
> 日期：2026-08-29
