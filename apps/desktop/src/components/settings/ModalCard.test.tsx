import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ModalCard } from "./ModalCard";

// In the test (non-Tauri) environment isTauri is false, so the card renders its
// "desktop app" fallback without invoking any Rust command — a mount smoke test.
describe("ModalCard", () => {
  it("renders the Modal compute card without crashing", () => {
    render(<ModalCard />);
    expect(screen.getByText(/云计算（Modal）/)).toBeInTheDocument();
    expect(screen.getByText(/该功能在桌面应用中可用|未安装|已就绪/)).toBeInTheDocument();
  });
});
