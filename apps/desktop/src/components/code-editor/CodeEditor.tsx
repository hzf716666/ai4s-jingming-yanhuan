import { useEffect, useRef } from "react";
import { EditorView, keymap, placeholder as placeholderExt } from "@codemirror/view";
import { EditorState, Compartment } from "@codemirror/state";
import { basicSetup } from "codemirror";
import { indentWithTab } from "@codemirror/commands";
import type { Extension } from "@codemirror/state";
import type { ViewUpdate } from "@codemirror/view";

/** Language extension loaded lazily per file extension. */
type LangFactory = () => Promise<{ default: () => Extension }>;

/** File-extension → language factory map. Lazy dynamic imports keep the bundle
 *  slim — each language pack is only loaded when a file of that type is opened. */
const LANG: Record<string, LangFactory> = {
  js: () => import("@codemirror/lang-javascript").then((m) => ({ default: m.javascript })),
  jsx: () => import("@codemirror/lang-javascript").then((m) => ({ default: () => m.javascript({ jsx: true }) })),
  ts: () => import("@codemirror/lang-javascript").then((m) => ({ default: () => m.javascript({ typescript: true }) })),
  tsx: () => import("@codemirror/lang-javascript").then((m) => ({ default: () => m.javascript({ jsx: true, typescript: true }) })),
  py: () => import("@codemirror/lang-python").then((m) => ({ default: m.python })),
  json: () => import("@codemirror/lang-json").then((m) => ({ default: m.json })),
  html: () => import("@codemirror/lang-html").then((m) => ({ default: m.html })),
  htm: () => import("@codemirror/lang-html").then((m) => ({ default: m.html })),
  css: () => import("@codemirror/lang-css").then((m) => ({ default: m.css })),
  md: () => import("@codemirror/lang-markdown").then((m) => ({ default: m.markdown })),
  xml: () => import("@codemirror/lang-xml").then((m) => ({ default: m.xml })),
  svg: () => import("@codemirror/lang-xml").then((m) => ({ default: m.xml })),
  sql: () => import("@codemirror/lang-sql").then((m) => ({ default: m.sql })),
  rs: () => import("@codemirror/lang-rust").then((m) => ({ default: m.rust })),
  yaml: () => import("@codemirror/lang-yaml").then((m) => ({ default: m.yaml })),
  yml: () => import("@codemirror/lang-yaml").then((m) => ({ default: m.yaml })),
  toml: () => import("@codemirror/lang-yaml").then((m) => ({ default: m.yaml })),
  sh: () => import("@codemirror/lang-javascript").then((m) => ({ default: m.javascript })),
  bash: () => import("@codemirror/lang-javascript").then((m) => ({ default: m.javascript })),
  tex: () => import("@codemirror/lang-markdown").then((m) => ({ default: m.markdown })),
  r: () => import("@codemirror/lang-python").then((m) => ({ default: m.python })),
};

const langCompartment = new Compartment();
const readOnlyCompartment = new Compartment();

interface CodeEditorProps {
  /** Current file content. */
  value: string;
  /** Called on every edit with the new document text. */
  onChange: (value: string) => void;
  /** File path for language detection (e.g. "src/main.py"). */
  path?: string;
  /** Explicit language mode, overrides path-based detection. */
  language?: string;
  /** Called on Ctrl+S / Cmd+S. When absent, the shortcut falls back to default. */
  onSave?: () => void;
  /** When true, the editor is read-only (no edits, no cursor blink). */
  readOnly?: boolean;
  /** Placeholder shown when the document is empty. */
  placeholder?: string;
}

/**
 * CodeMirror 6 editor for workspace files. Directly editable — no read-only
 * toggle needed. Auto-detects language from file extension with lazy-loaded
 * language packs. Ctrl+S triggers onSave.
 */
