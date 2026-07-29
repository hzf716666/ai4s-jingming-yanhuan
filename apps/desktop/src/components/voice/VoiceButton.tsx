/**
 * Microphone button for the Composer.
 *
 * Two backends selected automatically:
 *  - **Desktop (Tauri)**: whisper.cpp sidecar — full offline ASR, waveform display.
 *  - **Browser (Web)**: Web Speech API — built into Chrome/Edge, no installation.
 *
 * In browser mode, the button shows a simple recording indicator (no waveform).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Loader2, AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { isGatewayWeb } from "@/lib/webMode";
import { isTauri, logDebug } from "@/lib/tauri";
import { useVoiceRecorder } from "./useVoiceRecorder";
import { useWebSpeechRecorder, hasWebSpeechSupport } from "./useWebSpeechRecorder";

export interface VoiceButtonProps {
  onTranscribed: (text: string) => void;
  language?: string;
  disabled?: boolean;
}

/** Sea-wave animation driven by real mic volume (desktop only).
 *  Draws three overlapping sine waves on a tiny canvas — amplitude scales
 *  with `level` (0…1). Colours auto-adapt to the current theme:
 *  white for dark, black for light/warm. */
function SeaWave({ level, active }: { level: number; active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  const tRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // High-DPI scaling for crisp rendering.
    const dpr = window.devicePixelRatio || 1;
    const W = 64;
    const H = 16;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = `${W}px`;
    canvas.style.height = `${H}px`;
    ctx.scale(dpr, dpr);

    // Detect theme: dark → white waves, light/warm → black waves.
    const theme = document.documentElement.getAttribute("data-theme") ?? "dark";
    const isDark = theme === "dark";
    const fg = isDark ? "255,255,255" : "0,0,0";

    const draw = () => {
      tRef.current += 0.08;
      const t = tRef.current;
      ctx.clearRect(0, 0, W, H);

      const mid = H / 2;

      // Idle: nearly flat line.
      const idleAmp = active ? 0 : 0.1;
      // Amplitude: idle ~0.3px, full voice ~18px.
      const amp = idleAmp + level * 18;

      // Back wave — slowest, lowest opacity, largest wavelength.
      ctx.strokeStyle = `rgba(${fg},0.25)`;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      for (let x = 0; x <= W; x++) {
        const y = mid + Math.sin(x * 0.1 + t * 0.4) * amp * 0.8;
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Middle wave — medium speed, medium opacity, medium wavelength.
      ctx.strokeStyle = `rgba(${fg},0.5)`;
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      for (let x = 0; x <= W; x++) {
        const y = mid + Math.sin(x * 0.18 + t * 0.9) * amp;
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Front wave — fastest, brightest, shortest wavelength.
      ctx.strokeStyle = `rgba(${fg},0.9)`;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (let x = 0; x <= W; x++) {
        const y = mid + Math.sin(x * 0.25 - t) * amp * 1.1;
        x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.stroke();

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [active, level]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: 64, height: 16, display: "block" }}
    />
  );
}

export function VoiceButton({
  onTranscribed, language, disabled,
}: VoiceButtonProps) {
  const { t } = useTranslation("session");
  const [error, setError] = useState<string | null>(null);

  // Determine which backend to use.
  const useWhisper = isTauri;
  const webSpeechAvail = hasWebSpeechSupport();

  // ---- Desktop mode (whisper.cpp) ----
  const whisper = useVoiceRecorder({
    language,
    onPartial: undefined, // don't show partial text in input
    onFinal: useCallback(
      (text: string) => { if (text.trim()) onTranscribed(text.trim()); },
      [onTranscribed],
    ),
    onError: useCallback((msg: string) => {
      setError(msg);
      void logDebug(`[voice] whisper error: ${msg}`);
    }, []),
  });

  // ---- Browser mode (Web Speech API) ----
  const webSpeech = useWebSpeechRecorder({
    language,
    onPartial: undefined,
    onFinal: useCallback(
      (text: string) => { if (text.trim()) onTranscribed(text.trim()); },
      [onTranscribed],
    ),
    onError: useCallback((msg: string) => {
      setError(msg);
      void logDebug(`[voice] web speech error: ${msg}`);
    }, []),
  });

  // Pick the active backend.
  const backend = useWhisper ? whisper : webSpeech;
  const state = backend.state;
  const isRecording = state === "recording";
  const isProcessing = state === "transcribing" || state === "requesting" || state === "downloading";
  const isError = state === "error" || !!error;

  // Show a download percentage only for whisper's "downloading" phase.
  const isDownloading = useWhisper && state === "downloading";
  const downloadPct = useWhisper ? (whisper as any).downloadPct ?? 0 : 0;

  // Duration (whisper only) or just a generic recording indicator.
  const durationSecs = useWhisper ? whisper.durationSecs : 0;
  // Volume level (whisper only).
  const volumeLevel = useWhisper ? whisper.volumeLevel : 0;

  // Clear error after 8 seconds.
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(null), 8000);
    return () => clearTimeout(timer);
  }, [error]);

  // Hide entirely if neither backend is available.
  if (!useWhisper && !webSpeechAvail) return null;
  if (isGatewayWeb && !webSpeechAvail) return null;

  const label = (() => {
    if (isDownloading) {
      return downloadPct > 0
        ? `${t("voice.downloadingModel")} ${downloadPct}%`
        : t("voice.downloadingModel");
    }
    if (isRecording) {
      return useWhisper
        ? t("voice.recording", { seconds: durationSecs })
        : t("voice.recording", { seconds: 0 });
    }
    if (isProcessing) return t("voice.requesting");
    if (isError) return error || t("voice.error");
    return t("voice.start");
  })();

  const handleClick = () => {
    if (disabled || isProcessing || isDownloading) return;
    if (isError) {
      setError(null);
      backend.start();
      return;
    }
    if (isRecording) {
      backend.stop();
    } else {
      setError(null);
      backend.start();
    }
  };

  const icon = isDownloading ? (
    <span className="flex items-center gap-1">
      <Loader2 size={13} className="animate-spin" />
      {downloadPct > 0 && <span className="text-[10px] tabular-nums">{downloadPct}%</span>}
    </span>
  ) : isProcessing ? (
    <Loader2 size={15} className="animate-spin" />
  ) : isRecording && useWhisper ? (
    <SeaWave level={volumeLevel} active={true} />
  ) : isRecording ? (
    <span className="flex items-center gap-1">
      <Mic size={13} className="text-destructive" />
      <span className="w-1.5 h-1.5 rounded-full bg-destructive animate-pulse" />
    </span>
  ) : isError ? (
    <AlertCircle size={15} />
  ) : (
    <Mic size={15} />
  );

  return (
    <button
      type="button"
      className={cn(
        "flex h-7 shrink-0 items-center gap-1 rounded-input px-2 text-muted hover:bg-surface-2 hover:text-text disabled:opacity-40 transition-colors",
        isRecording && "text-destructive hover:text-destructive min-w-[44px]",
        isDownloading && "text-accent min-w-[52px]",
        isProcessing && "text-accent cursor-wait",
        isError && "text-destructive hover:text-destructive",
      )}
      aria-label={label}
      title={label}
      onClick={handleClick}
      disabled={disabled || isProcessing || isDownloading}
      data-voicerecording={isRecording ? "true" : "false"}
    >
      {icon}
      {isRecording && useWhisper && (
        <span className="text-[11px] tabular-nums leading-none">{durationSecs}s</span>
      )}
      {isError && error && (
        <span className="text-[10px] leading-tight max-w-[200px] truncate">{error}</span>
      )}
    </button>
  );
}
