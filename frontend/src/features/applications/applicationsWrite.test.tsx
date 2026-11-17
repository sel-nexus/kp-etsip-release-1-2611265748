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
