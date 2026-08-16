import { useTranslation } from "react-i18next";

/**
 * Terminal i18n label helper — compact key access with safe fallback.
 * Fallback ke string asli bila key belum diterjemahkan (dev/partial).
 */
export function useTerminalT() {
  const { t } = useTranslation();
  return (key: string, fallback: string): string => {
    const v = t(`terminal.${key}`, { defaultValue: undefined });
    return typeof v === "string" && v.length > 0 ? v : fallback;
  };
}