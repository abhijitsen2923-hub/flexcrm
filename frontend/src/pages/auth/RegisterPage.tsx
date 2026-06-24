import { Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button, SelectField, TextField } from "../../components";
import { useAuth } from "../../hooks/useAuth";
import type { LeadIndustry } from "../../types";
import { extractErrorMessage } from "../../utils/errors";
import { leadIndustryOptions } from "../../utils/options";


export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [orgName, setOrgName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [businessType, setBusinessType] = useState<LeadIndustry | "">("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register({
        first_name: firstName,
        last_name: lastName,
        email,
        password,
        phone: phone || null,
        business_type: businessType,
        organization_name: orgName.trim() || undefined
      });
      navigate("/", { replace: true });
    } catch (registerError) {
      setError(extractErrorMessage(registerError, "Registration failed."));
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
          <div className="auth-card__title">Create your account</div>
          <div className="auth-card__subtitle">
            Each registration creates a new workspace. You become its admin.
          </div>
        </div>

        <form className="form" onSubmit={handleSubmit}>
          <TextField
            id="register-org-name"
            label="Organization name"
            value={orgName}
            onChange={(event) => setOrgName(event.target.value)}
            placeholder="e.g. Acme Tutorials"
            hint="What's the name of your business? Optional — defaults to your first name's workspace."
            autoComplete="organization"
          />
          <div className="form-grid">
            <TextField
              id="register-first-name"
              label="First name"
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
              required
              autoComplete="given-name"
            />
            <TextField
              id="register-last-name"
              label="Last name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
              required
              autoComplete="family-name"
            />
          </div>
          <TextField
            id="register-email"
            label="Email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
            autoComplete="email"
          />
          <TextField
            id="register-phone"
            label="Phone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            placeholder="Optional"
            autoComplete="tel"
          />
          <SelectField
            id="register-business-type"
            label="Business type"
            value={businessType}
            placeholder="Choose your business type"
            onChange={(event) => setBusinessType(event.target.value as LeadIndustry | "")}
            options={leadIndustryOptions}
            required
            hint="Drives the default industry shown on Leads and other CRM views. You can still switch industries later."
          />
          <TextField
            id="register-password"
            label="Password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
            hint="At least 8 characters."
          />
          {error && <div className="error-banner">{error}</div>}
          <Button type="submit" loading={submitting} disabled={submitting}>
            Create account
          </Button>
        </form>

        <div className="auth-card__footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </div>
      </div>
    </div>
  );
}
