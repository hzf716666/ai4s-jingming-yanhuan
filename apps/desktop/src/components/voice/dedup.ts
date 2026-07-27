/**
 * Incremental text-deduplication for streaming ASR. Each whisper-cli call
 * returns the full transcription of all audio accumulated so far — this
 * module extracts only the *new* text appended since the previous call.
 *
 * Strategy: longest-common-subsequence (LCS) at the character level.
 * The "appended" portion is everything in `next` that comes after the LCS
 * match with `prev`. This naturally handles corrections (whisper sometimes
 * revises earlier words in the same segment) — the revision becomes part of
 * the "appended" diff and the caller can either replace or append.
 */

/**
 * Result of comparing two consecutive transcription snapshots.
 * - `appended`: text that appears to be new since `prev`.
 * - `full`: the complete `next` text (for a full-replace display mode).
 */
export interface TextDiff {
  appended: string;
  full: string;
}

/**
 * Compute the longest common subsequence length between two strings.
 * Uses the classic O(n·m) DP with a single-row optimization for space.
 */
function lcsLength(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  // Keep only the previous row.
  let prev = new Uint16Array(n + 1);
  for (let i = 1; i <= m; i++) {
    const cur = new Uint16Array(n + 1);
    const ca = a.charCodeAt(i - 1);
    for (let j = 1; j <= n; j++) {
      if (ca === b.charCodeAt(j - 1)) {
        cur[j] = prev[j - 1] + 1;
      } else {
        cur[j] = Math.max(prev[j], cur[j - 1]);
      }
    }
    prev = cur;
  }
  return prev[n];
}

/** Find the index in `next` where the LCS with `prev` ends. Everything after
 *  that index is "new" text. Returns `next.length` when the strings are
 *  identical (no new text). */
function splitAfterLcs(prev: string, next: string): number {
  if (!prev) return 0; // first call — everything is new
  if (prev === next) return next.length;

  // Walk backwards from the end of both strings — the common suffix is the
  // cheapest and most reliable signal. Whisper rarely changes the *beginning*
  // of its output within a single streaming session; it appends or revises
  // the tail. A suffix match is O(min(m,n)) and handles the common case.
  let i = prev.length - 1;
  let j = next.length - 1;
  let suffix = 0;
  while (i >= 0 && j >= 0 && prev.charCodeAt(i) === next.charCodeAt(j)) {
    i--;
    j--;
    suffix++;
  }

  // If over half of the shorter string matched as a suffix, it's a clean
  // append — the new text starts right after the common prefix, which we
  // approximate as the old text minus the suffix.
  const minLen = Math.min(prev.length, next.length);
  if (suffix >= minLen * 0.4) {
    // The stable prefix is whatever came before the matched suffix in `prev`.
    // New text is everything past that prefix in `next`.
    const prefixLen = prev.length - suffix;
    return Math.min(prefixLen, next.length);
  }

  // Fallback: full LCS. Expensive for long text, but transcription outputs
  // are bounded (a few hundred chars per 2 s window).
  const lcs = lcsLength(prev, next);
  if (lcs === 0) return 0; // completely different — return all

  // Estimate the split point: walk `next` and find where LCS coverage drops.
  // Simple heuristic: the appended text starts after `lcs` chars of `next`
  // when the strings are mostly aligned.
  const ratio = lcs / Math.max(prev.length, 1);
  if (ratio >= 0.85) {
    // High overlap — the new text is roughly past `prev.length` in `next`.
    return Math.min(prev.length, next.length);
  }

  // Low overlap (significant revision) — return the full `next` so the UI
  // replaces rather than appends.
  return 0;
}

/**
 * Given two consecutive full transcriptions, return the new text.
 *
 *   diffText("你好", "你好世界")     → { appended: "世界", full: "你好世界" }
 *   diffText("", "你好")             → { appended: "你好", full: "你好" }
 *   diffText("abc", "xyz")           → { appended: "xyz", full: "xyz" }
 */
export function diffText(prev: string, next: string): TextDiff {
  const split = splitAfterLcs(prev, next);
  const appended = next.slice(split);
  return { appended, full: next };
}
