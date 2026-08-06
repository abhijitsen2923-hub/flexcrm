import {
  createContext,
  useContext,
  useEffect,
  useState,
  type PropsWithChildren,
} from "react";

import { organizationsService } from "../services/organizations";
import type { ModuleKey, Organization } from "../types";
import { useAuth } from "../hooks/useAuth";


const ALL_OFF: Record<ModuleKey, boolean> = {
  deals: false,
  tasks: false,
  activities: false,
  finance: false,
  hr: false,
  inventory: false,
  bookings: false,
  site_visits: false,
  projects: false,
  meta_leads: false,
};

interface OrgContextValue {
  org: Organization | null;
  modules: Record<ModuleKey, boolean>;
  refresh: () => Promise<void>;
}

const OrgContext = createContext<OrgContextValue>({
  org: null,
  modules: ALL_OFF,
  refresh: async () => {},
});


export function OrgProvider({ children }: PropsWithChildren) {
  const { user } = useAuth();
  const [org, setOrg] = useState<Organization | null>(null);

  const fetchOrg = async () => {
    try {
      const data = await organizationsService.me();
      setOrg(data);
    } catch {
      setOrg(null);
    }
  };

  useEffect(() => {
    if (user) {
      void fetchOrg();
    } else {
      setOrg(null);
    }
  }, [user?.id]);

  const modules: Record<ModuleKey, boolean> = org?.modules ?? ALL_OFF;

  return (
    <OrgContext.Provider value={{ org, modules, refresh: fetchOrg }}>
      {children}
    </OrgContext.Provider>
  );
}


export function useOrgModules(): Record<ModuleKey, boolean> {
  return useContext(OrgContext).modules;
}


export function useOrg(): OrgContextValue {
  return useContext(OrgContext);
}
