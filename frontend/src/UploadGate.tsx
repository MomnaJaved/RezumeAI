import { Navigate } from "react-router-dom";
import DashFrame from "./DashFrame";
import UploadPage from "./pages/UploadPage";
import { useAuth } from "./auth";

/** Recruiters: DashFrame + full upload tool. Candidates: upload from candidate home (+) or profile. */
export default function UploadGate() {
  const { accountRole } = useAuth();

  if (accountRole === null) {
    return (
      <div className="route-role-loading" role="status" aria-live="polite">
        Loading…
      </div>
    );
  }
  if (accountRole === "candidate") {
    return <Navigate to="/candidate" replace />;
  }
  return (
    <DashFrame>
      <UploadPage variant="recruiter" />
    </DashFrame>
  );
}
