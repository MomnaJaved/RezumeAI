import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { healthCheck } from "../api";
import LandingPlexusBackdrop from "../LandingPlexusBackdrop";

function IconUploadResumes() {
  return (
    <svg className="landing-how-icon" viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M18 14h20l8 8v30H18V14z" strokeLinejoin="round" />
      <path d="M38 14v8h8" strokeLinejoin="round" />
      <circle cx="32" cy="36" r="7" />
      <path d="M26 46c2-4 6-6 12-6s10 2 12 6" strokeLinecap="round" />
    </svg>
  );
}

function IconAiScreening() {
  return (
    <svg className="landing-how-icon" viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path
        d="M32 12c-8 0-14 6-14 14 0 7 5 13 12 14v6h4v-6c7-1 12-7 12-14 0-8-6-14-14-14z"
        strokeLinejoin="round"
      />
      <path d="M22 28h4M38 28h4M28 34h8" strokeLinecap="round" />
      <path d="M14 52h36" strokeLinecap="round" />
      <path d="M48 20l6-4M48 28l6 2M48 36l6 0" strokeLinecap="round" opacity="0.85" />
    </svg>
  );
}

function IconRankHire() {
  return (
    <svg className="landing-how-icon" viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
      <path d="M14 48V22h8v26M26 48V30h8v18M38 48V18h8v30" strokeLinejoin="round" strokeLinecap="round" />
      <path d="M44 14l6-4 4 8" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="50" cy="38" r="10" />
      <path d="M47 38h6M50 35v6" strokeLinecap="round" />
    </svg>
  );
}

function IconSavesTime() {
  return (
    <svg className="landing-why-icon" viewBox="0 0 56 56" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <circle cx="28" cy="30" r="12" />
      <path d="M28 22v9l5 3" strokeLinecap="round" />
      <path d="M12 18l3 2M44 18l-3 2M10 30h3M43 30h3" strokeLinecap="round" opacity="0.7" />
    </svg>
  );
}

function IconSmartMatching() {
  return (
    <svg className="landing-why-icon" viewBox="0 0 56 56" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <path d="M18 20h20a4 4 0 014 4v14H14V24a4 4 0 014-4z" strokeLinejoin="round" />
      <rect x="22" y="12" width="12" height="8" rx="2" strokeLinejoin="round" />
      <path d="M26 12v-3h4v3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="24" cy="30" r="2.5" />
      <circle cx="32" cy="30" r="2.5" />
      <path d="M24 35c1 2 3 3 4 3s3-1 4-3" strokeLinecap="round" />
      <path d="M16 24h-3M43 24h3" strokeLinecap="round" opacity="0.75" />
    </svg>
  );
}

function IconMultiPlatform() {
  return (
    <svg className="landing-why-icon" viewBox="0 0 56 56" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <path d="M12 38h32v6H12v-6z" strokeLinejoin="round" />
      <path d="M16 26h24v10H16V26z" strokeLinejoin="round" />
      <path d="M20 16h16v8H20V16z" strokeLinejoin="round" />
    </svg>
  );
}

function IconAccurateRankings() {
  return (
    <svg className="landing-why-icon" viewBox="0 0 56 56" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <circle cx="28" cy="28" r="14" />
      <circle cx="28" cy="28" r="6" />
      <path d="M28 14v4M38 22l-3 3M40 28h-4" strokeLinecap="round" />
      <path d="M36 18l6-6" strokeLinecap="round" />
    </svg>
  );
}

function IconBiasFree() {
  return (
    <svg className="landing-why-icon" viewBox="0 0 56 56" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <path d="M28 12v32" strokeLinecap="round" />
      <path d="M12 26h32" strokeLinecap="round" />
      <path d="M16 26l6-8h12l6 8" strokeLinejoin="round" />
      <circle cx="19" cy="34" r="3.5" />
      <path d="M19 31v-2" strokeLinecap="round" />
      <circle cx="37" cy="34" r="3.5" />
      <path d="M37 31v-2" strokeLinecap="round" />
    </svg>
  );
}

const WHY_ITEMS = [
  { title: "Saves Time", Icon: IconSavesTime, blurb: "Automate first-pass review so you focus on finalists." },
  { title: "Smart Matching", Icon: IconSmartMatching, blurb: "Semantic understanding beyond keyword overlap." },
  { title: "Multi-Platform Access", Icon: IconMultiPlatform, blurb: "Web uploads, bulk résumé import, and extension-ready flows." },
  { title: "Accurate Rankings", Icon: IconAccurateRankings, blurb: "Embeddings plus reranking for hiring-style scores." },
  { title: "Bias-free Scoring", Icon: IconBiasFree, blurb: "Designed for fair, explainable candidate signals." },
] as const;

