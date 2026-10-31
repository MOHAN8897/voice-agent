import React from 'react';
import { EmptyState } from './EmptyState';

/**
 * DataTable — the shell every console table uses. It owns the chrome (header row,
 * row dividers, hover, horizontal scroll on narrow screens, empty and loading
 * states); callers own the cells.
 *
 *   <DataTable
 *     columns={[{ key: 'name', header: 'Contact' }, { key: 'dur', header: 'Duration', numeric: true }]}
 *     rows={calls} rowKey={(c) => c.id} onRowClick={open}
 *     renderCell={(row, col) => …}
 *     empty={{ title: 'No calls yet', description: '…' }} />
 *
 * Headers are sentence case, 12px, medium weight — never all caps. Numeric
 * columns are right-aligned and use tabular mono figures.
 */
export function DataTable({
  columns,
  rows,
  rowKey = (row, index) => row.id ?? index,
  renderCell = (row, column) => row[column.key],
  onRowClick = null,
  empty = null,
  loading = false,
  loadingRows = 4,
  caption = null,
  className = '',
}) {
  if (!loading && rows.length === 0 && empty) {
    return <EmptyState compact {...empty} />;
  }
  return (
    <div className={`relative -mx-1 overflow-x-auto ${className}`}>
      <table className="w-full min-w-[560px] text-left text-ui">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-line">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`px-1 pb-2 text-meta font-medium text-fg-muted ${column.numeric ? 'text-right' : ''} ${column.className || ''}`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {loading
            ? Array.from({ length: loadingRows }).map((_, i) => (
                <tr key={`loading-${i}`}>
                  {columns.map((column) => (
                    <td key={column.key} className="px-1 py-3">
                      <span className="block h-3.5 w-3/4 animate-pulse rounded bg-line motion-reduce:animate-none" />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row, index) => (
                <tr
                  key={rowKey(row, index)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={`${onRowClick ? 'cursor-pointer' : ''} transition-colors hover:bg-canvas`}
                >
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={`px-1 py-3 align-top text-fg-body ${column.numeric ? 'text-right font-mono tabular-nums text-ink' : ''} ${column.cellClassName || ''}`}
                    >
                      {renderCell(row, column)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
