import { cloneElement, useId, type ReactElement } from "react";

import styles from "./FormField.module.css";

interface FormFieldProps {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactElement<{ id?: string; "aria-describedby"?: string; "aria-invalid"?: boolean }>;
}

export function FormField({ label, hint, error, required, children }: FormFieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>
        {label}
        {required && (
          <span className={styles.required} aria-hidden="true">
            *
          </span>
        )}
      </label>
      {cloneElement(children, {
        id,
        "aria-describedby": describedBy,
        "aria-invalid": Boolean(error),
      })}
      {hint && !error && (
        <span className={styles.hint} id={hintId}>
          {hint}
        </span>
      )}
      {error && (
        <span className={styles.error} id={errorId} role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
