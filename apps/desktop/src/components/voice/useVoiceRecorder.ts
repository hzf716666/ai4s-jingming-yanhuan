/**
 * React hook that encapsulates the full voice-recording → transcription
 * pipeline using sherpa-onnx streaming for real-time word-by-word display.
 * Manages MediaRecorder lifecycle and streaming session.
 *
 * State machine:
 *   idle → requesting → downloading → recording → idle
 *
 * Key design decisions:
 *  - useRef for mutable recorder state to avoid stale-closure issues
 *    with useCallback dependencies.
 *  - useState only for UI-rendered fields (recorderState, partialText,
 *    durationSecs).
 *  - All async callbacks read the stable ref, not the render state.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  streamingVoiceStatus,
  downloadStreamingModel,
  startStreamingSession,
  acceptAudioChunk,
  endStreamingSession,
  cancelStreamingSession,
  watchStreamingPartial,
  watchStreamingFinal,
  isTauri,
  logDebug,
} from "@/lib/tauri";

/** The voice recorder's UI-facing state. */
export type RecorderState =
  | "idle"
  | "requesting" // waiting for mic permission
  | "downloading" // downloading the speech model
  | "recording"
  | "transcribing" // processing last chunk after stop
  | "error";

export interface VoiceRecorderOptions {
  /** Called every ~0.5 s with newly-appended text (incremental). */
  onPartial?: (appended: string, full: string) => void;
  /** Called once when recording stops and the final transcription completes. */
  onFinal?: (text: string) => void;
  /** Called when an error occurs (permission denied, sidecar failure, etc.). */
  onError?: (message: string) => void;
  /** ISO 639-1 language code or "auto" (default). */
  language?: string;
}

export interface VoiceRecorderAPI {
  state: RecorderState;
  /** The current full transcription text while recording. */
  partialText: string;
  /** Recording duration in seconds (0 when idle). */
  durationSecs: number;
  /** Real audio volume level (0–1), updated ~30×/s via AnalyserNode. */
  volumeLevel: number;
  /** Download progress percentage (0–100), only meaningful during "downloading". */
  downloadPct: number;
  /** Start recording. Requests microphone permission on first call. */
  start: () => void;
  /** Stop recording and finalize transcription. */
  stop: () => void;
}

const CHUNK_INTERVAL_MS = 100; // send audio chunk every 100ms for real-time streaming
const SAMPLE_RATE = 16000;

