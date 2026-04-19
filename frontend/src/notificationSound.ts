/**
 * Shared Web Audio context + soft two-tone chime.
 * Browsers block AudioContext until a user gesture — call `unlockNotificationAudio()` from a pointer/key handler.
 */

let sharedCtx: AudioContext | null = null;

export function getSharedAudioContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  if (!sharedCtx) sharedCtx = new Ctor();
  return sharedCtx;
}

/** Resume context after user has interacted (or no-op if already running). */
export async function unlockNotificationAudio(): Promise<void> {
  const ctx = getSharedAudioContext();
  if (!ctx) return;
  if (ctx.state === "suspended") {
    try {
      await ctx.resume();
    } catch {
      /* ignore */
    }
  }
}

/** Register one-time listeners so the first click/keypress unlocks audio for later notification sounds. */
export function installNotificationAudioUnlock(): () => void {
  const go = () => {
    void unlockNotificationAudio();
  };
  document.addEventListener("pointerdown", go, { capture: true });
  document.addEventListener("keydown", go, { capture: true });
  return () => {
    document.removeEventListener("pointerdown", go, { capture: true });
    document.removeEventListener("keydown", go, { capture: true });
  };
}

/** Short, audible Slack-like “pop” (two soft sine notes). */
export async function playNotificationChime(): Promise<void> {
  if (typeof window === "undefined") return;
  try {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  } catch {
    /* ignore */
  }
  const ctx = getSharedAudioContext();
  if (!ctx) return;
  try {
    await ctx.resume();
  } catch {
    return;
  }
  if (ctx.state !== "running") return;

  const t0 = ctx.currentTime;
  const playTone = (freq: number, start: number, dur: number, vol: number) => {
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, start);
    g.gain.setValueAtTime(0, start);
    g.gain.linearRampToValueAtTime(vol, start + 0.018);
    g.gain.exponentialRampToValueAtTime(0.001, start + dur);
    osc.connect(g);
    g.connect(ctx.destination);
    osc.start(start);
    osc.stop(start + dur + 0.02);
  };
  // Pleasant fifth: C5 → G5
  playTone(523.25, t0, 0.11, 0.11);
  playTone(783.99, t0 + 0.085, 0.13, 0.09);
}

/** Distinct from activity chime: brighter major triad for direct messages. */
export async function playMessageChime(): Promise<void> {
  if (typeof window === "undefined") return;
  try {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  } catch {
    /* ignore */
  }
  const ctx = getSharedAudioContext();
  if (!ctx) return;
  try {
    await ctx.resume();
  } catch {
    return;
  }
  if (ctx.state !== "running") return;

  const t0 = ctx.currentTime;
  const playTone = (freq: number, start: number, dur: number, vol: number) => {
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, start);
    g.gain.setValueAtTime(0, start);
    g.gain.linearRampToValueAtTime(vol, start + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, start + dur);
    osc.connect(g);
    g.connect(ctx.destination);
    osc.start(start);
    osc.stop(start + dur + 0.02);
  };
  // E5 → G#5 → B5 (bright, “message” feel)
  playTone(659.25, t0, 0.1, 0.1);
  playTone(830.61, t0 + 0.09, 0.1, 0.085);
  playTone(987.77, t0 + 0.18, 0.12, 0.075);
}
