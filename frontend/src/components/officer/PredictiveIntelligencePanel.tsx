import React, { useState, useEffect } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Minus,
  HelpCircle,
  Shield,
  Clock,
  Database,
  Layers,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  RefreshCw,
  Info,
  CheckCircle2,
  FileText,
  Radio,
  Eye,
  Activity,
  CloudRain,
  Wind,
  Thermometer,
  Droplets,
  Sun,
  Compass,
} from 'lucide-react';
import type {
  IncidentPredictionResponse,
  PredictiveDataSufficiency,
} from '../../types';
import { getIncidentPrediction } from '../../services/predictiveApi';

interface PredictiveIntelligencePanelProps {
  incidentId: string;
  onRefreshParent?: () => void;
}

export const PredictiveIntelligencePanel: React.FC<PredictiveIntelligencePanelProps> = ({
  incidentId,
}) => {
  const [data, setData] = useState<IncidentPredictionResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedHorizon, setSelectedHorizon] = useState<number>(30);
  const [selectedWindow, setSelectedWindow] = useState<number>(60);
  const [showFeaturesDrawer, setShowFeaturesDrawer] = useState<boolean>(false);

  const fetchPrediction = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await getIncidentPrediction(incidentId, {
        window_minutes: selectedWindow,
        horizon_minutes: selectedHorizon,
      });
      setData(res);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to generate advisory predictive intelligence.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (incidentId) {
      fetchPrediction();
    }
  }, [incidentId, selectedHorizon, selectedWindow]);

  const activeForecast = data?.horizons?.[`${selectedHorizon}m`] || data?.forecast;

  const getRiskBadgeClass = (riskLevel?: string) => {
    switch (riskLevel) {
      case 'CRITICAL':
        return 'bg-red-100 text-red-800 border-red-300';
      case 'HIGH':
        return 'bg-amber-100 text-amber-800 border-amber-300';
      case 'MEDIUM':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'LOW':
        return 'bg-emerald-100 text-emerald-800 border-emerald-300';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-300';
    }
  };

  const getWeatherStatusBadge = (status?: string) => {
    switch (status) {
      case 'FRESH':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-emerald-700" />
            FRESH
          </span>
        );
      case 'STALE':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 flex items-center gap-1">
            <Info className="w-3 h-3 text-amber-700" />
            STALE
          </span>
        );
      case 'ERROR':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-800 border border-red-300 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 text-red-700" />
            ERROR
          </span>
        );
      case 'UNAVAILABLE':
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300 flex items-center gap-1">
            <HelpCircle className="w-3 h-3 text-slate-500" />
            UNAVAILABLE
          </span>
        );
    }
  };

  const getSufficiencyBadge = (status?: PredictiveDataSufficiency) => {
    switch (status) {
      case 'SUFFICIENT_DATA':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3 text-emerald-700" />
            SUFFICIENT DATA
          </span>
        );
      case 'LIMITED_DATA':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-300 flex items-center gap-1">
            <Info className="w-3 h-3 text-amber-700" />
            LIMITED DATA
          </span>
        );
      case 'INSUFFICIENT_DATA':
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-yellow-100 text-yellow-800 border border-yellow-300 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3 text-yellow-700" />
            INSUFFICIENT DATA
          </span>
        );
      case 'NO_DATA':
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-300 flex items-center gap-1">
            <HelpCircle className="w-3 h-3 text-slate-500" />
            NO DATA
          </span>
        );
    }
  };

  const renderTrendIcon = (trend?: string) => {
    switch (trend) {
      case 'RISING':
        return (
          <span className="flex items-center gap-1 text-red-700 font-bold text-xs bg-red-50 px-2 py-0.5 rounded border border-red-200">
            <TrendingUp className="w-3.5 h-3.5 text-red-600" />
            RISING
          </span>
        );
      case 'FALLING':
        return (
          <span className="flex items-center gap-1 text-emerald-700 font-bold text-xs bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
            <TrendingDown className="w-3.5 h-3.5 text-emerald-600" />
            FALLING
          </span>
        );
      case 'STABLE':
        return (
          <span className="flex items-center gap-1 text-blue-700 font-bold text-xs bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
            <Minus className="w-3.5 h-3.5 text-blue-600" />
            STABLE
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1 text-slate-600 font-medium text-xs bg-slate-100 px-2 py-0.5 rounded border border-slate-300">
            <HelpCircle className="w-3.5 h-3.5 text-slate-500" />
            UNKNOWN
          </span>
        );
    }
  };

  return (
    <div className="border border-slate-200 rounded-xl bg-white shadow-xs overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 bg-gradient-to-r from-slate-50 to-indigo-50/40 border-b border-slate-200 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-indigo-100 text-indigo-700 rounded-lg">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-900">
                Predictive Intelligence & Escalation Forecast
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.5 bg-indigo-100 text-indigo-800 rounded font-semibold">
                Phase 1 Deterministic + Weather
              </span>
            </div>
            <p className="text-[11px] text-slate-500">
              Advisory temporal risk analysis fused with real-world weather observations & multi-horizon forecasts
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {data && getSufficiencyBadge(data.data_status)}
          <button
            onClick={fetchPrediction}
            disabled={loading}
            title="Re-evaluate predictive signals from live database state and weather"
            className="p-1.5 text-slate-500 hover:text-slate-800 bg-white border border-slate-200 hover:border-slate-300 rounded-lg transition shadow-2xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="p-4 space-y-4">
        {/* Horizon & Window Selector Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50 p-2.5 rounded-lg border border-slate-200 text-xs">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-600 flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-slate-500" />
              Forecast Horizon:
            </span>
            <div className="flex items-center bg-white rounded-md border border-slate-200 p-0.5 shadow-2xs">
              {[15, 30, 60].map((h) => (
                <button
                  key={h}
                  onClick={() => setSelectedHorizon(h)}
                  className={`px-2.5 py-1 rounded text-xs font-bold transition ${
                    selectedHorizon === h
                      ? 'bg-indigo-600 text-white shadow-xs'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                  }`}
                >
                  {h} min
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-600 flex items-center gap-1">
              <Database className="w-3.5 h-3.5 text-slate-500" />
              Historical Window:
            </span>
            <select
              value={selectedWindow}
              onChange={(e) => setSelectedWindow(parseInt(e.target.value, 10))}
              className="bg-white border border-slate-200 rounded-md px-2 py-1 text-xs font-medium text-slate-700 shadow-2xs focus:ring-2 focus:ring-indigo-500"
            >
              <option value={60}>Last 60 minutes</option>
              <option value={360}>Last 6 hours</option>
              <option value={1440}>Last 24 hours</option>
            </select>
          </div>
        </div>

        {loading && !data ? (
          <div className="py-12 text-center text-slate-500 space-y-2">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto text-indigo-600" />
            <p className="text-xs font-medium">Extracting temporal features, weather observations, and calculating escalation risk...</p>
          </div>
        ) : error && !data ? (
          <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs space-y-2">
            <div className="flex items-center gap-2 font-bold">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 text-red-600" />
              <span>Predictive Intelligence Unavailable</span>
            </div>
            <p className="text-slate-600">{error}</p>
            <button
              onClick={fetchPrediction}
              className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold shadow-xs transition flex items-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Predictive Analysis</span>
            </button>
          </div>
        ) : data ? (
          <>
            {/* Insufficient or Limited Data Truthful Notification */}
            {(data.data_status === 'INSUFFICIENT_DATA' || data.data_status === 'NO_DATA') && (
              <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-xs space-y-1">
                <div className="flex items-center gap-2 font-bold text-amber-900">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  <span>Insufficient Genuine Historical Observations ({data.data_status.replace('_', ' ')})</span>
                </div>
                <p className="text-amber-800 leading-relaxed">
                  The database contains insufficient time-series observations within the last {data.historical_window_minutes} minutes to compute a dynamic rate-of-change curve. The predicted escalation risk reflects baseline authoritative triage. Switch to Last 6 hours or Last 24 hours to include earlier records.
                </p>
              </div>
            )}

            {/* Primary Forecast & Authoritative Separation Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Left: Authoritative Current State */}
              <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/70 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                    <Shield className="w-3.5 h-3.5 text-slate-700" />
                    Current Authoritative State
                  </span>
                  {data.is_officer_override && (
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                      OFFICER OVERRIDE
                    </span>
                  )}
                </div>

                <div className="flex items-baseline justify-between pt-1">
                  <div>
                    <span className={`px-2.5 py-1 rounded-full text-xs font-black border ${getRiskBadgeClass(data.current_authoritative_severity)}`}>
                      {data.current_authoritative_severity}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-xl font-black text-slate-900 font-mono">
                      {data.current_severity_score.toFixed(1)}
                    </span>
                    <span className="text-xs text-slate-400 font-normal"> / 10</span>
                  </div>
                </div>

                <p className="text-[11px] text-slate-500 pt-1 border-t border-slate-200/80">
                  Authoritative triage level designated by Emergency Operations. Unchanged by advisory prediction.
                </p>
              </div>

              {/* Right: Predicted Future State */}
              <div className="p-3.5 rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50/50 to-white space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-indigo-900 uppercase tracking-wider flex items-center gap-1.5">
                    <TrendingUp className="w-3.5 h-3.5 text-indigo-600" />
                    Predicted Escalation Risk (+{selectedHorizon}m)
                  </span>
                  {renderTrendIcon(activeForecast?.trend)}
                </div>

                <div className="flex items-baseline justify-between pt-1">
                  <div className="flex items-center gap-2">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-black border ${getRiskBadgeClass(activeForecast?.risk_level)}`}>
                      {activeForecast?.risk_level || 'UNKNOWN'}
                    </span>
                    <span className="text-xs font-bold text-indigo-900">
                      Risk Score: {(activeForecast?.risk_score ?? 0).toFixed(2)}
                    </span>
                  </div>

                  <div className="text-right text-[11px] font-medium text-slate-600">
                    <span>Confidence: </span>
                    <strong className="text-indigo-900 font-bold">{Math.round((activeForecast?.confidence_score ?? 0) * 100)}%</strong>
                    <span className="text-slate-400"> ({activeForecast?.confidence_label})</span>
                  </div>
                </div>

                {/* Score Bar */}
                <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden mt-1">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      (activeForecast?.risk_score ?? 0) >= 0.85
                        ? 'bg-red-600'
                        : (activeForecast?.risk_score ?? 0) >= 0.65
                        ? 'bg-amber-500'
                        : (activeForecast?.risk_score ?? 0) >= 0.35
                        ? 'bg-yellow-500'
                        : 'bg-emerald-500'
                    }`}
                    style={{ width: `${Math.round((activeForecast?.risk_score ?? 0) * 100)}%` }}
                  />
                </div>

                <p className="text-[11px] text-indigo-800/80 pt-1 border-t border-indigo-100 flex items-center justify-between">
                  <span>* Advisory predictive estimate.</span>
                  <span className="font-semibold text-slate-600">{data.historical_window_minutes}m window data</span>
                </p>
              </div>
            </div>

            {/* Multi-Horizon Risk Progression Timeline */}
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-slate-500" />
                  <span>Multi-Horizon Escalation Progression (Deterministic Projections)</span>
                </div>
                {data.all_horizons_capped && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300">
                    Forecast Ceiling Reached (0.98)
                  </span>
                )}
              </div>

              {data.all_horizons_capped && (
                <div className="p-2.5 bg-amber-50/80 border border-amber-200 rounded-lg text-xs text-amber-900 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <Info className="w-3.5 h-3.5 text-amber-700 flex-shrink-0" />
                    <span>Advisory Risk Score Ceiling Active</span>
                  </div>
                  <p className="text-[11px] text-amber-800 leading-relaxed">
                    All forecast horizons reach the advisory ceiling (0.98) because the baseline operational state ({data.current_severity_score.toFixed(1)}/10) is already near the maximum risk boundary. Underlying continuous projections are preserved internally.
                  </p>
                </div>
              )}

              <div className="grid grid-cols-4 gap-2 text-center text-xs">
                {/* Current */}
                <div className="p-2 bg-white rounded-lg border border-slate-200 flex flex-col justify-between">
                  <div>
                    <div className="text-[10px] text-slate-500 font-semibold uppercase">Current State</div>
                    <div className={`mt-1 font-bold text-xs ${getRiskBadgeClass(data.current_authoritative_severity)} py-0.5 rounded`}>
                      {data.current_authoritative_severity}
                    </div>
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono mt-1">{data.current_severity_score.toFixed(1)}/10</div>
                </div>

                {/* 15m */}
                {data.horizons?.['15m'] && (
                  <div className={`p-2 rounded-lg border flex flex-col justify-between transition ${selectedHorizon === 15 ? 'bg-indigo-50 border-indigo-300 ring-2 ring-indigo-400/40' : 'bg-white border-slate-200'}`}>
                    <div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase flex items-center justify-center gap-1">
                        +15 min
                        {data.horizons['15m'].is_capped && (
                          <span className="text-[9px] px-1 bg-amber-100 text-amber-800 rounded font-mono font-bold" title="Capped at advisory ceiling 0.98">
                            CAP
                          </span>
                        )}
                      </div>
                      <div className={`mt-1 font-bold text-xs ${getRiskBadgeClass(data.horizons['15m'].risk_level)} py-0.5 rounded`}>
                        {data.horizons['15m'].risk_level}
                      </div>
                    </div>
                    <div className="mt-1">
                      <div className="text-[10px] text-slate-600 font-mono font-bold">
                        Score: {data.horizons['15m'].risk_score.toFixed(2)}
                      </div>
                      {data.horizons['15m'].is_capped && typeof data.horizons['15m'].raw_score === 'number' && (
                        <div className="text-[9px] text-slate-400 font-mono" title="Uncapped continuous projection">
                          (raw: {data.horizons['15m'].raw_score?.toFixed(3)})
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* 30m */}
                {data.horizons?.['30m'] && (
                  <div className={`p-2 rounded-lg border flex flex-col justify-between transition ${selectedHorizon === 30 ? 'bg-indigo-50 border-indigo-300 ring-2 ring-indigo-400/40' : 'bg-white border-slate-200'}`}>
                    <div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase flex items-center justify-center gap-1">
                        +30 min (Std)
                        {data.horizons['30m'].is_capped && (
                          <span className="text-[9px] px-1 bg-amber-100 text-amber-800 rounded font-mono font-bold" title="Capped at advisory ceiling 0.98">
                            CAP
                          </span>
                        )}
                      </div>
                      <div className={`mt-1 font-bold text-xs ${getRiskBadgeClass(data.horizons['30m'].risk_level)} py-0.5 rounded`}>
                        {data.horizons['30m'].risk_level}
                      </div>
                    </div>
                    <div className="mt-1">
                      <div className="text-[10px] text-slate-600 font-mono font-bold">
                        Score: {data.horizons['30m'].risk_score.toFixed(2)}
                      </div>
                      {data.horizons['30m'].is_capped && typeof data.horizons['30m'].raw_score === 'number' && (
                        <div className="text-[9px] text-slate-400 font-mono" title="Uncapped continuous projection">
                          (raw: {data.horizons['30m'].raw_score?.toFixed(3)})
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* 60m */}
                {data.horizons?.['60m'] && (
                  <div className={`p-2 rounded-lg border flex flex-col justify-between transition ${selectedHorizon === 60 ? 'bg-indigo-50 border-indigo-300 ring-2 ring-indigo-400/40' : 'bg-white border-slate-200'}`}>
                    <div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase flex items-center justify-center gap-1">
                        +60 min
                        {data.horizons['60m'].is_capped && (
                          <span className="text-[9px] px-1 bg-amber-100 text-amber-800 rounded font-mono font-bold" title="Capped at advisory ceiling 0.98">
                            CAP
                          </span>
                        )}
                      </div>
                      <div className={`mt-1 font-bold text-xs ${getRiskBadgeClass(data.horizons['60m'].risk_level)} py-0.5 rounded`}>
                        {data.horizons['60m'].risk_level}
                      </div>
                    </div>
                    <div className="mt-1">
                      <div className="text-[10px] text-slate-600 font-mono font-bold">
                        Score: {data.horizons['60m'].risk_score.toFixed(2)}
                      </div>
                      {data.horizons['60m'].is_capped && typeof data.horizons['60m'].raw_score === 'number' && (
                        <div className="text-[9px] text-slate-400 font-mono" title="Uncapped continuous projection">
                          (raw: {data.horizons['60m'].raw_score?.toFixed(3)})
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Weather Intelligence & Atmospheric Context Section */}
            {data.weather && (
              <div className="p-3.5 bg-gradient-to-br from-sky-50/60 via-slate-50 to-indigo-50/30 border border-sky-200/80 rounded-xl space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                    <CloudRain className="w-4 h-4 text-sky-600" />
                    <span>Real Weather Intelligence & Atmospheric Context</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-mono text-slate-500">
                      Provider: <strong className="text-slate-700 capitalize">{data.weather.provider}</strong>
                    </span>
                    {getWeatherStatusBadge(data.weather.data_status)}
                  </div>
                </div>

                {data.weather.data_status === 'UNAVAILABLE' || data.weather.data_status === 'ERROR' ? (
                  <div className="p-2 bg-slate-100 rounded text-xs text-slate-600">
                    <span className="font-semibold">{data.weather.error_detail || 'Weather data unavailable for this location.'}</span>
                  </div>
                ) : (
                  <>
                    {/* Current Observed Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                      <div className="p-2 bg-white rounded-lg border border-slate-200">
                        <div className="text-[10px] text-slate-400 font-semibold uppercase flex items-center gap-1">
                          <Thermometer className="w-3 h-3 text-red-500" />
                          Temperature
                        </div>
                        <div className="text-sm font-bold text-slate-900 font-mono mt-0.5">
                          {data.weather.temperature_c !== null && data.weather.temperature_c !== undefined ? `${data.weather.temperature_c.toFixed(1)}°C` : 'N/A'}
                        </div>
                      </div>

                      <div className="p-2 bg-white rounded-lg border border-slate-200">
                        <div className="text-[10px] text-slate-400 font-semibold uppercase flex items-center gap-1">
                          <CloudRain className="w-3 h-3 text-sky-500" />
                          Precipitation
                        </div>
                        <div className="text-sm font-bold text-sky-900 font-mono mt-0.5">
                          {data.weather.precipitation_mm !== null && data.weather.precipitation_mm !== undefined ? `${data.weather.precipitation_mm.toFixed(1)} mm/h` : 'N/A'}
                        </div>
                      </div>

                      <div className="p-2 bg-white rounded-lg border border-slate-200">
                        <div className="text-[10px] text-slate-400 font-semibold uppercase flex items-center gap-1">
                          <Wind className="w-3 h-3 text-blue-500" />
                          Wind Velocity
                        </div>
                        <div className="text-sm font-bold text-slate-900 font-mono mt-0.5">
                          {data.weather.wind_speed_mps !== null && data.weather.wind_speed_mps !== undefined ? `${data.weather.wind_speed_mps.toFixed(1)} m/s` : 'N/A'}
                          {data.weather.wind_gust_mps ? ` (gust: ${data.weather.wind_gust_mps.toFixed(1)})` : ''}
                        </div>
                      </div>

                      <div className="p-2 bg-white rounded-lg border border-slate-200">
                        <div className="text-[10px] text-slate-400 font-semibold uppercase flex items-center gap-1">
                          <Droplets className="w-3 h-3 text-indigo-500" />
                          Humidity
                        </div>
                        <div className="text-sm font-bold text-slate-900 font-mono mt-0.5">
                          {data.weather.humidity_percent !== null && data.weather.humidity_percent !== undefined ? `${data.weather.humidity_percent}%` : 'N/A'}
                        </div>
                      </div>
                    </div>

                    {/* Condition & Coordinates Subtext */}
                    <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-600 pt-1 border-t border-sky-100">
                      <div className="flex items-center gap-1 font-medium">
                        <Sun className="w-3.5 h-3.5 text-amber-500" />
                        <span>Condition: <strong>{data.weather.condition || 'Clear / Normal'}</strong></span>
                      </div>
                      <div className="text-slate-400 font-mono text-[10px]">
                        Location: {data.weather.latitude.toFixed(4)}, {data.weather.longitude.toFixed(4)}
                        {data.weather.freshness_seconds !== undefined && data.weather.freshness_seconds !== null && ` (${Math.round(data.weather.freshness_seconds / 60)}m age)`}
                      </div>
                    </div>

                    {/* Multi-Horizon Weather Forecast Row */}
                    {data.weather.forecast_periods && data.weather.forecast_periods.length > 0 && (
                      <div className="pt-2 border-t border-sky-100/80">
                        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                          <Clock className="w-3 h-3 text-slate-400" />
                          <span>Horizon Atmospheric Projections:</span>
                        </div>
                        <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
                          {data.weather.forecast_periods.map((fp, idx) => (
                            <div key={idx} className="p-1.5 bg-white/90 rounded border border-slate-200">
                              <div className="text-[10px] font-bold text-slate-700">+{fp.horizon_minutes} min</div>
                              <div className="font-mono text-slate-900 font-semibold">
                                {fp.precipitation_mm !== null && fp.precipitation_mm !== undefined ? `${fp.precipitation_mm.toFixed(1)}mm rain` : 'No rain'}
                              </div>
                              <div className="text-[10px] text-slate-500">
                                {fp.temperature_c !== null && fp.temperature_c !== undefined ? `${fp.temperature_c.toFixed(1)}°C` : ''}
                                {fp.precipitation_probability !== null && fp.precipitation_probability !== undefined ? ` • ${fp.precipitation_probability.toFixed(0)}% prob` : ''}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* WHY THIS PREDICTION? Contributing Signals */}
            <div className="p-3.5 bg-white border border-slate-200 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                  <Info className="w-3.5 h-3.5 text-indigo-600" />
                  Why This Prediction? (Contributing Evidence Signals)
                </span>
                <span className="text-[11px] text-slate-500 font-medium">
                  {activeForecast?.contributing_factors?.length || 0} Factors Identified
                </span>
              </div>

              <ul className="space-y-1.5 text-xs text-slate-700 pl-1">
                {(activeForecast?.contributing_factors || []).map((factor, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-600 mt-1.5 flex-shrink-0" />
                    <span className="leading-relaxed">{factor}</span>
                  </li>
                ))}
              </ul>

              {/* Genuine Corroborating Evidence Items */}
              {data.evidence && data.evidence.length > 0 && (
                <div className="pt-2 border-t border-slate-100 space-y-1.5">
                  <div className="text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                    Recent Genuine Evidence Records:
                  </div>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {data.evidence.map((ev, i) => (
                      <div key={i} className="p-2 bg-slate-50 rounded border border-slate-200 text-[11px] flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5 truncate">
                          {ev.source_type === 'CITIZEN_REPORT' && <FileText className="w-3.5 h-3.5 text-blue-600 flex-shrink-0" />}
                          {ev.source_type === 'IOT_SENSOR' && <Radio className="w-3.5 h-3.5 text-purple-600 flex-shrink-0" />}
                          {ev.source_type === 'FIELD_VERIFICATION' && <Eye className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />}
                          {ev.source_type === 'MONITORING_EVENT' && <Activity className="w-3.5 h-3.5 text-amber-600 flex-shrink-0" />}
                          {ev.source_type === 'WEATHER_API' && <CloudRain className="w-3.5 h-3.5 text-sky-600 flex-shrink-0" />}
                          <span className="font-bold text-slate-800">{ev.source_id}:</span>
                          <span className="text-slate-600 truncate">{ev.contribution}</span>
                        </div>
                        <span className="text-[10px] text-slate-400 font-mono flex-shrink-0">
                          {new Date(ev.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Signal Contribution Breakdown */}
            {activeForecast && (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
                <div className="text-[11px] font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                  <Compass className="w-3.5 h-3.5 text-slate-500" />
                  <span>Deterministic Multi-Signal Contribution Breakdown (+{selectedHorizon}m Horizon)</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 text-center text-xs">
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <div className="text-[10px] text-slate-400 font-semibold uppercase">Sensor</div>
                    <div className={`font-mono font-bold text-xs mt-0.5 ${(activeForecast.sensor_contribution || 0) > 0 ? 'text-red-700' : 'text-slate-700'}`}>
                      {activeForecast.sensor_contribution !== null && activeForecast.sensor_contribution !== undefined ? `${(activeForecast.sensor_contribution > 0 ? '+' : '')}${activeForecast.sensor_contribution.toFixed(3)}` : '0.000'}
                    </div>
                  </div>
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <div className="text-[10px] text-slate-400 font-semibold uppercase">Weather</div>
                    <div className={`font-mono font-bold text-xs mt-0.5 ${(activeForecast.weather_contribution || 0) > 0 ? 'text-sky-700' : 'text-slate-700'}`}>
                      {activeForecast.weather_contribution !== null && activeForecast.weather_contribution !== undefined ? `${(activeForecast.weather_contribution > 0 ? '+' : '')}${activeForecast.weather_contribution.toFixed(3)}` : '0.000'}
                    </div>
                  </div>
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <div className="text-[10px] text-slate-400 font-semibold uppercase">Reports</div>
                    <div className={`font-mono font-bold text-xs mt-0.5 ${(activeForecast.incident_contribution || 0) > 0 ? 'text-blue-700' : 'text-slate-700'}`}>
                      {activeForecast.incident_contribution !== null && activeForecast.incident_contribution !== undefined ? `${(activeForecast.incident_contribution > 0 ? '+' : '')}${activeForecast.incident_contribution.toFixed(3)}` : '0.000'}
                    </div>
                  </div>
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <div className="text-[10px] text-slate-400 font-semibold uppercase">Field</div>
                    <div className={`font-mono font-bold text-xs mt-0.5 ${(activeForecast.field_contribution || 0) > 0 ? 'text-emerald-700' : 'text-slate-700'}`}>
                      {activeForecast.field_contribution !== null && activeForecast.field_contribution !== undefined ? `${(activeForecast.field_contribution > 0 ? '+' : '')}${activeForecast.field_contribution.toFixed(3)}` : '0.000'}
                    </div>
                  </div>
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <div className="text-[10px] text-slate-400 font-semibold uppercase">Monitoring</div>
                    <div className={`font-mono font-bold text-xs mt-0.5 ${(activeForecast.monitoring_contribution || 0) > 0 ? 'text-amber-700' : 'text-slate-700'}`}>
                      {activeForecast.monitoring_contribution !== null && activeForecast.monitoring_contribution !== undefined ? `${(activeForecast.monitoring_contribution > 0 ? '+' : '')}${activeForecast.monitoring_contribution.toFixed(3)}` : '0.000'}
                    </div>
                  </div>
                  <div className="p-2 bg-white rounded border border-slate-200">
                    <div className="text-[10px] text-slate-400 font-semibold uppercase">Task Pressure</div>
                    <div className={`font-mono font-bold text-xs mt-0.5 ${(activeForecast.task_contribution || 0) > 0 ? 'text-red-700' : 'text-slate-700'}`}>
                      {activeForecast.task_contribution !== null && activeForecast.task_contribution !== undefined ? `+${activeForecast.task_contribution.toFixed(3)}` : '0.000'}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* DATA POINTS USED Breakdown */}
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
                  <Database className="w-3.5 h-3.5 text-slate-500" />
                  <span>Genuine Operational Records Evaluated ({data.historical_window_minutes}m Window)</span>
                </div>
                <div className="text-[10px] font-mono text-slate-500 flex items-center gap-2">
                  <span>Physical Sources: <strong className="text-slate-800">{data.independent_physical_sources_count ?? data.independent_sources_count ?? 1}</strong></span>
                  <span>•</span>
                  <span>Weather Context: <strong className="text-sky-800">{data.external_context_sources_count ?? (data.weather ? 1 : 0)}</strong></span>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
                <div className="p-2 bg-white rounded border border-slate-200">
                  <span className="text-[10px] text-slate-400 font-semibold uppercase block">Reports</span>
                  <span className="text-sm font-bold text-slate-900 font-mono">
                    {data.data_points_used.citizen_reports ?? 0}
                  </span>
                </div>
                <div className="p-2 bg-white rounded border border-slate-200">
                  <span className="text-[10px] text-slate-400 font-semibold uppercase block">Sensor Readings</span>
                  <span className="text-sm font-bold text-purple-900 font-mono">
                    {data.data_points_used.sensor_readings ?? 0}
                  </span>
                </div>
                <div className="p-2 bg-white rounded border border-slate-200">
                  <span className="text-[10px] text-slate-400 font-semibold uppercase block">Sensor Alerts</span>
                  <span className="text-sm font-bold text-red-900 font-mono">
                    {data.data_points_used.sensor_alerts ?? 0}
                  </span>
                </div>
                <div className="p-2 bg-white rounded border border-slate-200">
                  <span className="text-[10px] text-slate-400 font-semibold uppercase block">Verifications</span>
                  <span className="text-sm font-bold text-emerald-900 font-mono">
                    {data.data_points_used.field_verifications ?? 0}
                  </span>
                </div>
                <div className="p-2 bg-white rounded border border-slate-200">
                  <span className="text-[10px] text-slate-400 font-semibold uppercase block">Telemetry Events</span>
                  <span className="text-sm font-bold text-blue-900 font-mono">
                    {data.data_points_used.monitoring_events ?? 0}
                  </span>
                </div>
              </div>
            </div>

            {/* Explainable Features & Limitations Drawer */}
            <div className="border border-slate-200 rounded-xl overflow-hidden bg-white">
              <button
                onClick={() => setShowFeaturesDrawer(!showFeaturesDrawer)}
                className="w-full px-4 py-2.5 text-xs font-bold text-slate-800 bg-slate-50 hover:bg-slate-100 flex items-center justify-between transition"
              >
                <div className="flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-slate-600" />
                  <span>Feature Extraction Provenance & Model Limitations ({data.features.length} Features)</span>
                </div>
                {showFeaturesDrawer ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </button>

              {showFeaturesDrawer && (
                <div className="p-4 space-y-4 text-xs bg-white border-t border-slate-200">
                  {/* Summary Provenance Header */}
                  <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-700 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span>Raw Database Records: </span>
                      <strong className="font-mono text-slate-900 font-bold">
                        {Object.values(data.data_points_used).reduce((a, b) => a + b, 0)}
                      </strong>
                    </div>
                    <div>
                      <span>Physical Corroborating Sources: </span>
                      <strong className="font-mono text-indigo-900 font-bold">
                        {data.independent_physical_sources_count ?? data.independent_sources_count ?? 1}
                      </strong>
                    </div>
                    <div>
                      <span>Aggregation Model: </span>
                      <span className="font-mono text-slate-600 font-semibold">Deterministic Time-Series + Weather Fusion</span>
                    </div>
                  </div>

                  {/* Features Table */}
                  <div className="space-y-2">
                    <h4 className="font-bold text-slate-800">Extracted Deterministic Features:</h4>
                    <div className="space-y-2 max-h-80 overflow-y-auto">
                      {data.features.map((f, i) => (
                        <div key={i} className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 space-y-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0">
                              <div className="font-mono font-bold text-slate-900 truncate">{f.name}</div>
                              <div className="text-[11px] text-slate-500">{f.description || f.source}</div>
                            </div>
                            <div className="text-right flex-shrink-0 font-mono font-bold text-indigo-900 text-sm">
                              {f.value}
                            </div>
                          </div>

                          {/* Rich Sensor Provenance Metadata */}
                          {f.metadata && f.metadata.sensor_id && (
                            <div className="mt-1 p-2 bg-white rounded border border-slate-200 text-[11px] space-y-1">
                              <div className="font-semibold text-slate-700 flex items-center justify-between">
                                <span>Sensor: {f.metadata.sensor_name || f.metadata.sensor_id}</span>
                                <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold ${f.metadata.health === 'HEALTHY' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-700'}`}>
                                  {f.metadata.health || 'HEALTHY'}
                                </span>
                              </div>
                              <div className="grid grid-cols-2 sm:grid-cols-4 gap-1 text-[10px] text-slate-600 font-mono pt-1 border-t border-slate-100">
                                <div>Raw: <strong>{f.metadata.raw_records ?? f.data_points}</strong></div>
                                <div>Span: <strong>{f.metadata.time_span_minutes?.toFixed(1) || 0}m</strong></div>
                                <div>First: <strong>{f.metadata.first_reading}m</strong></div>
                                <div>Latest: <strong>{f.metadata.latest_reading}m</strong></div>
                                <div>Min/Max: <strong>{f.metadata.min_reading}/{f.metadata.max_reading}m</strong></div>
                                <div>Threshold: <strong>{f.metadata.threshold}m</strong></div>
                                <div>Breaches: <strong>{f.metadata.breach_count} ({((f.metadata.breach_ratio || 0) * 100).toFixed(0)}%)</strong></div>
                                <div>Trend: <strong className={f.metadata.trend_direction === 'RISING' ? 'text-red-700' : f.metadata.trend_direction === 'FALLING' ? 'text-emerald-700' : 'text-blue-700'}>{f.metadata.trend_direction}</strong></div>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Missing Features */}
                  {data.missing_features && data.missing_features.length > 0 && (
                    <div className="pt-2 border-t border-slate-100">
                      <h4 className="font-bold text-amber-800 mb-1">Unavailable Signals:</h4>
                      <ul className="list-disc list-inside text-slate-600 space-y-0.5 text-[11px]">
                        {data.missing_features.map((mf, i) => (
                          <li key={i}>{mf}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Limitations */}
                  {data.limitations && data.limitations.length > 0 && (
                    <div className="pt-2 border-t border-slate-100">
                      <h4 className="font-bold text-slate-800 mb-1">Methodological Limitations:</h4>
                      <ul className="list-disc list-inside text-slate-600 space-y-0.5 text-[11px]">
                        {data.limitations.map((lim, i) => (
                          <li key={i}>{lim}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Advisory Mandatory Notice */}
            <div className="p-3 bg-amber-50/70 border border-amber-200 rounded-xl text-[11px] text-amber-900 flex items-start gap-2">
              <Shield className="w-4 h-4 text-amber-700 flex-shrink-0 mt-0.5" />
              <div className="leading-relaxed">
                <strong>Human-in-the-Loop Safeguard:</strong> {data.advisory_notice}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
};
