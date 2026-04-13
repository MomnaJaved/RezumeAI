import DashFrame from "../DashFrame";
import ActivityNotificationList from "../components/ActivityNotificationList";
import { useActivityNotifications } from "../hooks/useActivityNotifications";

export default function InboxPage() {
  const { items, pollErr } = useActivityNotifications(undefined);

  return (
    <DashFrame>
      <h1 className="dash-title">Inbox</h1>
      <p className="dash-inbox-lead">
        Live feed of resume uploads, new candidates, ranking runs, and shortlist actions. Updates every few seconds while this tab is open.
      </p>
      {pollErr ? <p className="banner banner-error">{pollErr}</p> : null}
      <section className="dash-panel dash-inbox-panel">
        <h2>Activity</h2>
        <ActivityNotificationList items={items} emptyLabel="No activity yet. Upload a resume or run a job ranking to see events here." />
      </section>
    </DashFrame>
  );
}
