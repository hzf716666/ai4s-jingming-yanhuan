# EconDataForge — 多源数据自动抽取与整合模块

> 计量经济学科研流程中的多源异构数据自动抽取、整合与标准化系统

## 快速开始

```bash
cd packages/data-integration
pip install -r requirements.txt
python -m src.run_pipeline --input <数据目录> --output output/
```

## 测试

```bash
python tests/test_smoke.py
```

## 架构

七模块流水线：

| 模块 | 功能 | 论文溯源 |
|------|------|---------|
| M1 | 需求理解 | SciEx |
| M2 | 来源发现+质量评估 | Färber 2017 |
| M3 | 多格式解析 (5 Pipeline) | 吴廷鑫 §2.3.5 |
| M4 | 字段对齐+整合 | 张辉§5 + HLER+PIEVO + 论文p6 |
| M5 | 质量检查+闭环修正 | Casini-Perron + Lenz-Shoshani |
| M6 | 结构化输出 | — |
| M7 | GIS关联+可视化 | Lloyd 2019 + H3 |

详见 [docs/FINAL_INTEGRATED_DESIGN.md](docs/FINAL_INTEGRATED_DESIGN.md)

## 输出文件

```
output/
├── sst_cube/
│   ├── long_table_fused.csv      七元组长表
│   ├── h3_cube_res5.json         H3 GeoCube
│   ├── anomalies.json            异常检测
│   ├── structural_breaks.json    结构突变
│   ├── summarizability.json      汇总合法性
│   ├── reverse_validation.json   反向校验
│   ├── fusion_debug.json         融合证据链
│   └── source_quality.json       数据源质量
└── eval/
    ├── report.md                 综合评测报告
    └── scores.json               评分数据
```
