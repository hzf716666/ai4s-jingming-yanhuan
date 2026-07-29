/**
 * Web Speech API recorder for browser environments.
 * Provides real-time streaming transcription via interimResults.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type WebSpeechState =
  | "idle"
  | "requesting"
  | "recording"
  | "transcribing"
  | "error";

export interface WebSpeechRecorderOptions {
  onPartial?: (appended: string, full: string) => void;
  onFinal?: (text: string) => void;
  onError?: (message: string) => void;
  language?: string;
}

export interface WebSpeechRecorderAPI {
  state: WebSpeechState;
  partialText: string;
  durationSecs: number;
  volumeLevel: number;
  downloadPct: number;
  start: () => void;
  stop: () => void;
}

export function hasWebSpeechSupport(): boolean {
  return typeof window !== "undefined" && "webkitSpeechRecognition" in window;
}

export function useWebSpeechRecorder(
  options: WebSpeechRecorderOptions = {}
): WebSpeechRecorderAPI {
  // Stable refs to avoid stale closures
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const [state, setState] = useState<WebSpeechState>("idle");
  const [partialText, setPartialText] = useState("");
  const [durationSecs, setDurationSecs] = useState(0);
  const [volumeLevel, setVolumeLevel] = useState(0);

  const recognitionRef = useRef<any>(null);
  const startTimeRef = useRef(0);
  const durationTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevTextRef = useRef("");

  const start = useCallback(() => {
    if (!hasWebSpeechSupport()) {
      optionsRef.current.onError?.("Web Speech API not supported in this browser");
      return;
    }

    const SpeechRecognition = (window as any).webkitSpeechRecognition;
    recognitionRef.current = new SpeechRecognition();
    recognitionRef.current.continuous = true;
    recognitionRef.current.interimResults = true; // Enable interim results for real-time streaming
    recognitionRef.current.lang = optionsRef.current.language || "zh-CN";

    recognitionRef.current.onresult = (event: any) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalText += transcript;
        } else {
          interimText += transcript;
        }
      }

      const full = finalText + interimText;
      setPartialText(full);

      // Call onPartial for interim results (real-time streaming)
      if (interimText) {
        // Calculate newly appended text since last result
        const appended = full.slice(prevTextRef.current.length);
        if (appended) {
          optionsRef.current.onPartial?.(appended, full);
        }
        prevTextRef.current = full;
      }

      // When final result arrives, also call onPartial with the final text
      if (finalText) {
        optionsRef.current.onPartial?.(finalText, full);
      }
    };

    recognitionRef.current.onerror = (event: any) => {
      setState("error");
      optionsRef.current.onError?.(event.error);
      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
        durationTimerRef.current = null;
      }
    };

    recognitionRef.current.onend = () => {
      // Only process if we were actually recording
      if (recognitionRef.current && state === "recording") {
        setState("idle");
        if (durationTimerRef.current) {
          clearInterval(durationTimerRef.current);
          durationTimerRef.current = null;
        }
      }
    };

    recognitionRef.current.start();
    setState("recording");
    startTimeRef.current = Date.now();
    prevTextRef.current = "";

    // Duration counter
    durationTimerRef.current = setInterval(() => {
      const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000);
      setDurationSecs(elapsed);
    }, 250);
  }, []);

  const stop = useCallback(() => {
    if (durationTimerRef.current) {
      clearInterval(durationTimerRef.current);
      durationTimerRef.current = null;
    }
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setState("idle");
    setDurationSecs(0);
    setPartialText("");
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (durationTimerRef.current) {
        clearInterval(durationTimerRef.current);
      }
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  return {
    state,
    partialText,
    durationSecs,
    volumeLevel,
    downloadPct: 0,
    start,
    stop,
  };
}
