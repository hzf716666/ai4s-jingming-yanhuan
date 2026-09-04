// "开始研究"流程 hook: 点假设 → 建研究项目 + 写数据快照 + 新会话发任务 → 跳工作台。
// 可靠性关键: 不依赖"当前工作区已切换"的时序 —— 显式把数据用 root="base" +
// 项目相对路径写入, 并轮询 workspacePath() 确认 AI 会话将落在项目目录。
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRuntimeStore } from "@/lib/runtime";
import { writeWorkspaceFile, absoluteArtifactPath } from "@/lib/artifactFile";
import { workspacePath, isTauri } from "@/lib/tauri";
import { fetchRecords, fetchGraph, buildBrief, type HypothesisSummary } from "@/lib/researchLib";

export function useStartResearch() {
  const navigate = useNavigate();
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const store = useRuntimeStore;

  async function startResearch(h: HypothesisSummary) {
    if (starting) return;
    setStarting(h.id);
    setError(null);
    try {
      const name = `研究-${h.id}-${new Date().toISOString().slice(0, 10)}`;
      // 1) 建研究项目 + 切工作区
      const project = await store.getState().createProject(name);
      if (!project) throw new Error("创建研究项目失败");

      // 2) 轮询确认 Tauri 侧 active workspace 已指向项目(connectRetry 是异步的)
      if (isTauri) {
        for (let i = 0; i < 25; i++) {
          const cur = await workspacePath();
          if (cur && cur.replace(/\\\\?\\/, "") === project.path.replace(/\\\\?\\/, "")) break;
          await new Promise((r) => setTimeout(r, 200));
        }
      }

      // 3) 并行拉取最新数据(实时快照)
      const [records, graph, hyps] = await Promise.all([
        fetchRecords(),
        fetchGraph(),
        fetch("/data/hypotheses.json").then((r) => r.json()).then((d) => (d?.hypotheses ?? []) as HypothesisSummary[]),
      ]);
      const { buildHypothesesMd } = await import("@/lib/researchLib");
      const brief = buildBrief(h, new Date().toLocaleString("zh-CN"));
      const hypsMd = buildHypothesesMd(hyps);

      // 4) 写入项目目录: 用 createProject 返回的 project.path 的 basename + root="base"
      //    (create_in 会防冲突加 -2/-3 后缀, active-workspace 不一定立刻同步; 用精确路径最稳)
      const projName = project.path.split(/[\\\\/]/).pop()!;
      const rel = (p: string) => `${projName}/${p}`;
      await writeWorkspaceFile(rel("README.md"), brief, "base");
      await writeWorkspaceFile(rel("data/records.json"), JSON.stringify(records), "base");
      await writeWorkspaceFile(rel("data/fkg_graph.json"), JSON.stringify(graph), "base");
      await writeWorkspaceFile(rel("data/hypotheses.md"), hypsMd, "base");
      // 验证至少一个文件真的在项目目录
      const abs = await absoluteArtifactPath(`${projName}/data/records.json`, "base");
      if (!abs) throw new Error("数据写入失败: 未检测到 data/records.json 在项目 " + projName);

      // 5) 在(已切换)研究目录开新 draft 会话, 发首条任务消息
      const runtime = store.getState();
      await runtime.startDraftInWorkspace(project.path);
      await runtime.sendPrompt(
        `这是研究项目 ${h.id} 的任务书(README.md),数据已写入 data/ 目录,流程指引与工装已随项目注入(PIPELINE.md / tools/runner.py / tools/probe_profile.py / tools/method_cards/)。` +
        `请先阅读 README.md、PIPELINE.md 与 data/,然后按七阶段流水线执行: ` +
        `P1 econ-decompose 拆解(sub_problems.json) → P2 econ-data 过滤(filtered_problems.json,需用户确认 A 档) → ` +
        `P3 tools/probe_profile.py 数据盘点 → P4 tools/runner.py 运行实验(results/<sid>/run_XX) → ` +
        `P5 econ-synthesis 判定 per_hypothesis_verdict.md → P6 econ-write 论文 paper/main.md → P7 econ-review 评审 review_report.md。` +
        `统计护栏:显著结果附效应量+CI,主结论 ≥2 稳健性检验,观测数据禁用因果语言。每完成一阶段向我汇报产物与关键结论。`,
      );

      // 6) 跳工作台, 用户直接看到 AI 开工
      navigate("/live");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(null);
    }
  }

  return { starting, error, startResearch };
}
