import { useCallback, useEffect, useState } from "react";
import {
  getQoderToken,
  isTauri,
  loginQoderViaCli,
  qoderCliStatus,
  saveQoderToken,
} from "@/lib/tauri";

type GateStatus = "checking" | "missing" | "needs-login" | "ready";

/** Pre-boot gate for the Qoder backend: new users must first install the
 *  Qoder CLI, then sign in (browser OAuth or a personal access token).
 *  Shown instead of the app while the backend is qoder and not ready.
 *  Polls status so finishing a login in the browser auto-continues. */
export function QoderGate({ onReady }: { onReady: () => void }) {
  const [status, setStatus] = useState<GateStatus>("checking");
  const [busy, setBusy] = useState(false);
  const [pat, setPat] = useState("");
  const [error, setError] = useState("");

  const check = useCallback(async () => {
    if (!isTauri) return;
    try {
      const [authed, cli] = await Promise.all([getQoderToken(), qoderCliStatus()]);
      if (authed) {
        setStatus("ready");
        onReady();
        return;
      }
      setStatus(cli.installed ? "needs-login" : "missing");
    } catch {
      setStatus("checking");
    }
  }, [onReady]);

  useEffect(() => {
    void check();
    const timer = setInterval(() => void check(), 4000);
    return () => clearInterval(timer);
  }, [check]);

  const doLogin = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const ok = await loginQoderViaCli();
      if (!ok) setError("登录未完成，请在弹出的浏览器页面中完成授权");
      await check();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const savePat = async () => {
    const tok = pat.trim();
    if (!tok || busy) return;
    setBusy(true);
    setError("");
    try {
      const ok = await saveQoderToken(tok);
      if (!ok) setError("令牌保存失败，请检查后重试");
      await check();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (status === "ready") return null;

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg p-6 text-text">
      <div className="w-full max-w-md rounded-card border border-border bg-surface p-7 shadow-xl">
        <h1 className="text-lg font-semibold">景明研环</h1>

        {status === "checking" && (
          <p className="mt-2 text-sm text-muted">正在检查 Qoder 运行环境…</p>
        )}

        {status === "missing" && (
          <>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              景明研环默认使用 Qoder（通义灵码）作为智能体后端。首次使用请先安装 Qoder CLI：
            </p>
            <pre className="mt-3 overflow-x-auto rounded-input border border-border bg-surface-2 p-3 text-xs leading-relaxed">
              npm install -g @qoder-ai/qodercli
            </pre>
            <p className="mt-2 text-xs text-muted">
              安装完成后点击下方按钮继续；也可以访问 Qoder 官网（qoder.com）获取安装说明。
            </p>
            <button
              type="button"
              onClick={() => void check()}
              disabled={busy}
              className="mt-4 h-10 w-full rounded-input bg-accent text-sm font-medium text-white transition-opacity disabled:opacity-50"
            >
              我已安装，重新检测
            </button>
          </>
        )}

        {status === "needs-login" && (
          <>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              已检测到 Qoder CLI。点击下方按钮将打开浏览器完成 Qoder 账号授权。
            </p>
            <button
              type="button"
              onClick={() => void doLogin()}
              disabled={busy}
              className="mt-4 h-10 w-full rounded-input bg-accent text-sm font-medium text-white transition-opacity disabled:opacity-50"
            >
              {busy ? "登录中…" : "登录 Qoder"}
            </button>
            <div className="my-4 flex items-center gap-3 text-xs text-muted">
              <span className="h-px flex-1 bg-border" />
              或使用个人访问令牌（PAT）
              <span className="h-px flex-1 bg-border" />
            </div>
            <input
              type="password"
              autoComplete="off"
              value={pat}
              onChange={(e) => setPat(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void savePat();
              }}
              placeholder="粘贴 Qoder 个人访问令牌"
              className="h-10 w-full rounded-input border border-border bg-surface-2 px-3 text-sm outline-none focus:border-accent"
            />
            <button
              type="button"
              onClick={() => void savePat()}
              disabled={busy || !pat.trim()}
              className="mt-3 h-10 w-full rounded-input border border-border text-sm font-medium transition-opacity disabled:opacity-50"
            >
              保存令牌
            </button>
          </>
        )}

        {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
      </div>
    </div>
  );
}
