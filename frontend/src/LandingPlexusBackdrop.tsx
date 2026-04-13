/** Shared SVG + bokeh used on the marketing landing and auth pages. */
export default function LandingPlexusBackdrop() {
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
