import { useTranslation } from "react-i18next";
import { useThemeStore } from "@/stores/theme-store";

const languages = [
  { code: "en", label: "EN" },
  { code: "id", label: "ID" },
];

export function LanguageSwitcher() {
  const { i18n } = useTranslation();

  const handleLanguageChange = (langCode: string) => {
    i18n.changeLanguage(langCode);
  };

  return (
    <div className="flex items-center gap-1 rounded-md border border-line bg-raised p-0.5">
      {languages.map((lang) => (
        <button
          key={lang.code}
          onClick={() => handleLanguageChange(lang.code)}
          className={`px-2 py-1 text-[10px] font-mono font-medium tracking-wider transition-all duration-200 ${
            i18n.language === lang.code
              ? "bg-accent text-white"
              : "text-ink-faint hover:text-ink"
          }`}
        >
          {lang.label}
        </button>
      ))}
    </div>
  );
}