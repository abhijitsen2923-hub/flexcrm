import { useCallback, useState } from "react";


export function useAsyncResource<T, TArgs extends unknown[]>(
  executor: (...args: TArgs) => Promise<T>,
  initialData: T
) {
  const [data, setData] = useState<T>(initialData);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const execute = useCallback(
    async (...args: TArgs) => {
      setLoading(true);
      setError(null);

      try {
        const result = await executor(...args);
        setData(result);
        return result;
      } catch (requestError) {
        setError(requestError);
        throw requestError;
      } finally {
        setLoading(false);
      }
    },
    [executor]
  );

  return {
    data,
    setData,
    loading,
    error,
    execute
  };
}
