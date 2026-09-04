import { useEffect, type ReactNode } from "react";
import { DEFAULT_LOCALE } from "@/i18n/config";
import i18n from "@/i18n";

/** 应用固定简体中文界面（单语言构建），同步到 i18next 与文档根节点。
 *  Direction is set once here — components must never hardcode direction
 *  (see the i18n design doc, §7 RTL readiness). */
export function LocaleProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    void i18n.changeLanguage(DEFAULT_LOCALE);
    document.documentElement.lang = DEFAULT_LOCALE;
    document.documentElement.dir = "ltr";
  }, []);
  return <>{children}</>;
}
