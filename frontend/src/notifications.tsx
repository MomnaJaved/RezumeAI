import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { clearActivityNotifications, fetchActivityNotifications, fetchInbox, type ActivityNotification } from "./api";
import { getNotifSettings, type NotifSettings } from "./settings";
import { useToast } from "./toast";
import { useAuth } from "./auth";
import { installNotificationAudioUnlock, playMessageChime, playNotificationChime } from "./notificationSound";
import { parseDmIncomingLine } from "./inboxTime";

/** Outgoing DM line echoed in UI; never show as a system notification toast. */
function looksLikeOutgoingDmLine(message: string): boolean {
  return /^message\s+to\s+/i.test((message || "").trim());
}

// ── Settings-based filter ─────────────────────────────────────────────────────

function shouldShow(kind: string, message: string, s: NotifSettings): boolean {
  const k = (kind ?? "").toLowerCase();
  const m = (message ?? "").toLowerCase();

  if (k === "upload" || k === "candidate_added" || (k === "success" && m.includes("added to the pool")))
    return s.newCandidateApplied === "ON";

  if (k === "shortlist" || k === "select" ||
    (k === "feedback" && (m.includes("shortlist") || m.includes("selected"))))
    return s.candidateShortlisted === "ON";

  if (k === "reject" || k === "not_a_fit" ||
    (k === "feedback" && (m.includes("not a fit") || m.includes("rejected"))))
    return s.candidateRejected === "ON";

  if (k === "hired" || (k === "feedback" && m.includes("hired")))
    return s.candidateHired === "ON";

  if (k === "ranking" || k === "top_matches")
    return s.topMatchesFound === "ON";

  if (k === "low_match")
    return s.lowMatchWarning === "ON";

  return true;
}

// ── Context ───────────────────────────────────────────────────────────────────

const POLL_MS = 4000;

type NotifCtx = {
  items: ActivityNotification[];
  pollErr: string | null;
  /** Unread incoming DMs (Rezume inbox), scoped for Candidates tab badge. */
  inboxUnreadCandidates: number;
  inboxUnreadDmTotal: number;
  clearAll: () => Promise<void>;
};

const NotificationContext = createContext<NotifCtx>({
  items: [],
  pollErr: null,
  inboxUnreadCandidates: 0,
  inboxUnreadDmTotal: 0,
  clearAll: async () => {},
});

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const toast = useToast();
  const { token } = useAuth();
  const [items, setItems] = useState<ActivityNotification[]>([]);
  const [pollErr, setPollErr] = useState<string | null>(null);
  const [inboxUnreadCandidates, setInboxUnreadCandidates] = useState(0);
  const [inboxUnreadDmTotal, setInboxUnreadDmTotal] = useState(0);
  const clearAll = useCallback(async () => {
    await clearActivityNotifications();
    setItems([]);
    seenIds.current.clear();
    bootstrapped.current = false;
  }, []);

  const seenIds = useRef<Set<string>>(new Set());
  const bootstrapped = useRef(false);
  const seenInboxMsgIds = useRef<Set<string>>(new Set());
  const inboxBootstrapped = useRef(false);

  const tick = useCallback(() => {
    if (!token) return; // not authenticated — skip polling
    Promise.allSettled([fetchActivityNotifications(), fetchInbox()])
      .then((results) => {
        const act = results[0];
        const inboxRes = results[1];

        if (inboxRes.status === "fulfilled") {
          const inboxList = inboxRes.value;
          let uc = 0;
          let dmTotal = 0;
          for (const it of inboxList) {
            if (!it.direct || it.direction !== "in" || it.read) continue;
            dmTotal += 1;
            if (it.chat_scope === "candidates") uc += 1;
          }
          setInboxUnreadCandidates(uc);
          setInboxUnreadDmTotal(dmTotal);

          if (!inboxBootstrapped.current) {
            for (const it of inboxList) {
              if (it.id.startsWith("msg-")) seenInboxMsgIds.current.add(it.id);
            }
            inboxBootstrapped.current = true;
          } else {
            const newMsgs = inboxList.filter((it) => it.id.startsWith("msg-") && !seenInboxMsgIds.current.has(it.id));
            for (const it of inboxList) {
              if (it.id.startsWith("msg-")) seenInboxMsgIds.current.add(it.id);
            }
            const incomingNew = newMsgs.filter(
              (it) =>
                it.direct &&
                it.direction === "in" &&
                !looksLikeOutgoingDmLine(it.message || ""),
            );
            if (incomingNew.length > 0) {
              void playMessageChime();
              const n = incomingNew.length;
              const first = incomingNew[0];
              const { from } = parseDmIncomingLine((first.message ?? "").trim());
              const sender =
                ((first.peer_display_name || "") as string).trim() ||
                (from && from !== "Someone" ? from : "") ||
                (first.sender_email || "").trim() ||
                "someone";
              const line =
                n === 1 ? `New message from ${sender}` : `New message from ${sender} (+${n - 1} more)`;
              toast.info(line);
            }
          }
        }

        if (act.status !== "fulfilled") {
          const msg = act.reason instanceof Error ? act.reason.message : String(act.reason);
          if (!msg?.toLowerCase().includes("unauthorized")) setPollErr(msg || "Activity poll failed");
          return;
        }

        const list = act.value;
        setItems(list);
        setPollErr(null);

        if (!bootstrapped.current) {
          for (const x of list) seenIds.current.add(x.id);
          bootstrapped.current = true;
          return;
        }

        const newly = list.filter((x) => !seenIds.current.has(x.id) && !looksLikeOutgoingDmLine(x.message));
        for (const x of list) seenIds.current.add(x.id);
        if (newly.length === 0) return;

        const s = getNotifSettings();
        const toShow = newly.filter((n) => shouldShow(n.kind, n.message, s) && !looksLikeOutgoingDmLine(n.message));
        if (toShow.length === 0) return;

        void playNotificationChime();
        for (const n of toShow.slice(0, 3)) {
          const msg = (n.message ?? "").trim();
          if (msg) toast.info(msg, { title: "Rezume AI" });
        }
      })
      .catch((e: Error) => {
        if (!e.message?.toLowerCase().includes("unauthorized")) {
          setPollErr(e.message);
        }
      });
  }, [token, toast]);

  useEffect(() => {
    const removeUnlock = installNotificationAudioUnlock();
    return removeUnlock;
  }, []);

  useEffect(() => {
    tick();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") tick();
    }, POLL_MS);
    const onVis = () => { if (document.visibilityState === "visible") tick(); };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [tick]);

  // Re-bootstrap when user logs in/out
  useEffect(() => {
    bootstrapped.current = false;
    seenIds.current.clear();
    inboxBootstrapped.current = false;
    seenInboxMsgIds.current.clear();
    setItems([]);
    setPollErr(null);
    setInboxUnreadCandidates(0);
    setInboxUnreadDmTotal(0);
  }, [token]);

  return (
    <NotificationContext.Provider
      value={{ items, pollErr, inboxUnreadCandidates, inboxUnreadDmTotal, clearAll }}
    >
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications(): NotifCtx {
  return useContext(NotificationContext);
}
