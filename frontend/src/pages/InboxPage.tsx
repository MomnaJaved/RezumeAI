import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import DashFrame from "../DashFrame";
import {
  fetchCandidatesPage,
  fetchInbox,
  inboxDeleteMessage,
  inboxDeleteThread,
  inboxMarkAllRead,
  inboxMarkAllUnread,
  inboxMarkRead,
  inboxMarkUnread,
  inboxSendMessage,
  type InboxItem,
  type InboxTab,
} from "../api";
import { formatDmPreview, formatInboxRelative, inboxAllTabLine, parseInboxDate } from "../inboxTime";
import { useNotifications } from "../notifications";

const TABS: { key: InboxTab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "alerts", label: "Alerts" },
  { key: "candidates", label: "Candidates" },
];

function IconSearch(props: { className?: string }) {
  return (
    <svg className={props.className} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="M21 21l-4.3-4.3" strokeLinecap="round" />
    </svg>
  );
}

function IconBack() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M15 18l-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function itemMatchesTab(item: InboxItem, tab: InboxTab): boolean {
  if (tab === "all") return true;
  if (tab === "alerts") return !item.direct;
  if (tab === "candidates") return Boolean(item.direct) && item.chat_scope === "candidates";
  return false;
}

function normEmail(s: string): string {
  return (s || "").trim().toLowerCase();
}

type ThreadSummary = {
  peerEmail: string;
  displayName: string;
  peerProfilePath: string | null;
  latestAt: string;
  preview: string;
  unread: number;
};

function buildThreadSummaries(items: InboxItem[]): ThreadSummary[] {
  const byPeer = new Map<string, InboxItem[]>();
  for (const it of items) {
    if (!it.direct) continue;
    const p = normEmail(it.peer_email || "");
    if (!p) continue;
    if (!byPeer.has(p)) byPeer.set(p, []);
    byPeer.get(p)!.push(it);
  }
  const out: ThreadSummary[] = [];
  for (const [peerEmail, msgs] of byPeer) {
    const sorted = [...msgs].sort((a, b) => parseInboxDate(b.at).getTime() - parseInboxDate(a.at).getTime());
    const latest = sorted[0];
    const unread = sorted.filter((m) => m.direction === "in" && !m.read).length;
    const display = ((latest.peer_display_name || latest.peer_email || peerEmail) as string).trim() || peerEmail;
    const pathRaw = (latest.peer_profile_path || "").trim();
    out.push({
      peerEmail,
      displayName: display,
      peerProfilePath: pathRaw || null,
      latestAt: latest.at,
      preview: formatDmPreview(latest.message || ""),
      unread,
    });
  }
  out.sort((a, b) => parseInboxDate(b.latestAt).getTime() - parseInboxDate(a.latestAt).getTime());
  return out;
}

type DirectoryHit = { id: string; name: string; email: string; subtitle: string };

type ActiveThread = {
  peerEmail: string;
  displayName: string;
  scope: "candidates";
  profilePath: string | null;
};

function MarkRowButtons({ busy, read, onRead, onUnread }: { busy: boolean; read: boolean; onRead: () => void; onUnread: () => void }) {
  return (
    <div className="dash-inbox-row-actions dash-inbox-row-actions-split">
      <button type="button" className="dash-btn dash-btn-inbox-mark" disabled={busy || read} onClick={onRead}>
        Mark read
      </button>
      <button type="button" className="dash-btn dash-btn-inbox-mark" disabled={busy || !read} onClick={onUnread}>
        Mark unread
      </button>
    </div>
  );
}

