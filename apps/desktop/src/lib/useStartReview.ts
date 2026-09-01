// "完整评审报告"工作流 hook: 点假设"评审报告" → 建研究项目文件夹 + 写任务书(含评审要求)
// + 新会话发评审指令 → 跳工作台看 AI 在对话中生成完整报告(仿 useStartResearch 的机制)。
// 关键: 报告由 agent 在新对话中生成并展示(不像快速评审那样 API 静态返回), 用户可继续追问。
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRuntimeStore } from "@/lib/runtime";
import { writeWorkspaceFile, absoluteArtifactPath } from "@/lib/artifactFile";
import { workspacePath, isTauri } from "@/lib/tauri";
import { fetchRecords, type HypothesisSummary } from "@/lib/researchLib";

export function useStartReview() {
  const navigate = useNavigate();
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const store = useRuntimeStore;

  async function startReview(h: HypothesisSummary) {
    if (starting) return;
    setStarting(h.id);
    setError(null);
    try {
      const name = `研究-${h.id}-评审-${new Date().toISOString().slice(0, 10)}`;
      // 1) 建研究项目 + 切工作区(复用 useStartResearch 的项目机制)
      const project = await store.getState().createProject(name);
      if (!project) throw new Error("创建研究项目失败");

      // 2) 轮询确认 Tauri 侧 active workspace 已指向项目
      if (isTauri) {
        for (let i = 0; i < 25; i++) {
          const cur = await workspacePath();
          if (cur && cur.replace(/\\\\?\\/, "") === project.path.replace(/\\\\?\\/, "")) break;
          await new Promise((r) => setTimeout(r, 200));
        }
      }

      // 3) 写任务书(评审版) + 数据快照 + 反馈记录工具脚本
      const [records] = await Promise.all([fetchRecords()]);
      const brief = buildReviewBrief(h, new Date().toLocaleString("zh-CN"));
      const projName = project.path.split(/[\\\\/]/).pop()!;
      const rel = (p: string) => `${projName}/${p}`;
      await writeWorkspaceFile(rel("README.md"), brief, "base");
      await writeWorkspaceFile(rel("data/records.json"), JSON.stringify(records), "base");
      await writeWorkspaceFile(rel("tools/record_feedback.py"), RECORD_FEEDBACK_SCRIPT, "base");
      // 验证至少一个文件真的在项目目录
      const abs = await absoluteArtifactPath(`${projName}/data/records.json`, "base");
      if (!abs) throw new Error("数据写入失败: 未检测到 data/records.json 在项目 " + projName);

      // 4) 在(已切换)研究目录开新 draft 会话, 发评审指令(报告 + 用户反馈融合)
      const runtime = store.getState();
      await runtime.startDraftInWorkspace(project.path);
      await runtime.sendPrompt(
        `这是研究项目 ${h.id} 的评审任务书(README.md)。请用技能 hypothesis-review 对这条候选假设做完整四档评审:` +
        `请阅读 README.md(含假设/研究问题/分析建议/预期发现/支撑证据)与 data/records.json 与 tools/record_feedback.py,` +
        `然后**在当前对话中输出一份完整 Markdown 评审报告**: ` +
        `一句话结论(集成预测 Top/Top-/Good/Fair + 置信度 + 一致数) → 四档概率分布(表格 + \`\`\`tierchart\`\`\` JSON 块, 前端渲染仪表图) → ` +
        `香农熵置信度分析 → 新颖性-有用性双透镜(1-5 分, 指出短板) → 强化建议(往上一档推的 2-4 条) → ` +
        `限制与注意事项 → 相关文献锚点(检索 5 篇最相关, 如可)。` +
        `报告要完整展现, 并落盘 review_report.md。` +
        `\n\n**评审完成后, 请等用户表态**: 请用户直接回复 \`采纳\` 或 \`否决\`(可附带他们的观点/原因)。` +
        `收到后运行 \`python tools/record_feedback.py ${h.id} <adopt|reject> "<用户观点>"\` 把评价写入向量库(用户反馈与评审融合, 未来重新生成假设时 AI 会学习), ` +
        `并把用户观点追加到 review_report.md 的"用户评价"一节, 然后讨论下一步(是否接续正式研究 P1 拆解)。`,
      );

      // 5) 跳工作台, 用户直接看到 AI 在对话中生成报告
      navigate("/live");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(null);
    }
  }

  return { starting, error, startReview };
}

/** 反馈记录工具脚本(agent 在对话中运行: 把用户采纳/否决+观点写入向量库) */
const RECORD_FEEDBACK_SCRIPT = `# -*- coding: utf-8 -*-
"""记录用户对假设的评价到向量库(供 AI 重新生成学习).
用法: python tools/record_feedback.py <hypothesis_id> <adopt|reject> "<观点文本>"
"""
import json
import sys
import urllib.request

if len(sys.argv) < 3:
    print("usage: python tools/record_feedback.py <hypothesis_id> <adopt|reject> [观点]")
    sys.exit(1)

hid, verdict = sys.argv[1], sys.argv[2]
note = sys.argv[3] if len(sys.argv) > 3 else ""
if verdict not in ("adopt", "reject"):
    print("verdict must be adopt or reject")
    sys.exit(1)

req = urllib.request.Request(
    "http://127.0.0.1:8787/api/hypotheses/feedback",
    data=json.dumps({"id": hid, "verdict": verdict, "note": note}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(resp.read().decode())
except Exception as e:
    print(f"记录失败(检查数据面板 8787 是否在线): {e}")
`;

/** 评审版任务书(在 buildBrief 之上增加评审要求, 并省略七阶段执行流程) */
export function buildReviewBrief(h: HypothesisSummary, date: string): string {
  return `# 研究评审任务书 — ${h.id}

> 由知识图谱"完整评审报告"生成 · ${date}
> 本目录是评审工作区: 数据在 data/, AI 在对话中生成完整评审报告, 完成后落盘 review_report.md。

## 待评审假设

${h.hypothesis}

## 研究问题

${h.research_question}

## 图模式

${h.graph_pattern}

## 分析建议方法

${h.analysis_method}

## 预期发现

${h.expected_finding}

## 支撑证据

${(h.evidence ?? []).map((e) => `- ${e.k}: ${e.v}`).join("\n")}

## 评审要求(技能 hypothesis-review)

1. 四档标签: **exceptional(Top 顶级) / strong(Top- 强顶) / fair(Good 中档) / limited(Fair 区域低档)**
2. 输出完整 Markdown 评审报告(见对话指令), 并落盘 review_report.md
3. 观测数据场景: 禁用因果语言; 概率四档和=1; 不编造文献
4. 报告是对话的一部分: 生成后在对话中与用户讨论, 可追问展开
`;
}
