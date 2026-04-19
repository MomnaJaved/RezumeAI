import { Link, NavLink, useLocation } from "react-router-dom";
import React, { useEffect, useRef, useState } from "react";
import DashGlobalSearch from "./DashGlobalSearch";
import { useAuth } from "./auth";
import { useT } from "./i18n";
import { useNotifications } from "./notifications";

function Icon({
  name,
}: {
  name: "dashboard" | "candidates" | "addCandidate" | "clients" | "jobs" | "reports" | "settings" | "inbox" | "matching";
}) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  switch (name) {
    case "dashboard":
      return (
        <svg {...common}>
          <path d="M3 3h8v8H3z" />
          <path d="M13 3h8v5h-8z" />
          <path d="M13 10h8v11h-8z" />
          <path d="M3 13h8v8H3z" />
        </svg>
      );
    case "candidates":
      return (
        <svg {...common}>
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a3 3 0 0 0-2-2.83" />
          <path d="M18 3a4 4 0 0 1 0 8" />
        </svg>
      );
    case "addCandidate":
      return (
        <svg {...common}>
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M19 8v6M22 11h-6" strokeLinecap="round" />
        </svg>
      );
    case "clients":
      return (
        <svg {...common}>
          <path d="M3 21V7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14" />
          <path d="M7 21v-4a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v4" />
          <path d="M8 9h8" />
          <path d="M8 12h8" />
        </svg>
      );
    case "jobs":
      return (
        <svg {...common}>
          <path d="M16 6V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
          <path d="M3 7h18v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
          <path d="M3 12h18" />
        </svg>
      );
    case "reports":
      return (
        <svg {...common}>
          <path d="M3 3v18h18" />
          <path d="M7 14l3-3 4 4 6-6" />
        </svg>
      );
    case "settings":
      /* Feather “settings” / gear: center hub + outer cog (24×24 viewBox, scales to 18px). */
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      );
    case "inbox":
      return (
        <svg {...common}>
          <path d="M4 4h16v12H4z" />
          <path d="M22 16l-4 4H6l-4-4" />
          <path d="M8 12l4 3 4-3" />
        </svg>
      );
    case "matching":
      return (
        <svg {...common}>
          <path d="M10 13a5 5 0 0 1 0-7l1-1a5 5 0 0 1 7 7l-1 1" />
          <path d="M14 11a5 5 0 0 1 0 7l-1 1a5 5 0 0 1-7-7l1-1" />
        </svg>
      );
    default:
      return null;
  }
}

function DashOverflowMenu() {
  const { email, logout } = useAuth();
  const t = useT();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div className="dash-menu-wrap" ref={wrapRef}>
      <button
        type="button"
        className="dash-menu-trigger"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Open menu"
        onClick={() => setOpen((o) => !o)}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <circle cx="12" cy="6" r="1.85" />
          <circle cx="12" cy="12" r="1.85" />
          <circle cx="12" cy="18" r="1.85" />
        </svg>
      </button>
      {open ? (
        <div className="dash-menu-dropdown" role="menu">
          {email ? (
            <div className="dash-menu-email" role="presentation">
              {email}
            </div>
          ) : null}
          <Link to="/settings" className="dash-menu-link" role="menuitem" onClick={() => setOpen(false)}>
            {t("nav.settings")}
          </Link>
          <button
            type="button"
            className="dash-menu-logout"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              logout();
            }}
          >
            {t("nav.logout")}
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function DashFrame({ topExtra, children }: { topExtra?: React.ReactNode; children: React.ReactNode }) {
  const loc = useLocation();
  const t = useT();
  const { inboxUnreadDmTotal } = useNotifications();
  const hideGlobalSearch = loc.pathname === "/candidates" || loc.pathname.startsWith("/candidates/");

  return (
    <div className="dash">
      <aside className="dash-sidebar">
        <nav className="dash-nav">
          <NavLink to="/dashboard" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            <Icon name="dashboard" /> {t("nav.dashboard")}
          </NavLink>
          <NavLink end to="/candidates" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            <Icon name="candidates" /> {t("nav.candidates")}
          </NavLink>
          <NavLink to="/clients" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            <Icon name="clients" /> {t("nav.clients")}
          </NavLink>
          <NavLink to="/jobs" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            <Icon name="jobs" /> {t("nav.jobs")}
          </NavLink>
          <NavLink to="/reports" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            <Icon name="reports" /> {t("nav.reports")}
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            <Icon name="settings" /> {t("nav.settings")}
          </NavLink>
          <NavLink to="/inbox" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            <Icon name="inbox" /> {t("nav.inbox")}
            {inboxUnreadDmTotal > 0 ? (
              <span className="dash-nav-badge" aria-label={`${inboxUnreadDmTotal} unread messages`}>
                {inboxUnreadDmTotal > 99 ? "99+" : inboxUnreadDmTotal}
              </span>
            ) : null}
          </NavLink>
          <NavLink to="/matching" className={({ isActive }) => (isActive ? "dash-link active" : "dash-link")}>
            <Icon name="matching" /> {t("nav.matching")}
          </NavLink>
        </nav>
      </aside>

      <div className={topExtra ? "dash-main dash-main--toolbar" : "dash-main"}>
        <header className="dash-topbar">
          <Link to="/dashboard" className="dash-topbar-brand">
            <span className="landing-logo" aria-hidden="true" />
            <span>Rezume AI</span>
          </Link>
          {hideGlobalSearch ? (
            <div className="dash-topbar-search" aria-hidden="true" />
          ) : (
            <div className="dash-topbar-search">
              <DashGlobalSearch />
            </div>
          )}
          <div className="dash-topbar-actions">
            <DashOverflowMenu />
          </div>
        </header>
        {topExtra ? <div className="dash-toolbar">{topExtra}</div> : null}
        <div className="dash-content">{children}</div>
      </div>
    </div>
  );
}