export function useVoiceRecorder(options: VoiceRecorderOptions = {}): VoiceRecorderAPI {
  // ---- Stable refs for callbacks (avoid useCallback dep churn) ----
  const optsRef = useRef(options);
  optsRef.current = options;

  // ---- Mutable recorder state (ref, not render state) ----
  const phaseRef = useRef<RecorderState>("idle");

  // ---- UI-rendered fields (state) ----
  const [recorderState, setRecorderState] = useState<RecorderState>("idle");
  const [partialText, setPartialText] = useState("");
  const [durationSecs, setDurationSecs] = useState(0);
  const [volumeLevel, setVolumeLevel] = useState(0);
  const [downloadPct, setDownloadPct] = useState(0);

  // ---- Internal handles ----
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const transcribeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef(0);
  const sessionIdRef = useRef<string | null>(null);
  const unlistenPartialRef = useRef<(() => void) | null>(null);
  const unlistenFinalRef = useRef<(() => void) | null>(null);

  /** Set both the ref (for stable async reads) and the React state (for UI). */
  const setPhase = useCallback((p: RecorderState) => {
    phaseRef.current = p;
    setRecorderState(p);
  }, []);

  // ---- Cleanup (stable — never recreated) ----
  const cleanup = useCallback(() => {
    if (transcribeTimerRef.current) {
      clearInterval(transcribeTimerRef.current);
      transcribeTimerRef.current = null;
    }
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
    if (animFrameRef.current != null) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    // Close AudioContext — browsers throttle unused contexts.
    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      void audioCtxRef.current.close();
    }
    audioCtxRef.current = null;
    analyserRef.current = null;
    scriptProcessorRef.current = null;
    setVolumeLevel(0);
  }, []);

  // Cleanup on unmount.
  useEffect(() => () => cleanup(), [cleanup]);

  // ---- Audio chunk sender (stable ref so interval captures current) ----
  const sendChunkRef = useRef<() => Promise<void>>(async () => {});
  sendChunkRef.current = async () => {
    if (!audioCtxRef.current || !sessionIdRef.current) return;
    try {
      // Process audio from the MediaRecorder chunks
      // We use AudioContext to capture and process the raw samples
      const processor = audioCtxRef.current;
      // The audioCtx is already set up with the media stream as source
      // We capture audio via the ScriptProcessor/AudioWorklet approach
    } catch (err) {
      console.warn("voice: send chunk failed", err);
    }
  };

  // ---- Start ----
  const start = useCallback(async () => {
    if (!isTauri) {
      optsRef.current.onError?.("Voice input is only available in the desktop app.");
      return;
    }
    if (phaseRef.current !== "idle") return;
    setPhase("requesting");

    // Ensure the sherpa-onnx streaming model is downloaded before we record.
    try {
      const st = await streamingVoiceStatus();
      void logDebug(`[voice] streamingVoiceStatus: available=${st?.available}, modelDownloaded=${st?.modelDownloaded}`);
      if (!st?.modelDownloaded) {
        void logDebug("[voice] streaming model not downloaded — starting auto-download");
        setPhase("downloading");
        setDownloadPct(0);

        // Download the sherpa-onnx streaming model
        await downloadStreamingModel("tiny");
        void logDebug("[voice] streaming model download completed");
        setDownloadPct(0);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      void logDebug(`[voice] model download FAILED: ${msg}`);
      cleanup();
      setDownloadPct(0);
      setPhase("error");
      optsRef.current.onError?.(
        msg.includes("timeout") || msg.includes("timed out")
          ? "Model download timed out. Check your network and try again."
          : `Download failed: ${msg}`,
      );
      return;
    }

    // Back to requesting state for mic permission.
    setPhase("requesting");
    void logDebug("[voice] requesting microphone permission");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      // Start streaming session with sherpa-onnx
      const { sessionId, sampleRate } = await startStreamingSession();
      void logDebug(`[voice] streaming session started, sessionId=${sessionId}, sampleRate=${sampleRate}`);
      sessionIdRef.current = sessionId;

      // Create AudioContext for capturing and processing audio
      const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioCtxRef.current = audioCtx;

      // Create a ScriptProcessorNode to capture audio chunks
      // Note: ScriptProcessor is deprecated but still widely supported
      // Alternative would be AudioWorklet but that's more complex
      const scriptProcessor = audioCtx.createScriptProcessor(4096, 1, 1);
      scriptProcessorRef.current = scriptProcessor;

      scriptProcessor.onaudioprocess = (e) => {
        if (phaseRef.current !== "recording" || !sessionIdRef.current) return;
        const inputData = e.inputBuffer.getChannelData(0);
        // Convert Float32Array to number array for Tauri invoke
        const samples = Array.from(inputData);
        void acceptAudioChunk(sessionIdRef.current, samples);
      };

      // Connect the stream to the script processor
      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(scriptProcessor);
      // Don't connect to destination — we don't want audio feedback
      scriptProcessor.connect(audioCtx.destination);

      // Duration counter.
      startTimeRef.current = Date.now();
      durationTimerRef.current = setInterval(() => {
        const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000);
        setDurationSecs(elapsed);
      }, 250);

      // Real-time volume analysis via Web Audio API AnalyserNode
      try {
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        analyser.smoothingTimeConstant = 0.4;
        source.connect(analyser);
        analyserRef.current = analyser;

        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        const tick = () => {
          if (!analyserRef.current) return;
          analyser.getByteFrequencyData(dataArray);
          const sum = dataArray.reduce((a, b) => a + b, 0);
          const avg = sum / dataArray.length / 255;
          setVolumeLevel(avg);
          animFrameRef.current = requestAnimationFrame(tick);
        };
        animFrameRef.current = requestAnimationFrame(tick);
      } catch {
        // Analyser can fail — degrade gracefully
      }

      // Listen for partial results
      const unlistenPartial = await watchStreamingPartial((p) => {
        if (p.sessionId === sessionIdRef.current) {
          setPartialText(p.text);
          optsRef.current.onPartial?.(p.text, p.text);
        }
      });
      unlistenPartialRef.current = unlistenPartial;

      // Listen for final results
      const unlistenFinal = await watchStreamingFinal((p) => {
        if (p.sessionId === sessionIdRef.current) {
          setPartialText("");
          if (p.text.trim()) optsRef.current.onFinal?.(p.text.trim());
        }
      });
      unlistenFinalRef.current = unlistenFinal;

      setPhase("recording");
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Mic permission denied. Check Windows Settings → Privacy → Microphone."
          : `Mic error: ${err instanceof Error ? err.message : String(err)}`;
      void logDebug(`[voice] getUserMedia FAILED: ${msg}`);
      cleanup();
      setPhase("error");
      optsRef.current.onError?.(msg);
    }
  }, [cleanup, setPhase]);

  // ---- Stop ----
  const stop = useCallback(async () => {
    if (phaseRef.current !== "recording") return;

    // Kill timers
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
    if (animFrameRef.current != null) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }

    // Disconnect audio processing
    if (scriptProcessorRef.current) {
      scriptProcessorRef.current.disconnect();
      scriptProcessorRef.current = null;
    }

    const sid = sessionIdRef.current;
    sessionIdRef.current = null;

    cleanup();
    setDurationSecs(0);
    setPhase("idle");

    // End streaming session
    if (sid) {
      try {
        const finalText = await endStreamingSession(sid);
        if (finalText.trim()) optsRef.current.onFinal?.(finalText.trim());
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        optsRef.current.onError?.(`End streaming failed: ${msg}`);
      }
    }

    // Cleanup listeners
    if (unlistenPartialRef.current) {
      unlistenPartialRef.current();
      unlistenPartialRef.current = null;
    }
    if (unlistenFinalRef.current) {
      unlistenFinalRef.current();
      unlistenFinalRef.current = null;
    }
  }, [cleanup, setPhase]);

  return { state: recorderState, partialText, durationSecs, volumeLevel, downloadPct, start, stop };
}
