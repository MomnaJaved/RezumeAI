import { Link } from "react-router-dom";
import type { ActivityNotification } from "../api";

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export default function ActivityNotificationList({
  items,
  emptyLabel = "No recent activity yet.",
}: {
  items: ActivityNotification[];
  emptyLabel?: string;
}) {
  if (items.length === 0) {
    return <p className="muted">{emptyLabel}</p>;
  }

  return (
    <ul className="dash-notes dash-activity-list">
      {items.map((n) => {
        const meta = formatTime(n.at);
        const inner = (
          <>
            <span className="dash-activity-msg">{n.message}</span>
            {meta ? <time className="dash-activity-time" dateTime={n.at}>{meta}</time> : null}
          </>
        );
        return (
          <li key={n.id}>
            {n.href ? (
              <Link to={n.href} className="dash-activity-link">
                {inner}
              </Link>
            ) : (
              <span className="dash-activity-row">{inner}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}
