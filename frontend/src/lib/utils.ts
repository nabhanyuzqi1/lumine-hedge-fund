import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind classes safely.
 *
 * clsx collapses conditional/duplicate class strings; tailwind-merge resolves
 * conflicting utility classes so the last intent wins (e.g. "bg-up bg-down"
 * resolves to bg-down).
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
