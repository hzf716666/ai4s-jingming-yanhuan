#!/usr/bin/env python3
"""一次性技能合并迁移脚本（v5 方案，见 docs/skills-consolidation-plan.md）。
【状态】已于 2026-09-01 执行完毕（66→11），旧技能目录已删除；本脚本保留用于
审计与恢复对照（--verify-only 校验映射完整性，源头已不在不可重跑迁移）。
迁移报告：docs/skills-consolidation-migration-report.json。

功能：
1. 全量校验 66 个旧技能 SKILL.md 都在映射表中（缺一即报错，防漏）；
2. 每个旧技能目录整体归档到新技能 references/<旧目录名>/
   （SKILL.md 改名 README.md，references/ 与 assets/ 原样保留 → 内容零丢失）；
3. 每个新技能生成中文骨架 SKILL.md（frontmatter + 子模块索引表）；
4. 活化脚本按附录 B 拷贝到新技能 scripts/ 或 assets/（原始文件仍留在 references/ 归档中）；
5. 领域科学 → _archive/（SKILL.md 改名 README.md，不再计入技能数）；
6. 输出迁移报告 runtime/skills/_migration_report.json。

用法：
    python scripts/dev/consolidate_skills.py --verify-only   # 只校验映射完整性
    python scripts/dev/consolidate_skills.py                 # 执行迁移（幂等：已归档目录跳过）
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS = ROOT / "runtime" / "skills"
REPORT = SKILLS / "_migration_report.json"

# (新技能目录, [旧技能目录, ...])
MAP = [
    ("00-通用工具/econ-orchestrator", [
        "00-通用工具/科研编排主控",
        "00-通用工具/智能体进化",
        "02-假设设计/自主科研流水线",
        "00-通用工具/onescience-orchestrator",
        "04-实验执行/onescience-research-workflow",
    ]),
    ("00-通用工具/大文件安全读取", [  # 存量技能：整目录移动，正文后续中文重写
        "04-实验执行/大文件安全读取",
    ]),
    ("00-通用工具/云端计算", [
        "00-通用工具/onescience-cli",
        "00-通用工具/onescience-installer",
        "00-通用工具/onescience-runsite",
        "00-通用工具/onescience-runtime",
        "00-通用工具/超算平台助手",
        "04-实验执行/云端GPU执行",
        "04-实验执行/远程计算作业",
        "04-实验执行/资源规划",
    ]),
    ("08-经济实证/econ-resources", [  # 资源层: primitives(资源技能化规范) + 新资产整理
        "00-通用工具/onescience-primitives",
    ]),
    ("08-经济实证/econ-planner", [
        "02-假设设计/研究范围界定",
        "02-假设设计/假设生成",
        "02-假设设计/假设生成方法",
        "02-假设设计/研究决策",
        "01-文献调研/知识综合",
        "01-文献调研/文献策略",
    ]),
    ("08-经济实证/econ-review", [
        "08-经济实证/hypothesis-review",
        "08-经济实证/econ-stat-review",
        "05-分析验证/统计检验报告",
        "05-分析验证/同行评审",
        "05-分析验证/质量把关",
    ]),
    ("08-经济实证/econ-decompose", [
        "08-经济实证/econ-decompose-question",
        "08-经济实证/econ-literature",
        "01-文献调研/文献收集",
        "01-文献调研/文献筛选",
        "01-文献调研/文献检索方法",
        "01-文献调研/引用验证",
        "03-数据工程/知识抽取",
        "03-数据工程/onescience-paper-repro",
    ]),
    ("08-经济实证/econ-data", [
        "08-经济实证/econ-filter-subproblems",
        "08-经济实证/econ-data-fill",
        "08-经济实证/econ-data-profile",
        "03-数据工程/onescience-data-profile",
        "03-数据工程/onescience-dataset-builder",
        "03-数据工程/onescience-data-analyzer",
    ]),
    ("08-经济实证/econ-run", [
        "08-经济实证/econ-run-experiment",
        "02-假设设计/实验方案设计",
        "04-实验执行/代码生成",
        "04-实验执行/实验执行",
        "04-实验执行/迭代优化",
        "04-实验执行/领域正确性检查",
        "04-实验执行/onescience-coder",
        "04-实验执行/onescience-infer",
        "04-实验执行/onescience-trainer",
        "04-实验执行/onescience-parallel",
    ]),
    ("08-经济实证/econ-synthesis", [
        "08-经济实证/econ-synthesize-results",
        "05-分析验证/结果分析",
        "05-分析验证/统计完整性检查",
        "05-分析验证/科学图表设计",
        "05-分析验证/可追溯性审计",
    ]),
    ("08-经济实证/econ-write", [
        "08-经济实证/econ-write-paper",
        "06-写作发表/论文结构规划",
        "06-写作发表/论文初稿",
        "06-写作发表/论文修订",
        "06-写作发表/学术论文写作",
        "06-写作发表/发表级图表规范",
        "06-写作发表/知识存档",
        "06-写作发表/导出发布",
        "06-写作发表/onescience-modelscope-publish",
    ]),
]

# 领域科学 → _archive（不再是技能）
ARCHIVE = [
    ("07-领域科学/生物信息学分析", "领域科学"),
    ("07-领域科学/计算化学分析", "领域科学"),
]

# 活化脚本： (来源旧目录相对路径, 新技能目录, 目标相对路径)
LIVE_SCRIPTS = [
    ("00-通用工具/onescience-runsite/scripts/runsite_config.py", "00-通用工具/云端计算", "scripts/runsite_config.py"),
    ("00-通用工具/onescience-runsite/scripts/scnet_config.py", "00-通用工具/云端计算", "scripts/scnet_config.py"),
    ("00-通用工具/onescience-runsite/scripts/ssh_config.py", "00-通用工具/云端计算", "scripts/ssh_config.py"),
    ("00-通用工具/超算平台助手/scripts/scnet.py", "00-通用工具/云端计算", "scripts/scnet/scnet.py"),
    ("00-通用工具/超算平台助手/scripts/scnet_chat.py", "00-通用工具/云端计算", "scripts/scnet/scnet_chat.py"),
    ("00-通用工具/超算平台助手/scripts/scnet_file.py", "00-通用工具/云端计算", "scripts/scnet/scnet_file.py"),
    ("00-通用工具/超算平台助手/scripts/scnet_container.py", "00-通用工具/云端计算", "scripts/scnet/scnet_container.py"),
    ("00-通用工具/超算平台助手/scripts/scnet_notebook.py", "00-通用工具/云端计算", "scripts/scnet/scnet_notebook.py"),
    ("00-通用工具/超算平台助手/scripts/cache.py", "00-通用工具/云端计算", "scripts/scnet/cache.py"),
    ("00-通用工具/超算平台助手/scripts/compat.py", "00-通用工具/云端计算", "scripts/scnet/compat.py"),
    ("00-通用工具/超算平台助手/scripts/config.py", "00-通用工具/云端计算", "scripts/scnet/config.py"),
    ("00-通用工具/超算平台助手/scripts/config_manager.py", "00-通用工具/云端计算", "scripts/scnet/config_manager.py"),
    ("00-通用工具/超算平台助手/scripts/file.py", "00-通用工具/云端计算", "scripts/scnet/file.py"),
    ("00-通用工具/超算平台助手/scripts/job.py", "00-通用工具/云端计算", "scripts/scnet/job.py"),
    ("00-通用工具/超算平台助手/scripts/user.py", "00-通用工具/云端计算", "scripts/scnet/user.py"),
    ("00-通用工具/超算平台助手/scripts/utils.py", "00-通用工具/云端计算", "scripts/scnet/utils.py"),
    ("00-通用工具/超算平台助手/assets/config.example.env", "00-通用工具/云端计算", "assets/scnet/config.example.env"),
    ("00-通用工具/超算平台助手/assets/test_cases.json", "00-通用工具/云端计算", "assets/scnet/test_cases.json"),
    ("00-通用工具/超算平台助手/assets/run_integration_tests.py", "00-通用工具/云端计算", "assets/scnet/run_integration_tests.py"),
    ("00-通用工具/超算平台助手/assets/test_intent_unit.py", "00-通用工具/云端计算", "assets/scnet/test_intent_unit.py"),
    ("04-实验执行/云端GPU执行/record_run.py", "00-通用工具/云端计算", "scripts/record_run.py"),
    ("04-实验执行/领域正确性检查/domain_check.py", "08-经济实证/econ-run", "scripts/domain_check.py"),
    ("05-分析验证/可追溯性审计/pdf_extract.py", "08-经济实证/econ-synthesis", "scripts/pdf_extract.py"),
    ("05-分析验证/统计完整性检查/stats_integrity_check.py", "08-经济实证/econ-synthesis", "scripts/stats_integrity_check.py"),
    ("06-写作发表/发表级图表规范/jingming.mplstyle", "08-经济实证/econ-write", "assets/jingming.mplstyle"),
]

# 新技能元数据（骨架用；正文本体随后人工打磨覆盖）
META = {
    "00-通用工具/econ-orchestrator": dict(type="orchestrator", stage=0,
        stages=list(range(0, 8)), name="econ-orchestrator", cn="经管编排主控",
        desc="经管实证总编控: 路由表+技能分值识别意图→召回资源/专家→按P0~P7编排执行顺序→调度执行层→Task State→进度上报; 非经管任务走通用通道"),
    "08-经济实证/econ-resources": dict(type="resource", name="econ-resources", cn="经管资源召回",
        desc="经管知识资产召回: 数据源63源/方法卡12张索引/指标口径/FKG图谱/因果识别策略; 输出 resource_retrieval_result, 执行技能不得直读资产"),
    "00-通用工具/大文件安全读取": dict(type="executor", name="大文件安全读取", cn="大文件安全读取",
        desc="大数据文件(CSV/Parquet/HDF5/FITS/NetCDF/FASTQ/VCF/ROOT等)读取前安全探测与采样, 返回小指针避免内存溢出"),
    "00-通用工具/云端计算": dict(type="executor", name="云端计算", cn="云端计算",
        desc="计算通道工具: 远程SSH/SLURM/SCNet/Modal通道选择+环境安装修复+作业提交+资源规划+失败诊断重试"),
    "08-经济实证/econ-planner": dict(type="expert", name="econ-planner", cn="经管专家规划",
        desc="经管规划决策(专家层): 拆解方案(relation/identification/data_needed/method_cards四件套)+A/B/C分级+实验方案+文献检索计划+研究决策; 产出planner_proposal不执行"),
    "08-经济实证/econ-review": dict(type="executor", name="econ-review", cn="假设与结果评审",
        desc="评审执行: P0研究想法四档评审(exceptional/strong/fair/limited→概率分布+香农熵置信度)+P7统计自检与VLM图表评审(≤2轮)+同行评审+质量把关"),
    "08-经济实证/econ-decompose": dict(type="executor", name="econ-decompose", cn="拆解与文献",
        desc="P1假设拆解(3~6子问题DAG,四件套硬约束,标gap即补)+P1.5经管文献检索(OpenAlex/参考文献/4层引用验证)+知识抽取"),
    "08-经济实证/econ-data": dict(type="executor", name="econ-data", cn="过滤与数据",
        desc="P2子问题三关过滤(A/B/C分级+人工门禁)+P3数据盘点(probe_profile.py)+P2.5外部补数+数据集构建/分析通道"),
    "08-经济实证/econ-run": dict(type="executor", name="econ-run", cn="实验执行",
        desc="P4实验执行: runner.py契约+统计护栏(6条)+代码生成/分步编码/迭代优化/领域正确性检查+模型训练推理分布式通道"),
    "08-经济实证/econ-synthesis": dict(type="executor", name="econ-synthesis", cn="整合与分析",
        desc="P5结果整合: 汇总results/run_XX→四档判定(支持/弱支持/不支持/证据不足)+统计完整性检查+图表设计+可追溯性审计+研究决策"),
    "08-经济实证/econ-write": dict(type="executor", name="econ-write", cn="写作与评审",
        desc="P6经管实证论文写作(变量表→描述统计→基准回归→稳健性→异质性)+P7统计自检+论文修订+发表级图表规范+导出发布/模型发布"),
}


def old_skill_dirs() -> list[Path]:
    return sorted(
        p.parent for p in SKILLS.rglob("SKILL.md")
        if "external" not in p.parts and "_archive" not in p.parts
        and p.parent.name != "econ-orchestrator"  # 排除新骨架
    )


def verify():
    mapped = {p: t for t, olds in MAP for p in olds}
    # 领域科学走 ARCHIVE 归档, 不算入技能映射
    for old_rel, _ in ARCHIVE:
        mapped[old_rel] = "_archive"
    existing_rel = {p.relative_to(SKILLS).as_posix() for p in old_skill_dirs()}
    missing = existing_rel - set(mapped)
    extra = set(mapped) - existing_rel
    assert not missing, f"未映射旧技能: {sorted(missing)}"
    assert not extra, f"映射了不存在的旧技能: {sorted(extra)}"
    print(f"[verify] 校验通过: {len(existing_rel)} 个旧技能全部在映射表中")
    return sorted(existing_rel)


def archive_skill(target_rel: str, old_rel: str, report: dict):
    old = SKILLS / old_rel
    dest = SKILLS / target_rel / "references" / old.name
    if dest.exists():
        print(f"[skip ] 已归档: {old_rel} → {dest.relative_to(SKILLS)}")
        report.setdefault(target_rel, []).append({"old": old_rel, "dest": dest.relative_to(SKILLS).as_posix(), "skipped": True})
        return
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(old.rglob("*")):
        if f.is_dir():
            (dest / f.relative_to(old)).mkdir(parents=True, exist_ok=True)
            continue
        rel = f.relative_to(old)
        td = dest / rel
        td.parent.mkdir(parents=True, exist_ok=True)
        if rel.name == "SKILL.md":
            shutil.copy2(f, td.parent / "README.md")
        else:
            shutil.copy2(f, td)
    print(f"[arch ] {old_rel} → {dest.relative_to(SKILLS)}")
    report.setdefault(target_rel, []).append({"old": old_rel, "dest": dest.relative_to(SKILLS).as_posix()})


def gen_skel(target_rel: str, report: dict):
    meta = META[target_rel]
    target = SKILLS / target_rel
    sk = target / "SKILL.md"
    if sk.exists():
        print(f"[skip ] 骨架已存在: {sk.relative_to(SKILLS)}")
        return
    subs = dict(MAP).get(target_rel, [])
    lines = ["---",
             f"name: {meta['name']}",
             f"type: {meta['type']}",
             f"description: {meta['desc']}".replace("\n", " "),
             'version: "2.0.0"',
             f"stage: {meta.get('stage', '')}",
             f"stages: {json.dumps(meta.get('stages', []), ensure_ascii=False)}",
             f"sub_skills: {json.dumps([s.split('/')[-1] for s in subs], ensure_ascii=False)}",
             "source: econ",
             "---",
             "",
             f"# {meta['cn']}",
             "",
             "> 本文件为合并骨架，正文待打磨。子模块索引：",
             "",
             "| 原子技能 | 归档位置 |",
             "|---|---|",
             ]
    for s in subs:
        lines.append(f"| {s.split('/')[-1]} | `references/{s.split('/')[-1]}/README.md` |")
    lines += ["", "（完整正文打磨后覆盖本文件）", ""]
    sk.write_text("\n".join(lines), encoding="utf-8")
    print(f"[skel ] {sk.relative_to(SKILLS)}")


def live_scripts(report: dict):
    for src_rel, target_rel, dst_rel in LIVE_SCRIPTS:
        src = SKILLS / src_rel
        dst = SKILLS / target_rel / dst_rel
        if not src.exists():
            print(f"[warn ] 脚本不存在: {src_rel}")
            continue
        if dst.exists():
            print(f"[skip ] 脚本已存在: {dst.relative_to(SKILLS)}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"[live ] {src_rel} → {dst.relative_to(SKILLS)}")
        report.setdefault("_live_scripts", []).append({"src": src_rel, "dst": dst.relative_to(SKILLS).as_posix()})


def archive_domain():
    dst_root = SKILLS / "_archive" / "领域科学"
    for old_rel, _ in ARCHIVE:
        old = SKILLS / old_rel
        dest = dst_root / old.name
        if dest.exists():
            print(f"[skip ] 已归档: {old_rel} → {dest.relative_to(SKILLS)}")
            continue
        shutil.copytree(old, dest)
        # SKILL.md 改名 README.md 使其不再被识别为技能
        if (dest / "SKILL.md").exists():
            (dest / "SKILL.md").replace(dest / "README.md")
        print(f"[arch ] 领域科学 {old_rel} → {dest.relative_to(SKILLS)} (SKILL.md→README.md)")


def main():
    verify()
    if "--verify-only" in sys.argv:
        return
    MAPD = {t: olds for t, olds in MAP}
    targets = sorted(MAPD)
    report = {}
    for t in targets:
        for old in MAPD[t]:
            archive_skill(t, old, report)
    # 大文件安全读取: 整体移动(整目录, 含 SKILL.md)
    src_dir = SKILLS / "04-实验执行" / "大文件安全读取"
    dst_dir = SKILLS / "00-通用工具" / "大文件安全读取"
    if src_dir.exists() and not dst_dir.exists():
        shutil.move(str(src_dir), str(dst_dir))
        print(f"[move ] 大文件安全读取 → {dst_dir.relative_to(SKILLS)}")
    live_scripts(report)
    archive_domain()
    for t in targets:
        gen_skel(t, report)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n完成. 报告: {REPORT}\n下一步: 打磨 11 个正文 → 更新引用点 → 验证")


if __name__ == "__main__":
    main()
