import { useEffect } from "react";
import { Link, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { applyAppSettings } from "./settings";
import HomePage from "./pages/HomePage";
import JobsPage from "./pages/JobsPage";
import JobDetailPage from "./pages/JobDetailPage";
import AddJobPage from "./pages/AddJobPage";
import PlaygroundPage from "./pages/PlaygroundPage";
import IngestPage from "./pages/IngestPage";
import UploadGate from "./UploadGate";
import CandidatesPage from "./pages/CandidatesPage";
import CandidatesComparePage from "./pages/CandidatesComparePage";
import CandidateDetailPage from "./pages/CandidateDetailPage";
import CandidateLookupPage from "./pages/CandidateLookupPage";
import ReportsPage from "./pages/ReportsPage";
import SettingsPage from "./pages/SettingsPage";
import LoginPage from "./pages/LoginPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import VerifyEmailPage from "./pages/VerifyEmailPage";
import InboxPage from "./pages/InboxPage";
import ClientsPage from "./pages/ClientsPage";
import ClientDetailPage from "./pages/ClientDetailPage";
import AddClientPage from "./pages/AddClientPage";
import MatchingPage from "./pages/MatchingPage";
import CandidateDashboardPage from "./pages/candidate/CandidateDashboardPage";
import CandidateJobsPage from "./pages/candidate/CandidateJobsPage";
import CandidateApplicationsPage from "./pages/candidate/CandidateApplicationsPage";
import CandidateProfilePage from "./pages/candidate/CandidateProfilePage";
import CandidateResumePage from "./pages/candidate/CandidateResumePage";
import CandidateFrame from "./CandidateFrame";
import ScanGate from "./ScanGate";
import RequireAuth from "./RequireAuth";
import RequireRecruiter from "./RequireRecruiter";
import RequireCandidate from "./RequireCandidate";
import { useAuth } from "./auth";

export default function App() {
  const loc = useLocation();

  // Apply persisted theme + font-size on every navigation and on first load
  useEffect(() => {
    applyAppSettings();
  }, [loc.pathname]);
  const isHome = loc.pathname === "/";
  const isAuthMarketing =
    loc.pathname === "/login" ||
    loc.pathname === "/register" ||
    loc.pathname === "/forgot-password" ||
    loc.pathname === "/verify-email";
  const isDashRoute =
    loc.pathname.startsWith("/dashboard") ||
    loc.pathname.startsWith("/candidates") ||
    loc.pathname.startsWith("/clients") ||
    loc.pathname.startsWith("/jobs") ||
    loc.pathname.startsWith("/reports") ||
    loc.pathname.startsWith("/settings") ||
    loc.pathname.startsWith("/inbox") ||
    loc.pathname.startsWith("/matching") ||
    loc.pathname.startsWith("/candidate") ||
    loc.pathname.startsWith("/upload") ||
    loc.pathname.startsWith("/scan");
  const isFullBleed = isHome || isAuthMarketing || isDashRoute;
  const usesDashChrome =
    loc.pathname.startsWith("/dashboard") ||
    loc.pathname.startsWith("/candidates") ||
    loc.pathname.startsWith("/clients") ||
    loc.pathname.startsWith("/jobs") ||
    loc.pathname.startsWith("/reports") ||
    loc.pathname.startsWith("/settings") ||
    loc.pathname.startsWith("/inbox") ||
    loc.pathname.startsWith("/matching") ||
    loc.pathname.startsWith("/candidate") ||
    loc.pathname.startsWith("/upload") ||
    loc.pathname.startsWith("/scan");
  const { token, email, logout, accountRole } = useAuth();

  const hideAppHeader = isHome || isAuthMarketing || usesDashChrome;

  return (
    <div className={isHome || isAuthMarketing ? "app-shell app-shell-home" : "app-shell"}>
      {hideAppHeader ? null : (
        <header className="app-header">
          <strong>Rezume AI</strong>
          <nav>
            <Link to="/">Home</Link>
            {token ? (
              accountRole === "candidate" ? (
                <>
                  <Link to="/candidate">Home</Link>
                  <Link to="/candidate/jobs">Jobs</Link>
                  <Link to="/candidate/applications">Applications</Link>
                  <Link to="/candidate/resume">Resume</Link>
                  <Link to="/candidate/profile">Profile</Link>
                  <span className="muted" style={{ marginLeft: "0.5rem" }}>
                    {email ?? "signed in"}
                  </span>
                  <button type="button" className="small-btn" onClick={() => logout()}>
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <Link to="/dashboard">Dashboard</Link>
                  <Link to="/jobs">Jobs</Link>
                  <Link to="/playground">Playground</Link>
                  <Link to="/upload">Upload resume</Link>
                  <Link to="/scan">Scan resume</Link>
                  <Link to="/candidates/add">Add candidate</Link>
                  <span className="muted" style={{ marginLeft: "0.5rem" }}>
                    {email ?? "signed in"}
                  </span>
                  <button type="button" className="small-btn" onClick={() => logout()}>
                    Logout
                  </button>
                </>
              )
            ) : (
              <>
                <Link to="/login">Login</Link>
                <Link to="/register">Register</Link>
              </>
            )}
          </nav>
        </header>
      )}
      <main className={isFullBleed ? "" : "layout"}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route
            path="/dashboard"
            element={
              <RequireRecruiter>
                <DashboardPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/jobs"
            element={
              <RequireRecruiter>
                <JobsPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/jobs/add"
            element={
              <RequireRecruiter>
                <AddJobPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/candidates/add"
            element={
              <RequireRecruiter>
                <IngestPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/candidates/lookup/:externalId"
            element={
              <RequireRecruiter>
                <CandidateLookupPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/candidates/compare"
            element={
              <RequireRecruiter>
                <CandidatesComparePage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/candidates/:candidateId"
            element={
              <RequireRecruiter>
                <CandidateDetailPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/candidates"
            element={
              <RequireRecruiter>
                <CandidatesPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/clients"
            element={
              <RequireRecruiter>
                <ClientsPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/clients/add"
            element={
              <RequireRecruiter>
                <AddClientPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/clients/:clientId"
            element={
              <RequireRecruiter>
                <ClientDetailPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/reports"
            element={
              <RequireRecruiter>
                <ReportsPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/settings"
            element={
              <RequireRecruiter>
                <SettingsPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/inbox"
            element={
              <RequireRecruiter>
                <InboxPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/matching"
            element={
              <RequireRecruiter>
                <MatchingPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/jobs/:externalId"
            element={
              <RequireRecruiter>
                <JobDetailPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/playground"
            element={
              <RequireRecruiter>
                <PlaygroundPage />
              </RequireRecruiter>
            }
          />
          <Route
            path="/candidate"
            element={
              <RequireCandidate>
                <CandidateFrame>
                  <Outlet />
                </CandidateFrame>
              </RequireCandidate>
            }
          >
            <Route index element={<CandidateDashboardPage />} />
            <Route path="jobs" element={<CandidateJobsPage />} />
            <Route path="applications" element={<CandidateApplicationsPage />} />
            <Route path="profile" element={<CandidateProfilePage />} />
            <Route path="resume" element={<CandidateResumePage />} />
          </Route>
          <Route
            path="/upload"
            element={
              <RequireAuth>
                <UploadGate />
              </RequireAuth>
            }
          />
          <Route
            path="/scan"
            element={
              <RequireAuth>
                <ScanGate />
              </RequireAuth>
            }
          />
          <Route
            path="/ingest"
            element={
              <RequireAuth>
                <Navigate to="/candidates/add" replace />
              </RequireAuth>
            }
          />
        </Routes>
      </main>
    </div>
  );
}
