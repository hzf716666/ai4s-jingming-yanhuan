/**
 * React hook that encapsulates the full voice-recording → transcription
 * pipeline using the local whisper.cpp sidecar. Manages MediaRecorder
 * lifecycle, periodic incremental transcription, and text deduplication.
 *
 * State machine:
 *   idle → requesting → recording → transcribing → idle
 *                ↓
 *           transcribing (periodic bursts while recording)
 *
 * Key design decisions:
 *  - useRef for mutable recorder state to avoid stale-closure issues
 *    with useCallback dependencies.
 *  - useState only for UI-rendered fields (recorderState, partialText,
 *    durationSecs).
 *  - All async callbacks read the stable ref, not the render state.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeAudio, addBinaryToWorkspace, voiceStatus, downloadVoiceModel, watchVoiceProgress, isTauri, logDebug } from "@/lib/tauri";
import { diffText } from "./dedup";

/** The voice recorder's UI-facing state. */
export type RecorderState =
  | "idle"
  | "requesting" // waiting for mic permission
  | "downloading" // downloading the speech model
  | "recording"
  | "transcribing" // processing last chunk after stop
  | "error";

export interface VoiceRecorderOptions {
  /** Called every ~2 s with newly-appended text (incremental). */
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

const CHUNK_INTERVAL_MS = 2000; // transcribe every 2 seconds
const SAMPLE_RATE = 16000;

/**
 * Convert a webm/opus Blob (MediaRecorder default) to 16-bit mono 16 kHz
 * PCM WAV — the only format whisper.cpp reliably decodes. Uses the Web Audio
 * API to decode, then manually writes the WAV header + PCM samples.
 */
async function webmToWav(blob: Blob): Promise<Blob> {
  const arrayBuf = await blob.arrayBuffer();
  const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
  try {
    const audioBuf = await audioCtx.decodeAudioData(arrayBuf);
    // Downmix to mono + resample to SAMPLE_RATE.
    const length = audioBuf.length;
    const numChannels = audioBuf.numberOfChannels;
    const pcm = new Int16Array(length);
    for (let i = 0; i < length; i++) {
      let sample = 0;
      for (let ch = 0; ch < numChannels; ch++) {
        sample += audioBuf.getChannelData(ch)[i];
      }
      sample = sample / numChannels; // average channels → mono
      // Clamp to [-1, 1] then scale to i16.
      sample = Math.max(-1, Math.min(1, sample));
      pcm[i] = sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767);
    }
    // Build WAV file.
    const header = new ArrayBuffer(44);
    const v = new DataView(header);
    const byteRate = SAMPLE_RATE * 2; // mono 16-bit
    writeStr(v, 0, "RIFF");
    v.setUint32(4, 36 + pcm.byteLength, true);
    writeStr(v, 8, "WAVE");
    writeStr(v, 12, "fmt ");
    v.setUint32(16, 16, true);      // PCM
    v.setUint16(20, 1, true);       // format = 1
    v.setUint16(22, 1, true);       // mono
    v.setUint32(24, SAMPLE_RATE, true);
    v.setUint32(28, byteRate, true);
    v.setUint16(32, 2, true);       // block align
    v.setUint16(34, 16, true);      // bits per sample
    writeStr(v, 36, "data");
    v.setUint32(40, pcm.byteLength, true);
    const wav = new Uint8Array(header.byteLength + pcm.byteLength);
    wav.set(new Uint8Array(header), 0);
    wav.set(new Uint8Array(pcm.buffer), header.byteLength);
    return new Blob([wav], { type: "audio/wav" });
  } finally {
    void audioCtx.close();
  }
}
function writeStr(v: DataView, off: number, s: string) {
  for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i));
}

