/* eslint-disable react-refresh/only-export-components */
import * as React from "react";

import { cn } from "@/lib/utils";

type ToastVariant = "neutral" | "success" | "warn" | "danger";

interface ToastItem {
  id: string;
  variant: ToastVariant;
  title: string;
  description?: string;
  duration?: number;
}

interface ToastContextValue {
  toasts: ToastItem[];
  toast: (item: Omit<ToastItem, "id">) => string;
  dismiss: (id: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

function useToastContext() {
  const context = React.useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<ToastItem[]>([]);

  const toast = React.useCallback((item: Omit<ToastItem, "id">) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    setToasts((prev) => [...prev, { ...item, id }]);
    return id;
  }, []);

  const dismiss = React.useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const value = React.useMemo(() => ({ toasts, toast, dismiss }), [toasts, toast, dismiss]);

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}

export function useToast() {
  return useToastContext();
}

const variantClasses: Record<ToastVariant, string> = {
  neutral: "border border-border-subtle bg-bg-raised text-text-primary",
  success: "border border-up/30 bg-up/10 text-up",
  warn: "border border-warn/30 bg-warn/10 text-warn",
  danger: "border border-danger/30 bg-danger/10 text-danger",
};

export function ToastViewport() {
  const { toasts, dismiss } = useToastContext();

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="fixed bottom-4 right-4 z-50 flex w-full max-w-xs flex-col gap-2"
    >
      {toasts.map((item) => (
        <Toast key={item.id} item={item} onDismiss={() => dismiss(item.id)} />
      ))}
    </div>
  );
}

function Toast({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  React.useEffect(() => {
    const duration = item.duration ?? 5000;
    const timer = setTimeout(onDismiss, duration);
    return () => clearTimeout(timer);
  }, [item.duration, onDismiss]);

  const isDanger = item.variant === "danger";

  return (
    <div
      role="status"
      aria-live={isDanger ? "assertive" : "polite"}
      className={cn(
        "flex items-start justify-between gap-3 rounded-panel p-3 shadow-panel",
        variantClasses[item.variant]
      )}
    >
      <div className="min-w-0">
        <p className="text-sm font-medium">{item.title}</p>
        {item.description ? <p className="mt-0.5 text-xs opacity-90">{item.description}</p> : null}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="text-text-secondary hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </div>
  );
}
