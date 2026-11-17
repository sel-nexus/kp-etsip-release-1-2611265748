/** Render consistent semantic action buttons with pending-state support. */
import type { ButtonHTMLAttributes } from 'react';
interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary';
  pending?: boolean;
}
const variants = { primary: 'button-primary', secondary: 'button-secondary' };
/** Preserve native button behavior and expose loading to assistive technology. */
export function Button({ variant = 'primary', pending = false, className = '', disabled, ...props }: Props) {
  return (
    <button
      {...props}
      className={`button ${variants[variant]} ${className}`}
      disabled={disabled || pending}
      aria-busy={pending}
    />
  );
}
