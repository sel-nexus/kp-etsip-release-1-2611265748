/** Render every maintained portfolio field with associated validation feedback. */
import { useState } from 'react';
import type { FormEvent } from 'react';
import type { PortfolioWrite } from '../../types';
import { Button } from '../../shared/Button';
import { FormField } from '../../shared/FormField';
interface Props { initial?: PortfolioWrite; onSave: (value: PortfolioWrite) => Promise<void>; onCancel: () => void }
/** Keep user input on errors and prevent invalid or duplicate submissions. */
export default function PortfolioForm({ initial, onSave, onCancel }: Props) {
  const [value, setValue] = useState<PortfolioWrite>(initial ? {
    name: initial.name, owner: initial.owner, description: initial.description,
    productArea: initial.productArea, status: initial.status,
  } : { name: '', owner: '', description: '', productArea: '', status: 'Active' });
  const [errors, setErrors] = useState<Partial<Record<keyof PortfolioWrite, string>>>({});
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  /** Validate the complete write contract before crossing the API boundary. */
  async function submit(event: FormEvent) {
    event.preventDefault();
    const next: typeof errors = {};
    for (const field of ['name', 'owner', 'description', 'productArea'] as const) {
      if (value[field].trim().length > (field === 'description' ? 2000 : 200)) next[field] = `${field === 'description' ? 'Description' : 'Field'} is too long.`;
    }
    if (!value.name.trim()) next.name = 'Name is required.';
    setErrors(next);
    if (Object.keys(next).length) return;
    setPending(true);
    setError('');
    try { await onSave({ ...value, name: value.name.trim(), owner: value.owner.trim(), description: value.description.trim(), productArea: value.productArea.trim() }); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to save portfolio.'); }
    finally { setPending(false); }
  }
  return (
    <form className="card" onSubmit={submit} noValidate aria-label="Portfolio form">
      <fieldset disabled={pending}>
        <legend>{initial ? 'Edit portfolio' : 'New portfolio'}</legend>
        <FormField id="portfolio-name" label="Name" required value={value.name} error={errors.name}
          onChange={event => setValue({ ...value, name: event.target.value })} />
        <FormField id="portfolio-owner" label="Owner" value={value.owner} error={errors.owner}
          onChange={event => setValue({ ...value, owner: event.target.value })} />
        <FormField id="portfolio-area" label="Product area" value={value.productArea} error={errors.productArea}
          onChange={event => setValue({ ...value, productArea: event.target.value })} />
        <div className="field">
          <label htmlFor="portfolio-description">Description</label>
          <textarea id="portfolio-description" value={value.description} aria-invalid={Boolean(errors.description)}
            aria-describedby={errors.description ? 'description-error' : undefined}
            onChange={event => setValue({ ...value, description: event.target.value })} />
          {errors.description && <p id="description-error" role="alert" className="error">{errors.description}</p>}
        </div>
        <div className="field">
          <label htmlFor="portfolio-status">Status</label>
          <select id="portfolio-status" value={value.status}
            onChange={event => setValue({ ...value, status: event.target.value as PortfolioWrite['status'] })}>
            <option>Active</option>
            <option>Archived</option>
          </select>
        </div>
        {error && <p role="alert" className="error">{error}</p>}
        <div className="actions">
          <Button type="submit" pending={pending}>{pending ? 'Saving…' : 'Save portfolio'}</Button>
          <Button type="button" variant="secondary" disabled={pending} onClick={onCancel}>Cancel</Button>
        </div>
      </fieldset>
    </form>
  );
}
