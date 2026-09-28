import { useCallback, useEffect, useRef, useState } from "react";

import { useRealtimeRefresh } from "../realtime";
import { campaignsService, type CampaignOption } from "../services/campaigns";
import { leadsService } from "../services/leads";
import { campaignKey, isCampaignListEvent, shouldUseLegacyCampaigns } from "../utils/campaigns";

/**
 * The workspace's campaign list (New Lead form) plus the campaign values on the leads this user can see
 * (Leads filter). `legacy` = the backend has no campaign list yet (older version mid-deploy, or the tenant
 * migration still running): callers fall back to free text so creating a lead never breaks.
 * The list reloads on list-changing realtime events only; the cheap in-use values on every lead event.
 */
export function useCampaignOptions(includeInactive: boolean) {
  const [campaigns, setCampaigns] = useState<CampaignOption[]>([]);
  const [inUse, setInUse] = useState<string[]>([]);
  const [legacy, setLegacy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const reloadList = useCallback(async () => {
    try {
      setCampaigns(await campaignsService.list(includeInactive));
      setLegacy(false);
    } catch (error) {
      // Only a backend WITHOUT campaign lists means legacy; on a 5xx / network blip keep the last list.
      if (shouldUseLegacyCampaigns(error)) setLegacy(true);
    } finally {
      setLoaded(true);
    }
  }, [includeInactive]);

  const reloadInUse = useCallback(async () => {
    try {
      setInUse(await leadsService.campaigns());
    } catch {
      /* non-fatal: the filter keeps its last values */
    }
  }, []);

  const reload = useCallback(async () => {
    await Promise.all([reloadList(), reloadInUse()]);
  }, [reloadList, reloadInUse]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useRealtimeRefresh(isCampaignListEvent, () => void reloadList());
  useRealtimeRefresh((event) => event.event.startsWith("lead."), () => void reloadInUse());

  // A campaign added by an import / sheet / another manager's new lead shows up on leads first: when a
  // visible lead carries a campaign the list doesn't know, fetch the list once for that name.
  const checkedMissing = useRef(new Set<string>());
  useEffect(() => {
    if (!loaded || legacy) return;
    const known = new Set(campaigns.map((c) => campaignKey(c.name)));
    const missing = inUse.map(campaignKey).filter((key) => key && !known.has(key) && !checkedMissing.current.has(key));
    if (missing.length === 0) return;
    missing.forEach((key) => checkedMissing.current.add(key));
    void reloadList();
  }, [campaigns, inUse, legacy, loaded, reloadList]);

  return { campaigns, inUse, legacy, loaded, reload };
}
