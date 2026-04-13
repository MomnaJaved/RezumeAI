import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { healthCheck } from "../api";

function PlexusBackdrop() {
  return (
    <div className="landing-plexus" aria-hidden="true">
      <svg className="landing-plexus-svg" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="plexLine" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00f5ff" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.12" />
          </linearGradient>
          <radialGradient id="plexGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#00f5ff" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#00f5ff" stopOpacity="0" />
          </radialGradient>
          <filter id="plexBlur" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="2" result="b" />
          </filter>
        </defs>
        <g opacity="0.85">
          <line x1="80" y1="120" x2="220" y2="200" stroke="url(#plexLine)" strokeWidth="0.8" />
          <line x1="220" y1="200" x2="340" y2="140" stroke="url(#plexLine)" strokeWidth="0.7" />
          <line x1="340" y1="140" x2="480" y2="220" stroke="url(#plexLine)" strokeWidth="0.6" />
          <line x1="480" y1="220" x2="620" y2="160" stroke="url(#plexLine)" strokeWidth="0.7" />
          <line x1="620" y1="160" x2="780" y2="240" stroke="url(#plexLine)" strokeWidth="0.65" />
          <line x1="180" y1="320" x2="320" y2="280" stroke="url(#plexLine)" strokeWidth="0.55" />
          <line x1="320" y1="280" x2="460" y2="360" stroke="url(#plexLine)" strokeWidth="0.6" />
          <line x1="460" y1="360" x2="600" y2="300" stroke="url(#plexLine)" strokeWidth="0.55" />
          <line x1="600" y1="300" x2="760" y2="380" stroke="url(#plexLine)" strokeWidth="0.6" />
          <line x1="760" y1="380" x2="920" y2="320" stroke="url(#plexLine)" strokeWidth="0.5" />
          <line x1="120" y1="480" x2="280" y2="420" stroke="url(#plexLine)" strokeWidth="0.5" />
          <line x1="280" y1="420" x2="440" y2="500" stroke="url(#plexLine)" strokeWidth="0.55" />
          <line x1="440" y1="500" x2="580" y2="440" stroke="url(#plexLine)" strokeWidth="0.5" />
          <line x1="580" y1="440" x2="720" y2="520" stroke="url(#plexLine)" strokeWidth="0.55" />
          <line x1="720" y1="520" x2="900" y2="460" stroke="url(#plexLine)" strokeWidth="0.45" />
          <line x1="200" y1="200" x2="320" y2="280" stroke="url(#plexLine)" strokeWidth="0.4" />
          <line x1="520" y1="100" x2="640" y2="180" stroke="url(#plexLine)" strokeWidth="0.45" />
          <line x1="900" y1="140" x2="1040" y2="220" stroke="url(#plexLine)" strokeWidth="0.4" />
          <line x1="100" y1="600" x2="260" y2="540" stroke="url(#plexLine)" strokeWidth="0.4" />
          <line x1="380" y1="640" x2="540" y2="580" stroke="url(#plexLine)" strokeWidth="0.45" />
          <line x1="800" y1="600" x2="960" y2="660" stroke="url(#plexLine)" strokeWidth="0.4" />
        </g>
        <g fill="#00f5ff">
          <circle cx="80" cy="120" r="2.2" opacity="0.9" />
          <circle cx="220" cy="200" r="2.5" opacity="1" />
          <circle cx="340" cy="140" r="1.8" opacity="0.75" />
          <circle cx="480" cy="220" r="2.8" opacity="0.95" filter="url(#plexBlur)" />
          <circle cx="620" cy="160" r="2" opacity="0.85" />
          <circle cx="780" cy="240" r="2.4" opacity="0.9" />
          <circle cx="920" cy="320" r="1.6" opacity="0.7" />
          <circle cx="180" cy="320" r="1.5" opacity="0.65" />
          <circle cx="320" cy="280" r="2.2" opacity="0.88" />
          <circle cx="460" cy="360" r="2.6" opacity="0.92" filter="url(#plexBlur)" />
          <circle cx="600" cy="300" r="1.7" opacity="0.72" />
          <circle cx="760" cy="380" r="2.1" opacity="0.82" />
          <circle cx="120" cy="480" r="1.4" opacity="0.6" />
          <circle cx="440" cy="500" r="2.3" opacity="0.88" />
          <circle cx="720" cy="520" r="1.9" opacity="0.78" />
          <circle cx="1040" cy="220" r="1.5" opacity="0.55" />
          <circle cx="520" cy="100" r="1.8" opacity="0.7" />
          <circle cx="900" cy="140" r="2" opacity="0.8" />
          <circle cx="260" cy="540" r="2.4" opacity="0.85" filter="url(#plexBlur)" />
          <circle cx="960" cy="660" r="1.6" opacity="0.62" />
        </g>
        <g fill="url(#plexGlow)" opacity="0.25">
          <circle cx="350" cy="250" r="40" />
          <circle cx="850" cy="450" r="55" />
          <circle cx="150" cy="650" r="35" />
        </g>
      </svg>
      <div className="landing-plexus-bokeh" />
    </div>
  );
}

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
  { title: "Multi-Platform Access", Icon: IconMultiPlatform, blurb: "Web uploads, bulk ingest, and extension-ready flows." },
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

      <section className="landing-tech-section landing-about-wrap" id="about">
        <PlexusBackdrop />
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
        <PlexusBackdrop />
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
        <PlexusBackdrop />
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
        <PlexusBackdrop />
        <div className="landing-tech-inner">
          <h2 className="landing-section-title landing-section-title-fade">Features</h2>
          <div className="landing-how-grid">
            <div className="landing-how-card">
              <h3>Resume ingestion</h3>
              <p>Upload PDF/DOCX/TXT or bulk ingest extracted text. PII is stripped before storage.</p>
            </div>
            <div className="landing-how-card">
              <h3>Skills + experience signals</h3>
              <p>Extracts key skills, estimates work experience, and stores structured fields for ranking.</p>
            </div>
            <div className="landing-how-card">
              <h3>Job-to-candidate ranking</h3>
              <p>Shortlist with embeddings then rerank with a cross-encoder for a hiring-style score.</p>
            </div>
          </div>
        </div>
      </section>

      <footer className="landing-footer landing-footer-dark">
        <div className="landing-section-inner">
          <span className="landing-muted">© {new Date().getFullYear()} Rezume AI</span>
        </div>
      </footer>
    </div>
  );
}
