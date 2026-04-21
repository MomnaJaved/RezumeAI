import { Navigate } from "react-router-dom";
import DashFrame from "./DashFrame";
import ScanResumePage from "./pages/ScanResumePage";
import { useAuth } from "./auth";

/** Recruiters: DashFrame + OCR scan. Candidates: resume lives under /candidate/resume. */
export default function ScanGate() {
  const { accountRole } = useAuth();

  if (accountRole === null) {
    return (
      <div className="route-role-loading" role="status" aria-live="polite">
        Loading…
      </div>
    );
  }
  if (accountRole === "candidate") {
    return <Navigate to="/candidate/resume" replace />;
  }
  return (
    <DashFrame>
      <ScanResumePage />
    </DashFrame>
  );
}
