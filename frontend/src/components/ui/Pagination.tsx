import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "./Button";


interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}


export function Pagination({ page, pageSize, total, totalPages, onPageChange }: PaginationProps) {
  if (total === 0) {
    return null;
  }
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="pagination">
      <div>
        Showing <strong>{start}</strong>–<strong>{end}</strong> of <strong>{total}</strong>
      </div>
      <div className="pagination__controls">
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
          Page {page} / {Math.max(totalPages, 1)}
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
      </div>
    </div>
  );
}
