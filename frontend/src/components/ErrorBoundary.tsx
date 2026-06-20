import { Component, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
  retryKey: number;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, retryKey: 0 };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  handleRetry = () => {
    this.setState((s) => ({ error: null, retryKey: s.retryKey + 1 }));
  };

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
          <AlertTriangle className="h-10 w-10 text-amber-400" />
          <h1 className="text-lg font-semibold text-slate-200">
            Something went wrong
          </h1>
          <p className="max-w-md text-sm text-slate-400">
            {this.state.error.message}
          </p>
          <button
            type="button"
            onClick={this.handleRetry}
            className="mt-2 inline-flex items-center gap-2 rounded-md bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500"
          >
            <RefreshCw className="h-4 w-4" />
            Retry
          </button>
        </div>
      );
    }
    return <div key={this.state.retryKey}>{this.props.children}</div>;
  }
}
