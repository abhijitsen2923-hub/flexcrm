import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from "react";


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
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }

    if (this.props.fallback) {
      return this.props.fallback(error, this.reset);
    }

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
        <h1 style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>Something went wrong.</h1>
        <p style={{ marginBottom: "1.5rem", color: "#4b5563" }}>
          The application hit an unexpected error and could not continue rendering.
        </p>
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
        <button
          type="button"
          onClick={this.reset}
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
          Try again
        </button>
      </div>
    );
  }
}
