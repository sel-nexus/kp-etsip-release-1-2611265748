/** Render semantic inventory tables with accessible overflow and pagination. */
import type { ReactNode } from 'react';
import { Button } from './Button';
import type { ListPage } from '../types';
export interface Column<T> { title: string; render: (row: T) => ReactNode }
interface Props<T extends { id: string }> {
  caption: string;
  columns: Column<T>[];
  data: ListPage<T>;
  onPage: (page: number) => void;
  emptyMessage?: string;
}
/** Keep table headers and row identity intact at every viewport width. */
export function DataTable<T extends { id: string }>({ caption, columns, data, onPage, emptyMessage = 'No records found.' }: Props<T>) {
  const pages = Math.max(1, Math.ceil(data.total / data.pageSize));
  return (
    <section aria-label={caption}>
      <div className="table-scroll" tabIndex={0} role="region" aria-label={`${caption} table`}>
        <table>
          <caption>{caption}</caption>
          <thead>
            <tr>{columns.map(column => <th key={column.title} scope="col">{column.title}</th>)}</tr>
          </thead>
          <tbody>
            {data.items.map(row => (
              <tr key={row.id}>{columns.map(column => <td key={column.title}>{column.render(row)}</td>)}</tr>
            ))}
            {!data.items.length && (
              <tr><td colSpan={columns.length}>{emptyMessage}</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <nav className="actions" aria-label={`${caption} pagination`}>
        <Button variant="secondary" disabled={data.page <= 1} onClick={() => onPage(data.page - 1)}>Previous</Button>
        <span aria-live="polite">Page {data.page} of {pages} · {data.total} records</span>
        <Button variant="secondary" disabled={data.page >= pages} onClick={() => onPage(data.page + 1)}>Next</Button>
      </nav>
    </section>
  );
}