/** Write a Blob into the workspace as WAV and return the filename. */
async function persistAudio(blob: Blob): Promise<string> {
  const wav = await webmToWav(blob);
  const base64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(wav);
  });
  const name = `voice-${Date.now()}.wav`;
  const written = await addBinaryToWorkspace(name, base64);
  return written;
}

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
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const prevTextRef = useRef("");
  const transcribeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef(0);
  const stoppingRef = useRef(false);

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
    recorderRef.current = null;
    chunksRef.current = [];
    setVolumeLevel(0);
  }, []);

  // Cleanup on unmount.
  useEffect(() => () => cleanup(), [cleanup]);

  // ---- Incremental transcription (stable ref so interval captures current) ----
  const doTranscribeRef = useRef<() => Promise<void>>(async () => {});
  doTranscribeRef.current = async () => {
    if (chunksRef.current.length === 0) return;
    try {
      const merged = new Blob(chunksRef.current, { type: "audio/webm" });
      const audioPath = await persistAudio(merged);
      const result = await transcribeAudio(audioPath, optsRef.current.language);
      const { appended, full } = diffText(prevTextRef.current, result.text);
      prevTextRef.current = full;
      setPartialText(full);
      if (appended) optsRef.current.onPartial?.(appended, full);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      // If the model or binary is missing, surface it now rather than
      // silently retrying every 2 s. Stop recording so the user sees the fix.
      if (msg.includes("model not downloaded") || msg.includes("whisper-cli not found")) {
        cleanup();
        setPhase("error");
        optsRef.current.onError?.(msg);
        return;
      }
      // Other failures (e.g. audio decode issues) are non-fatal —
      // the next tick will retry with more accumulated audio.
      console.warn("voice: incremental transcription failed", err);
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

    // Ensure the whisper model is downloaded before we record.
    // If not, auto-download (tiny, ~75 MB) with live progress.
    try {
      const st = await voiceStatus();
      void logDebug(`[voice] voiceStatus: available=${st?.available}, models=${st?.modelsDownloaded?.join(",") || "none"}`);
      if (st && !st.available) {
        void logDebug("[voice] model not downloaded — starting auto-download");
        setPhase("downloading");
        setDownloadPct(0);

        const unlisten = await watchVoiceProgress((p) => {
          if (p.totalBytes > 0) {
            setDownloadPct(Math.round((p.downloadedBytes / p.totalBytes) * 100));
          }
        });

        try {
          await downloadVoiceModel("tiny");
          void logDebug("[voice] model download completed");
        } finally {
          unlisten();
        }

        await new Promise((r) => setTimeout(r, 200));
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

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "audio/mp4";

      const recorder = new MediaRecorder(stream, { mimeType });
      recorderRef.current = recorder;
      chunksRef.current = [];
      prevTextRef.current = "";
      setPartialText("");
      stoppingRef.current = false;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onerror = () => {
        void logDebug("[voice] MediaRecorder onerror fired");
        cleanup();
        setPhase("error");
        optsRef.current.onError?.("Microphone recording failed.");
      };

      recorder.start(CHUNK_INTERVAL_MS);
      startTimeRef.current = Date.now();

      // Periodic transcription (uses the stable ref so no stale closure).
      transcribeTimerRef.current = setInterval(() => {
        void doTranscribeRef.current();
      }, CHUNK_INTERVAL_MS);

      // Duration counter.
      durationTimerRef.current = setInterval(() => {
        const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000);
        setDurationSecs(elapsed);
      }, 250); // 250 ms for smoother updates

      // Real-time volume analysis via Web Audio API.
      // Create an AudioContext, connect the stream to an AnalyserNode,
      // and read frequency data on every animation frame.
      try {
        const audioCtx = new AudioContext();
        audioCtxRef.current = audioCtx;
        const src = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256; // small = faster updates
        analyser.smoothingTimeConstant = 0.4;
        src.connect(analyser);
        // Don't connect to destination — we don't want feedback.
        analyserRef.current = analyser;

        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        const tick = () => {
          if (!analyserRef.current) return;
          analyser.getByteFrequencyData(dataArray);
          // Average across frequency bins → 0–1 level.
          const sum = dataArray.reduce((a, b) => a + b, 0);
          const avg = sum / dataArray.length / 255;
          setVolumeLevel(avg);
          animFrameRef.current = requestAnimationFrame(tick);
        };
        animFrameRef.current = requestAnimationFrame(tick);
      } catch {
        // AudioContext can fail (e.g. in restrictive environments).
        // Degrade gracefully — the waveform just stays flat.
      }

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
  }, [cleanup, setPhase]); // stable deps — never recreated

  // ---- Stop ----
  const stop = useCallback(async () => {
    if (phaseRef.current !== "recording") return;
    stoppingRef.current = true;
    setPhase("transcribing");

    // Kill the periodic timers.
    if (transcribeTimerRef.current) {
      clearInterval(transcribeTimerRef.current);
      transcribeTimerRef.current = null;
    }
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }

    // Flush the final chunk.
    const recorder = recorderRef.current;
    if (recorder && recorder.state === "recording") {
      recorder.requestData();
      // Small delay so the last ondataavailable fires.
      await new Promise((r) => setTimeout(r, 150));
      recorder.stop();
    }

    // Final transcription.
    let finalErr: string | null = null;
    try {
      if (chunksRef.current.length > 0) {
        const merged = new Blob(chunksRef.current, { type: "audio/webm" });
        const audioPath = await persistAudio(merged);
        const result = await transcribeAudio(audioPath, optsRef.current.language);
        const { appended, full } = diffText(prevTextRef.current, result.text);
        const finalText = appended ? full : result.text;
        setPartialText("");
        if (finalText.trim()) optsRef.current.onFinal?.(finalText.trim());
      }
    } catch (err) {
      finalErr = err instanceof Error ? err.message : String(err);
    }

    cleanup();
    setDurationSecs(0);
    setPhase("idle");

    // Surface transcription failure AFTER cleanup so the UI is back to idle.
    if (finalErr) {
      optsRef.current.onError?.(
        `Transcription failed: ${finalErr}. Is whisper-cli installed? Run scripts/dev/fetch-whisper.sh`,
      );
    }
  }, [cleanup, setPhase]); // stable deps

  return { state: recorderState, partialText, durationSecs, volumeLevel, downloadPct, start, stop };
}
