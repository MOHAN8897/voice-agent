import React, { Component } from 'react';
import { AlertTriangle, RefreshCw, LayoutDashboard } from 'lucide-react';

/**
 * RootErrorBoundary
 * Top-level error safety boundary wrapping the entire application.
 * Prevents any unhandled rendering error from crashing to a blank white screen,
 * and guarantees that the tenant's authentication and workspace session are preserved.
 */
export class RootErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, showDetails: false };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[RootErrorBoundary] Unhandled UI error caught:', error, errorInfo);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null });
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  handleReturnToDashboard = () => {
    this.setState({ hasError: false, error: null });
    if (typeof window !== 'undefined') {
      window.location.hash = '#dashboard/overview';
    }
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#FAF9FD] flex items-center justify-center p-4 select-none font-sans antialiased text-[#0F0E17]">
          <div className="w-full max-w-lg bg-white border border-[#E4E2EB] rounded-2xl p-6 sm:p-8 shadow-sm text-center">
            <div className="w-14 h-14 rounded-2xl bg-amber-100 text-amber-700 flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-7 h-7" />
            </div>

            <h1 className="text-xl font-bold tracking-tight text-[#0F0E17]">
              Something interrupted this view
            </h1>

            <p className="text-sm text-[#524E5E] mt-2 leading-relaxed">
              An unexpected display issue occurred in this section. Your workspace session, phone configuration, and data remain safe and active.
            </p>

            {this.state.error && (
              <div className="mt-4 text-left">
                <button
                  type="button"
                  onClick={() => this.setState((prev) => ({ showDetails: !prev.showDetails }))}
                  className="text-xs font-semibold text-[#6366F1] hover:underline"
                >
                  {this.state.showDetails ? 'Hide technical details' : 'Show technical details'}
                </button>
                {this.state.showDetails && (
                  <div className="mt-2 p-3 rounded-xl bg-gray-50 border border-gray-200 text-xs font-mono text-red-600 max-h-36 overflow-y-auto break-all">
                    {this.state.error?.message || String(this.state.error)}
                  </div>
                )}
              </div>
            )}

            <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
              <button
                type="button"
                onClick={this.handleReload}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-[#0F0E17] text-white text-sm font-semibold hover:bg-black transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                Reload Workspace
              </button>
              <button
                type="button"
                onClick={this.handleReturnToDashboard}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl border border-[#E4E2EB] bg-white text-sm font-semibold text-[#0F0E17] hover:bg-gray-50 transition-colors"
              >
                <LayoutDashboard className="w-4 h-4" />
                Return to Overview
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
