import { Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { Button, TextField } from "../../components";
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
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ email, password });
      navigate(from, { replace: true });
    } catch (loginError) {
      setError(extractErrorMessage(loginError, "Login failed."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-card__brand">
          <Sparkles size={22} color="var(--color-primary)" />
          FlexCRM
        </div>
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
