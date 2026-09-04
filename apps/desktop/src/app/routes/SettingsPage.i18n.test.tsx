import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderAt } from "@/test/render";
import { useRuntimeStore } from "@/lib/runtime";

describe("Settings page strings (i18n)", () => {
  it("renders the General section with the settings sidebar navigation", async () => {
    renderAt("/settings");
    expect(await screen.findByRole("heading", { level: 1, name: "通用" })).toBeInTheDocument();
    expect(screen.getByText("工作区")).toBeInTheDocument();
    expect(screen.getByText("该功能在桌面应用中可用")).toBeInTheDocument();
    // The sidebar became the settings navigation with a way back to the app.
    expect(screen.getByRole("button", { name: "返回应用" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "连接器" })).toBeInTheDocument();
  });

  it("renders each section's own title and disconnected-runtime prompt", async () => {
    const runtime = renderAt("/settings/runtime");
    expect(await screen.findByText("代理运行时")).toBeInTheDocument();
    runtime.unmount();

    const connectors = renderAt("/settings/connectors");
    expect(await screen.findByText("MCP 服务器")).toBeInTheDocument();
    expect(screen.getByText("连接运行时以配置 MCP 服务器。")).toBeInTheDocument();
    connectors.unmount();

    renderAt("/settings/models");
    expect(await screen.findByText("连接运行时以配置模型。")).toBeInTheDocument();
  });

  it("renders separate model browsing and provider management surfaces when connected", async () => {
    const original = useRuntimeStore.getState();
    let view: ReturnType<typeof renderAt> | undefined;
    try {
      useRuntimeStore.setState({ status: "ready", defaultModel: null });
      view = renderAt("/settings/models");
      // No client behind this render: the Models card sits in its loading
      // state while the separate Providers card is already on screen.
      expect(await screen.findByText("正在加载模型目录…")).toBeInTheDocument();
      expect(screen.getByRole("heading", { level: 2, name: "供应商" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "管理" })).toHaveAttribute("aria-expanded", "false");
    } finally {
      view?.unmount();
      useRuntimeStore.setState({ status: original.status, defaultModel: original.defaultModel });
    }
  });
});
