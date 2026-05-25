import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren
} from "react";

import { useAuth } from "../hooks/useAuth";
import { groupStagesByIndustry, pipelinesService } from "../services/pipelines";
import type { LeadIndustry, PipelineStage } from "../types";


interface PipelineContextValue {
  stages: PipelineStage[];
  byIndustry: Record<LeadIndustry, PipelineStage[]>;
  loading: boolean;
  error: string | null;
  getStage: (industry: LeadIndustry, code: string) => PipelineStage | undefined;
  refresh: () => Promise<void>;
}


const PipelineContext = createContext<PipelineContextValue | null>(null);


export function PipelineProvider({ children }: PropsWithChildren) {
  const { user } = useAuth();
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setStages(await pipelinesService.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pipeline stages.");
    } finally {
      setLoading(false);
    }
  }, []);

  // The /pipeline-stages endpoint requires auth — fetch only after the user
  // resolves. Without this gate, the initial render (pre-login) fires an
  // unauth'd request that 401s and silently leaves `stages` empty, which is
  // why the in-row stage dropdown rendered with no options.
  useEffect(() => {
    if (user) {
      void refresh();
    }
  }, [user, refresh]);

  const value = useMemo<PipelineContextValue>(() => {
    const byIndustry = groupStagesByIndustry(stages);
    const lookup = new Map<string, PipelineStage>();
    for (const stage of stages) {
      lookup.set(`${stage.industry}:${stage.code}`, stage);
    }
    return {
      stages,
      byIndustry,
      loading,
      error,
      refresh,
      getStage: (industry, code) => lookup.get(`${industry}:${code}`)
    };
  }, [stages, loading, error, refresh]);

  return <PipelineContext.Provider value={value}>{children}</PipelineContext.Provider>;
}


export function usePipelines(): PipelineContextValue {
  const ctx = useContext(PipelineContext);
  if (!ctx) {
    throw new Error("usePipelines must be used within PipelineProvider");
  }
  return ctx;
}
