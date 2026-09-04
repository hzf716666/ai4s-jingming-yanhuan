import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceButton } from "./VoiceButton";

// Platform mocks: we need isTauri=true and mic support for the button to render.
vi.mock("@/lib/tauri", () => ({
  isTauri: true,
  transcribeAudio: vi.fn(),
  addBinaryToWorkspace: vi.fn(),
  workspacePath: vi.fn(),
  voiceStatus: vi.fn().mockResolvedValue({ available: true, modelsDownloaded: ["tiny"], activeModel: "tiny", downloading: false }),
  downloadVoiceModel: vi.fn().mockResolvedValue(undefined),
  watchVoiceProgress: vi.fn().mockResolvedValue(() => {}),
  logDebug: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/lib/webMode", () => ({
  isGatewayWeb: false,
}));

// Provide a fake getUserMedia so hasMicSupport() returns true.
beforeEach(() => {
  Object.defineProperty(globalThis.navigator, "mediaDevices", {
    value: { getUserMedia: vi.fn() },
    writable: true,
    configurable: true,
  });
});

// Mock the voice hook so we control state.
const mockStart = vi.fn();
const mockStop = vi.fn();

vi.mock("./useVoiceRecorder", () => ({
  useVoiceRecorder: vi.fn(() => ({
    state: "idle",
    partialText: "",
    durationSecs: 0,
    volumeLevel: 0,
    downloadPct: 0,
    start: mockStart,
    stop: mockStop,
  })),
}));

import { useVoiceRecorder } from "./useVoiceRecorder";

describe("VoiceButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useVoiceRecorder).mockReturnValue({
      state: "idle",
      partialText: "",
      durationSecs: 0,
      volumeLevel: 0,
      downloadPct: 0,
      start: mockStart,
      stop: mockStop,
    });
  });

  it("renders a microphone button in idle state", () => {
    render(<VoiceButton onTranscribed={vi.fn()} />);
    const btn = screen.getByRole("button");
    expect(btn).toBeInTheDocument();
    expect(btn.getAttribute("aria-label")).toContain("开始语音输入");
  });

  it("shows recording state with duration counter", () => {
    vi.mocked(useVoiceRecorder).mockReturnValue({
      state: "recording",
      partialText: "Hello",
      durationSecs: 5,
      volumeLevel: 0.7,
      downloadPct: 0,
      start: mockStart,
      stop: mockStop,
    });
    render(<VoiceButton onTranscribed={vi.fn()} />);
    const btn = screen.getByRole("button");
    expect(btn.getAttribute("data-voicerecording")).toBe("true");
    expect(btn.textContent).toContain("5");
    expect(btn.getAttribute("aria-label")).toContain("5");
  });

  it("shows processing (transcribing) state as disabled", () => {
    vi.mocked(useVoiceRecorder).mockReturnValue({
      state: "transcribing",
      partialText: "",
      durationSecs: 0,
      volumeLevel: 0,
      downloadPct: 0,
      start: mockStart,
      stop: mockStop,
    });
    render(<VoiceButton onTranscribed={vi.fn()} />);
    const btn = screen.getByRole("button");
    expect(btn).toBeDisabled();
  });

  it("renders with the correct accessible label in idle state", () => {
    render(<VoiceButton onTranscribed={vi.fn()} />);
    const btn = screen.getByRole("button");
    expect(btn).not.toBeDisabled();
    expect(btn.getAttribute("aria-label")).toBeTruthy();
  });
});
