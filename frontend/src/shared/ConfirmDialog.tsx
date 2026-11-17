/** Provide native modal confirmation with focus trapping and restoration. */
import { useEffect, useId, useRef } from 'react';
import { Button } from './Button';
interface Props { title: string; message: string; pending: boolean; error?: string; onCancel: () => void; onConfirm: () => void }
/** Keep destructive actions behind an explicit, keyboard-safe decision. */
export function ConfirmDialog({ title, message, pending, error, onCancel, onConfirm }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog?.showModal();
    return () => {
      dialog?.close();
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="card confirm-dialog"
      aria-labelledby={titleId}
      aria-modal="true"
      onCancel={event => { event.preventDefault(); if (!pending) onCancel(); }}
      onClick={event => { if (event.target === ref.current && !pending) onCancel(); }}
    >
      <div>
        <h2 id={titleId}>{title}</h2>
        <p>{message}</p>
        {error && <p role="alert" className="error">{error}</p>}
        <div className="actions">
          <Button variant="secondary" autoFocus disabled={pending} onClick={onCancel}>Cancel</Button>
          <Button pending={pending} onClick={onConfirm}>{pending ? 'Deleting…' : 'Confirm delete'}</Button>
        </div>
      </div>
    </dialog>
  );
}
