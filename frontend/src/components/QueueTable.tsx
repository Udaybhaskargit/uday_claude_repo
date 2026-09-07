import type { ReactNode } from "react";

export interface QueueColumn<Row> {
  header: string;
  render: (row: Row) => ReactNode;
}

interface QueueTableProps<Row> {
  columns: QueueColumn<Row>[];
  rows: Row[];
  rowKey: (row: Row) => string | number;
  emptyMessage?: string;
}

export function QueueTable<Row>({
  columns,
  rows,
  rowKey,
  emptyMessage = "No items to show.",
}: QueueTableProps<Row>) {
  if (rows.length === 0) {
    return <p className="text-sm text-slate-700">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto rounded-md border border-slate-300">
      <table className="min-w-full divide-y divide-slate-300 text-left text-sm">
        <thead className="bg-slate-100">
          <tr>
            {columns.map((col) => (
              <th key={col.header} className="px-4 py-2 font-semibold text-navy-950">
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-300 bg-white">
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((col) => (
                <td key={col.header} className="px-4 py-2 text-slate-700">
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
