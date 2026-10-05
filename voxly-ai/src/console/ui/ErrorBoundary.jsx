import React, { Component } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';
import { SolidCard } from './SolidCard';
import { TactileButton } from './TactileButton';

/**
 * Console ErrorBoundary
 * Catches JavaScript errors anywhere in their child component tree,
 * logs the error, and renders a fallback UI instead of crashing the entire console to a blank screen.
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    console.error('[Console ErrorBoundary]', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    this.props.onRetry?.();
  };

  handleGoHome = () => {
    this.setState({ hasError: false, error: null, errorInfo: null });
    if (typeof window !== 'undefined') {
      window.location.hash = '#dashboard/overview';
    }
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return typeof this.props.fallback === 'function'
          ? this.props.fallback(this.state.error, this.handleRetry)
          : this.props.fallback;
      }

      return (
        <div className="p-4 sm:p-6 max-w-2xl mx-auto my-6 animate-in fade-in duration-200" data-testid="error-boundary-fallback">
          <SolidCard className="space-y-4 p-5 sm:p-6 border-amber-300/70 bg-amber-50/30">
            <div className="flex items-start gap-3.5">
              <div className="w-10 h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center shrink-0 mt-0.5">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-sm sm:text-base font-bold text-[#0F0E17]">
                  {this.props.title || 'Unable to display this view'}
                </h3>
                <p className="text-xs text-[#524E5E] mt-1">
                  {this.props.description || 'An unexpected issue occurred while rendering this section. Your workspace session is still active.'}
                </p>
              </div>
            </div>

            {this.state.error && (
              <div className="p-3 rounded-xl bg-white border border-[#E4E2EB] font-mono text-[11px] text-red-600 overflow-x-auto max-h-28">
                {this.state.error?.message || String(this.state.error)}
              </div>
            )}

            <div className="flex items-center gap-2.5 pt-1">
              <TactileButton
                variant="primary"
                size="sm"
                icon={RefreshCw}
                onClick={this.handleRetry}
              >
                Reload section
              </TactileButton>
              <TactileButton
                variant="secondary"
                size="sm"
                icon={Home}
                onClick={this.handleGoHome}
              >
                Back to Overview
              </TactileButton>
            </div>
          </SolidCard>
        </div>
      );
    }

    return this.props.children;
  }
}
