import { Component } from "react";

// A render-time exception in React 18 unmounts the entire tree, which presents as a
// blank white page with the cause only visible in the console. This catches it and puts
// the message on screen instead, because "read me the console" is a bad thing to ask
// someone mid-debug.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.setState({ info });
    console.error("render failed:", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="crash">
        <h2>The page hit a JavaScript error</h2>
        <p>Copy this and send it over — it says exactly what broke.</p>
        <pre>
          {String(this.state.error?.stack || this.state.error)}
          {this.state.info?.componentStack || ""}
        </pre>
        <button onClick={() => window.location.reload()}>Reload</button>
      </div>
    );
  }
}
