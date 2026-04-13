import { Link } from "react-router-dom";
import LandingPlexusBackdrop from "./LandingPlexusBackdrop";

type Props = {
  children: React.ReactNode;
  /** Extra links after Home (e.g. Register or Login). */
  navRight: React.ReactNode;
};

export default function AuthMarketingShell({ children, navRight }: Props) {
  return (
    <div className="landing landing-auth-page">
      <header className="landing-topbar">
        <Link to="/" className="landing-brand">
          <span className="landing-logo" aria-hidden="true" />
          <span className="landing-name">Rezume AI</span>
        </Link>
        <nav className="landing-nav" aria-label="Auth">
          <Link to="/">Home</Link>
          {navRight}
        </nav>
      </header>
      <main className="landing-auth-main">
        <div className="landing-auth-cluster">
          <LandingPlexusBackdrop />
          <div className="landing-auth-panel">{children}</div>
        </div>
      </main>
    </div>
  );
}
