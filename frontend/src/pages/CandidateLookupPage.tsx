import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DashFrame from "../DashFrame";
import { fetchCandidateByExternalId } from "../api";
import { useToast } from "../toast";

/**
 * Resolves stable resume / upload external_id to the UUID used in /candidates/:id routes.
 */
export default function CandidateLookupPage() {
  const { externalId } = useParams<{ externalId: string }>();
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    const ext = (externalId || "").trim();
    if (!ext) {
      navigate("/candidates", { replace: true });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const c = await fetchCandidateByExternalId(ext);
        if (!cancelled) navigate(`/candidates/${c.id}`, { replace: true });
      } catch (e) {
        if (!cancelled) {
          toast.error((e as Error).message || "Candidate not found");
          navigate("/candidates", { replace: true });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [externalId, navigate, toast]);

  return (
    <DashFrame>
      <p className="muted" style={{ margin: "1rem 0" }}>
        Opening candidate…
      </p>
    </DashFrame>
  );
}
