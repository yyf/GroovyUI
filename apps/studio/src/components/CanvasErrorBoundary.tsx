import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = {
  children: ReactNode;
  onError?: (error: Error) => void;
  onReset?: () => void;
  crashed: boolean;
};

type State = { error: Error | null };

/** Catches canvas render crashes and surfaces a minimal recovery UI. */
export default class CanvasErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, _info: ErrorInfo): void {
    this.props.onError?.(error);
  }

  componentDidUpdate(prevProps: Props): void {
    if (prevProps.crashed && !this.props.crashed && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="canvas-fault" role="alert">
        <p className="canvas-fault__tag">CVS FAULT</p>
        <p className="canvas-fault__msg">{this.state.error.message || "Canvas crashed"}</p>
        <button
          type="button"
          className="canvas-fault__reset"
          onClick={() => {
            this.setState({ error: null });
            this.props.onReset?.();
          }}
        >
          Reset canvas
        </button>
      </div>
    );
  }
}
