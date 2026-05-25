import { Link } from "react-router-dom";

import { EmptyState } from "../components";


export default function NotFoundPage() {
  return (
    <EmptyState
      title="404 — Page not found"
      description="The page you’re looking for doesn’t exist."
      action={<Link to="/">Back to dashboard</Link>}
    />
  );
}
