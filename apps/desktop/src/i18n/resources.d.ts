import "i18next";

import type zhCommon from "./locales/zh-Hans/common.json";
import type zhNav from "./locales/zh-Hans/nav.json";
import type zhSettings from "./locales/zh-Hans/settings.json";
import type zhRuns from "./locales/zh-Hans/runs.json";
import type zhSession from "./locales/zh-Hans/session.json";
import type zhInspector from "./locales/zh-Hans/inspector.json";
import type zhErrors from "./locales/zh-Hans/errors.json";
import type zhPages from "./locales/zh-Hans/pages.json";

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "common";
    resources: {
      common: typeof zhCommon;
      nav: typeof zhNav;
      settings: typeof zhSettings;
      runs: typeof zhRuns;
      session: typeof zhSession;
      inspector: typeof zhInspector;
      errors: typeof zhErrors;
      pages: typeof zhPages;
    };
  }
}
