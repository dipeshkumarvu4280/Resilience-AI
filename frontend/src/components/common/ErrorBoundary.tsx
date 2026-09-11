import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackTitle?: string;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Resilience UI Error Boundary caught an unhandled exception:', error, errorInfo);
  }

  public handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-[400px] flex items-center justify-center p-6">
          <div className="max-w-md w-full p-6 sm:p-8 rounded-2xl bg-white border border-red-200 shadow-xl text-center space-y-4">
            <div className="w-14 h-14 rounded-2xl bg-red-50 border border-red-200 text-[#dc2626] flex items-center justify-center mx-auto shadow-sm">
              <AlertTriangle className="w-7 h-7" />
            </div>

            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-50 border border-red-200 text-[#dc2626] font-mono text-[10px] font-bold uppercase tracking-wider">
              COMPONENT DIAGNOSTIC NOTICE
            </div>

            <h2 className="text-xl font-bold font-sans text-slate-900">
              {this.props.fallbackTitle || 'Emergency Report Form Could Not Be Loaded'}
            </h2>

            <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
              {this.props.fallbackMessage ||
                'An unexpected rendering issue occurred while initializing the intake interface. Please retry or contact emergency dispatch directly.'}
            </p>

            {this.state.error && (
              <div className="p-3 rounded-lg bg-slate-900 text-left overflow-x-auto text-[11px] font-mono text-red-300 border border-slate-700">
                <span className="text-slate-400 font-bold">DIAGNOSTIC: </span>
                {this.state.error.toString()}
              </div>
            )}

            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-2">
              <button
                type="button"
                onClick={this.handleReset}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition-all shadow-sm"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Retry Loading Form</span>
              </button>

              <a
                href="tel:112"
                className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all shadow-sm"
              >
                <span>Call Emergency Services (112)</span>
              </a>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