export default function HomePage() {
  const [status, setStatus] = useState<string>("checking…");
  const [err, setErr] = useState<string | null>(null);

  const apiOk = useMemo(() => status === "ok", [status]);
  const whyMarqueeItems = useMemo(() => [...WHY_ITEMS, ...WHY_ITEMS], []);

  useEffect(() => {
    healthCheck()
      .then((r) => setStatus(r.status))
      .catch((e: Error) => {
        setErr(e.message);
        setStatus("unreachable");
      });
  }, []);

  return (
    <div className="landing">
      <header className="landing-topbar">
        <a href="#home" className="landing-brand">
          <span className="landing-logo" aria-hidden="true" />
          <span className="landing-name">Rezume AI</span>
        </a>
        <nav className="landing-nav" aria-label="Primary">
          <a href="#home">Home</a>
          <a href="#about">About Us</a>
          <a href="#features">Features</a>
          <a href="#how">How It Works</a>
          <a href="#why">Why Choose Us</a>
          <Link to="/login" className="landing-nav-link-external">
            Login
          </Link>
        </nav>
      </header>

      <section className="landing-hero" id="home">
        <div className="landing-hero-inner">
          <div className="landing-copy">
            <h1>Hire Smart. Hire Fast.</h1>
            <p className="landing-subtitle">AI that finds the perfect fit.</p>

            <div className="landing-cta-row">
              <Link to="/jobs" className="btn btn-primary">
                Get Started
              </Link>
              <a href="#how" className="btn btn-ghost">
                Watch Demo
              </a>
            </div>

            <p className="landing-health">
              API health:{" "}
              <strong className={apiOk ? "ok" : "bad"}>{status}</strong>
              {err ? <span className="bad"> — {err}</span> : null}
            </p>
          </div>
        </div>
      </section>

      <div className="landing-body-cluster">
        <LandingPlexusBackdrop />
        <section className="landing-tech-section landing-about-wrap" id="about">
          <div className="landing-tech-inner">
            <header className="landing-about-header">
              <h2 className="landing-about-title">About Us</h2>
            </header>
            <div className="landing-about-center">
              <div className="landing-about-glass">
                <p className="landing-about-copy">
                  At Rezume AI, we make hiring easier and smarter. Our AI helps you quickly find the right candidates by
                  reviewing resumes, highlighting top talent, and giving insights that save time. We believe in making
                  recruitment simple, fair, and stress-free for both companies and candidates.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-tech-section" id="how">
          <div className="landing-tech-inner">
            <h2 className="landing-section-title landing-section-title-fade">How Rezume Works</h2>
            <div className="landing-how-grid">
              <article className="landing-how-card">
                <div className="landing-how-icon-wrap">
                  <IconUploadResumes />
                </div>
                <h3>Upload Resumes</h3>
                <p>Upload or scan multiple resumes in one click.</p>
              </article>
              <article className="landing-how-card">
                <div className="landing-how-icon-wrap">
                  <IconAiScreening />
                </div>
                <h3>AI Screening</h3>
                <p>NLP and ML match candidates to your job description.</p>
              </article>
              <article className="landing-how-card">
                <div className="landing-how-icon-wrap">
                  <IconRankHire />
                </div>
                <h3>Rank &amp; Hire</h3>
                <p>View top candidates instantly. Faster, fairer, smarter.</p>
              </article>
            </div>
          </div>
        </section>

        <section className="landing-tech-section landing-why-section" id="why">
          <div className="landing-tech-inner">
            <h2 className="landing-section-title landing-section-title-fade">Why Choose Us</h2>
            <div
              className="landing-why-marquee-wrap"
              role="region"
              aria-label="Why choose Rezume AI — continuously scrolling highlights"
            >
              <div className="landing-why-marquee-track">
                {whyMarqueeItems.map(({ title, Icon, blurb }, i) => (
                  <article key={`${title}-${i}`} className="landing-why-card">
                    <div className="landing-why-icon-wrap">
                      <Icon />
                    </div>
                    <h3>{title}</h3>
                    <p>{blurb}</p>
                  </article>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="landing-tech-section landing-features-on-dark" id="features">
          <div className="landing-tech-inner">
            <h2 className="landing-section-title landing-section-title-fade">Features</h2>
            <div className="landing-how-grid">
              <div className="landing-how-card">
                <h3 className="landing-feature-card-title">Printed résumé capture (OCR)</h3>
                <p>
                  Photograph hard-copy CVs; new candidates are added to your pool automatically, with no manual re-entry.
                </p>
              </div>
              <div className="landing-how-card">
                <h3 className="landing-feature-card-title">In-browser import (Chrome)</h3>
                <p>
                  Import profile or résumé text from the web, then evaluate fit to your open requisitions in the same
                  workflow.
                </p>
              </div>
              <div className="landing-how-card">
                <h3 className="landing-feature-card-title">Full-pool job matching &amp; shortlists</h3>
                <p>
                  Run fit scoring across your entire candidate database, review ranked results, and save shortlists your
                  team can use as a single source of truth.
                </p>
              </div>
            </div>
          </div>
        </section>
      </div>

      <footer className="landing-footer landing-footer-dark">
        <div className="landing-section-inner">
          <span className="landing-muted">© {new Date().getFullYear()} Rezume AI</span>
        </div>
      </footer>
    </div>
  );
}
