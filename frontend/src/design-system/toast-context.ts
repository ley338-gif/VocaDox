import { createContext } from "react";

export interface ToastContextValue {
  showToast: (type: "success" | "info" | "warning" | "error", message: string) => void;
}

export const ToastContext = createContext<ToastContextValue | undefined>(undefined);
