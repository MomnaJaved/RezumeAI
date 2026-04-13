import { useEffect, useState } from "react";
import { fetchActivityNotifications, type ActivityNotification } from "../api";

const POLL_MS = 4000;

/**
 * Keeps activity notifications fresh while the tab is visible (dashboard + inbox).
 */
export function useActivityNotifications(initial: ActivityNotification[] | undefined) {
  const [items, setItems] = useState<ActivityNotification[]>(initial ?? []);
  const [pollErr, setPollErr] = useState<string | null>(null);

  useEffect(() => {
    if (initial !== undefined) setItems(initial);
  }, [initial]);

  useEffect(() => {
    let cancelled = false;

    function tick() {
      fetchActivityNotifications()
        .then((list) => {
          if (!cancelled) {
            setItems(list);
            setPollErr(null);
          }
        })
        .catch((e: Error) => {
          if (!cancelled) setPollErr(e.message);
        });
    }

    tick();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") tick();
    }, POLL_MS);

    function onVis() {
      if (document.visibilityState === "visible") tick();
    }
    document.addEventListener("visibilitychange", onVis);

    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return { items, pollErr };
}
