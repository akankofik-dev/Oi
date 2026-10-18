export type UiLocale = "zh" | "en" | "id";

export const UI_LOCALE_STORAGE_KEY = "oi:ui-locale";

/** Map browser language tags to a supported dashboard locale. */
export function detectBrowserLocale(): UiLocale {
  if (typeof navigator === "undefined") return "en";

  const candidates =
    navigator.languages?.length > 0
      ? navigator.languages
      : [navigator.language];

  for (const raw of candidates) {
    const lang = raw?.toLowerCase() ?? "";
    if (lang.startsWith("zh")) return "zh";
    if (lang.startsWith("id")) return "id";
    if (lang.startsWith("en")) return "en";
  }

  const primary = navigator.language?.toLowerCase() ?? "";
  if (primary.startsWith("zh")) return "zh";
  if (primary.startsWith("id")) return "id";
  if (primary.startsWith("en")) return "en";

  return "en";
}

export function normalizeUiLocale(raw: string | null | undefined): UiLocale {
  if (!raw) return "zh";
  const v = raw.toLowerCase();
  if (v.startsWith("zh")) return "zh";
  if (v.startsWith("id")) return "id";
  return "en";
}

export function readStoredUiLocale(): UiLocale | null {
  try {
    const raw = localStorage.getItem(UI_LOCALE_STORAGE_KEY);
    if (raw === "zh" || raw === "en" || raw === "id") return raw;
  } catch {
    // localStorage unavailable
  }
  return null;
}

export function storeUiLocale(locale: UiLocale): void {
  try {
    localStorage.setItem(UI_LOCALE_STORAGE_KEY, locale);
  } catch {
    // quota / disabled
  }
}

/** Stored user preference wins; otherwise follow the browser. */
export function resolveInitialLocale(): UiLocale {
  return readStoredUiLocale() ?? detectBrowserLocale();
}

export function syncDocumentLang(locale: UiLocale): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang =
    locale === "zh" ? "zh-CN" : locale === "id" ? "id" : "en";
}

/** BCP-47 tag for STT / SpeechRecognition from dashboard UI locale. */
export function speechLocaleFromUi(locale: string | null | undefined): string {
  const n = normalizeUiLocale(locale);
  return n === "zh" ? "zh-CN" : n === "id" ? "id-ID" : "en-US";
}
