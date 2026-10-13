import { useEffect, useState } from "react";

import { localDay } from "../utils/assignedDay";

/**
 * Today's LOCAL date ("YYYY-MM-DD"), kept current: it flips at local midnight and is re-checked when the tab
 * comes back into view (a sleeping laptop's timers don't fire on time). Lets "Assigned today" mean today in a
 * tab that was left open overnight.
 */
export function useLocalDay(): string {
  const [day, setDay] = useState(() => localDay(new Date()));
  useEffect(() => {
    const check = () => setDay((prev) => {
      const now = localDay(new Date());
      return now === prev ? prev : now;
    });
    let timer: ReturnType<typeof setTimeout>;
    const arm = () => {
      const now = new Date();
      const nextMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 1);
      timer = setTimeout(() => {
        check();
        arm();
      }, nextMidnight.getTime() - now.getTime());
    };
    arm();
    const onVisible = () => {
      if (document.visibilityState === "visible") check();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", check);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", check);
    };
  }, []);
  return day;
}
