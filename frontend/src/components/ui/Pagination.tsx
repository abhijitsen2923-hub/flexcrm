import { ChevronLeft, ChevronRight, ChevronsRight } from "lucide-react";

import { Button } from "./Button";


interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  // Opt-in extras (used by Leads). When omitted the bar renders exactly as before,
  // so the other list pages are unaffected.
  pageSizeOptions?: number[];
  onPageSizeChange?: (pageSize: number) => void;
  showJumpToLast?: boolean;
}


export function Pagination({
  page,
  pageSize,
  total,
  totalPages,
  onPageChange,
  pageSizeOptions,
  onPageSizeChange,
  showJumpToLast = false,
}: PaginationProps) {
  if (total === 0) {
    return null;
  }
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  const lastPage = Math.max(totalPages, 1);
  const showPageSize = Boolean(pageSizeOptions && onPageSizeChange);

  return (
    <div className="pagination">
      <div>
        Showing <strong>{start}</strong>–<strong>{end}</strong> of <strong>{total}</strong>
      </div>
      <div className="pagination__controls">
        {showPageSize && (
          <label className="pagination__page-size" style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
            <span className="text-xs muted">Per page</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange?.(Number(e.target.value))}
              aria-label="Rows per page"
            >
              {pageSizeOptions?.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        )}
        <Button
          size="sm"
          variant="secondary"
          icon={<ChevronLeft size={14} />}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Prev
        </Button>
        <span style={{ minWidth: 70, textAlign: "center" }}>
          Page {page} / {lastPage}
        </span>
        <Button
          size="sm"
          variant="secondary"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
          <ChevronRight size={14} />
        </Button>
        {showJumpToLast && (
          <Button
            size="sm"
            variant="secondary"
            disabled={page >= lastPage}
            onClick={() => onPageChange(lastPage)}
          >
            Last
            <ChevronsRight size={14} />
          </Button>
        )}
      </div>
    </div>
  );
}
