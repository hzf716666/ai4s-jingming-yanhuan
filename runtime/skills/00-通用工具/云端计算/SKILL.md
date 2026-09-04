---
name: 云端计算
type: executor
description: 计算通道工具(通用): 远程 SSH/SLURM/SCNet(超算平台助手全套)/Modal 通道选择 + 运行站点配置(runsite) + 环境安装修复(conda) + 作业提交与文件管理 + 资源规划(资源摘要/通道自动选择) + 失败诊断重试(discover→preflight→execute→diagnose 闭环)。
version: "2.0.0"
stage: 60
stages: [60]
sub_skills: ["onescience-cli", "onescience-installer", "onescience-runsite", "onescience-runtime", "超算平台助手", "云端GPU执行", "远程计算作业", "资源规划"]
source: econ
---

# 云端计算 — 计算通道工具

> 通用通道（不属 P 链）。任何技能需要"算力"时，把**规格与步骤**交给本技能，
> 它负责选通道、配环境、提交、监控、诊断与重试。本技能不做科研决策。

## 一、通道选择（按用户语境与资源需求）

| 通道 | 适用 | 关键资产/脚本 |
|---|---|---|
| **本地** | 小数据/短任务 | 直接执行，无需配置 |
| **SSH/SLURM 远程** | 集群作业 | `scripts/runsite_config.py`、`scripts/ssh_config.py`（站点配置）；`scripts/record_run.py`（作业记录） |
| **SCNet 超算** | 超算平台 | `scripts/scnet/`（scnet_chat.py 等全套：作业提交/查询/文件/容器/notebook；`assets/scnet/config.example.env`） |
| **Modal 云端** | 重型/GPU | `scripts/record_run.py`（Modal 函数部署与执行记录） |

选择逻辑（来自资源规划技能）：先看资源摘要（数据量/GPU 需求/时长），
再按 `本地 → 远程 SSH → 超算 SCNet → Modal` 的复杂度递增顺序选，避免过度配置。

## 二、标准闭环（discover → preflight → execute → diagnose）

1. **discover**：读运行站点配置（`assets/runsite.example.json` 的对应配置；缺失走
   runsite 流程补问/复用）；
2. **preflight**：验证远程连接、确认 DCU/GPU 类型、modules 写入、目录可写；
   环境缺失/版本不符 → 进入安装修复（conda 创建/复用，见
   `references/onescience-installer/README.md`）；
3. **execute**：提交作业（或本地执行）→ 监控状态 → 收集输出；
   资源不可用（partition/gpus_per_node/memory 不足）→ 探测可用 SLURM 资源，
   受控调整后重试；
4. **diagnose**：失败时按证据链诊断（stderr 尾部 → 资源日志 → 回归最小复现）；
   修复循环有上限（默认 3 次），超限上报 blocked 附证据。

## 三、作业与文件管理

- 作业：提交/查询/取消；结果回传格式统一为
  `{job_id, status, stdout_tail, stderr_tail, outputs[]}`；
- 文件：上传/下载/远程目录浏览（超算通道用 scnet 文件子命令）；
- 环境：`scripts/scnet/` 的 config_manager 管理账户与区域切换。

## 四、资源规划（并入）

- 估算：数据规模 × 算子复杂度 → CPU/GPU/内存/时长建议；
- 输出到 `resources_plan.md`（含 通道选择理由），供编排层与执行层引用；
- 与 P4 的接口：econ-run 只提交规格，不写通道细节。

## 五、子模块索引

| 原子技能 | 归档 | 何时读 |
|---|---|---|
| onescience-runtime | references/onescience-runtime/README.md | 闭环/执行路由细节 |
| onescience-installer | references/onescience-installer/README.md | conda 环境规则 |
| onescience-runsite | references/onescience-runsite/README.md | 站点配置字段 |
| onescience-cli | references/onescience-cli/README.md | 命令调度/级别 |
| 超算平台助手 | references/超算平台助手/README.md | SCNet API 细节 |
| 云端GPU执行 / 远程计算作业 | references/云端GPU执行/README.md、references/远程计算作业/README.md | 通道规格 |
| 资源规划 | references/资源规划/README.md | 估算模型 |
