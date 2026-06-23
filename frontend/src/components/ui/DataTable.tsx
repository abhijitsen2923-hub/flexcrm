import type { ReactNode } from "react";


export interface DataTableColumn<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  width?: string;
  align?: "left" | "right" | "center";
}


interface DataTableProps<T> {
  columns: ReadonlyArray<DataTableColumn<T>>;
  rows: ReadonlyArray<T>;
  rowKey: (row: T) => string;
  empty?: ReactNode;
  onRowClick?: (row: T) => void;
}


export function DataTable<T>({ columns, rows, rowKey, empty, onRowClick }: DataTableProps<T>) {
  if (rows.length === 0) {
    return <>{empty}</>;
  }
  return (
    <table className="table">
      <thead>
        <tr>
          {columns.map((column) => (
            <th
              key={column.key}
              style={{ width: column.width, textAlign: column.align ?? "left" }}
            >
              {column.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={rowKey(row)}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            style={onRowClick ? { cursor: "pointer" } : undefined}
          >
            {columns.map((column) => (
              <td key={column.key} data-label={column.key} style={{ textAlign: column.align ?? "left" }}>
                {column.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
