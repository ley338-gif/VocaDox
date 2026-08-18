import { ChevronDown } from "lucide-react";

import styles from "./FormControls.module.css";

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={styles.input} {...props} />;
}

export function Select({ children, ...rest }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={styles.selectWrap}>
      <select className={styles.select} {...rest}>
        {children}
      </select>
      <ChevronDown size={16} className={styles.chevron} />
    </div>
  );
}

export function Checkbox(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input type="checkbox" className={styles.checkbox} {...props} />;
}

export function Radio(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input type="radio" className={styles.radio} {...props} />;
}
