import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";

// COPYCAT RULE: useRuntimeStore is module-global — restore the
// disconnected default after any test that fakes a "ready" runtime.
import { useRuntimeStore } from "@/lib/runtime";
const RUNTIME_DEFAULTS = { status: useRuntimeStore.getState().status, agents: useRuntimeStore.getState().agents };
afterEach(() => useRuntimeStore.setState(RUNTIME_DEFAULTS));

describe("RunsPage strings (i18n)", () => {
  it("renders the page heading and description in Chinese", async () => {
    renderAt("/runs");
    expect(await screen.findByRole("heading", { level: 1, name: "运行" })).toBeInTheDocument();
    expect(
      screen.getByText(
        /跨所有会话的每一次实验执行——命令、代码版本、环境、硬件与输出。/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("复现")).toBeInTheDocument();
  });

  it("renders the empty state (no runs recorded) in Chinese", async () => {
    renderAt("/runs");
    expect(await screen.findByText("尚无运行记录")).toBeInTheDocument();
    expect(
      screen.getByText((_, node) => node?.textContent === "当代理运行代码时（例如 python train.py），每次执行都会连同其可复现方案记录于此。"),
    ).toBeInTheDocument();
  });
});
