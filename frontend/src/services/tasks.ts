import type { ApiMessageResponse, PaginationQuery, SearchSortQuery, Task, TaskListResponse } from "../types";
import { buildQueryString } from "../utils/queryString";
import { apiClient } from "./http";


export interface TaskListQuery extends PaginationQuery, SearchSortQuery {
  assigned_to_id?: string;
  priority?: string;
  status?: string;
}

export interface TaskPayload {
  title: string;
  description?: string | null;
  assigned_to_id?: string | null;
  due_date?: string | null;
  priority?: string;
  status?: string;
}

export const tasksService = {
  async list(query: TaskListQuery = {}): Promise<TaskListResponse> {
    const { data } = await apiClient.get<TaskListResponse>(`/tasks${buildQueryString(query)}`);
    return data;
  },

  async create(payload: TaskPayload): Promise<Task> {
    const { data } = await apiClient.post<Task>("/tasks", payload);
    return data;
  },

  async update(taskId: string, payload: Partial<TaskPayload>): Promise<Task> {
    const { data } = await apiClient.put<Task>(`/tasks/${taskId}`, payload);
    return data;
  },

  async remove(taskId: string): Promise<ApiMessageResponse> {
    const { data } = await apiClient.delete<ApiMessageResponse>(`/tasks/${taskId}`);
    return data;
  }
};
