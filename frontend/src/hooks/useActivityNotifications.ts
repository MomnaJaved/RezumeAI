import { useEffect, useRef, useState } from "react";
import { fetchActivityNotifications, type ActivityNotification } from "../api";
import { useToast } from "../toast";

const POLL_MS = 4000;

/**
 * Keeps activity notifications fresh while the tab is visible (dashboard + inbox).
 */
export function useActivityNotifications(
  initial: ActivityNotification[] | undefined,
  opts?: { toastOnNew?: boolean },
) {
  const toast = useToast();
  const [items, setItems] = useState<ActivityNotification[]>(initial ?? []);
  const [pollErr, setPollErr] = useState<string | null>(null);
  const seenIds = useRef<Set<string>>(new Set());
  const bootstrapped = useRef(false);

  useEffect(() => {
    if (initial !== undefined) setItems(initial);
  }, [initial]);

  /** Seed from dashboard payload so the first poll does not toast the whole history. */
  useEffect(() => {
    if (!initial?.length) return;
    for (const x of initial) seenIds.current.add(x.id);
    bootstrapped.current = true;
  }, [initial]);

  useEffect(() => {
    let cancelled = false;

    function tick() {
      fetchActivityNotifications()
        .then((list) => {
          if (!cancelled) {
            setItems(list);
            setPollErr(null);
            if (opts?.toastOnNew) {
              if (!bootstrapped.current) {
                for (const x of list) seenIds.current.add(x.id);
                bootstrapped.current = true;
                return;
              }
              const newly = list.filter((x) => !seenIds.current.has(x.id));
              for (const x of list) seenIds.current.add(x.id);
              for (const n of newly.slice(0, 3)) {
                const msg = (n.message || "").trim();
                if (msg) toast.info(msg);
              }
            } else {
              for (const x of list) seenIds.current.add(x.id);
            }
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
  }, [opts?.toastOnNew, toast]);

  return { items, pollErr };
}
