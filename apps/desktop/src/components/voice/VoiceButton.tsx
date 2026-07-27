/**
 * Microphone button for the Composer. Toggles voice recording on/off.
 *
 * States (shown inline with icon + text):
 *  - idle:          [mic]              — click to start
 *  - downloading:   [spinner] 45%      — model download in progress
 *  - requesting:    [spinner]          — waiting for mic permission dialog
 *  - recording:     [waveform] 12s     — live audio, click to stop
 *  - transcribing:  [spinner]          — final transcription
 *  - error:         [mic] Error text   — with retry hint
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Mic, Loader2, AlertCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/cn";
import { isGatewayWeb } from "@/lib/webMode";
import { isTauri, logDebug } from "@/lib/tauri";
import { useVoiceRecorder } from "./useVoiceRecorder";

export interface VoiceButtonProps {
  onTranscribed: (text: string) => void;
  onPartialText?: (appended: string, full: string) => void;
  language?: string;
  disabled?: boolean;
}

function hasMicSupport(): boolean {
  return !!(
    typeof navigator !== "undefined" &&
    navigator.mediaDevices &&
    navigator.mediaDevices.getUserMedia
  );
}

/** Waveform bars driven by real mic volume. */
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
  onTranscribed, onPartialText, language, disabled,
}: VoiceButtonProps) {
  const { t } = useTranslation("session");
  const [error, setError] = useState<string | null>(null);
  const [micSupported] = useState(hasMicSupport);
  const [lastPhase, setLastPhase] = useState("");

  const onPartialStable = useCallback(
    (a: string, f: string) => onPartialText?.(a, f), [onPartialText]);
  const onFinalStable = useCallback(
    (text: string) => { if (text.trim()) onTranscribed(text.trim()); }, [onTranscribed]);
  const onErrorStable = useCallback((msg: string) => {
    setError(msg);
    void logDebug(`[voice] error: ${msg}`);
  }, []);

  const { state, durationSecs, volumeLevel, downloadPct, start, stop } = useVoiceRecorder({
    language, onPartial: onPartialStable, onFinal: onFinalStable, onError: onErrorStable,
  });

  // Log every state transition.
  useEffect(() => {
    if (state !== lastPhase) {
      setLastPhase(state);
      void logDebug(`[voice] phase: ${lastPhase} → ${state}`);
    }
  }, [state, lastPhase]);

  // Clear error after 8 seconds so retry is possible.
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(null), 8000);
    return () => clearTimeout(timer);
  }, [error]);

  if (!isTauri || isGatewayWeb || !micSupported) return null;

  const isDownloading = state === "downloading";
  const isRecording = state === "recording";
  const isProcessing = state === "transcribing" || state === "requesting";
  const isError = state === "error" || !!error;

  const label = (() => {
    if (isDownloading) return downloadPct > 0
      ? `${t("voice.downloadingModel")} ${downloadPct}%`
      : t("voice.downloadingModel");
    if (isRecording) return t("voice.recording", { seconds: durationSecs });
    if (isProcessing) return t("voice.requesting");
    if (isError) return error || t("voice.error");
    return t("voice.start");
  })();

  const handleClick = () => {
    if (disabled || isProcessing || isDownloading) return;
    if (isError) {
      // Allow retry from error state.
      setError(null);
      start();
      return;
    }
    if (isRecording) {
      stop();
    } else {
      setError(null);
      start();
    }
  };

  const icon = isDownloading ? (
    <span className="flex items-center gap-1">
      <Loader2 size={13} className="animate-spin" />
      {downloadPct > 0 && <span className="text-[10px] tabular-nums">{downloadPct}%</span>}
    </span>
  ) : isProcessing ? (
    <Loader2 size={15} className="animate-spin" />
  ) : isRecording ? (
    <WaveformBars level={volumeLevel} active={true} />
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
      {isRecording && <span className="text-[11px] tabular-nums leading-none">{durationSecs}s</span>}
      {isError && error && (
        <span className="text-[10px] leading-tight max-w-[200px] truncate">{error}</span>
      )}
    </button>
  );
}
