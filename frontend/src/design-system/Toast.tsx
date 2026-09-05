import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";

import { ToastContext } from "./toast-context";
import styles from "./Toast.module.css";

type ToastType = "success" | "info" | "warning" | "error";

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
}

const ICONS: Record<ToastType, typeof CheckCircle2> = {
  success: CheckCircle2,
  info: Info,
  warning: AlertTriangle,
  error: XCircle,
};

const AUTO_DISMISS_MS = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const showToast = useCallback(
    (type: ToastType, message: string) => {
      const id = nextId.current++;
      setToasts((current) => [...current, { id, type, message }]);
      window.setTimeout(() => dismiss(id), AUTO_DISMISS_MS);
    },
    [dismiss]
  );

  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className={styles.viewport} role="region" aria-label="Benachrichtigungen">
        {toasts.map((toast) => {
          const Icon = ICONS[toast.type];
          return (
            <div key={toast.id} className={`${styles.toast} ${styles[toast.type]}`} role="status">
              <Icon size={16} className={styles.icon} aria-hidden="true" />
              <span>{toast.message}</span>
              <button
                type="button"
                className={styles.closeButton}
                onClick={() => dismiss(toast.id)}
                aria-label="Benachrichtigung schließen"
              >
                <X size={14} aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
