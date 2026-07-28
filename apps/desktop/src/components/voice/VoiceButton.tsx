/**
 * Microphone button for the Composer.
 *
 * Two backends selected automatically:
 *  - **Desktop (Tauri)**: whisper.cpp sidecar — full offline ASR, waveform display.
 *  - **Browser (Web)**: Web Speech API — built into Chrome/Edge, no installation.
 *
 * In browser mode, the button shows a simple recording indicator (no waveform).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Mic, Loader2, AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { isGatewayWeb } from "@/lib/webMode";
import { isTauri, logDebug } from "@/lib/tauri";
import { useVoiceRecorder } from "./useVoiceRecorder";
import { useWebSpeechRecorder, hasWebSpeechSupport } from "./useWebSpeechRecorder";

export interface VoiceButtonProps {
  /** Called with final transcription when recording stops. */
  onTranscribed: (text: string) => void;
  /** Called with accumulated text during recording (for real-time display). */
  onPartial?: (text: string) => void;
  language?: string;
  disabled?: boolean;
}

/** Waveform bars driven by real mic volume (desktop only). */
function WaveformBars({ level, active }: { level: number; active: boolean }) {
  const bars = useMemo(() => [0, 1, 2, 3, 4], []);
  const maxH = 14;
  if (!active) {
    return (
      <span className="flex items-end gap-[2px]" style={{ height: maxH }}>
        {bars.map((i) => (
          <span key={i} className="w-[2px] rounded-full bg-current opacity-40" style={{ height: "4px" }} />
        ))}
      </span>
    );
  }
  return (
    <span className="flex items-end gap-[2px]" style={{ height: maxH }}>
      {bars.map((i) => {
        const h = Math.max(3, Math.min(maxH, level * maxH * (0.4 + i * 0.25)));
        return (
          <span key={i} className="w-[2px] rounded-full bg-current transition-[height] duration-75 ease-out"
            style={{ height: `${h}px` }} />
        );
      })}
    </span>
  );
}

export function VoiceButton({
  onTranscribed, onPartial, language, disabled,
}: VoiceButtonProps) {
  const { t } = useTranslation("session");
  const [error, setError] = useState<string | null>(null);

  // Determine which backend to use.
  const useWhisper = isTauri;
  const webSpeechAvail = hasWebSpeechSupport();

  // ---- Desktop mode (whisper.cpp) ----
  const whisper = useVoiceRecorder({
    language,
    onPartial: onPartial ? (appended, full) => onPartial(full) : undefined,
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
    onPartial: onPartial ? (appended, full) => onPartial(full) : undefined,
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
    <WaveformBars level={volumeLevel} active={true} />
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
