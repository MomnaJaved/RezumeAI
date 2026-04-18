import { useEffect, useRef, useState } from "react";
import DashFrame from "../DashFrame";
import { changePassword, fetchMyProfile, updateMyProfile, type UserProfile } from "../api";
import { useToast } from "../toast";
import { applyAppSettings } from "../settings";

// ── Local profile cache (fallback when not authenticated) ─────────────────────
const LOCAL_PROFILE_KEY = "rezume.local_profile";

function loadLocalProfile(): Partial<UserProfile> {
  try {
    const raw = localStorage.getItem(LOCAL_PROFILE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

function saveLocalProfile(p: UserProfile) {
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
    ...cached,
  };
}

// ── localStorage helpers ──────────────────────────────────────────────────────

type AccountSettings = {
  defaultDashboard: string;
  candidatesPerPage: string;
  defaultTopMatches: string;
  dateFormat: string;
  timeZone: string;
  language: string;
};

type ScreeningSettings = {
  minMatchScore: string;
  showOnlyTopMatches: string;
  skillsImportance: string;
  experienceImportance: string;
  certifications: string;
  autoRankCandidates: string;
  autoRejectLowMatches: string;
};

type NotifSettings = {
  newCandidateApplied: string;
  candidateShortlisted: string;
  candidateRejected: string;
  topMatchesFound: string;
  lowMatchWarning: string;
  weeklySummaryEmail: string;
  monthlyHiringReport: string;
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
  dateFormat: "DD/MM/YYYY",
  timeZone: "GMT +05:00",
  language: "English",
};

const DEFAULT_SCREENING: ScreeningSettings = {
  minMatchScore: "70%",
  showOnlyTopMatches: "ON",
  skillsImportance: "High",
  experienceImportance: "Medium",
  certifications: "Low",
  autoRankCandidates: "ON",
  autoRejectLowMatches: "OFF",
};

const DEFAULT_NOTIF: NotifSettings = {
  newCandidateApplied: "ON",
  candidateShortlisted: "ON",
  candidateRejected: "OFF",
  topMatchesFound: "ON",
  lowMatchWarning: "ON",
  weeklySummaryEmail: "ON",
  monthlyHiringReport: "OFF",
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

function StInput({ value, onChange, type = "text", placeholder = "" }: {
  value: string; onChange: (v: string) => void; type?: string; placeholder?: string;
}) {
  return (
    <input
      className="st-input"
      type={type}
      value={value}
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

function SaveBtn({ onClick, saving }: { onClick: () => void; saving?: boolean }) {
  return (
    <div className="st-save-row">
      <button type="button" className="st-save-btn" onClick={onClick} disabled={saving}>
        {saving ? "Saving…" : "Save Changes"}
      </button>
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

const TABS = ["Profile", "Account", "Screening", "Notifications", "Preferences", "Security"] as const;
type Tab = (typeof TABS)[number];

// ── Main component ────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const toast = useToast();
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
  const [twoFA, setTwoFA] = useState(() => loadLS<{ enabled: string }>("rezume.settings.security", { enabled: "ON" }).enabled);

  // Fetch profile from backend; merge onto the local fallback
  useEffect(() => {
    setProfileLoading(true);
    fetchMyProfile()
      .then((remote) => {
        // Prefer remote data; keep local avatar if remote has none
        setProfile((local) => ({
          ...remote,
          avatar_data: remote.avatar_data || local.avatar_data,
        }));
        saveLocalProfile({ ...buildFallbackProfile(), ...remote });
      })
      .catch(() => {
        // Auth not configured or no token — stay with local fallback, that's fine
      })
      .finally(() => setProfileLoading(false));
  }, []);

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
      saveLocalProfile(updated);          // persist locally immediately
      // Also push to backend (best-effort)
      try {
        const remote = await updateMyProfile({ avatar_data: dataUrl });
        setProfile((p) => ({ ...p, ...remote }));
        saveLocalProfile({ ...updated, ...remote });
        toast.success("Profile picture updated");
      } catch {
        toast.success("Profile picture saved locally");
      } finally {
        setAvatarUploading(false);
        // Reset so the same file can be re-selected
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
    // Always persist locally
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
      setProfile((p) => ({ ...p, ...updated }));
      saveLocalProfile({ ...profile, ...updated });
      setEditingName(false);
      toast.success("Profile saved");
    } catch {
      // Saved locally — user not on authenticated backend
      setEditingName(false);
      toast.success("Profile saved locally");
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

  const pField = (k: keyof UserProfile) => (v: string) =>
    setProfile((p) => ({ ...p, [k]: v }));

  return (
    <DashFrame>
      <div className="settings-page">
        <h1 className="settings-title">Manage Your Account and System Preferences</h1>

        <div className="settings-card">
          {/* Tab bar */}
          <div className="settings-tabs">
            {TABS.map((tab, i) => (
              <button
                key={tab}
                type="button"
                className={`settings-tab${activeTab === tab ? " active" : ""}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
                {i < TABS.length - 1 && <span className="settings-tab-sep" aria-hidden>|</span>}
              </button>
            ))}
          </div>

          {/* ── Profile ── */}
          {activeTab === "Profile" && (
            <div className="st-content">
              {profileLoading && !profile.email && (
                <p className="muted">Loading profile…</p>
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
                      <div className="st-profile-name">{profile.full_name || "(no name)"}</div>
                    )}
                    <div className="st-profile-email">{profile.email || "—"}</div>
                    <div className="st-profile-role">{profile.role_label || "Recruiter"}</div>
                    <button
                      type="button"
                      className="st-upload-btn"
                      disabled={avatarUploading}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      {avatarUploading ? "Uploading…" : "Upload Profile Picture"}
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
                    {editingName ? "Cancel" : "Change name"}
                  </button>
                </div>

                <Panel>
                  <SettingsRow label="Phone Number">
                    <StInput value={profile.phone} onChange={pField("phone")} placeholder="e.g. 03001234567" />
                  </SettingsRow>
                  <SettingsRow label="Address">
                    <StInput value={profile.address} onChange={pField("address")} placeholder="Street, City" />
                  </SettingsRow>
                  <SettingsRow label="Email">
                    <input className="st-input st-input--readonly" value={profile.email} readOnly />
                  </SettingsRow>
                  <SettingsRow label="Company">
                    <StInput value={profile.company} onChange={pField("company")} placeholder="Company name" />
                  </SettingsRow>
                  <SettingsRow label="Available Hours">
                    <StInput value={profile.available_hours} onChange={pField("available_hours")} placeholder="e.g. 10am – 7pm" />
                  </SettingsRow>
                </Panel>
                <SaveBtn onClick={saveProfile} saving={profileSaving} />
              </>
            </div>
          )}

          {/* ── Account ── */}
          {activeTab === "Account" && (
            <div className="st-content">
              <SectionTitle>General</SectionTitle>
              <Panel hint="Changes apply on next page visit">
                <SettingsRow label="Default Dashboard">
                  <StSelect value={account.defaultDashboard} onChange={(v) => setAccount((a) => ({ ...a, defaultDashboard: v }))}
                    options={["Dashboard Overview", "Candidates", "Jobs", "Reports"]} />
                </SettingsRow>
                <SettingsRow label="Candidates Per Page">
                  <StSelect value={account.candidatesPerPage} onChange={(v) => setAccount((a) => ({ ...a, candidatesPerPage: v }))}
                    options={["5", "10", "20", "50"]} />
                </SettingsRow>
                <SettingsRow label="Default Top Matches">
                  <StSelect value={account.defaultTopMatches} onChange={(v) => setAccount((a) => ({ ...a, defaultTopMatches: v }))}
                    options={["3", "5", "10", "20"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>Localization</SectionTitle>
              <Panel>
                <SettingsRow label="Date Format">
                  <StSelect value={account.dateFormat} onChange={(v) => setAccount((a) => ({ ...a, dateFormat: v }))}
                    options={["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"]} />
                </SettingsRow>
                <SettingsRow label="Time Zone">
                  <StSelect value={account.timeZone} onChange={(v) => setAccount((a) => ({ ...a, timeZone: v }))}
                    options={["GMT +05:00", "GMT +00:00", "GMT -05:00", "GMT +01:00", "GMT +08:00"]} />
                </SettingsRow>
                <SettingsRow label="Language">
                  <StSelect value={account.language} onChange={(v) => setAccount((a) => ({ ...a, language: v }))}
                    options={["English", "Urdu", "Arabic", "French"]} />
                </SettingsRow>
              </Panel>
              <SaveBtn onClick={() => { saveLS("rezume.settings.account", account); applyAppSettings(); toast.success("Account settings saved"); }} />
            </div>
          )}

          {/* ── Screening ── */}
          {activeTab === "Screening" && (
            <div className="st-content">
              <SectionTitle>Matching Thresholds</SectionTitle>
              <Panel hint="Filters candidates on the Matching page — candidates below the minimum score are hidden">
                <SettingsRow label="Minimum Match Score">
                  <StSelect value={screening.minMatchScore} onChange={(v) => setScreening((s) => ({ ...s, minMatchScore: v }))}
                    options={["50%", "60%", "70%", "80%", "90%"]} />
                </SettingsRow>
                <SettingsRow label="Show Only Top Matches">
                  <StSelect value={screening.showOnlyTopMatches} onChange={(v) => setScreening((s) => ({ ...s, showOnlyTopMatches: v }))}
                    options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>Scoring Weights</SectionTitle>
              <Panel>
                <SettingsRow label="Skills Importance">
                  <StSelect value={screening.skillsImportance} onChange={(v) => setScreening((s) => ({ ...s, skillsImportance: v }))}
                    options={["High", "Medium", "Low"]} />
                </SettingsRow>
                <SettingsRow label="Experience Importance">
                  <StSelect value={screening.experienceImportance} onChange={(v) => setScreening((s) => ({ ...s, experienceImportance: v }))}
                    options={["High", "Medium", "Low"]} />
                </SettingsRow>
                <SettingsRow label="Certifications">
                  <StSelect value={screening.certifications} onChange={(v) => setScreening((s) => ({ ...s, certifications: v }))}
                    options={["High", "Medium", "Low"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>Automation</SectionTitle>
              <Panel>
                <SettingsRow label="Auto Rank Candidates">
                  <StSelect value={screening.autoRankCandidates} onChange={(v) => setScreening((s) => ({ ...s, autoRankCandidates: v }))}
                    options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label="Auto Reject Low Matches">
                  <StSelect value={screening.autoRejectLowMatches} onChange={(v) => setScreening((s) => ({ ...s, autoRejectLowMatches: v }))}
                    options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>
              <SaveBtn onClick={() => { saveLS("rezume.settings.screening", screening); applyAppSettings(); toast.success("Screening settings saved — reload any open page to apply"); }} />
            </div>
          )}

          {/* ── Notifications ── */}
          {activeTab === "Notifications" && (
            <div className="st-content">
              <div className="st-notif-hint">Choose when you want to be notified</div>

              <SectionTitle>Candidate Activity</SectionTitle>
              <Panel>
                <SettingsRow label="New Candidate Applied">
                  <StSelect value={notif.newCandidateApplied} onChange={(v) => setNotif((n) => ({ ...n, newCandidateApplied: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label="Candidate Shortlisted">
                  <StSelect value={notif.candidateShortlisted} onChange={(v) => setNotif((n) => ({ ...n, candidateShortlisted: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label="Candidate Rejected">
                  <StSelect value={notif.candidateRejected} onChange={(v) => setNotif((n) => ({ ...n, candidateRejected: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>Alerts</SectionTitle>
              <Panel>
                <SettingsRow label="Top Matches Found">
                  <StSelect value={notif.topMatchesFound} onChange={(v) => setNotif((n) => ({ ...n, topMatchesFound: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label="Low Match Warning">
                  <StSelect value={notif.lowMatchWarning} onChange={(v) => setNotif((n) => ({ ...n, lowMatchWarning: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>Reports</SectionTitle>
              <Panel>
                <SettingsRow label="Weekly Summary Email">
                  <StSelect value={notif.weeklySummaryEmail} onChange={(v) => setNotif((n) => ({ ...n, weeklySummaryEmail: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
                <SettingsRow label="Monthly Hiring Report">
                  <StSelect value={notif.monthlyHiringReport} onChange={(v) => setNotif((n) => ({ ...n, monthlyHiringReport: v }))} options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>
              <SaveBtn onClick={() => { saveLS("rezume.settings.notif", notif); toast.success("Notification settings saved"); }} />
            </div>
          )}

          {/* ── Preferences ── */}
          {activeTab === "Preferences" && (
            <div className="st-content">
              <SectionTitle>Interface</SectionTitle>
              <Panel hint="Font size and theme are applied immediately on save">
                <SettingsRow label="Theme">
                  <StSelect value={pref.theme} onChange={(v) => setPref((p) => ({ ...p, theme: v }))}
                    options={["Light / Dark", "Dark", "Light"]} />
                </SettingsRow>
                <SettingsRow label="Font Size">
                  <StSelect value={pref.fontSize} onChange={(v) => setPref((p) => ({ ...p, fontSize: v }))}
                    options={["Small", "Medium", "Large"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>Defaults</SectionTitle>
              <Panel hint="Sort order used when you first open each list page">
                <SettingsRow label="Default Candidate Sort">
                  <StSelect value={pref.defaultCandidateSort} onChange={(v) => setPref((p) => ({ ...p, defaultCandidateSort: v }))}
                    options={["Match Score", "Name", "Date Added", "Status"]} />
                </SettingsRow>
                <SettingsRow label="Default Client Sort">
                  <StSelect value={pref.defaultClientSort} onChange={(v) => setPref((p) => ({ ...p, defaultClientSort: v }))}
                    options={["Newest", "Name", "Status"]} />
                </SettingsRow>
                <SettingsRow label="Default Job Sort">
                  <StSelect value={pref.defaultJobSort} onChange={(v) => setPref((p) => ({ ...p, defaultJobSort: v }))}
                    options={["Priority Based", "Date Added", "Title", "Status"]} />
                </SettingsRow>
              </Panel>
              <SaveBtn onClick={() => { saveLS("rezume.settings.pref", pref); applyAppSettings(); toast.success("Preferences saved — theme and font applied"); }} />
            </div>
          )}

          {/* ── Security ── */}
          {activeTab === "Security" && (
            <div className="st-content">
              <SectionTitle>Password</SectionTitle>
              <Panel>
                <SettingsRow label="Current Password">
                  <StInput value={currentPwd} onChange={setCurrentPwd} type="password" placeholder="••••••••" />
                </SettingsRow>
                <SettingsRow label="New Password">
                  <StInput value={newPwd} onChange={setNewPwd} type="password" placeholder="••••••••" />
                </SettingsRow>
                <SettingsRow label="Confirm Password">
                  <StInput value={confirmPwd} onChange={setConfirmPwd} type="password" placeholder="••••••••" />
                </SettingsRow>
                <div className="st-row">
                  <span />
                  <button type="button" className="st-change-pwd-btn" onClick={handleChangePassword} disabled={pwdSaving}>
                    {pwdSaving ? "Changing…" : "Change Password"}
                  </button>
                </div>
              </Panel>

              <SectionTitle>Two-Factor Authentication</SectionTitle>
              <Panel>
                <SettingsRow label="Enable 2FA">
                  <StSelect value={twoFA} onChange={setTwoFA} options={["ON", "OFF"]} />
                </SettingsRow>
              </Panel>

              <SectionTitle>Sessions</SectionTitle>
              <Panel>
                <SettingsRow label="Logged-in Devices">
                  <span className="st-device-label">This device</span>
                </SettingsRow>
                <div className="st-row">
                  <span />
                  <button type="button" className="st-change-pwd-btn"
                    onClick={() => { localStorage.removeItem("rezume.token"); localStorage.removeItem("rezume.email"); window.location.href = "/login"; }}>
                    Log Out of All Devices
                  </button>
                </div>
              </Panel>

              <SaveBtn onClick={() => { saveLS("rezume.settings.security", { enabled: twoFA }); toast.success("Security settings saved"); }} />
            </div>
          )}
        </div>
      </div>
    </DashFrame>
  );
}
