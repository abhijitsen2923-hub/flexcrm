import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from "react";

import { isChunkLoadError, reloadOnceForChunkError } from "../utils/chunkReload";


interface ErrorBoundaryProps extends PropsWithChildren {
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}


export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // A stale-chunk error after a deploy: try to recover with a one-time guarded
    // reload rather than stranding the user on the error screen. (The lazy-import
    // wrapper and the vite:preloadError listener usually catch this first; this
    // is the backstop for a chunk error that reaches render.)
    if (isChunkLoadError(error)) {
      reloadOnceForChunkError(error);
    }
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  reload = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    if (this.props.fallback) {
      return this.props.fallback(error, this.reset);
    }

    // A stale-chunk error means a new build shipped while this tab was open;
    // componentDidCatch has already asked for a one-time reload, so show a calm
    // "updating" message rather than a scary crash for the brief moment before
    // the reload lands (or if the loop guard held it back).
    const chunkError = isChunkLoadError(error);
    const heading = chunkError ? "Updating to the latest version…" : "Something went wrong.";
    const message = chunkError
      ? "A new version of the app was just released. Reloading to update — nothing you were typing is lost."
      : "The application hit an unexpected error and could not continue rendering.";

    return (
      <div
        role="alert"
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "2rem",
          fontFamily: "system-ui, -apple-system, sans-serif",
          color: "#111827",
          background: "#f9fafb"
        }}
      >
        <h1 style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>{heading}</h1>
        <p style={{ marginBottom: "1.5rem", color: "#4b5563" }}>{message}</p>
        {import.meta.env.DEV && !chunkError && (
          <pre
            style={{
              maxWidth: "32rem",
              padding: "1rem",
              background: "#fff",
              border: "1px solid #e5e7eb",
              borderRadius: "0.5rem",
              color: "#b91c1c",
              whiteSpace: "pre-wrap",
              overflowWrap: "anywhere"
            }}
          >
            {error.message}
          </pre>
        )}
        <button
          type="button"
          onClick={this.reload}
          style={{
            marginTop: "1.5rem",
            padding: "0.5rem 1rem",
            borderRadius: "0.375rem",
            border: "1px solid #2563eb",
            background: "#2563eb",
            color: "#ffffff",
            cursor: "pointer"
          }}
        >
          {chunkError ? "Reload now" : "Try again"}
        </button>
      </div>
    );
  }
}
