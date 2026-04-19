/**
 * Inbox timestamps from the API are often naive UTC (no "Z" suffix). Parse them as UTC
 * so relative times match the server clock instead of being shifted by the local offset.
 */
export function parseInboxDate(iso: string): Date {
  const s = (iso || "").trim();
  if (!s) return new Date(NaN);
  const hasTz = /z$/i.test(s) || /[+-]\d{2}:?\d{2}$/.test(s);
  if (!hasTz && s.includes("T")) return new Date(`${s}Z`);
  return new Date(s);
}

export function formatInboxRelative(iso: string): string {
  try {
    const d = parseInboxDate(iso);
    const t = d.getTime();
    if (Number.isNaN(t)) return "";
    const diffSec = Math.round((t - Date.now()) / 1000);
    const abs = Math.abs(diffSec);
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    if (abs < 45) return rtf.format(0, "second");
    if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
    if (abs < 86400 * 7) return rtf.format(Math.round(diffSec / 86400), "day");
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

export function formatDmPreview(raw: string): string {
  const m = raw || "";
  const sep = " — ";
  const i = m.indexOf(sep);
  if (i >= 0) return m.slice(i + sep.length).trim() || m;
  return m.trim();
}

/** Parse "New message from email — …" for toast copy. */
export function parseDmIncomingLine(message: string): { from: string; preview: string } {
  const sep = " — ";
  const i = message.indexOf(sep);
  const head = i >= 0 ? message.slice(0, i).trim() : message.trim();
  const preview = i >= 0 ? message.slice(i + sep.length).trim() : "";
  const from = head.replace(/^New message from\s+/i, "").trim() || "Someone";
  return { from, preview: preview || message.trim() };
}

/** "Message to x@y.com — …" → peer part before em dash. */
export function parseDmOutgoingHead(message: string): { to: string } {
  const sep = " — ";
  const i = message.indexOf(sep);
  const head = i >= 0 ? message.slice(0, i).trim() : message.trim();
  const to = head.replace(/^Message to\s+/i, "").trim() || "";
  return { to };
}

/**
 * In the **All** tab, show only who the DM is from/to — no " — preview" body
 * (full `item.message` still exists for thread views / other tabs).
 */
export function inboxAllTabLine(item: {
  message: string;
  direct?: boolean;
  direction?: string | null;
  sender_email?: string | null;
  peer_email?: string | null;
  peer_display_name?: string | null;
}): string {
  if (!item.direct) return item.message || "";
  if (item.direction === "out") {
    const label = ((item.peer_display_name || item.peer_email || "") as string).trim();
    if (label) return `Message to ${label}`;
    const { to } = parseDmOutgoingHead(item.message || "");
    return to ? `Message to ${to}` : (item.message || "").split(" — ")[0]?.trim() || item.message || "";
  }
  const fromLabel = ((item.peer_display_name || item.sender_email || "") as string).trim();
  if (fromLabel) return `New message from ${fromLabel}`;
  const { from } = parseDmIncomingLine(item.message || "");
  return from && from !== "Someone" ? `New message from ${from}` : "New message";
}
