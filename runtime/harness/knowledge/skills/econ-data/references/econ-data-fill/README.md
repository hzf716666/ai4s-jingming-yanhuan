---
name: econ-data-fill
type: executor
description: 数据缺口主动寻找: 检测到 P3 数据盘点或 P2 过滤中出现指标/空间/年份缺失时, 必须先主动去外部经济数据源(按本机实测可达渠道表)检索补充, 产出 data_gap_report.md + data_supplement.json; 未给出"尝试矩阵"前不允许降级子问题或停下来等用户
version: "1.1.0"
phase: analysis
stage: 10
inputs: ["data_profile.md", "filtered_problems.json"]
outputs: ["data_gap_report.md", "data_supplement.json"]
dependencies: []
natural_next: ["econ-run-experiment"]
gate: false
idempotent: false
reentrant_strategy: skip_if_cached
entry_points: []
mid_chain_entry: true
domain: econ
trigger_keywords: ["数据缺失", "数据补充", "找数据", "外部数据", "data gap", "补数据", "缺数据", "没有这个数据"]
source: custom
max_retries: 2
timeout_sec: 1800
---

# econ-data-fill — 数据缺口主动寻找

> 核心规则：**"数据缺失"首先是行动信号,不是停止信号**。一旦检测到缺口,
> 第一步就是主动找——按下面的实测渠道表充分尝试后仍没有,才允许标注
> "待外部数据";绝不允许没试够就降级子问题,或把"缺数据"当理由停下等用户。

## 触发条件(任一即触发)

- P1 拆解中标了 `data_gap: true` 的子问题;
- P3 盘点(probe_profile)发现缺失指标/截面;
- P2 过滤的"数据可行性"关发现 data/ 撑不住;
- 用户/评审提到"没这个数据/找一下这个数据"。

## 本机实测渠道表(2026-09-02 实测,按可达性优先; 别再把时间砸在不可达源上)

| 渠道 | 地址与可用性 | 抓取方法 |
|---|---|---|
| **湖北省科技厅**【可达】 | `http://kjt.hubei.gov.cn` (**http 200**; https 偶发超时) | curl `-s -L` 带 UA; 站内搜索 `so/s?qt=<关键词>`; 政府信息公开 `zfxxgk_GK2020/`; 找集群试点名单/政策目录 |
| **武汉市统计局**【可达】 | `https://tjj.wuhan.gov.cn` (200) | 目录 `tjfw/`(统计分析与年鉴)、`zfxxgk/fdzdgknr/tjsj/`(统计数据); 分区县GDP/统计公报 |
| **国家统计局**【页面可达/接口403】 | `https://data.stats.gov.cn` | 页面 200 但 `easyquery.htm` 接口 403 → **必须浏览器**(带 Referer/Cookie), 或页面检索"分县(市、区)地区生产总值" |
| **湖北省政府门户**【首页被拦/文章可试】 | `https://www.hubei.gov.cn` | 首页 412; 具体文章页 `t*.shtml` 带 UA+Referer 可抓(统计公报/政策文件) |
| **各市统计局**【逐一探测】 | `tjj.<city>.gov.cn`(宜昌 000 不可达示例) | 先 curl 探测, 200 再抓目录 |
| **OECD/世行** | stats.oecd.org / databank.worldbank.org | 有专用 MCP/CSV 落盘路径时优先(本机 E:\tb\oecd_data) |

**明确不可达(别再浪费时间)**: `tjj.hubei.gov.cn` 年度数据 404; `en/zh.wikipedia.org` 超时; `baike.baidu.com` 404。
抓取参数统一: `curl -s -L -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"`; 接口 403/需 JS → 换浏览器(agent-browser/playwright)。

## 尝试矩阵(硬门槛)

在**任何**"降级/标注待数据/询问用户"之前,必须完成:
1. **≥2 类渠道 × ≥5 个动作**(其中至少 1 次浏览器尝试);
2. 逐条记录到 `data_gap_report.md` 的尝试矩阵表:`源/URL | 动作 | 结果码 | 拿到什么`;
3. 矩阵齐全仍未找到 → 才允许写"网络受限/源无此指标"。

未满足矩阵就下结论 → 视为**未充分尝试**,应当继续找,而不是直接交给用户拍板。

## 落地要求

- 找到 → 转成 `data/records.json` 同构条目 `{space, year, indicator, value, unit, source, source_url}`(禁编造指标, 每条必须带 source/source_url), 写 `data_supplement.json` 说明补采来源与置信;
- 找不到 → `data_gap_report.md` 写明: 剩余缺口 + 尝试矩阵 + **可行替代方案**(代理变量/派生归并/报告口径核算/子样本), 并将子问题标为 **B 档(代理)** 或"待外部数据"——**不静默降级为 C**;
- 缺口记录精确到子问题 `data_needed`(指标名/空间单元/年份/分组), 按需补采, 不整库重复拉取。

## 参考示例(输出格式)

```json
{"supplements": [
  {"space": "武汉", "year": "2024", "indicator": "生产总值", "value": 2.1e12,
   "unit": "元", "source": "武汉市统计局 2024 统计公报", "source_url": "https://tjj.wuhan.gov.cn/..."}
]}
```

## 质量自查
- [ ] 尝试矩阵 ≥2 渠道 × ≥5 动作(含浏览器 1 次)已记录
- [ ] 每条补充数据都有 source/source_url, 没有编造指标
- [ ] 确实找不到的缺口有替代方案建议, 未静默降级为 C
- [ ] 找到的数据已追加进 data/records.json(runner 可直接用)
