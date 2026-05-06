import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import DashFrame from "../DashFrame";
import {
  changePassword,
  deleteAccount,
  deleteAllAuthSessions,
  deleteAuthSession,
  fetchAuthSessions,
  fetchMyProfile,
  updateMyProfile,
  type AuthSessionRow,
  type UserProfile,
} from "../api";
import { useToast } from "../toast";
import { applyAppSettings } from "../settings";
import { useT } from "../i18n";
import { useAuth } from "../auth";

// ── Local profile cache (fallback when not authenticated) ─────────────────────
const LOCAL_PROFILE_KEY = "rezume.local_profile";

function loadLocalProfile(): Partial<UserProfile> {
  try {
    const raw = localStorage.getItem(LOCAL_PROFILE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveLocalProfile(p: Partial<UserProfile>) {
  try { localStorage.setItem(LOCAL_PROFILE_KEY, JSON.stringify(p)); } catch {}
}

function buildFallbackProfile(): UserProfile {
  const email = localStorage.getItem("rezume.email") || "";
  const cached = loadLocalProfile();
  return {
    id: "",
    email,
    full_name: cached.full_name ?? "",
    phone: cached.phone ?? "",
    address: cached.address ?? "",
    company: cached.company ?? "",
    available_hours: cached.available_hours ?? "",
    role_label: cached.role_label ?? "Recruiter",
    avatar_data: cached.avatar_data ?? null,
    two_factor_enabled: cached.two_factor_enabled ?? false,
    ...cached,
  };
}

// Merge remote profile onto local: prefer non-empty values so locally saved
// fields are never clobbered by empty strings returned from the backend.
function mergeProfile(local: UserProfile, remote: Partial<UserProfile>): UserProfile {
  return {
    ...local,
    ...remote,
    full_name: remote.full_name || local.full_name,
    phone: remote.phone || local.phone,
    address: remote.address || local.address,
    company: remote.company || local.company,
    available_hours: remote.available_hours || local.available_hours,
    role_label: remote.role_label || local.role_label,
    avatar_data: remote.avatar_data || local.avatar_data,
    two_factor_enabled:
      typeof remote.two_factor_enabled === "boolean" ? remote.two_factor_enabled : (local.two_factor_enabled ?? false),
  };
}

// ── localStorage helpers ──────────────────────────────────────────────────────

type AccountSettings = {
  defaultDashboard: string;
  candidatesPerPage: string;
  defaultTopMatches: string;
  language: string;
};

type ScreeningSettings = {
  minMatchScore: string;
  showOnlyTopMatches: string;
  autoRankCandidates: string;
  autoRejectLowMatches: string;
};

type NotifSettings = {
  newCandidateApplied: string;
  candidateShortlisted: string;
  candidateRejected: string;
  candidateHired: string;
  topMatchesFound: string;
  lowMatchWarning: string;
};

type PrefSettings = {
  theme: string;
  fontSize: string;
  defaultCandidateSort: string;
  defaultClientSort: string;
  defaultJobSort: string;
};

function loadLS<T>(key: string, defaults: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return defaults;
    return { ...defaults, ...JSON.parse(raw) } as T;
  } catch {
    return defaults;
  }
}

function saveLS(key: string, val: unknown) {
  localStorage.setItem(key, JSON.stringify(val));
}

const DEFAULT_ACCOUNT: AccountSettings = {
  defaultDashboard: "Dashboard Overview",
  candidatesPerPage: "10",
  defaultTopMatches: "3",
  language: "English",
};

const DEFAULT_SCREENING: ScreeningSettings = {
  minMatchScore: "70%",
  showOnlyTopMatches: "ON",
  autoRankCandidates: "OFF",
  autoRejectLowMatches: "OFF",
};

const DEFAULT_NOTIF: NotifSettings = {
  newCandidateApplied: "ON",
  candidateShortlisted: "ON",
  candidateRejected: "OFF",
  candidateHired: "ON",
  topMatchesFound: "ON",
  lowMatchWarning: "ON",
};

const DEFAULT_PREF: PrefSettings = {
  theme: "Light / Dark",
  fontSize: "Medium",
  defaultCandidateSort: "Match Score",
  defaultClientSort: "Newest",
  defaultJobSort: "Priority Based",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function SettingsRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="st-row">
      <span className="st-row-label">{label}</span>
      <div className="st-row-control">{children}</div>
    </div>
  );
}

function StSelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <select className="st-select" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

function StInput({ value, onChange, type = "text", placeholder = "", autoComplete, name, id }: {
  value: string; onChange: (v: string) => void; type?: string; placeholder?: string;
  autoComplete?: string; name?: string; id?: string;
}) {
  return (
    <input
      className="st-input"
      type={type}
      id={id}
      name={name}
      value={value}
      autoComplete={autoComplete}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
    />
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="st-section-title">{children}</div>;
}

function Panel({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <div className="st-panel">
      {children}
      {hint && <div className="st-panel-hint">{hint}</div>}
    </div>
  );
}

function SaveBtn({ onClick, saving, label, savingLabel }: {
  onClick: () => void;
  saving?: boolean;
  label?: string;
  savingLabel?: string;
}) {
  return (
    <div className="st-save-row">
      <button type="button" className="st-save-btn" onClick={onClick} disabled={saving}>
        {saving ? (savingLabel ?? "Saving…") : (label ?? "Save Changes")}
      </button>
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

const TAB_KEYS = ["Profile", "Account", "Screening", "Notifications", "Preferences", "Security"] as const;
type Tab = (typeof TAB_KEYS)[number];

const TAB_I18N_KEYS: Record<Tab, `settings.tab.${string}`> = {
  Profile: "settings.tab.profile",
  Account: "settings.tab.account",
  Screening: "settings.tab.screening",
  Notifications: "settings.tab.notifications",
  Preferences: "settings.tab.preferences",
  Security: "settings.tab.security",
} as const;

// ── Main component ────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const toast = useToast();
  const t = useT();
  const nav = useNavigate();
  const { logout } = useAuth();
  const [activeTab, setActiveTab] = useState<Tab>("Profile");

  // Profile tab — always non-null (falls back to localStorage cache)
  const [profile, setProfile] = useState<UserProfile>(() => buildFallbackProfile());
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileSaving, setProfileSaving] = useState(false);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Account tab
  const [account, setAccount] = useState<AccountSettings>(() => loadLS("rezume.settings.account", DEFAULT_ACCOUNT));

  // Screening tab
  const [screening, setScreening] = useState<ScreeningSettings>(() => loadLS("rezume.settings.screening", DEFAULT_SCREENING));

  // Notifications tab
  const [notif, setNotif] = useState<NotifSettings>(() => loadLS("rezume.settings.notif", DEFAULT_NOTIF));

  // Preferences tab
  const [pref, setPref] = useState<PrefSettings>(() => loadLS("rezume.settings.pref", DEFAULT_PREF));

  // Security tab
  const [currentPwd, setCurrentPwd] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [pwdSaving, setPwdSaving] = useState(false);
  const [twoFA, setTwoFA] = useState(() => loadLS<{ enabled: string }>("rezume.settings.security", { enabled: "OFF" }).enabled);
  const [sessions, setSessions] = useState<AuthSessionRow[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [securitySaving, setSecuritySaving] = useState(false);
  const [sessionsBusy, setSessionsBusy] = useState(false);

  const [deletePwd, setDeletePwd] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
  /** After first click we show a toast; second click performs the API delete. */
  const [deleteAwaitingConfirm, setDeleteAwaitingConfirm] = useState(false);

  // Fetch profile from backend; merge onto local fallback without clobbering
  // fields that were explicitly saved locally (backend may return empty strings).
  useEffect(() => {
    setProfileLoading(true);
    fetchMyProfile()
      .then((remote) => {
        setProfile((local) => {
          const merged = mergeProfile(local, remote);
          saveLocalProfile(merged);
          return merged;
        });
        if (typeof remote.two_factor_enabled === "boolean") {
          setTwoFA(remote.two_factor_enabled ? "ON" : "OFF");
        }
      })
      .catch(() => {
        // Auth not configured or no token — stay with local fallback
      })
      .finally(() => setProfileLoading(false));
  }, []);

  useEffect(() => {
    if (activeTab !== "Security") return;
    setSessionsLoading(true);
    fetchAuthSessions()
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setSessionsLoading(false));
  }, [activeTab]);

  // Handlers
  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 400_000) { toast.error("Image must be under 400 KB"); return; }
    setAvatarUploading(true);
    const reader = new FileReader();
    reader.onload = async () => {
      const dataUrl = reader.result as string;
      const updated = { ...profile, avatar_data: dataUrl };
      setProfile(updated);
      saveLocalProfile(updated);
      try {
        const remote = await updateMyProfile({ avatar_data: dataUrl });
        const merged = mergeProfile(updated, remote);
        setProfile(merged);
        saveLocalProfile(merged);
        toast.success(t("profile.picUpdated"));
      } catch {
        toast.success(t("profile.picLocal"));
      } finally {
        setAvatarUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    };
    reader.onerror = () => {
      toast.error("Could not read the image file");
      setAvatarUploading(false);
    };
    reader.readAsDataURL(file);
  };

  const saveProfile = async () => {
    setProfileSaving(true);
    // Always persist locally first so fields survive page reloads
    saveLocalProfile(profile);
    try {
      const updated = await updateMyProfile({
        full_name: profile.full_name,
        phone: profile.phone,
        address: profile.address,
        company: profile.company,
        available_hours: profile.available_hours,
        role_label: profile.role_label,
        avatar_data: profile.avatar_data ?? undefined,
      });
      const merged = mergeProfile(profile, updated);
      setProfile(merged);
      saveLocalProfile(merged);
      setEditingName(false);
      toast.success(t("profile.saved"));
    } catch {
      setEditingName(false);
      toast.success(t("profile.savedLocally"));
    } finally {
      setProfileSaving(false);
    }
  };

  const handleChangePassword = async () => {
    if (!newPwd || !currentPwd) { toast.error("Fill in all password fields"); return; }
    if (newPwd !== confirmPwd) { toast.error("New passwords do not match"); return; }
    if (newPwd.length < 8) { toast.error("New password must be at least 8 characters"); return; }
    setPwdSaving(true);
    try {
      await changePassword(currentPwd, newPwd);
      toast.success("Password changed");
      setCurrentPwd(""); setNewPwd(""); setConfirmPwd("");
    } catch (e) {
      toast.error((e as Error).message || "Failed to change password");
    } finally {
      setPwdSaving(false);
    }
  };

  const refreshSessions = () => {
    fetchAuthSessions()
      .then(setSessions)
      .catch(() => {});
  };

  const handleRevokeSession = async (row: AuthSessionRow) => {
    setSessionsBusy(true);
    try {
      await deleteAuthSession(row.id);
      if (row.is_current) {
        logout();
        nav("/login");
        return;
      }
      refreshSessions();
      toast.success(t("security.sessionRevoked"));
    } catch (e) {
      toast.error((e as Error).message || "Could not revoke session");
    } finally {
      setSessionsBusy(false);
    }
  };

  const handleLogoutAllDevices = async () => {
    setSessionsBusy(true);
    try {
      await deleteAllAuthSessions();
      logout();
      toast.success(t("security.signedOutAll"));
      nav("/login");
    } catch (e) {
      toast.error((e as Error).message || "Could not sign out all devices");
    } finally {
      setSessionsBusy(false);
    }
  };

  const saveSecuritySettings = async () => {
    setSecuritySaving(true);
    try {
      const updated = await updateMyProfile({ two_factor_enabled: twoFA === "ON" });
      const merged = mergeProfile(profile, updated);
      setProfile(merged);
      saveLocalProfile(merged);
      saveLS("rezume.settings.security", { enabled: twoFA });
      toast.success(t("security.saved"));
    } catch (e) {
      toast.error((e as Error).message || "Could not save security settings");
    } finally {
      setSecuritySaving(false);
    }
  };

  const pField = (k: keyof UserProfile) => (v: string) =>
    setProfile((p) => ({ ...p, [k]: v }));

  const saveAccountSettings = () => {
    saveLS("rezume.settings.account", account);
    applyAppSettings();
    // Notify the language context to re-read and update direction/language
    window.dispatchEvent(new CustomEvent("rezume:language-changed"));
    toast.success(t("account.saved"));
  };

  const handleDeleteAccount = async () => {
    if (!deletePwd.trim()) {
      toast.error(t("profile.deleteAccountNeedPassword"));
      return;
    }
    if (!deleteAwaitingConfirm) {
      toast.info(t("profile.deleteAccountConfirm"), { title: t("profile.deleteAccountToastTitle") });
      setDeleteAwaitingConfirm(true);
      return;
    }
    setDeleteBusy(true);
    try {
      await deleteAccount(deletePwd);
      try {
        localStorage.removeItem(LOCAL_PROFILE_KEY);
      } catch {
        /* ignore */
      }
      logout();
      toast.success(t("profile.deleteAccountSuccess"));
      nav("/");
    } catch (e) {
      toast.error((e as Error).message || t("profile.deleteAccountFailed"));
    } finally {
      setDeleteBusy(false);
      setDeletePwd("");
      setDeleteAwaitingConfirm(false);
    }
  };

  return (
    <DashFrame>
      <div className="settings-page">
        <h1 className="settings-title">{t("settings.title")}</h1>

        <div className="settings-card">
          {/* Tab bar */}
          <div className="settings-tabs">
            {TAB_KEYS.map((tab, i) => (
              <button
                key={tab}
                type="button"
                className={`settings-tab${activeTab === tab ? " active" : ""}`}
                onClick={() => setActiveTab(tab)}
              >
                {t(TAB_I18N_KEYS[tab] as Parameters<typeof t>[0])}
                {i < TAB_KEYS.length - 1 && <span className="settings-tab-sep" aria-hidden>|</span>}
              </button>
            ))}
          </div>

          {/* ── Profile ── */}
          {activeTab === "Profile" && (
            <div className="st-content">
              {profileLoading && !profile.email && (
                <p className="muted">{t("common.loading")}</p>
              )}
              <>
                <div className="st-profile-header">
                  <div className="st-avatar-wrap">
                    <div className={`st-avatar${avatarUploading ? " st-avatar--uploading" : ""}`}>
                      {profile.avatar_data
                        ? <img src={profile.avatar_data} alt="avatar" />
                        : <span className="st-avatar-initials">{(profile.full_name || profile.email || "?")[0].toUpperCase()}</span>
                      }
                      {avatarUploading && <div className="st-avatar-spinner" />}
                    </div>
                  </div>
                  <div className="st-profile-info">
                    {editingName ? (
                      <input
                        className="st-input st-name-input"
                        value={profile.full_name}
                        onChange={(e) => pField("full_name")(e.target.value)}
                        placeholder="Full name"
                        autoFocus
                      />
                    ) : (
                      <div className="st-profile-name">{profile.full_name || t("profile.noName")}</div>
                    )}
                    <div className="st-profile-email">{profile.email || "—"}</div>
                    <div className="st-profile-role">{profile.role_label || "Recruiter"}</div>
                    <button
                      type="button"
                      className="st-upload-btn"
                      disabled={avatarUploading}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      {avatarUploading ? t("common.uploading") : t("common.upload")}
                    </button>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept="image/*"
                      style={{ display: "none" }}
                      onChange={handleAvatarChange}
                    />
                  </div>
                  <button type="button" className="st-change-name-btn" onClick={() => setEditingName((v) => !v)}>
                    {editingName ? t("common.cancel") : t("common.changeName")}
                  </button>
                </div>

                <Panel>
                  <SettingsRow label={t("profile.phoneNumber")}>
                    <StInput value={profile.phone} onChange={pField("phone")} placeholder="e.g. 03001234567" />
                  </SettingsRow>
                  <SettingsRow label={t("profile.address")}>
                    <StInput value={profile.address} onChange={pField("address")} placeholder="Street, City" />
                  </SettingsRow>
                  <SettingsRow label={t("profile.email")}>
                    <input className="st-input st-input--readonly" value={profile.email} readOnly />
                  </SettingsRow>
                  <SettingsRow label={t("profile.company")}>
                    <StInput value={profile.company} onChange={pField("company")} placeholder="Company name" />
                  </SettingsRow>
                  <SettingsRow label={t("profile.availableHours")}>
                    <StInput value={profile.available_hours} onChange={pField("available_hours")} placeholder="e.g. 10am – 7pm" />
                  </SettingsRow>
                </Panel>
                <SaveBtn onClick={saveProfile} saving={profileSaving} label={t("common.save")} savingLabel={t("common.saving")} />

                {profile.id ? (
                  <div className="st-delete-account">
                    <h3 className="st-delete-account-title">{t("profile.deleteAccountTitle")}</h3>
                    <p className="st-delete-account-hint muted">{t("profile.deleteAccountHint")}</p>
                    <SettingsRow label={t("profile.deleteAccountPasswordLabel")}>
                      <input
                        className="st-input"
                        type="password"
                        autoComplete="current-password"
                        value={deletePwd}
                        onChange={(e) => {
                          setDeletePwd(e.target.value);
                          setDeleteAwaitingConfirm(false);
                        }}
                        placeholder={t("profile.deleteAccountPasswordPlaceholder")}
                      />
                    </SettingsRow>
                    {deleteAwaitingConfirm ? (
                      <p className="st-delete-account-toast-hint muted" role="status">
                        {t("profile.deleteAccountToastHint")}
                      </p>
                    ) : null}
                    <div className="st-delete-account-actions">
                      {deleteAwaitingConfirm ? (
                        <button
                          type="button"
                          className="st-delete-account-cancel"
                          disabled={deleteBusy}
                          onClick={() => setDeleteAwaitingConfirm(false)}
                        >
                          {t("profile.deleteAccountCancelConfirm")}
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="st-delete-account-btn"
                        disabled={deleteBusy || !deletePwd.trim()}
                        onClick={() => void handleDeleteAccount()}
                      >
                        {deleteBusy
                          ? t("profile.deleteAccountBusy")
                          : deleteAwaitingConfirm
                            ? t("profile.deleteAccountConfirmButton")
                            : t("profile.deleteAccountButton")}
                      </button>
                    </div>
                  </div>
                ) : null}
              </>
            </div>
          )}

          {/* ── Account ── */}
          {activeTab === "Account" && (
            <div className="st-content">
              <SectionTitle>{t("account.general")}</SectionTitle>
              <Panel hint={t("account.hint")}>
                <SettingsRow label={t("account.defaultDashboard")}>
                  <StSelect value={account.defaultDashboard} onChange={(v) => setAccount((a) => ({ ...a, defaultDashboard: v }))}
                    options={["Dashboard Overview", "Candidates", "Jobs", "Reports"]} />
                </SettingsRow>
                <SettingsRow label={t("account.candidatesPerPage")}>
                  <StSelect value={account.candidatesPerPage} onChange={(v) => setAccount((a) => ({ ...a, candidatesPerPage: v }))}
                    options={["5", "10", "20", "50"]} />
                </SettingsRow>
                <SettingsRow label={t("account.defaultTopMatches")}>
                  <StSelect value={account.defaultTopMatches} onChange={(v) => setAccount((a) => ({ ...a, defaultTopMatches: v }))}
                    options={["3", "5", "10", "20"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>{t("account.localization")}</SectionTitle>
              <Panel>
                <SettingsRow label={t("account.language")}>
                  <StSelect value={account.language} onChange={(v) => setAccount((a) => ({ ...a, language: v }))}
                    options={["English", "Urdu", "Arabic", "French"]} />
                </SettingsRow>
              </Panel>
              <SaveBtn onClick={saveAccountSettings} label={t("common.save")} savingLabel={t("common.saving")} />
            </div>
          )}

          {/* ── Screening ── */}
          {activeTab === "Screening" && (
            <div className="st-content">
              <SectionTitle>{t("screening.thresholds")}</SectionTitle>
              <Panel hint="Minimum Match Score: hides ranked candidates below this threshold on the Matching page (requires Auto Reject to be ON). Show Only Top Matches: when ON, only the top N candidates are displayed (N = Default Top Matches in Account settings); when OFF, all candidates passing other filters are shown.">
                <SettingsRow label={t("screening.minScore")}>
                  <StSelect value={screening.minMatchScore} onChange={(v) => setScreening((s) => ({ ...s, minMatchScore: v }))}
                    options={["10%", "20%", "30%", "40%", "50%", "60%", "70%", "80%", "90%"]} />
                </SettingsRow>
                <SettingsRow label={t("screening.showTopMatches")}>
                  <StSelect value={screening.showOnlyTopMatches} onChange={(v) => setScreening((s) => ({ ...s, showOnlyTopMatches: v }))}
                    options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>


              <SectionTitle>{t("screening.automation")}</SectionTitle>
              <Panel hint="Auto Rank: when ON, selecting a job on the Matching page immediately runs full matching and saves scores to the database for the whole candidate pool (up to Top matches), not only one profile. Leave OFF unless you want that. Auto Reject: when ON, ranked candidates below the Minimum Match Score are hidden from the list.">
                <SettingsRow label={t("screening.autoRank")}>
                  <StSelect value={screening.autoRankCandidates} onChange={(v) => setScreening((s) => ({ ...s, autoRankCandidates: v }))}
                    options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label={t("screening.autoReject")}>
                  <StSelect value={screening.autoRejectLowMatches} onChange={(v) => setScreening((s) => ({ ...s, autoRejectLowMatches: v }))}
                    options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>
              <SaveBtn onClick={() => { saveLS("rezume.settings.screening", screening); applyAppSettings(); toast.success(t("screening.saved")); }}
                label={t("common.save")} savingLabel={t("common.saving")} />
            </div>
          )}

          {/* ── Notifications ── */}
          {activeTab === "Notifications" && (
            <div className="st-content">
              <div className="st-notif-hint">{t("notif.hint")}</div>

              <SectionTitle>{t("notif.candidateActivity")}</SectionTitle>
              <Panel>
                <SettingsRow label={t("notif.newApplied")}>
                  <StSelect value={notif.newCandidateApplied} onChange={(v) => setNotif((n) => ({ ...n, newCandidateApplied: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label={t("notif.shortlisted")}>
                  <StSelect value={notif.candidateShortlisted} onChange={(v) => setNotif((n) => ({ ...n, candidateShortlisted: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label={t("notif.rejected")}>
                  <StSelect value={notif.candidateRejected} onChange={(v) => setNotif((n) => ({ ...n, candidateRejected: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label={t("notif.hired")}>
                  <StSelect value={notif.candidateHired} onChange={(v) => setNotif((n) => ({ ...n, candidateHired: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>{t("notif.alerts")}</SectionTitle>
              <Panel>
                <SettingsRow label={t("notif.topMatchesFound")}>
                  <StSelect value={notif.topMatchesFound} onChange={(v) => setNotif((n) => ({ ...n, topMatchesFound: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label={t("notif.lowMatch")}>
                  <StSelect value={notif.lowMatchWarning} onChange={(v) => setNotif((n) => ({ ...n, lowMatchWarning: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>

              <SaveBtn onClick={() => { saveLS("rezume.settings.notif", notif); toast.success(t("notif.saved")); }}
                label={t("common.save")} savingLabel={t("common.saving")} />
            </div>
          )}

          {/* ── Preferences ── */}
          {activeTab === "Preferences" && (
            <div className="st-content">
              <SectionTitle>{t("pref.interface")}</SectionTitle>
              <Panel hint="Font size and theme are applied immediately on save">
                <SettingsRow label={t("pref.theme")}>
                  <StSelect value={pref.theme} onChange={(v) => setPref((p) => ({ ...p, theme: v }))}
                    options={["Light / Dark", "Dark", "Light"]} />
                </SettingsRow>
                <SettingsRow label={t("pref.fontSize")}>
                  <StSelect value={pref.fontSize} onChange={(v) => setPref((p) => ({ ...p, fontSize: v }))}
                    options={["Small", "Medium", "Large"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>{t("pref.defaults")}</SectionTitle>
              <Panel hint="Sort order used when you first open each list page">
                <SettingsRow label={t("pref.candidateSort")}>
                  <StSelect value={pref.defaultCandidateSort} onChange={(v) => setPref((p) => ({ ...p, defaultCandidateSort: v }))}
                    options={["Match Score", "Name", "Date Added", "Status"]} />
                </SettingsRow>
                <SettingsRow label={t("pref.clientSort")}>
                  <StSelect value={pref.defaultClientSort} onChange={(v) => setPref((p) => ({ ...p, defaultClientSort: v }))}
                    options={["Newest", "Name", "Status"]} />
                </SettingsRow>
                <SettingsRow label={t("pref.jobSort")}>
                  <StSelect value={pref.defaultJobSort} onChange={(v) => setPref((p) => ({ ...p, defaultJobSort: v }))}
                    options={["Priority Based", "Date Added", "Title", "Status"]} />
                </SettingsRow>
              </Panel>
              <SaveBtn onClick={() => { saveLS("rezume.settings.pref", pref); applyAppSettings(); toast.success(t("pref.saved")); }}
                label={t("common.save")} savingLabel={t("common.saving")} />
            </div>
          )}

          {/* ── Security ── */}
          {activeTab === "Security" && (
            <div className="st-content">
              <form className="st-security-form" autoComplete="on" onSubmit={(e) => e.preventDefault()}>
                {/* First focusable login field for password managers — keeps email out of the header search */}
                <label htmlFor="st-security-username" className="visually-hidden">
                  {t("security.accountEmail")}
                </label>
                <input
                  id="st-security-username"
                  className="visually-hidden"
                  type="email"
                  name="username"
                  autoComplete="username"
                  readOnly
                  tabIndex={-1}
                  aria-hidden
                  value={profile.email}
                  onChange={() => {}}
                />
                <SectionTitle>{t("security.password")}</SectionTitle>
                <Panel>
                  <SettingsRow label={t("security.currentPwd")}>
                    <StInput
                      id="st-security-current-pw"
                      name="current-password"
                      value={currentPwd}
                      onChange={setCurrentPwd}
                      type="password"
                      placeholder="••••••••"
                      autoComplete="current-password"
                    />
                  </SettingsRow>
                  <SettingsRow label={t("security.newPwd")}>
                    <StInput
                      id="st-security-new-pw"
                      name="new-password"
                      value={newPwd}
                      onChange={setNewPwd}
                      type="password"
                      placeholder="••••••••"
                      autoComplete="new-password"
                    />
                  </SettingsRow>
                  <SettingsRow label={t("security.confirmPwd")}>
                    <StInput
                      id="st-security-confirm-pw"
                      name="confirm-new-password"
                      value={confirmPwd}
                      onChange={setConfirmPwd}
                      type="password"
                      placeholder="••••••••"
                      autoComplete="new-password"
                    />
                  </SettingsRow>
                  <div className="st-row">
                    <span />
                    <button type="button" className="st-change-pwd-btn" onClick={handleChangePassword} disabled={pwdSaving}>
                      {pwdSaving ? t("security.changingPwd") : t("security.changePwd")}
                    </button>
                  </div>
                </Panel>

                <SectionTitle>{t("security.twoFA")}</SectionTitle>
                <Panel>
                  <SettingsRow label={t("security.enable2fa")}>
                    <StSelect value={twoFA} onChange={setTwoFA} options={["ON", "OFF"]} />
                  </SettingsRow>
                </Panel>
              </form>

              <SectionTitle>{t("security.sessions")}</SectionTitle>
              <Panel>
                {sessionsLoading ? (
                  <p className="muted">{t("common.loading")}</p>
                ) : sessions.length === 0 ? (
                  <p className="muted">{t("security.noSessions")}</p>
                ) : (
                  <ul className="st-session-list">
                    {sessions.map((s) => (
                      <li key={s.id} className="st-session-row">
                        <div className="st-session-meta">
                          <div className="st-session-device">
                            {s.device_label}
                            {s.is_current ? <span className="st-session-badge">{t("security.thisDevice")}</span> : null}
                          </div>
                          <div className="st-session-loc muted">
                            {[s.location_label, s.ip_address].filter(Boolean).join(" · ")}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="st-session-revoke"
                          disabled={sessionsBusy}
                          onClick={() => void handleRevokeSession(s)}
                        >
                          {t("security.revoke")}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="st-row">
                  <span />
                  <button type="button" className="st-change-pwd-btn" disabled={sessionsBusy} onClick={() => void handleLogoutAllDevices()}>
                    {t("security.logoutAll")}
                  </button>
                </div>
              </Panel>

              <SaveBtn
                onClick={() => void saveSecuritySettings()}
                saving={securitySaving}
                label={t("common.save")}
                savingLabel={t("common.saving")}
              />
            </div>
          )}
        </div>
      </div>
    </DashFrame>
  );
}
