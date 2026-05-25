import type { LeadIndustry, PipelineStage } from "../types";
import { apiClient } from "./http";


export const pipelinesService = {
  async list(): Promise<PipelineStage[]> {
    const { data } = await apiClient.get<PipelineStage[]>("/pipeline-stages");
    return data;
  }
};


export function groupStagesByIndustry(stages: PipelineStage[]): Record<LeadIndustry, PipelineStage[]> {
  const result: Record<LeadIndustry, PipelineStage[]> = { education: [], travel: [] };
  for (const stage of stages) {
    result[stage.industry].push(stage);
  }
  for (const industry of Object.keys(result) as LeadIndustry[]) {
    result[industry].sort((a, b) => a.position - b.position);
  }
  return result;
}
