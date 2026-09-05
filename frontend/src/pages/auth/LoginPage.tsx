import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { BrandLoader, BrandMark, Button, TextField } from "../../components";
import { useAuth } from "../../hooks/useAuth";
import { extractErrorMessage } from "../../utils/errors";


interface LocationState {
  from?: { pathname: string };
}


export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LocationState | null)?.from?.pathname ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // After a few seconds of a slow (likely cold) backend, reassure rather than
  // spin silently — mirrors the session-restore screen.
  useEffect(() => {
    if (!submitting) {
      setSlow(false);
      return;
    }
    const timer = window.setTimeout(() => setSlow(true), 4000);
    return () => window.clearTimeout(timer);
  }, [submitting]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const startedAt = Date.now();
    try {
      await login({ email, password });
      // Keep the branded loader on screen a beat so it reads as a transition
      // (not a flash) even when auth returns instantly.
      const elapsed = Date.now() - startedAt;
      if (elapsed < 650) {
        await new Promise((resolve) => window.setTimeout(resolve, 650 - elapsed));
      }
      navigate(from, { replace: true });
    } catch (loginError) {
      setError(extractErrorMessage(loginError, "Login failed."));
      setSubmitting(false);
    }
  }

  // On Sign in, show the full branded loader (same as the session-restore /
  // splash) through the auth call + navigation, instead of only a button spinner.
  if (submitting) {
    return <BrandLoader status={slow ? "Waking the server, one moment…" : "Signing you in…"} />;
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <BrandMark size="md" />
        <div>
          <div className="auth-card__title">Welcome back</div>
          <div className="auth-card__subtitle">Sign in to continue.</div>
        </div>

        <form className="form" onSubmit={handleSubmit}>
          <TextField
            id="login-email"
            label="Email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
          />
          <TextField
            id="login-password"
            label="Password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
            minLength={8}
          />
          {error && <div className="error-banner">{error}</div>}
          <Button type="submit" loading={submitting} disabled={submitting}>
            Sign in
          </Button>
        </form>

        <div className="auth-card__footer">
          New here? <Link to="/register">Create an account</Link>
        </div>
      </div>
    </div>
  );
}
