import { BrandMark } from "./BrandMark";


/**
 * Full-screen branded loading state — the FlexCRM lockup + an advancing amber
 * progress bar + a status line. Shared by the sign-in transition (LoginPage)
 * and the session-restore wait (SessionRestoreScreen) so both look identical.
 */
export function BrandLoader({ status }: { status: string }) {
  return (
    <div className="brand-loader">
      <BrandMark size="lg" />
      <div className="brand-loader__track" role="progressbar" aria-label="Loading">
        <div className="brand-loader__fill" />
      </div>
      <p className="brand-loader__status">{status}</p>
    </div>
  );
}
