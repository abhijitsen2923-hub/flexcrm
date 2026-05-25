import { useCallback, useEffect } from "react";

import { tasksService, type TaskListQuery, type TaskPayload } from "../services/tasks";
import type { TaskListResponse } from "../types";
import { useAsyncResource } from "./useAsyncResource";


const initialTasksResponse: TaskListResponse = {
  items: [],
  pagination: {
    page: 1,
    page_size: 20,
    total: 0,
    total_pages: 1
  }
};


export function useTasks(query: TaskListQuery = {}) {
  const { data, loading, error, execute } = useAsyncResource(tasksService.list, initialTasksResponse);

  const refresh = useCallback(async () => {
    await execute(query);
  }, [execute, query]);

  const createTask = useCallback(
    async (payload: TaskPayload) => {
      await tasksService.create(payload);
      await refresh();
    },
    [refresh]
  );

  const updateTask = useCallback(
    async (taskId: string, payload: Partial<TaskPayload>) => {
      await tasksService.update(taskId, payload);
      await refresh();
    },
    [refresh]
  );

  const deleteTask = useCallback(
    async (taskId: string) => {
      await tasksService.remove(taskId);
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return {
    tasks: data.items,
    pagination: data.pagination,
    loading,
    error,
    refresh,
    createTask,
    updateTask,
    deleteTask
  };
}
