import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchJobs,
  ocrParseResume,
  rankFromDatabase,
  uploadResume,
  type CandidateDto,
  type Job,
  type OcrParsedFields,
} from "../api";
import { useToast } from "../toast";

function isMobileDevice(): boolean {
  return /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

type Step = "capture" | "webcam" | "processing" | "edit" | "saving" | "done";

/** Keep max dimension aligned with server OCR downscale (REZUME_OCR_MAX_SIDE) for faster upload + Tesseract. */
async function compressImage(file: File, maxDim = 1600, quality = 0.88): Promise<File> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const { width, height } = img;
      let w = width;
      let h = height;
      if (w > maxDim || h > maxDim) {
        const ratio = Math.min(maxDim / w, maxDim / h);
        w = Math.round(w * ratio);
        h = Math.round(h * ratio);
      }
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0, w, h);
      canvas.toBlob(
        (blob) => {
          if (!blob) { resolve(file); return; }
          const compressed = new File([blob], file.name.replace(/\.[^.]+$/, ".jpg"), {
            type: "image/jpeg",
          });
          resolve(compressed.size < file.size ? compressed : file);
        },
        "image/jpeg",
        quality,
      );
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
}

export default function ScanResumePage() {
  const toast = useToast();
  const isMobile = isMobileDevice();

  const [step, setStep] = useState<Step>("capture");
  const [capturedFile, setCapturedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [ocr, setOcr] = useState<OcrParsedFields | null>(null);
  const [fields, setFields] = useState<OcrParsedFields>({
    full_name: "",
    contact_email: "",
    title: "",
    role_label: "",
    skills: "",
    years_experience: null,
    highest_degree: "",
    education_lines: "",
    certifications: "",
  });
  const [savedCandidate, setSavedCandidate] = useState<CandidateDto | null>(null);

  // Webcam state
  const [webcamError, setWebcamError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");
  const [rankLoading, setRankLoading] = useState(false);
  const [rankPreview, setRankPreview] = useState<
    Array<{ rank_position: number; candidate_external_id: string; candidate_name: string; cross_encoder_score: number }>
  >([]);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null); // mobile capture="environment"

  useEffect(() => {
    fetchJobs()
      .then((list) => { setJobs(list); setJobId(list[0]?.external_id ?? ""); })
      .catch(() => setJobs([]));
  }, []);

  // Revoke blob URL when it changes
  useEffect(() => {
    return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); };
  }, [previewUrl]);

  // Stop webcam stream when leaving webcam step
  const stopWebcam = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (step !== "webcam") stopWebcam();
  }, [step, stopWebcam]);

  // Start the webcam
  const startWebcam = useCallback(async () => {
    setWebcamError(null);
    setStep("webcam");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
    } catch (err) {
      const msg = (err as Error).message || String(err);
      setWebcamError(
        msg.includes("Permission")
          ? "Camera permission denied. Please allow camera access in your browser and try again."
          : `Could not open camera: ${msg}`,
      );
    }
  }, []);

  // Snapshot from webcam → run OCR
  const snapWebcam = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);

    stopWebcam();

    canvas.toBlob(async (blob) => {
      if (!blob) { toast.error("Snapshot failed."); setStep("capture"); return; }
      const file = new File([blob], `webcam-scan-${Date.now()}.jpg`, { type: "image/jpeg" });
      await runOcr(file);
    }, "image/jpeg", 0.92);
  }, [stopWebcam, toast]); // eslint-disable-line react-hooks/exhaustive-deps

  // Shared OCR runner (used by file input AND webcam snap)
  const runOcr = useCallback(async (rawFile: File) => {
    const compressed = await compressImage(rawFile);
    setCapturedFile(compressed);
    setPreviewUrl(URL.createObjectURL(compressed));
    setOcr(null);
    setFields({
      full_name: "", contact_email: "", title: "", role_label: "",
      skills: "", years_experience: null, highest_degree: "",
      education_lines: "", certifications: "",
    });
    setSavedCandidate(null);
    setRankPreview([]);
    setStep("processing");

    try {
      const result = await ocrParseResume(compressed);
      setOcr(result.parsed_fields);
      setFields(result.parsed_fields);
      setStep("edit");
    } catch (err) {
      toast.error(`OCR failed: ${(err as Error).message}`);
      setStep("capture");
    }
  }, [toast]);

  const handleFileInput = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    await runOcr(file);
  }, [runOcr]);

  const retake = useCallback(() => {
    stopWebcam();
    setCapturedFile(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setStep("capture");
  }, [previewUrl, stopWebcam]);

  const saveCandidate = useCallback(async (andMatch: boolean) => {
    if (!capturedFile) return;
    setStep("saving");
    try {
      const res = await uploadResume(capturedFile);
      setSavedCandidate(res.candidate);
      toast.success(res.status === "created" ? "Candidate created in the database." : "Existing candidate updated.");

      if (andMatch && jobId) {
        setRankLoading(true);
        try {
          const rankRes = await rankFromDatabase(jobId, { limit: 800, topReturn: 50, persist: true });
          setRankPreview(rankRes.rankings.map((row) => ({
            rank_position: row.rank_position,
            candidate_external_id: row.candidate_external_id,
            candidate_name: row.candidate_name,
            cross_encoder_score: row.cross_encoder_score,
          })));
          toast.success(`Saved ranking for job ${rankRes.job_external_id}.`);
        } catch (e) {
          toast.error(`Match failed: ${(e as Error).message}`);
        } finally {
          setRankLoading(false);
        }
      }
      setStep("done");
    } catch (err) {
      toast.error(`Save failed: ${(err as Error).message}`);
      setStep("edit");
    }
  }, [capturedFile, toast, jobId]);

  const field = <K extends keyof OcrParsedFields>(key: K) => ({
    value: fields[key] ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const raw = e.target.value;
      setFields((prev) => ({
        ...prev,
        [key]: key === "years_experience" ? (raw === "" ? null : parseFloat(raw) || null) : raw,
      }));
    },
  });

  return (
    <div className="scan-page dash-upload-page">
      <h1 className="dash-title scan-page-title">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: "middle", marginRight: "0.4rem" }}>
          <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
          <circle cx="12" cy="13" r="4" />
        </svg>
        Scan Resume
      </h1>

      <p className="muted scan-lead">
        Capture a printed resume with your camera or upload an image. OCR extracts the fields — review and correct before saving.
      </p>

      {/* ── Step: capture ────────────────────────────────────────────── */}
      {step === "capture" && (
        <div className="scan-capture-area">
          {isMobile ? (
            /* Mobile: rear camera button + gallery button */
            <div className="scan-mobile-btns">
              <button type="button" className="scan-big-btn" onClick={() => cameraInputRef.current?.click()}>
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
                <span>Take photo with camera</span>
                <small className="muted">Uses your phone's rear camera</small>
              </button>

              <button type="button" className="scan-big-btn scan-big-btn--secondary" onClick={() => fileInputRef.current?.click()}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <polyline points="21 15 16 10 5 21" />
                </svg>
                <span>Choose from gallery</span>
                <small className="muted">Pick an existing photo</small>
              </button>

              <input ref={cameraInputRef} type="file" accept="image/*" capture="environment"
                className="scan-hidden-input" onChange={handleFileInput} />
            </div>
          ) : (
            /* Desktop/laptop: live webcam + file upload */
            <div className="scan-desktop-btns">
              <button type="button" className="scan-big-btn" onClick={() => void startWebcam()}>
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
                <span>Use laptop camera</span>
                <small className="muted">Live webcam — hold resume in front of camera</small>
              </button>

              <button type="button" className="scan-big-btn scan-big-btn--secondary" onClick={() => fileInputRef.current?.click()}>
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <span>Upload image file</span>
                <small className="muted">PNG, JPEG, WebP, TIFF</small>
              </button>
            </div>
          )}

          {/* Shared file input (no capture attribute — works on both platforms) */}
          <input ref={fileInputRef} type="file" accept="image/*"
            className="scan-hidden-input" onChange={handleFileInput} />

          <p className="muted scan-hint">
            For best results: good lighting, flat surface, full resume page in frame.
          </p>
        </div>
      )}

      {/* ── Step: webcam (desktop live view) ────────────────────────── */}
      {step === "webcam" && (
        <div className="scan-webcam-wrap">
          {webcamError ? (
            <div className="scan-warn" style={{ maxWidth: "30rem" }}>
              <strong>Camera error:</strong> {webcamError}
              <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem" }}>
                <button type="button" className="primary" onClick={() => void startWebcam()}>Try again</button>
                <button type="button" onClick={retake}>Go back</button>
              </div>
            </div>
          ) : (
            <>
              <div className="scan-video-container">
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  className="scan-video"
                  onCanPlay={() => videoRef.current?.play()}
                />
                <div className="scan-video-overlay">
                  <div className="scan-video-guide">
                    <span>Align resume within this area</span>
                  </div>
                </div>
              </div>

              <div className="scan-webcam-controls">
                <button type="button" className="scan-snap-btn" onClick={() => void snapWebcam()}>
                  <span className="scan-snap-ring" />
                </button>
                <p className="muted" style={{ fontSize: "0.82rem", marginTop: "0.5rem" }}>
                  Click the button to capture
                </p>
                <button type="button" className="linkish scan-webcam-cancel" onClick={retake}>
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Step: processing ─────────────────────────────────────────── */}
      {step === "processing" && (
        <div className="scan-processing">
          {previewUrl && <img src={previewUrl} alt="Captured resume" className="scan-preview-img" />}
          <div className="scan-spinner-wrap">
            <div className="scan-spinner" />
            <p>Extracting text with OCR…<br /><span className="muted">Usually a few seconds; complex photos may take longer</span></p>
          </div>
        </div>
      )}

      {/* ── Step: edit ───────────────────────────────────────────────── */}
      {(step === "edit" || step === "saving") && capturedFile && (
        <div className="scan-edit-layout">
          <div className="scan-preview-col">
            {previewUrl && (
              <>
                <img src={previewUrl} alt="Captured resume" className="scan-preview-img" />
                <button type="button" className="scan-retake-btn" onClick={retake} disabled={step === "saving"}>
                  ↺ Retake
                </button>
              </>
            )}
          </div>

          <div className="scan-fields-col">
            <div className="card" style={{ marginBottom: "1rem" }}>
              <h2 style={{ marginTop: 0, fontSize: "1rem" }}>Extracted fields — review &amp; correct</h2>
              {ocr && !ocr.full_name && !ocr.title && !ocr.skills && (
                <p className="scan-warn">
                  OCR extracted little data. Ensure the image is clear and in focus. You can fill fields manually.
                </p>
              )}
              <div className="scan-field-group">
                <label>Full name</label>
                <input type="text" placeholder="e.g. Jane Smith" {...field("full_name")} />
              </div>
              <div className="scan-field-group">
                <label>Email</label>
                <input type="email" placeholder="e.g. jane@example.com" {...field("contact_email")} />
              </div>
              <div className="scan-field-group">
                <label>Title / Headline</label>
                <input type="text" placeholder="e.g. Senior Frontend Developer" {...field("title")} />
              </div>
              <div className="scan-field-group">
                <label>Role label</label>
                <input type="text" placeholder="e.g. frontend" {...field("role_label")} />
              </div>
              <div className="scan-field-group">
                <label>Skills</label>
                <textarea rows={3} placeholder="e.g. React, TypeScript, Node.js" {...field("skills")} />
              </div>
              <div className="scan-field-group">
                <label>Years of experience</label>
                <input type="number" min={0} max={60} step={0.5} placeholder="e.g. 3"
                  value={fields.years_experience ?? ""} onChange={field("years_experience").onChange} />
              </div>
              <div className="scan-field-group">
                <label>Highest degree</label>
                <input type="text" placeholder="e.g. Bachelor of Computer Science" {...field("highest_degree")} />
              </div>
              <div className="scan-field-group">
                <label>Education details</label>
                <textarea rows={2} placeholder="e.g. BSc CS — MIT 2018" {...field("education_lines")} />
              </div>
              <div className="scan-field-group">
                <label>Certifications</label>
                <textarea rows={2} placeholder="e.g. AWS Solutions Architect" {...field("certifications")} />
              </div>
            </div>

            <div className="card">
              <h2 style={{ marginTop: 0, fontSize: "1rem" }}>Save to candidate pool</h2>
              {jobs.length > 0 && (
                <div className="scan-field-group">
                  <label htmlFor="scan-job-select">Match against job (optional)</label>
                  <select id="scan-job-select" value={jobId}
                    onChange={(e) => setJobId(e.target.value)} disabled={step === "saving"}>
                    <option value="">— no matching —</option>
                    {jobs.map((j) => (
                      <option key={j.id} value={j.external_id}>
                        {j.external_id} — {j.title || "untitled"}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
                <button type="button" className="primary" disabled={step === "saving"}
                  onClick={() => void saveCandidate(false)}>
                  {step === "saving" ? "Saving…" : "Save candidate"}
                </button>
                {jobs.length > 0 && jobId && (
                  <button type="button" disabled={step === "saving"}
                    onClick={() => void saveCandidate(true)}>
                    {step === "saving" ? "Saving…" : "Save & Match"}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Step: done ───────────────────────────────────────────────── */}
      {step === "done" && savedCandidate && (
        <div className="scan-done">
          <div className="scan-success-banner">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
              strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6L9 17l-5-5" />
            </svg>
            <span>Candidate saved successfully</span>
          </div>

          <div className="card" style={{ marginTop: "1rem" }}>
            <dl className="field-grid">
              <dt>Name</dt><dd>{savedCandidate.full_name || "—"}</dd>
              <dt>Title</dt><dd>{savedCandidate.title || "—"}</dd>
              <dt>Role</dt><dd>{savedCandidate.role_label || "—"}</dd>
              <dt>Skills</dt><dd className="skills-dd">{savedCandidate.skills || "—"}</dd>
              <dt>Years exp.</dt><dd>{savedCandidate.years_experience ?? "—"}</dd>
              <dt>Degree</dt><dd>{savedCandidate.highest_degree || "—"}</dd>
            </dl>
            <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap", marginTop: "1rem" }}>
              <button type="button" className="primary"
                onClick={() => {
                  setCapturedFile(null);
                  if (previewUrl) URL.revokeObjectURL(previewUrl);
                  setPreviewUrl(null);
                  setSavedCandidate(null);
                  setRankPreview([]);
                  setStep("capture");
                }}>
                Scan another resume
              </button>
              <Link to={`/candidates/${savedCandidate.id}`} className="linkish">
                View profile
              </Link>
              <Link to="/candidates" className="linkish">
                All candidates
              </Link>
            </div>
          </div>

          {rankLoading && <p className="muted" style={{ marginTop: "1rem" }}>Running match ranking…</p>}
          {rankPreview.length > 0 && (
            <div className="card" style={{ marginTop: "1rem" }}>
              <h3 style={{ marginTop: 0 }}>Ranking preview (top {rankPreview.length})</h3>
              <div style={{ overflowX: "auto" }}>
                <table>
                  <thead><tr><th>#</th><th>Name</th><th>Score</th></tr></thead>
                  <tbody>
                    {rankPreview.map((row) => (
                      <tr key={row.candidate_external_id}
                        style={savedCandidate && row.candidate_external_id === savedCandidate.external_id
                          ? { background: "#eff6ff" } : undefined}>
                        <td>{row.rank_position}</td>
                        <td>{row.candidate_name || "—"}</td>
                        <td>{row.cross_encoder_score.toFixed(4)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
