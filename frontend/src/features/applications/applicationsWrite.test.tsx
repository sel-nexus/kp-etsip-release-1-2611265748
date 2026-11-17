/** Exercise application form validation and complete submission. */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import ApplicationForm from './ApplicationForm';
import { canWriteApplication } from './applicationApi';
import type { Portfolio, User } from '../../types';

const portfolio: Portfolio = { id: '123456789012345678901234', name: 'Payments', owner: '', description: '', productArea: '', status: 'Active', applicationCount: 0, qualityScore: null, createdAt: '', updatedAt: '' };

describe('application maintenance', () => {
  it('rejects missing required values and unsafe links, then saves all fields', async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ApplicationForm portfolios={[portfolio]} onSave={save} onCancel={() => {}} />);
    await user.click(screen.getByRole('button', { name: 'Save application' }));
    expect(screen.getByText('Name is required.')).toBeInTheDocument();
    expect(screen.getByText('Portfolio is required.')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Name'), 'New application');
    await user.selectOptions(screen.getByLabelText('Portfolio'), portfolio.id);
    await user.type(screen.getByLabelText('Repository link'), 'javascript:bad');
    await user.click(screen.getByRole('button', { name: 'Save application' }));
    expect(screen.getByText('Enter an HTTP(S) URL without credentials.')).toBeInTheDocument();
    await user.clear(screen.getByLabelText('Repository link'));
    await user.type(screen.getByLabelText('Repository link'), 'https://example.com/repo');
    await user.click(screen.getByRole('button', { name: 'Save application' }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0]).toMatchObject({ name: 'New application', portfolioId: portfolio.id, repositoryLink: 'https://example.com/repo', qualityScore: 0 });
  });
  it.each([
    ['Tier', '', 'Tier is outside the allowed range.'],
    ['Tier', '0', 'Tier is outside the allowed range.'],
    ['Tier', '5', 'Tier is outside the allowed range.'],
    ['Health score', '-1', 'Health score is outside the allowed range.'],
    ['Quality score', '101', 'Quality score is outside the allowed range.'],
    ['Automation coverage', '1.5', 'Automation coverage is outside the allowed range.'],
    ['Unit-test coverage', '', 'Unit-test coverage is outside the allowed range.'],
    ['Open defects', '-1', 'Open defects is outside the allowed range.'],
    ['Open critical defects', '-1', 'Open critical defects is outside the allowed range.'],
  ])('rejects invalid %s value %s and then accepts a corrected value', async (label, value, error) => {
    const save = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ApplicationForm portfolios={[portfolio]} onSave={save} onCancel={() => {}} />);
    await user.type(screen.getByLabelText('Name'), 'App');
    await user.selectOptions(screen.getByLabelText('Portfolio'), portfolio.id);
    const input = screen.getByLabelText(label);
    await user.clear(input);
    if (value) await user.type(input, value);
    await user.click(screen.getByRole('button', { name: 'Save application' }));
    expect(screen.getByText(error)).toBeVisible();
    expect(save).not.toHaveBeenCalled();
    await user.clear(input);
    await user.type(input, label === 'Tier' ? '4' : '0');
    await user.click(screen.getByRole('button', { name: 'Save application' }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(screen.queryByText(error)).not.toBeInTheDocument();
  });

  it.each([['Name', 201], ['Description', 2001]])('rejects oversized %s and saves at the limit', async (label, length) => {
    const save = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<ApplicationForm portfolios={[portfolio]} onSave={save} onCancel={() => {}} />);
    await user.type(screen.getByLabelText('Name'), 'App');
    await user.selectOptions(screen.getByLabelText('Portfolio'), portfolio.id);
    const input = screen.getByLabelText(label);
    await user.clear(input);
    await user.click(input);
    await user.paste('x'.repeat(length));
    await user.click(screen.getByRole('button', { name: 'Save application' }));
    expect(screen.getByText(`${label} is too long.`)).toBeVisible();
    expect(save).not.toHaveBeenCalled();
    await user.clear(input);
    await user.click(input);
    await user.paste('x'.repeat(length - 1));
    await user.click(screen.getByRole('button', { name: 'Save application' }));
    await waitFor(() => expect(save).toHaveBeenCalledOnce());
    expect(save.mock.calls[0][0][label === 'Name' ? 'name' : 'description']).toHaveLength(length - 1);
  });

  it.each([['Repository link', 'repositoryLink'], ['Pipeline link', 'pipelineLink']] as const)(
    'validates %s and submits a safe URL or an empty link', async (label, key) => {
      const save = vi.fn().mockResolvedValue(undefined);
      const user = userEvent.setup();
      render(<ApplicationForm portfolios={[portfolio]} onSave={save} onCancel={() => {}} />);
      await user.type(screen.getByLabelText('Name'), 'App');
      await user.selectOptions(screen.getByLabelText('Portfolio'), portfolio.id);
      const input = screen.getByLabelText(label);
      await user.type(input, 'https://user:pass@example.com');
      await user.click(screen.getByRole('button', { name: 'Save application' }));
      expect(screen.getByText('Enter an HTTP(S) URL without credentials.')).toBeVisible();
      expect(save).not.toHaveBeenCalled();
      await user.clear(input);
      await user.type(input, 'http://example.com/path');
      await user.click(screen.getByRole('button', { name: 'Save application' }));
      await waitFor(() => expect(save).toHaveBeenCalledOnce());
      expect(save.mock.calls[0][0][key]).toBe('http://example.com/path');
      await user.clear(input);
      await user.click(screen.getByRole('button', { name: 'Save application' }));
      await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
      expect(save.mock.calls[1][0][key]).toBeNull();
    },
  );

  it('shows server failures and prevents read-only mutation controls', async () => {
    const user = userEvent.setup();
    render(<ApplicationForm portfolios={[portfolio]} onSave={async () => { throw new Error('Conflict'); }} onCancel={() => {}} />);
    await user.type(screen.getByLabelText('Name'), 'App');
    await user.selectOptions(screen.getByLabelText('Portfolio'), portfolio.id);
    await user.click(screen.getByRole('button', { name: 'Save application' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Conflict');
    const reader = { role: 'Read Only', permissions: ['view', 'create', 'edit', 'delete'], mustChangePassword: false } as User;
    expect(canWriteApplication(reader, 'create')).toBe(false);
    expect(canWriteApplication(reader, 'delete')).toBe(false);
  });
});
