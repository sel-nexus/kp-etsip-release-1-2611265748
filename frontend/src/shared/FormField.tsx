/** Associate native form fields with their label and validation message. */
import type { InputHTMLAttributes } from 'react';
interface Props extends InputHTMLAttributes<HTMLInputElement> { label: string; error?: string }
/** Keep stable input identity and readable, associated validation feedback. */
export function FormField({ label, error, id, required, ...props }: Props) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        {...props}
        id={id}
        required={required}
        aria-required={required}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
      />
      {error && <p id={`${id}-error`} role="alert" className="error">{error}</p>}
    </div>
  );
}
