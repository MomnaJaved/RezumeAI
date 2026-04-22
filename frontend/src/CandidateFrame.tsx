import { Link, NavLink } from "react-router-dom";
import { useAuth } from "./auth";
import { useNotifications } from "./notifications";

export default function CandidateFrame({ children }: { children: React.ReactNode }) {
  const { email, logout } = useAuth();
  const { inboxUnreadDmTotal, inboxUnreadAlerts } = useNotifications();
  const inboxUnread = inboxUnreadDmTotal + inboxUnreadAlerts;

  return (
    <div className="dash">
      <aside className="dash-sidebar dash-sidebar-candidate">
        <nav className="dash-nav" aria-label="Candidate">
          <div className="dash-candidate-brand">
            <Link to="/candidate" className="dash-link dash-candidate-brand-link">
              Rezume <span className="dash-candidate-pill">Candidate</span>
            </Link>
          </div>
          <NavLink to="/candidate" end className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            Home
          </NavLink>
          <NavLink to="/candidate/jobs" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            Jobs
          </NavLink>
          <NavLink to="/candidate/applications" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            Applications
          </NavLink>
          <NavLink to="/candidate/inbox" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            Inbox
            {inboxUnread > 0 ? (
              <span className="dash-nav-badge" aria-label={`${inboxUnread} unread`}>
                {inboxUnread > 99 ? "99+" : inboxUnread}
              </span>
            ) : null}
          </NavLink>
          <NavLink to="/candidate/profile" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            Profile
          </NavLink>
        </nav>
        <div className="dash-nav-footer">
          {email ? <span className="dash-nav-email">{email}</span> : null}
          <button type="button" className="dash-btn dash-btn-xs dash-btn-ghost" onClick={() => logout()}>
            Log out
          </button>
        </div>
      </aside>
      <div className="dash-main">
        <div className="dash-content">{children}</div>
      </div>
    </div>
  );
}
