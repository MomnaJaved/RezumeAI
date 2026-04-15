import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import HomePage from "./pages/HomePage";
import JobsPage from "./pages/JobsPage";
import JobDetailPage from "./pages/JobDetailPage";
import AddJobPage from "./pages/AddJobPage";
import PlaygroundPage from "./pages/PlaygroundPage";
import IngestPage from "./pages/IngestPage";
import UploadPage from "./pages/UploadPage";
import CandidatesPage from "./pages/CandidatesPage";
import CandidateDetailPage from "./pages/CandidateDetailPage";
import CandidateLookupPage from "./pages/CandidateLookupPage";
import PlaceholderPage from "./pages/PlaceholderPage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import DashboardPage from "./pages/DashboardPage";
import VerifyEmailPage from "./pages/VerifyEmailPage";
import InboxPage from "./pages/InboxPage";
import ClientsPage from "./pages/ClientsPage";
import ClientDetailPage from "./pages/ClientDetailPage";
import AddClientPage from "./pages/AddClientPage";
import MatchingPage from "./pages/MatchingPage";
import RequireAuth from "./RequireAuth";
import { useAuth } from "./auth";

export default function App() {
  const loc = useLocation();
  const isHome = loc.pathname === "/";
  const isAuthMarketing = loc.pathname === "/login" || loc.pathname === "/register";
  const isDashRoute =
    loc.pathname.startsWith("/dashboard") ||
    loc.pathname.startsWith("/candidates") ||
    loc.pathname.startsWith("/clients") ||
    loc.pathname.startsWith("/jobs") ||
    loc.pathname.startsWith("/reports") ||
    loc.pathname.startsWith("/settings") ||
    loc.pathname.startsWith("/inbox") ||
    loc.pathname.startsWith("/matching");
  const isFullBleed = isHome || isAuthMarketing || isDashRoute;
  const usesDashChrome =
    loc.pathname.startsWith("/dashboard") ||
    loc.pathname.startsWith("/candidates") ||
    loc.pathname.startsWith("/clients") ||
    loc.pathname.startsWith("/jobs") ||
    loc.pathname.startsWith("/inbox") ||
    loc.pathname.startsWith("/matching");
  const { token, email, logout } = useAuth();

  const hideAppHeader = isHome || isAuthMarketing || usesDashChrome;

  return (
    <div className={isHome || isAuthMarketing ? "app-shell app-shell-home" : "app-shell"}>
      {hideAppHeader ? null : (
        <header className="app-header">
          <strong>Rezume AI</strong>
          <nav>
            <Link to="/">Home</Link>
            {token ? (
              <>
                <Link to="/dashboard">Dashboard</Link>
                <Link to="/jobs">Jobs</Link>
                <Link to="/playground">Playground</Link>
                <Link to="/upload">Upload resume</Link>
                <Link to="/candidates/add">Add candidate</Link>
                <span className="muted" style={{ marginLeft: "0.5rem" }}>
                  {email ?? "signed in"}
                </span>
                <button type="button" className="small-btn" onClick={() => logout()}>
                  Logout
                </button>
              </>
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
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route
            path="/dashboard"
            element={
              <RequireAuth>
                <DashboardPage />
              </RequireAuth>
            }
          />
          <Route
            path="/jobs"
            element={
              <RequireAuth>
                <JobsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/jobs/add"
            element={
              <RequireAuth>
                <AddJobPage />
              </RequireAuth>
            }
          />
          <Route
            path="/candidates/add"
            element={
              <RequireAuth>
                <IngestPage />
              </RequireAuth>
            }
          />
          <Route
            path="/candidates/lookup/:externalId"
            element={
              <RequireAuth>
                <CandidateLookupPage />
              </RequireAuth>
            }
          />
          <Route
            path="/candidates/:candidateId"
            element={
              <RequireAuth>
                <CandidateDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/candidates"
            element={
              <RequireAuth>
                <CandidatesPage />
              </RequireAuth>
            }
          />
          <Route
            path="/clients"
            element={
              <RequireAuth>
                <ClientsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/clients/add"
            element={
              <RequireAuth>
                <AddClientPage />
              </RequireAuth>
            }
          />
          <Route
            path="/clients/:clientId"
            element={
              <RequireAuth>
                <ClientDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/reports"
            element={
              <RequireAuth>
                <PlaceholderPage title="Reports" note="Reports dashboard is coming next. (We can add match reports, bias/fairness checks, and exports.)" />
              </RequireAuth>
            }
          />
          <Route
            path="/settings"
            element={
              <RequireAuth>
                <PlaceholderPage title="Settings" note="Settings page coming next (profile, auth, and API keys)." />
              </RequireAuth>
            }
          />
          <Route
            path="/inbox"
            element={
              <RequireAuth>
                <InboxPage />
              </RequireAuth>
            }
          />
          <Route
            path="/matching"
            element={
              <RequireAuth>
                <MatchingPage />
              </RequireAuth>
            }
          />
          <Route
            path="/jobs/:externalId"
            element={
              <RequireAuth>
                <JobDetailPage />
              </RequireAuth>
            }
          />
          <Route
            path="/playground"
            element={
              <RequireAuth>
                <PlaygroundPage />
              </RequireAuth>
            }
          />
          <Route
            path="/upload"
            element={
              <RequireAuth>
                <UploadPage />
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
