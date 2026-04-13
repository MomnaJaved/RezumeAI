import { useEffect, useRef } from "react";
import DashFrame from "../DashFrame";
import ActivityNotificationList from "../components/ActivityNotificationList";
import { useActivityNotifications } from "../hooks/useActivityNotifications";
import { useToast } from "../toast";

export default function InboxPage() {
  const toast = useToast();
  const lastPollErr = useRef<string | null>(null);
  const { items, pollErr } = useActivityNotifications(undefined);

  useEffect(() => {
    if (pollErr && pollErr !== lastPollErr.current) {
      lastPollErr.current = pollErr;
      toast.error(pollErr);
    }
    if (!pollErr) lastPollErr.current = null;
  }, [pollErr, toast]);

  return (
    <DashFrame>
      <h1 className="dash-title">Inbox</h1>
      <p className="dash-inbox-lead">
        Live feed of resume uploads, new candidates, ranking runs, and shortlist actions. Updates every few seconds while this tab is open.
      </p>
      <section className="dash-panel dash-inbox-panel">
        <h2>Activity</h2>
        <ActivityNotificationList items={items} emptyLabel="No activity yet. Upload a resume or run a job ranking to see events here." />
      </section>
    </DashFrame>
  );
}
