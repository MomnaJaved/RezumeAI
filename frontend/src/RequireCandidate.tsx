import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./auth";

/** Candidate-only routes (job discovery, applications, profile). */
export default function RequireCandidate({ children }: { children: JSX.Element }) {
  const { token, accountRole } = useAuth();
  const loc = useLocation();

  if (!token) {
    return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  }
  if (accountRole === null) {
    return (
      <div className="route-role-loading" role="status" aria-live="polite">
        Loading…
      </div>
    );
  }
  if (accountRole !== "candidate") {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
}