export function CodeEditor({
  value,
  onChange,
  path,
  language,
  onSave,
  readOnly = false,
  placeholder,
}: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const readOnlyRef = useRef(readOnly);
  readOnlyRef.current = readOnly;

  // Detect extension from path
  const ext = path ? path.split(".").pop()?.toLowerCase() ?? "" : "";
  const langFactory = language ? null : LANG[ext] ?? null;

  useEffect(() => {
    if (!containerRef.current) return;

    const saveKeymap = keymap.of([
      {
        key: "Mod-s",
        run: () => {
          onSaveRef.current?.();
          return true;
        },
        preventDefault: true,
      },
    ]);

    const extensions = [
      basicSetup,
      saveKeymap,
      keymap.of([indentWithTab]),
      // Theme — reads from the app's CSS custom properties so all three
      // themes (warm / light / dark) work without a re-init.
      EditorView.theme({
        "&": {
          fontSize: "12.5px",
          fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace",
          backgroundColor: "var(--surface)",
          color: "var(--text)",
        },
        ".cm-scroller": {
          fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace",
          lineHeight: "1.55",
        },
        ".cm-gutters": {
          backgroundColor: "var(--surface-2)",
          color: "var(--muted)",
          border: "none",
          borderRight: "1px solid var(--border)",
        },
        ".cm-activeLineGutter": {
          backgroundColor: "var(--surface-2)",
          color: "var(--text)",
        },
        ".cm-activeLine": {
          backgroundColor: "transparent",
        },
        ".cm-cursor": {
          borderLeftColor: "var(--accent)",
        },
        ".cm-selectionBackground, ::selection": {
          backgroundColor: "var(--border) !important",
        },
        ".cm-selectionMatch": {
          backgroundColor: "var(--border-faint)",
        },
        ".cm-matchingBracket": {
          backgroundColor: "var(--border)",
          outline: "none",
        },
        ".cm-foldPlaceholder": {
          backgroundColor: "var(--surface-2)",
          color: "var(--muted)",
          border: "1px solid var(--border)",
        },
        ".cm-tooltip": {
          backgroundColor: "var(--surface)",
          color: "var(--text)",
          border: "1px solid var(--border)",
        },
        // Syntax highlighting — reuse the app's hljs variables
        ".cm-keyword": { color: "var(--hl-keyword)" },
        ".cm-atom": { color: "var(--hl-constant)" },
        ".cm-number": { color: "var(--hl-constant)" },
        ".cm-typeName": { color: "var(--hl-entity)" },
        ".cm-def": { color: "var(--hl-entity)" },
        ".cm-property": { color: "var(--hl-entity)" },
        ".cm-operator": { color: "var(--text)" },
        ".cm-variableName": { color: "var(--text)" },
        ".cm-variable-2": { color: "var(--hl-builtin)" },
        ".cm-variable-3": { color: "var(--hl-entity)" },
        ".cm-comment": { color: "var(--hl-comment)", fontStyle: "italic" },
        ".cm-string": { color: "var(--hl-string)" },
        ".cm-string-2": { color: "var(--hl-string)" },
        ".cm-meta": { color: "var(--muted)" },
        ".cm-qualifier": { color: "var(--hl-keyword)" },
        ".cm-builtin": { color: "var(--hl-builtin)" },
        ".cm-tag": { color: "var(--hl-tag)" },
        ".cm-attribute": { color: "var(--hl-entity)" },
        ".cm-link": { color: "var(--link)", textDecoration: "underline" },
        ".cm-header": { color: "var(--text)", fontWeight: "600" },
        ".cm-quote": { color: "var(--muted)" },
        ".cm-error": { color: "var(--error)" },
        ".cm-bracket": { color: "var(--muted)" },
        ".cm-hr": { color: "var(--muted)" },
      }),
      // Language — placeholder (no syntax) until loaded lazily
      langCompartment.of([]),
      readOnlyCompartment.of(EditorState.readOnly.of(readOnly)),
      EditorView.updateListener.of((update: ViewUpdate) => {
        if (update.docChanged) {
          const newValue = update.state.doc.toString();
          onChangeRef.current(newValue);
        }
      }),
    ];

    if (placeholder) {
      extensions.push(placeholderExt(placeholder));
    }

    const state = EditorState.create({
      doc: value,
      extensions,
    });

    const view = new EditorView({
      state,
      parent: containerRef.current,
    });

    viewRef.current = view;

    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // Only recreate on mount/unmount. Language and value updates are handled
    // by the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load language extension lazily when path/language changes
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;

    if (language) {
      // Explicit language string — try to match
      const key = language.toLowerCase();
      const factory = LANG[key];
      if (factory) {
        void factory().then((mod) => {
          if (viewRef.current) {
            view.dispatch({ effects: langCompartment.reconfigure(mod.default()) });
          }
        });
      }
    } else if (langFactory) {
      void langFactory().then((mod) => {
        if (viewRef.current) {
          view.dispatch({ effects: langCompartment.reconfigure(mod.default()) });
        }
      });
    }
  }, [language, langFactory]);

  // Apply value changes from outside (e.g. file reload)
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (value !== current) {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value },
      });
    }
  }, [value]);

  // Apply readOnly changes
  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    view.dispatch({
      effects: readOnlyCompartment.reconfigure(
        EditorState.readOnly.of(readOnly),
      ),
    });
  }, [readOnly]);

  return (
    <div
      ref={containerRef}
      className="code-editor h-full overflow-auto"
    />
  );
}
