/** Edit all manually maintained application fields. */
import { useState } from 'react';
import type { FormEvent } from 'react';
import type { ApplicationWrite, Portfolio } from '../../types';
import { Button } from '../../shared/Button';

const initialValue: ApplicationWrite = {
  name: '', description: '', portfolioId: '', productArea: '', businessOwner: '', technologyOwner: '', etsOwner: '',
  criticality: 'Medium', tier: 2, lifecycleStatus: 'Active', technologyStack: '', repositoryLink: null, pipelineLink: null,
  applicationHealthScore: 0, qualityScore: 0, automationCoverage: 0, unitTestCoverage: 0, openDefects: 0,
  openCriticalDefects: 0, riskLevel: 'Low',
};
const textFields = [
  ['name', 'Name'], ['description', 'Description'], ['productArea', 'Product area'], ['businessOwner', 'Business owner'],
  ['technologyOwner', 'Technology owner'], ['etsOwner', 'ETS owner'], ['technologyStack', 'Technology stack'],
  ['repositoryLink', 'Repository link'], ['pipelineLink', 'Pipeline link'],
] as const;
const numericFields = [
  ['tier', 'Tier', 1, 4], ['applicationHealthScore', 'Health score', 0, 100], ['qualityScore', 'Quality score', 0, 100],
  ['automationCoverage', 'Automation coverage', 0, 100], ['unitTestCoverage', 'Unit-test coverage', 0, 100],
  ['openDefects', 'Open defects', 0, undefined], ['openCriticalDefects', 'Open critical defects', 0, undefined],
] as const;
interface Props { initial?: ApplicationWrite; portfolios: Portfolio[]; onSave: (value: ApplicationWrite) => Promise<void>; onCancel: () => void }

/** Retain edits and report field and server errors without losing input. */
export default function ApplicationForm({ initial, portfolios, onSave, onCancel }: Props) {
  const [value, setValue] = useState<ApplicationWrite>(initial ? Object.fromEntries(Object.keys(initialValue).map(key => [key, initial[key as keyof ApplicationWrite]])) as unknown as ApplicationWrite : initialValue);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!value.name.trim()) next.name = 'Name is required.';
    if (!value.portfolioId) next.portfolioId = 'Portfolio is required.';
    for (const [key, label] of textFields) {
      const text = value[key] || '';
      if (text.length > (key === 'name' ? 200 : 2000)) next[key] = `${label} is too long.`;
      if ((key === 'repositoryLink' || key === 'pipelineLink') && text) {
        try { const url = new URL(text); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error(); }
        catch { next[key] = 'Enter an HTTP(S) URL without credentials.'; }
      }
    }
    for (const [key, label, min, max] of numericFields) {
      if (!Number.isInteger(value[key]) || value[key] < min || (max !== undefined && value[key] > max)) next[key] = `${label} is outside the allowed range.`;
    }
    setErrors(next);
    if (Object.keys(next).length) return;
    setPending(true); setError('');
    try { await onSave({ ...value, name: value.name.trim() }); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to save application.'); }
    finally { setPending(false); }
  }
  return (
    <form className="card" onSubmit={submit} noValidate aria-label="Application form">
      <fieldset disabled={pending}>
        <legend>{initial ? 'Edit application' : 'New application'}</legend>
        {textFields.map(([key, label]) => (
          <div className="field" key={key}>
            <label htmlFor={`application-${key}`}>{label}</label>
            <input id={`application-${key}`} value={value[key] || ''} aria-required={key === 'name'} aria-invalid={Boolean(errors[key])}
              aria-describedby={errors[key] ? `application-${key}-error` : undefined}
              onChange={event => setValue({ ...value, [key]: event.target.value || (key === 'repositoryLink' || key === 'pipelineLink' ? null : '') })} />
            {errors[key] && <p id={`application-${key}-error`} role="alert" className="error">{errors[key]}</p>}
          </div>
        ))}
        <div className="field">
          <label htmlFor="application-portfolio">Portfolio</label>
          <select id="application-portfolio" value={value.portfolioId} aria-required="true" aria-invalid={Boolean(errors.portfolioId)}
            aria-describedby={errors.portfolioId ? 'application-portfolio-error' : undefined} onChange={event => setValue({ ...value, portfolioId: event.target.value })}>
            <option value="">Select a portfolio</option>
            {portfolios.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          {errors.portfolioId && <p id="application-portfolio-error" role="alert" className="error">{errors.portfolioId}</p>}
        </div>
        {numericFields.map(([key, label, min, max]) => (
          <div className="field" key={key}>
            <label htmlFor={`application-${key}`}>{label}</label>
            <input id={`application-${key}`} type="number" min={min} max={max} step="1" value={Number.isNaN(value[key]) ? '' : value[key]}
              aria-invalid={Boolean(errors[key])} aria-describedby={errors[key] ? `application-${key}-error` : undefined}
              onChange={event => setValue({ ...value, [key]: event.target.value === '' ? NaN : Number(event.target.value) })} />
            {errors[key] && <p id={`application-${key}-error`} role="alert" className="error">{errors[key]}</p>}
          </div>
        ))}
        {([['criticality', 'Criticality', ['Low', 'Medium', 'High', 'Critical']], ['lifecycleStatus', 'Lifecycle status', ['Active', 'Deprecated', 'Retired']], ['riskLevel', 'Risk level', ['Low', 'Medium', 'High']]] as const).map(([key, label, options]) => (
          <div className="field" key={key}>
            <label htmlFor={`application-${key}`}>{label}</label>
            <select id={`application-${key}`} value={value[key]} onChange={event => setValue({ ...value, [key]: event.target.value })}>
              {options.map(option => <option key={option}>{option}</option>)}
            </select>
          </div>
        ))}
        {error && <p role="alert" className="error">{error}</p>}
        <div className="actions">
          <Button type="submit" pending={pending}>{pending ? 'Saving…' : 'Save application'}</Button>
          <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        </div>
      </fieldset>
    </form>
  );
}
