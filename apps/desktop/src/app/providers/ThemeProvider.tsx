import { useEffect, type ReactNode } from "react";
import { isMacUA, isTauri, setWindowTheme } from "@/lib/tauri";

/** 应用固定深色外观（单主题构建），把 data-theme 和原生窗口主题设为 dark。 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    document.documentElement.dataset.theme = "dark";
    void setWindowTheme(true);
  }, []);
  // The macOS desktop window has a vibrancy material behind the webview
  // (tauri.macos.conf.json); flag the root so CSS can let the sidebar show it.
  useEffect(() => {
    if (isTauri && isMacUA()) document.documentElement.dataset.vibrancy = "1";
  }, []);
  return <>{children}</>;
}
