export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  pagination: PaginationMeta;
}

export interface ApiMessageResponse {
  message: string;
}

export interface ApiErrorPayload {
  error: {
    code: string;
    detail: unknown;
    extra?: Record<string, unknown>;
  };
  path: string;
  request_id: string;
}

export interface PaginationQuery {
  page?: number;
  page_size?: number;
}

export interface SearchSortQuery {
  search?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
}
