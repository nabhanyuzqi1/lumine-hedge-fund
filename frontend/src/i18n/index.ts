import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

// Lazy loading - translations akan di-load on-demand
// English sebagai default (sudah ada embedded untuk fast initial load)
const defaultTranslations = {
  nav: { overview: "Overview", risk: "Risk", research: "Research", performance: "Performance" },
  hero: { title: "AI-Native Quantitative Intelligence", subtitle: "Institutional-grade algorithmic trading powered by autonomous agents", cta: "Enter System", login: "Log In" },
  login: { title: "Authentication Required", username: "Username", password: "Password", submit: "Enter System", submitting: "Authenticating...", error: "Invalid credentials", restricted: "Restricted access — authorized users only", systemStatus: "System Status" },
};

const resources = {
  en: { translation: defaultTranslations },
  id: { translation: defaultTranslations }, // Fallback ke English dulu
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "en",
    supportedLngs: ["en", "id"],
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      caches: ["localStorage"],
    },
    // Load bahasa lain secara on-demand
    partialBundledLanguages: true,
  });

// Lazy load translations saat dibutuhkan
export const loadLanguage = async (lang: string) => {
  if (i18n.hasResourceBundle(lang, "translation")) return;
  
  try {
    const translations = await import(`./locales/${lang}.json`);
    i18n.addResourceBundle(lang, "translation", translations.default || translations);
  } catch (e) {
    console.warn(`Failed to load language: ${lang}`, e);
  }
};

export default i18n;