export default function InboxPage() {
  const { inboxUnreadCandidates } = useNotifications();
  const [tab, setTab] = useState<InboxTab>("all");
  const [items, setItems] = useState<InboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [threadInput, setThreadInput] = useState("");
  const [threadNotice, setThreadNotice] = useState<string | null>(null);
  const threadScrollRef = useRef<HTMLDivElement | null>(null);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const dirWrapRef = useRef<HTMLDivElement | null>(null);

  const [dirOpen, setDirOpen] = useState(false);
  const [dirQuery, setDirQuery] = useState("");
  const [dirLoading, setDirLoading] = useState(false);
  const [dirHits, setDirHits] = useState<DirectoryHit[]>([]);
  const [activeThread, setActiveThread] = useState<ActiveThread | null>(null);
  const [listNotice, setListNotice] = useState<string | null>(null);
  const [msgDeleteMenu, setMsgDeleteMenu] = useState<{ id: string; outgoing: boolean } | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const rows = await fetchInbox();
      setItems(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load inbox");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 5000);
    return () => window.clearInterval(id);
  }, [load]);

  useEffect(() => {
    setDirOpen(false);
    setDirQuery("");
    setDirHits([]);
    setActiveThread(null);
    setThreadInput("");
    setThreadNotice(null);
    setListNotice(null);
  }, [tab]);

  /** Fill profile link from API once messages load (e.g. after first reply). */
  useEffect(() => {
    if (!activeThread) return;
    const pe = normEmail(activeThread.peerEmail);
    const withPath = items.find(
      (it) =>
        it.direct &&
        normEmail(it.peer_email || "") === pe &&
        it.chat_scope === activeThread.scope &&
        (it.peer_profile_path || "").trim(),
    );
    const p = (withPath?.peer_profile_path || "").trim();
    if (!p || (activeThread.profilePath || "") === p) return;
    setActiveThread((prev) => (prev ? { ...prev, profilePath: p } : null));
  }, [items, activeThread?.peerEmail, activeThread?.scope, activeThread?.profilePath]);

  useEffect(() => {
    if (!dirOpen || tab !== "candidates") return;
    const q = dirQuery.trim();
    if (q.length < 1) {
      setDirHits([]);
      setDirLoading(false);
      return;
    }
    let cancelled = false;
    const t = window.setTimeout(async () => {
      setDirLoading(true);
      try {
        const { items: rows } = await fetchCandidatesPage({ skip: 0, limit: 30, q });
        if (cancelled) return;
        const hits: DirectoryHit[] = rows.map((c) => ({
          id: c.id,
          name: (c.full_name || "").trim() || "Candidate",
          email: (c.contact_email || "").trim(),
          subtitle: [c.title, c.external_id].filter(Boolean).join(" · ") || "—",
        }));
        setDirHits(hits);
      } catch {
        if (!cancelled) setDirHits([]);
      } finally {
        if (!cancelled) setDirLoading(false);
      }
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [dirQuery, dirOpen, tab]);

  useEffect(() => {
    if (!dirOpen) return;
    const onDoc = (ev: MouseEvent) => {
      const el = dirWrapRef.current;
      if (el && !el.contains(ev.target as Node)) setDirOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [dirOpen]);

  useEffect(() => {
    if (!msgDeleteMenu) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setMsgDeleteMenu(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [msgDeleteMenu]);

  const filtered = useMemo(() => items.filter((it) => itemMatchesTab(it, tab)), [items, tab]);

  const threadSummaries = useMemo(() => {
    if (tab !== "candidates") return [];
    return buildThreadSummaries(filtered);
  }, [tab, filtered]);

  const threadMessages = useMemo(() => {
    if (!activeThread) return [];
    const pe = normEmail(activeThread.peerEmail);
    const msgs = filtered.filter(
      (it) => it.direct && normEmail(it.peer_email || "") === pe && it.chat_scope === activeThread.scope,
    );
    return msgs.sort((a, b) => parseInboxDate(a.at).getTime() - parseInboxDate(b.at).getTime());
  }, [filtered, activeThread]);

  /** Mark incoming messages in this thread as read when opening (like Instagram). */
  useEffect(() => {
    if (!activeThread) return;
    const pe = normEmail(activeThread.peerEmail);
    const scope = activeThread.scope;
    const unreadIds = items
      .filter(
        (it) =>
          it.direct &&
          normEmail(it.peer_email || "") === pe &&
          it.chat_scope === scope &&
          it.direction === "in" &&
          !it.read,
      )
      .map((m) => m.id);
    if (unreadIds.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        await inboxMarkRead(unreadIds);
        if (!cancelled) {
          setItems((prev) => prev.map((x) => (unreadIds.includes(x.id) ? { ...x, read: true } : x)));
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeThread?.peerEmail, activeThread?.scope, items]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeThread?.peerEmail, threadMessages.length, tab]);

  const refreshOne = (id: string, read: boolean) => {
    setItems((prev) => prev.map((x) => (x.id === id ? { ...x, read } : x)));
  };

  const markRead = async (id: string) => {
    setBusy(true);
    try {
      await inboxMarkRead([id]);
      refreshOne(id, true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mark read failed");
    } finally {
      setBusy(false);
    }
  };

  const markUnread = async (id: string) => {
    setBusy(true);
    try {
      await inboxMarkUnread([id]);
      refreshOne(id, false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mark unread failed");
    } finally {
      setBusy(false);
    }
  };

  const markAllRead = async () => {
    setBusy(true);
    try {
      await inboxMarkAllRead(tab);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mark all read failed");
    } finally {
      setBusy(false);
    }
  };

  const markAllUnread = async () => {
    setBusy(true);
    try {
      await inboxMarkAllUnread(tab);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mark all unread failed");
    } finally {
      setBusy(false);
    }
  };

  const openThread = (peerEmail: string, displayName: string, profilePath: string | null = null) => {
    setListNotice(null);
    setThreadNotice(null);
    setThreadInput("");
    setActiveThread({ peerEmail: peerEmail.trim(), displayName, scope: "candidates", profilePath });
    setDirOpen(false);
    setDirQuery("");
    setDirHits([]);
  };

  const openChatWith = (hit: DirectoryHit) => {
    if (!hit.email) {
      setListNotice("No email on file for this record. Add an email on the profile, then search again.");
      setDirOpen(false);
      return;
    }
    openThread(hit.email, hit.name, `/candidates/${hit.id}`);
  };

  const sendThreadMessage = async () => {
    if (!activeThread) return;
    const bd = threadInput.trim();
    if (!bd) {
      setThreadNotice("Write a message to send.");
      return;
    }
    setBusy(true);
    setThreadNotice(null);
    try {
      await inboxSendMessage({
        to_email: activeThread.peerEmail,
        body: bd,
        chat_scope: activeThread.scope,
      });
      setThreadInput("");
      await load();
    } catch (e) {
      setThreadNotice(e instanceof Error ? e.message : "Send failed");
    } finally {
      setBusy(false);
    }
  };

  const deleteThreadChat = async () => {
    if (!activeThread) return;
    if (!window.confirm("Delete this entire chat? This cannot be undone.")) return;
    setBusy(true);
    setThreadNotice(null);
    try {
      await inboxDeleteThread({ peer_email: activeThread.peerEmail, chat_scope: activeThread.scope });
      setActiveThread(null);
      setThreadInput("");
      await load();
    } catch (e) {
      setThreadNotice(e instanceof Error ? e.message : "Could not delete chat");
    } finally {
      setBusy(false);
    }
  };

  const runMessageDelete = async (mode: "everyone" | "me") => {
    if (!msgDeleteMenu) return;
    const id = msgDeleteMenu.id;
    setBusy(true);
    setThreadNotice(null);
    try {
      await inboxDeleteMessage(id, mode);
      setMsgDeleteMenu(null);
      await load();
    } catch (e) {
      setThreadNotice(e instanceof Error ? e.message : "Could not delete message");
    } finally {
      setBusy(false);
    }
  };

  const showDirectorySearch = tab === "candidates";
  const isChatTab = showDirectorySearch;

  return (
    <DashFrame>
      <h1 className="dash-title dash-inbox-page-title">All system notifications and alerts</h1>

      <div className="dash-inbox-shell">
        <nav className="dash-inbox-side" aria-label="Inbox categories">
          {TABS.map((t) => {
            const n = t.key === "candidates" ? inboxUnreadCandidates : 0;
            return (
              <button
                key={t.key}
                type="button"
                className={`dash-inbox-tab ${tab === t.key ? "dash-inbox-tab-active" : ""}`}
                onClick={() => setTab(t.key)}
              >
                <span className="dash-inbox-tab-label">{t.label}</span>
                {n > 0 ? (
                  <span className="dash-inbox-tab-badge" aria-label={`${n} unread`}>
                    {n > 99 ? "99+" : n}
                  </span>
                ) : null}
              </button>
            );
          })}
        </nav>

        <div className="dash-inbox-main">
          {error ? (
            <p className="dash-inbox-banner dash-inbox-banner-error" role="alert">
              {error}
            </p>
          ) : null}
          {listNotice && tab === "candidates" && !activeThread ? (
            <p className="dash-inbox-banner dash-inbox-banner-error" role="status">
              {listNotice}
            </p>
          ) : null}

          <div
            className={`dash-inbox-toolbar ${showDirectorySearch ? "dash-inbox-toolbar-with-search" : "dash-inbox-toolbar-end"} ${activeThread && isChatTab ? "dash-inbox-toolbar-thread" : ""}`}
          >
            {!activeThread || !isChatTab ? (
              <div className="dash-inbox-toolbar-actions">
                <button type="button" className="dash-btn dash-btn-xs dash-btn-ghost" disabled={busy} onClick={markAllRead}>
                  Mark all read
                </button>
                <button type="button" className="dash-btn dash-btn-xs dash-btn-ghost" disabled={busy} onClick={markAllUnread}>
                  Mark all unread
                </button>
              </div>
            ) : (
              <div className="dash-inbox-toolbar-thread-row">
                <button
                  type="button"
                  className="dash-btn dash-btn-xs dash-btn-ghost dash-inbox-back-btn"
                  disabled={busy}
                  onClick={() => {
                    setActiveThread(null);
                    setThreadInput("");
                    setThreadNotice(null);
                  }}
                >
                  <IconBack />
                  <span>Chats</span>
                </button>
                <button
                  type="button"
                  className="dash-btn dash-btn-xs dash-inbox-del-chat"
                  disabled={busy}
                  title="Delete entire conversation"
                  onClick={() => void deleteThreadChat()}
                >
                  Delete chat
                </button>
              </div>
            )}
            {showDirectorySearch && !activeThread ? (
              <div className="dash-inbox-dir-search" ref={dirWrapRef}>
                <button
                  type="button"
                  className={`dash-icon-btn ${dirOpen ? "dash-icon-btn-active" : ""}`}
                  title="Search candidates by name or email"
                  aria-expanded={dirOpen}
                  aria-label="Search directory"
                  onClick={() => setDirOpen((o) => !o)}
                >
                  <IconSearch />
                </button>
                {dirOpen ? (
                  <div className="dash-inbox-dir-popover" role="dialog" aria-label="Directory search">
                    <input
                      className="dash-inbox-dir-input"
                      type="search"
                      autoFocus
                      value={dirQuery}
                      onChange={(e) => setDirQuery(e.target.value)}
                      placeholder="Name or email…"
                    />
                    {dirLoading ? <p className="dash-inbox-dir-empty">Searching…</p> : null}
                    {!dirLoading && dirQuery.trim().length > 0 && dirHits.length === 0 ? (
                      <p className="dash-inbox-dir-empty">No matches.</p>
                    ) : null}
                    {dirHits.length > 0 ? (
                      <ul className="dash-inbox-dir-results">
                        {dirHits.map((h) => (
                          <li key={h.id}>
                            <button
                              type="button"
                              className="dash-inbox-dir-hit"
                              disabled={!h.email}
                              onClick={() => openChatWith(h)}
                              title={h.email ? "Open chat" : "No email on file"}
                            >
                              <span className="dash-inbox-dir-hit-name">{h.name}</span>
                              <span className="dash-inbox-dir-hit-sub">{h.subtitle}</span>
                              <span className="dash-inbox-dir-hit-email">{h.email || "No email"}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          {isChatTab && activeThread ? (
            <div className="dash-inbox-thread-view">
              <header className="dash-inbox-thread-top">
                <div className="dash-inbox-thread-peer">
                  {activeThread.profilePath ? (
                    <Link to={activeThread.profilePath} className="dash-inbox-thread-peer-link">
                      <h2 className="dash-inbox-thread-title">{activeThread.displayName}</h2>
                      <p className="dash-inbox-thread-email">{activeThread.peerEmail}</p>
                    </Link>
                  ) : (
                    <>
                      <h2 className="dash-inbox-thread-title">{activeThread.displayName}</h2>
                      <p className="dash-inbox-thread-email">{activeThread.peerEmail}</p>
                    </>
                  )}
                </div>
              </header>
              {threadNotice ? (
                <p
                  className={
                    threadNotice.startsWith("Message sent") ? "dash-inbox-banner dash-inbox-banner-ok" : "dash-inbox-banner dash-inbox-banner-error"
                  }
                  role="status"
                >
                  {threadNotice}
                </p>
              ) : null}
              <div ref={threadScrollRef} className="dash-inbox-thread-scroll">
                {threadMessages.length === 0 ? (
                  <p className="dash-inbox-thread-empty">No messages yet. Say hello below — they need a Rezume account on this email to receive it.</p>
                ) : (
                  threadMessages.map((m) => {
                    const out = m.direction === "out";
                    return (
                      <div key={m.id} className={`dash-inbox-bubble-row ${out ? "dash-inbox-bubble-row-out" : "dash-inbox-bubble-row-in"}`}>
                        <div className="dash-inbox-bubble-wrap">
                          <div className={`dash-inbox-bubble ${out ? "dash-inbox-bubble-out" : "dash-inbox-bubble-in"}`}>
                            <p className="dash-inbox-bubble-text">{formatDmPreview(m.message || "")}</p>
                            <time className="dash-inbox-bubble-time" dateTime={m.at}>
                              {formatInboxRelative(m.at)}
                            </time>
                          </div>
                          <button
                            type="button"
                            className="dash-inbox-msg-del"
                            disabled={busy}
                            title="Remove message"
                            aria-label="Remove message"
                            onClick={() => setMsgDeleteMenu({ id: m.id, outgoing: out })}
                          >
                            ×
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={threadEndRef} />
              </div>
              <div className="dash-inbox-thread-compose">
                <textarea
                  className="dash-inbox-thread-textarea"
                  rows={2}
                  value={threadInput}
                  onChange={(e) => setThreadInput(e.target.value)}
                  placeholder="Message…"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void sendThreadMessage();
                    }
                  }}
                />
                <button type="button" className="dash-btn dash-btn-thread-send" disabled={busy} onClick={() => void sendThreadMessage()}>
                  Send
                </button>
              </div>
            </div>
          ) : isChatTab && !activeThread ? (
            <ul className="dash-inbox-list dash-inbox-thread-list" aria-busy={loading}>
              {loading && items.length === 0 ? (
                <li className="dash-inbox-row dash-inbox-row-muted">Loading…</li>
              ) : null}
              {!loading && threadSummaries.length === 0 ? (
                <li className="dash-inbox-row dash-inbox-row-muted">
                  No chats yet. Tap the search icon to find someone by name or email and start a conversation.
                </li>
              ) : null}
              {threadSummaries.map((s) => (
                <li key={s.peerEmail} className="dash-inbox-thread-summary">
                  <button
                    type="button"
                    className="dash-inbox-thread-summary-btn"
                    onClick={() => openThread(s.peerEmail, s.displayName, s.peerProfilePath)}
                  >
                    <span className="dash-inbox-thread-summary-avatar" aria-hidden>
                      {(s.displayName || s.peerEmail).charAt(0).toUpperCase()}
                    </span>
                    <span className="dash-inbox-thread-summary-main">
                      <span className="dash-inbox-thread-summary-name">{s.displayName}</span>
                      <span className="dash-inbox-thread-summary-preview">{s.preview}</span>
                    </span>
                    <span className="dash-inbox-thread-summary-meta">
                      {s.unread > 0 ? <span className="dash-inbox-thread-unread">{s.unread}</span> : null}
                      <time dateTime={s.latestAt}>{formatInboxRelative(s.latestAt)}</time>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <ul className="dash-inbox-list" aria-busy={loading}>
              {loading && items.length === 0 ? (
                <li className="dash-inbox-row dash-inbox-row-muted">Loading…</li>
              ) : null}
              {!loading && filtered.length === 0 ? (
                <li className="dash-inbox-row dash-inbox-row-muted">Nothing in this tab yet.</li>
              ) : null}
              {filtered.map((n) => {
                const meta = formatInboxRelative(n.at);
                const rowText = tab === "all" && n.direct ? inboxAllTabLine(n) : n.message;
                const main = (
                  <>
                    <span className={`dash-inbox-dot ${n.read ? "dash-inbox-dot-read" : ""}`} aria-hidden />
                    <div className="dash-inbox-row-body">
                      <span className="dash-inbox-msg">{rowText}</span>
                    </div>
                    {meta ? (
                      <time className="dash-inbox-time" dateTime={n.at}>
                        {meta}
                      </time>
                    ) : null}
                  </>
                );
                const showRead = !n.direct || n.direction !== "out";
                return (
                  <li key={n.id} className={`dash-inbox-row ${n.read ? "dash-inbox-row-read" : ""}`}>
                    <div className="dash-inbox-row-inner">
                      {n.href ? (
                        <Link to={n.href} className="dash-inbox-row-link">
                          {main}
                        </Link>
                      ) : (
                        <div className="dash-inbox-row-static">{main}</div>
                      )}
                      {showRead ? (
                        <MarkRowButtons busy={busy} read={n.read} onRead={() => markRead(n.id)} onUnread={() => markUnread(n.id)} />
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {msgDeleteMenu ? (
        <div
          className="dash-inbox-del-choice-backdrop"
          role="presentation"
          onClick={() => !busy && setMsgDeleteMenu(null)}
        >
          <div
            className="dash-inbox-del-choice"
            role="dialog"
            aria-modal="true"
            aria-labelledby="dash-inbox-del-choice-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="dash-inbox-del-choice-title" className="dash-inbox-del-choice-title">
              Remove this message?
            </h3>
            <p className="dash-inbox-del-choice-hint">
              {msgDeleteMenu.outgoing
                ? "Delete for everyone removes it for both you and the recipient. Delete for me only hides it on your side."
                : "Delete for me hides this message in your inbox. The sender can still see it unless they delete it for everyone."}
            </p>
            <div className="dash-inbox-del-choice-actions">
              <button type="button" className="dash-btn dash-inbox-del-choice-me" disabled={busy} onClick={() => void runMessageDelete("me")}>
                Delete for me
              </button>
              {msgDeleteMenu.outgoing ? (
                <button
                  type="button"
                  className="dash-btn dash-inbox-del-choice-everyone"
                  disabled={busy}
                  onClick={() => void runMessageDelete("everyone")}
                >
                  Delete for everyone
                </button>
              ) : null}
              <button type="button" className="dash-btn dash-btn-xs dash-btn-ghost" disabled={busy} onClick={() => setMsgDeleteMenu(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </DashFrame>
  );
}
