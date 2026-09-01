---
name: econ-data-fill
type: executor
description: 数据缺口主动寻找: 检测到 P3 数据盘点中指标缺失时, 去外部经济数据源(统计局/年鉴/OECD/数据库)检索补充数据, 产出 data_gap_report.md + data_supplement.json
version: "1.0.0"
phase: analysis
stage: 10
inputs: ["data_profile.md", "filtered_problems.json"]
outputs: ["data_gap_report.md", "data_supplement.json"]
dependencies: ["econ-data-profile"]
natural_next: ["econ-run-experiment"]
gate: false
idempotent: false
reentrant_strategy: new_run
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["数据缺失", "数据补充", "找数据", "外部数据", "data gap", "补数据"]
source: custom
max_retries: 2
timeout_sec: 1800
---

# econ-data-fill — 数据缺口主动寻找

## 目标
P3 数据盘点(cat profile)或 P2 过滤发现某子问题的 X/Y 指标缺失时,**主动去外部经济数据源检索补充**,而不是把子问题降级 C 档了事。

## 核心原则
1. **数据缺失 ≠ 不可做** —— 先尝试找数据,找不到才降级。
2. **引用来源**:每条补充数据必须记来源(机构/网站/年份/URL),禁编造指标。
3. **可执行性**:找到的数据要能落到 `data/records.json` 同构格式(space×year×indicator×value×unit×source),供 runner 实验直接用。

## 外部数据源优先级(经管实证常用,按序尝试)
1. **官方统计**:国家统计局(http://data.stats.gov.cn)、各省统计局、湖北省统计局、火炬统计年鉴(本地 `E:\tb\B中国火炬统计年鉴`)
2. **学术/政府公开库**:OECD(https://stats.oecd.org)、世界银行(https://databank.worldbank.org)、IMF、全国科技经费投入统计公报
3. **企业/行业库**:Wind/CSMAR(有账号时)、行业协会年报、上市公司年报(巨潮/上交所)
4. **政策文件**:政府工作报告、发改委/科技部公开数据

## 步骤
1. **读 data_profile.md**:列出有 data_gap 的子问题与缺的指标名。
2. **逐个缺口**:
   - 用 curl/requests 访问上述官方源的公开 API/下载页(注意本环境网络限制,国家数据网/统计局可能被挡 → 用浏览器或无缓存 URL 重试,或标注"网络受限"再试下一源)
   - 若本地有(如火炬年鉴),直接读 `E:\tb\B中国火炬统计年鉴` 下对应表
3. **产出 `data_gap_report.md`**:每个缺口 → 状态(已找到/网络受限/源无此指标)+ 尝试过的源 + 找到的数值/坐标。
4. **产出 `data_supplement.json`**:找到的数据以 `{space, year, indicator, value, unit, source, source_url}` 格式;同时**追加到 `data/records.json`**(保持同构,供 runner 直接使用)。
5. 汇报:哪些缺口已补,哪些确实找不到(找不到才允许在 P2 里标 B/C 档)。

## 输出格式(data_supplement.json)
```json
{"supplements": [
  {"space": "湖北", "year": "2024", "indicator": "风险投资额", "value": 851315,
   "unit": "万元", "source": "湖北省科技厅年报 2024", "source_url": "..."}
]}
```

## 质量自查
- [ ] 每条补充数据都有 source/source_url,没有编造指标
- [ ] 确实找不到的缺口在 data_gap_report.md 里说明尝试过的源
- [ ] 找到的数据已追加进 data/records.json(runner 可直接用)
