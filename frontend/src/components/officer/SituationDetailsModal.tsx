import React, { useState, useEffect } from 'react';
import {
  X,
  Shield,
  Activity,
  AlertTriangle,
  Users,
  MapPin,
  Compass,
  Sparkles,
  CheckCircle2,
  Edit3,
  XCircle,
  FileText,
  ExternalLink,
  Layers,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  RotateCcw,
  Radio,
  ShieldCheck,
  ShieldAlert,
  Info,
  Eye,
} from 'lucide-react';
import type {
  SituationCluster,
  SituationDetailResponse,
  SeverityLevel,
  OfficerReviewAction,
} from '../../types';
import {
  getSituationDetail,
  assessSituation,
  reviewSituation,
} from '../../services/situationsApi';
import { IncidentEvolutionTimeline } from '../common/IncidentEvolutionTimeline';
import { SubmitFieldVerificationModal } from '../volunteer/SubmitFieldVerificationModal';
import { PredictiveIntelligencePanel } from './PredictiveIntelligencePanel';

interface SituationDetailsModalProps {
  situationId: string;
  onClose: () => void;
  onSituationUpdated?: (updated: SituationCluster) => void;
  onViewReport?: (reportId: string) => void;
  onOpenCoordination?: (situationId: string, title: string, emergencyType: string) => void;
}

export const SituationDetailsModal: React.FC<SituationDetailsModalProps> = ({
  situationId,
  onClose,
  onSituationUpdated,
  onViewReport,
  onOpenCoordination,
}) => {
  const [data, setData] = useState<SituationDetailResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [showVerificationModal, setShowVerificationModal] = useState<boolean>(false);

  // Review Form state
  const [reviewMode, setReviewMode] = useState<OfficerReviewAction | null>(null);
  const [modifiedSeverity, setModifiedSeverity] = useState<SeverityLevel>('HIGH');
  const [modifiedScore, setModifiedScore] = useState<number>(7.0);
  const [reviewNotes, setReviewNotes] = useState<string>('');
  const [evidenceTab, setEvidenceTab] = useState<'ALL' | 'CITIZEN' | 'SENSORS'>('ALL');
  const [showCorroborationWhy, setShowCorroborationWhy] = useState<boolean>(false);

  const fetchDetail = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await getSituationDetail(situationId);
      setData(res);
      if (res.situation) {
        setModifiedSeverity(res.situation.severity_level);
        setModifiedScore(res.situation.severity_score);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load situation intelligence details.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (situationId) {
      fetchDetail();
    }
  }, [situationId]);

  const handleTriggerAssessment = async () => {
    try {
      setActionLoading(true);
      setError(null);
      const updated = await assessSituation(situationId);
      if (onSituationUpdated) onSituationUpdated(updated);
      await fetchDetail();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to run situation assessment.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSubmitReview = async () => {
    if (!reviewMode) return;
    try {
      setActionLoading(true);
      setError(null);
      const updated = await reviewSituation(situationId, {
        action: reviewMode,
        modified_severity_level: reviewMode === 'MODIFY' ? modifiedSeverity : undefined,
        modified_severity_score: reviewMode === 'MODIFY' ? modifiedScore : undefined,
        notes: reviewNotes.trim() || undefined,
      });
      if (onSituationUpdated) onSituationUpdated(updated);
      setReviewMode(null);
      setReviewNotes('');
      await fetchDetail();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to submit officer review.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleResetOverride = async () => {
    try {
      setActionLoading(true);
      setError(null);
      const updated = await reviewSituation(situationId, {
        action: 'ACCEPT',
        reset_override: true,
        notes: 'Officer reset operational severity back to AI computed assessment baseline.',
      });
      if (onSituationUpdated) onSituationUpdated(updated);
      await fetchDetail();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to reset officer severity override.');
    } finally {
      setActionLoading(false);
    }
  };

  const getSeverityBadgeClass = (level: SeverityLevel) => {
    switch (level) {
      case 'CRITICAL':
        return 'bg-red-100 text-red-800 border-red-300';
      case 'HIGH':
        return 'bg-amber-100 text-amber-800 border-amber-300';
      case 'MEDIUM':
        return 'bg-yellow-100 text-yellow-800 border-yellow-300';
      case 'LOW':
        return 'bg-emerald-100 text-emerald-800 border-emerald-300';
      default:
        return 'bg-slate-100 text-slate-800 border-slate-300';
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-2 sm:p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[calc(100dvh-1rem)] sm:max-h-[90vh] flex flex-col border border-slate-200 overflow-hidden">
        {/* Modal Header */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50 min-w-0">
          <div className="flex items-center space-x-2.5 sm:space-x-3 min-w-0">
            <div className="p-2 sm:p-2.5 bg-red-50 text-red-600 border border-red-200 rounded-xl flex-shrink-0">
              <Shield className="w-5 h-5 sm:w-6 sm:h-6" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center space-x-2 flex-wrap">
                <h2 className="text-base sm:text-xl font-bold text-slate-900 truncate">
                  {data?.situation.title || 'Situation Intelligence'}
                </h2>
                <span className="text-xs font-mono px-2 py-0.5 bg-slate-200 text-slate-700 rounded font-semibold">
                  {situationId}
                </span>
              </div>
              <p className="text-xs text-slate-500 flex items-center gap-2 mt-0.5 truncate">
                <span>Cluster: {data?.situation.cluster_id}</span>
                <span>•</span>
                <span>{data?.situation.report_count} Report(s)</span>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 sm:p-2 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-200 transition-colors flex-shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-3 sm:p-6 overflow-y-auto flex-1 space-y-4 sm:space-y-6 touch-scroll">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center text-slate-500">
              <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mb-3" />
              <p className="text-sm font-medium">Synthesizing Situation Intelligence...</p>
            </div>
          ) : error && !data ? (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          ) : data ? (
            <>
              {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {/* Top Overview Cards */}
              <div className="grid grid-cols-1 xs:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                {/* Severity */}
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl flex flex-col justify-between">
                  <div>
                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                      Severity Assessment
                    </div>
                    <div className="flex items-center justify-between">
                      <span
                        className={`px-2.5 py-1 rounded-full text-xs font-bold border ${getSeverityBadgeClass(
                          data.situation.severity_level
                        )}`}
                      >
                        {data.situation.severity_level}
                      </span>
                      <span className="text-lg font-black text-slate-800">
                        {data.situation.severity_score.toFixed(1)}
                        <span className="text-xs text-slate-400 font-normal">/10</span>
                      </span>
                    </div>
                  </div>

                  {data.situation.officer_override_severity && (
                    <div className="mt-2 pt-2 border-t border-amber-200 bg-amber-50/70 -mx-1 px-2 py-1 rounded text-[11px]">
                      <div className="flex items-center gap-1 font-bold text-amber-800">
                        <Shield className="w-3 h-3 text-amber-600" />
                        <span>Officer Override</span>
                      </div>
                      <div className="text-[10px] text-amber-900/80 truncate">
                        AI Baseline: {data.situation.computed_severity_level || data.situation.assessment?.severity_level || 'N/A'} ({(data.situation.computed_severity_score ?? data.situation.assessment?.severity_score ?? 0).toFixed(1)})
                      </div>
                    </div>
                  )}
                </div>

                {/* Impact Radius */}
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                    Impact Zone Radius
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-blue-700 font-bold text-lg">
                      <Compass className="w-4 h-4" />
                      <span>~{data.situation.impact_zone.radius_km} km</span>
                    </div>
                    <span className="text-[10px] text-slate-500 bg-slate-200 px-1.5 py-0.5 rounded">
                      Estimated
                    </span>
                  </div>
                </div>

                {/* Affected Population */}
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                    Est. Population
                  </div>
                  <div className="flex items-center gap-2 text-slate-800 font-bold text-lg">
                    <Users className="w-4 h-4 text-slate-500" />
                    <span>~{data.situation.estimated_affected_population.toLocaleString()}</span>
                  </div>
                </div>

                {/* Confidence */}
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">
                    Evidence Confidence
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-lg font-bold text-emerald-700">
                      {Math.round(data.situation.confidence * 100)}%
                    </span>
                    <div className="w-16 bg-slate-200 h-2 rounded-full overflow-hidden">
                      <div
                        className="bg-emerald-600 h-full rounded-full"
                        style={{ width: `${Math.round(data.situation.confidence * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* AI Situation Summary Card */}
              <div className="p-5 bg-gradient-to-br from-blue-50/70 to-indigo-50/70 border border-blue-200 rounded-xl relative">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-blue-900 font-bold text-sm">
                    <Sparkles className="w-4 h-4 text-blue-600" />
                    <span>Situation Assessment Summary</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-medium px-2 py-0.5 bg-blue-100 text-blue-800 rounded border border-blue-200">
                      {data.situation.assessment?.generated_by || 'AI / Heuristic Engine'}
                    </span>
                    <button
                      onClick={handleTriggerAssessment}
                      disabled={actionLoading}
                      className="text-xs font-medium text-blue-700 hover:text-blue-900 flex items-center gap-1 bg-white px-2.5 py-1 rounded-md border border-blue-200 shadow-sm hover:bg-blue-50 transition-colors"
                    >
                      <RefreshCw className={`w-3 h-3 ${actionLoading ? 'animate-spin' : ''}`} />
                      <span>Refresh Assessment</span>
                    </button>
                  </div>
                </div>
                <p className="text-sm text-slate-800 leading-relaxed">
                  {data.situation.situation_summary}
                </p>

                {/* Hazard Risk */}
                <div className="mt-3 pt-3 border-t border-blue-200/60 flex items-start gap-2 text-xs text-slate-700">
                  <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-slate-900">Hazard & Expansion Risks: </span>
                    <span>{data.situation.hazard_risk}</span>
                  </div>
                </div>

                <div className="mt-2 text-[11px] text-slate-500 italic">
                  * Advisory intelligence. Emergency Officer confirmation is mandatory before operational actions.
                </div>
              </div>

              {/* Key Factors & Recommendations */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Explainable Key Factors */}
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
                  <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                    <Activity className="w-4 h-4 text-slate-500" />
                    <span>Explainable Severity Factors</span>
                  </h3>
                  <ul className="space-y-1.5 text-xs text-slate-700">
                    {(data.situation.assessment?.key_factors || data.situation.clustering_reasoning).map(
                      (factor, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-blue-600 mt-1.5 flex-shrink-0" />
                          <span>{factor}</span>
                        </li>
                      )
                    )}
                  </ul>
                </div>

                {/* Actionable Recommendations */}
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
                  <h3 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                    <FileText className="w-4 h-4 text-slate-500" />
                    <span>Advisory Recommendations</span>
                  </h3>
                  <ul className="space-y-1.5 text-xs text-slate-700">
                    {(data.situation.assessment?.recommendations || [
                      'Assess immediate on-ground resource needs.',
                      'Maintain monitoring and incident response posture.',
                    ]).map((rec, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <ChevronRight className="w-3.5 h-3.5 text-emerald-600 mt-0.5 flex-shrink-0" />
                        <span>{rec}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Multi-Source Corroboration & Conflict Intelligence */}
              {data.corroboration && (
                <div className="border border-slate-200 rounded-xl p-4 bg-slate-50/70 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ShieldCheck className="w-4 h-4 text-blue-600" />
                      <h3 className="text-sm font-bold text-slate-900">
                        Multi-Source Corroboration & Conflict Intelligence
                      </h3>
                    </div>
                    <span
                      className={`text-xs px-2.5 py-1 rounded-full border font-bold ${
                        data.corroboration.corroboration_status === 'CORROBORATED'
                          ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                          : data.corroboration.corroboration_status === 'PARTIALLY_CORROBORATED'
                          ? 'bg-blue-50 text-blue-800 border-blue-300'
                          : data.corroboration.corroboration_status === 'CONFLICTED'
                          ? 'bg-red-50 text-red-800 border-red-300'
                          : 'bg-slate-100 text-slate-700 border-slate-300'
                      }`}
                    >
                      {data.corroboration.corroboration_status.replace(/_/g, ' ')}
                    </span>
                  </div>

                  {data.corroboration.corroboration_status === 'CONFLICTED' && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2.5">
                      <ShieldAlert className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <div className="text-xs font-bold text-red-800">
                          CONFLICT DETECTED — HUMAN REVIEW REQUIRED
                        </div>
                        <p className="text-xs text-red-700 mt-0.5">
                          {data.corroboration.explanation}
                        </p>
                      </div>
                    </div>
                  )}

                  <div className="grid grid-cols-3 gap-2">
                    <div className="p-2.5 bg-emerald-50/60 border border-emerald-200 rounded-lg text-center">
                      <div className="text-[11px] font-semibold text-emerald-800">Supporting</div>
                      <div className="text-lg font-bold text-emerald-700">
                        {data.corroboration.supporting_source_count}
                      </div>
                    </div>
                    <div className="p-2.5 bg-red-50/60 border border-red-200 rounded-lg text-center">
                      <div className="text-[11px] font-semibold text-red-800">Conflicting</div>
                      <div className="text-lg font-bold text-red-700">
                        {data.corroboration.conflicting_source_count}
                      </div>
                    </div>
                    <div className="p-2.5 bg-slate-100/80 border border-slate-200 rounded-lg text-center">
                      <div className="text-[11px] font-semibold text-slate-700">Neutral</div>
                      <div className="text-lg font-bold text-slate-700">
                        {data.corroboration.neutral_source_count}
                      </div>
                    </div>
                  </div>

                  {/* Why this result? explanation toggle */}
                  <div className="pt-2 border-t border-slate-200">
                    <button
                      onClick={() => setShowCorroborationWhy(!showCorroborationWhy)}
                      className="text-xs font-semibold text-blue-700 hover:text-blue-900 flex items-center justify-between w-full"
                    >
                      <div className="flex items-center gap-1.5">
                        <Info className="w-3.5 h-3.5" />
                        <span>Why this result?</span>
                      </div>
                      {showCorroborationWhy ? (
                        <ChevronUp className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </button>

                    {showCorroborationWhy && (
                      <div className="mt-2 text-xs text-slate-700 bg-white p-3 rounded-lg border border-slate-200 space-y-2">
                        <p className="leading-relaxed">{data.corroboration.explanation}</p>
                        {data.corroboration.corroboration_factors?.length > 0 && (
                          <div>
                            <div className="font-semibold text-slate-800 text-[11px] uppercase mb-1">
                              Supporting Factors:
                            </div>
                            <ul className="list-disc list-inside space-y-0.5 text-slate-600 pl-1">
                              {data.corroboration.corroboration_factors.map((f, i) => (
                                <li key={i}>{f}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {data.corroboration.conflict_factors?.length > 0 && (
                          <div>
                            <div className="font-semibold text-red-800 text-[11px] uppercase mb-1">
                              Conflict Factors:
                            </div>
                            <ul className="list-disc list-inside space-y-0.5 text-red-600 pl-1">
                              {data.corroboration.conflict_factors.map((f, i) => (
                                <li key={i}>{f}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {data.corroboration.recommendations?.length > 0 && (
                          <div className="pt-1.5 border-t border-slate-100">
                            <div className="font-semibold text-slate-800 text-[11px] uppercase mb-1">
                              Advisory Recommendations:
                            </div>
                            <ul className="list-disc list-inside space-y-0.5 text-slate-600 pl-1">
                              {data.corroboration.recommendations.map((r, i) => (
                                <li key={i}>{r}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Advisory Predictive Intelligence Panel (Phase 1) */}
              <PredictiveIntelligencePanel incidentId={situationId} />

              {/* Evidence & Operational Sources Console */}
              <div className="border border-slate-200 rounded-xl p-4 bg-white space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-blue-600" />
                    <h3 className="text-sm font-bold text-slate-900">
                      Corroborating Evidence & Incident Sources
                    </h3>
                  </div>
                  
                  {/* Evidence Category Filter Tabs */}
                  <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg text-xs font-semibold">
                    <button
                      onClick={() => setEvidenceTab('ALL')}
                      className={`px-2.5 py-1 rounded-md transition ${
                        evidenceTab === 'ALL'
                          ? 'bg-white text-slate-900 shadow-2xs font-bold'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      All ({(data.clustered_reports?.length || 0) + (data.sensor_evidence?.length || 0)})
                    </button>
                    <button
                      onClick={() => setEvidenceTab('CITIZEN')}
                      className={`px-2.5 py-1 rounded-md transition flex items-center gap-1.5 ${
                        evidenceTab === 'CITIZEN'
                          ? 'bg-white text-blue-700 shadow-2xs font-bold'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <span>Citizen Reports</span>
                      <span className="px-1.5 py-0.2 bg-blue-100 text-blue-800 rounded text-[10px]">
                        {data.clustered_reports?.length || 0}
                      </span>
                    </button>
                    <button
                      onClick={() => setEvidenceTab('SENSORS')}
                      className={`px-2.5 py-1 rounded-md transition flex items-center gap-1.5 ${
                        evidenceTab === 'SENSORS'
                          ? 'bg-white text-purple-700 shadow-2xs font-bold'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      <span>IoT Sensors</span>
                      <span className="px-1.5 py-0.2 bg-purple-100 text-purple-800 rounded text-[10px]">
                        {data.sensor_evidence?.length || 0}
                      </span>
                    </button>
                  </div>
                </div>

                <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
                  {/* Citizen Reports List */}
                  {(evidenceTab === 'ALL' || evidenceTab === 'CITIZEN') && (
                    <div className="space-y-2">
                      {evidenceTab === 'ALL' && data.clustered_reports?.length > 0 && (
                        <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                          <Users className="w-3 h-3" />
                          <span>Citizen Emergency Reports ({data.clustered_reports.length})</span>
                        </div>
                      )}
                      {data.clustered_reports?.map((rep) => (
                        <div
                          key={rep.report_id}
                          className="p-3 bg-slate-50 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors flex items-center justify-between"
                        >
                          <div className="flex-1 min-w-0 mr-3">
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className="text-xs font-bold text-slate-900 font-mono">
                                {rep.report_id}
                              </span>
                              <span className="text-[11px] px-2 py-0.2 bg-blue-100 text-blue-800 rounded font-medium">
                                {rep.emergency_type}
                              </span>
                              <span className="text-xs text-slate-400">
                                {rep.distance_to_center_km > 0
                                  ? `~${rep.distance_to_center_km.toFixed(2)} km from center`
                                  : 'Cluster primary'}
                              </span>
                            </div>
                            <p className="text-xs text-slate-600 truncate">{rep.description}</p>
                            <p className="text-[11px] text-slate-400 truncate mt-0.5 flex items-center gap-1">
                              <MapPin className="w-3 h-3" />
                              <span>{rep.address || `${rep.latitude.toFixed(4)}, ${rep.longitude.toFixed(4)}`}</span>
                            </p>
                          </div>

                          {onViewReport && (
                            <button
                              onClick={() => {
                                onClose();
                                onViewReport(rep.report_id);
                              }}
                              className="px-2.5 py-1.5 text-xs font-semibold text-blue-700 hover:text-blue-900 bg-white border border-slate-200 hover:border-blue-300 rounded-md flex items-center gap-1 transition-colors shadow-xs"
                            >
                              <span>Inspect Report</span>
                              <ExternalLink className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      ))}
                      {evidenceTab === 'CITIZEN' && (!data.clustered_reports || data.clustered_reports.length === 0) && (
                        <div className="p-4 text-center text-xs text-slate-400 bg-slate-50 rounded-lg border border-slate-200">
                          No citizen reports currently clustered in this situation.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Sensor Evidence List */}
                  {(evidenceTab === 'ALL' || evidenceTab === 'SENSORS') && (
                    <div className="space-y-2">
                      {evidenceTab === 'ALL' && data.sensor_evidence && data.sensor_evidence.length > 0 && (
                        <div className="text-[11px] font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1 pt-1">
                          <Radio className="w-3 h-3 text-purple-600" />
                          <span>Corroborating IoT Sensor Telemetry ({data.sensor_evidence.length})</span>
                        </div>
                      )}
                      {data.sensor_evidence && data.sensor_evidence.length > 0 ? (
                        data.sensor_evidence.map((sensor) => (
                          <div
                            key={sensor.sensor_id}
                            className={`p-3 rounded-lg border transition-colors ${
                              sensor.is_breach
                                ? 'bg-red-50/60 border-red-200'
                                : 'bg-slate-50 border-slate-200'
                            }`}
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                              <div className="flex items-center gap-2">
                                <Radio className={`w-3.5 h-3.5 ${sensor.is_breach ? 'text-red-600' : 'text-purple-600'}`} />
                                <span className="text-xs font-bold text-slate-900">
                                  {sensor.sensor_name}
                                </span>
                                <span className="font-mono text-[10px] text-slate-500">
                                  {sensor.sensor_id}
                                </span>
                                <span className="text-[10px] px-1.5 py-0.2 bg-purple-100 text-purple-800 rounded font-medium">
                                  {sensor.sensor_type}
                                </span>
                              </div>

                              {/* SIMULATED SENSOR Transparency Badge & Breach State */}
                              <div className="flex items-center gap-1.5">
                                <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-cyan-100 text-cyan-800 border border-cyan-300">
                                  SIMULATED SENSOR
                                </span>
                                {(() => {
                                  const ageSec = sensor.timestamp ? (Date.now() - new Date(sensor.timestamp).getTime()) / 1000 : 9999;
                                  if (ageSec > 300) {
                                    return (
                                      <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-amber-100 text-amber-800 border border-amber-300">
                                        STALE DATA (&gt;5m)
                                      </span>
                                    );
                                  }
                                  return (
                                    <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-emerald-100 text-emerald-800 border border-emerald-300">
                                      FRESH
                                    </span>
                                  );
                                })()}
                                {sensor.threshold_state === 'BREACHED' ? (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-red-100 text-red-800 border border-red-300 flex items-center gap-1">
                                    <AlertTriangle className="w-2.5 h-2.5" />
                                    CRITICAL BREACH
                                  </span>
                                ) : sensor.threshold_state === 'RECOVERED' ? (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-blue-100 text-blue-800 border border-blue-300">
                                    RECOVERED
                                  </span>
                                ) : (
                                  <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-emerald-100 text-emerald-800 border border-emerald-300">
                                    NORMAL
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Telemetry Metrics & Location Comparison */}
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 my-2 text-xs">
                              <div className="p-2 rounded-md bg-white border border-slate-200">
                                <span className="text-[10px] text-slate-400 font-semibold uppercase block">Live Reading</span>
                                <span className={`font-mono font-black ${sensor.is_breach ? 'text-red-600' : 'text-slate-900'}`}>
                                  {sensor.current_value} {sensor.unit}
                                </span>
                              </div>
                              <div className="p-2 rounded-md bg-white border border-slate-200">
                                <span className="text-[10px] text-slate-400 font-semibold uppercase block">Alert Threshold</span>
                                <span className="font-mono font-bold text-slate-700">
                                  &gt; {sensor.threshold} {sensor.unit}
                                </span>
                              </div>
                              <div className="p-2 rounded-md bg-white border border-slate-200">
                                <span className="text-[10px] text-slate-400 font-semibold uppercase block">Coverage Radius</span>
                                <span className="font-mono font-bold text-red-700">
                                  {sensor.coverage_radius_km ? `${sensor.coverage_radius_km.toFixed(2)} km` : '2.00 km'}
                                </span>
                              </div>
                              <div className="p-2 rounded-md bg-white border border-slate-200">
                                <span className="text-[10px] text-slate-400 font-semibold uppercase block">Distance to Center</span>
                                <span className="font-mono font-bold text-slate-800">
                                  ~{sensor.distance_to_center_km.toFixed(2)} km away
                                </span>
                              </div>
                            </div>

                            {/* Detailed Location & Spatial Evidence Summary */}
                            <div className="space-y-1 pt-1.5 border-t border-slate-200/70 text-[11px]">
                              <div className="flex flex-wrap items-center justify-between gap-1 text-slate-600">
                                <span>
                                  <strong className="text-slate-800">Sensor Location:</strong> {sensor.sensor_address || sensor.location_name || 'Station Location'}
                                </span>
                                <span className="font-mono text-[10px] text-slate-500">
                                  GPS: {sensor.latitude.toFixed(6)}, {sensor.longitude.toFixed(6)}
                                </span>
                              </div>

                              <div className="flex flex-wrap items-center justify-between gap-1 text-slate-500 text-[10px]">
                                <span className="truncate">
                                  <strong className="text-slate-700">Spatial Correlation:</strong> {sensor.correlation_reason}
                                </span>
                                <span className="font-mono text-slate-400">
                                  {new Date(sensor.timestamp).toLocaleTimeString()}
                                </span>
                              </div>
                            </div>
                          </div>
                        ))
                      ) : (
                        evidenceTab === 'SENSORS' && (
                          <div className="p-4 text-center text-xs text-slate-400 bg-slate-50 rounded-lg border border-slate-200">
                            No active IoT sensors or simulated breach events currently correlated with this situation area.
                          </div>
                        )
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Incident Evolution Timeline */}
              <IncidentEvolutionTimeline
                targetId={situationId}
                targetType="SITUATION"
              />

              {/* Officer Human-in-the-Loop Review Section */}
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Shield className="w-4 h-4 text-slate-700" />
                    <h3 className="text-sm font-bold text-slate-900">
                      Emergency Officer Review & Authority
                    </h3>
                  </div>
                  {data.situation.officer_review && (
                    <span className="text-xs font-semibold px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded border border-emerald-200">
                      Reviewed by {data.situation.officer_review.reviewed_by_name} ({data.situation.officer_review.action})
                    </span>
                  )}
                </div>

                {reviewMode ? (
                  <div className="space-y-3 bg-white p-4 rounded-lg border border-slate-200">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-800">
                        Action: {reviewMode} Assessment
                      </span>
                      <button
                        onClick={() => setReviewMode(null)}
                        className="text-xs text-slate-400 hover:text-slate-600"
                      >
                        Cancel
                      </button>
                    </div>

                    {reviewMode === 'MODIFY' && (
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-semibold text-slate-700 mb-1">
                            Operational Severity Level
                          </label>
                          <select
                            value={modifiedSeverity}
                            onChange={(e) => setModifiedSeverity(e.target.value as SeverityLevel)}
                            className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500 bg-white"
                          >
                            <option value="CRITICAL">CRITICAL</option>
                            <option value="HIGH">HIGH</option>
                            <option value="MEDIUM">MEDIUM</option>
                            <option value="LOW">LOW</option>
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-700 mb-1">
                            Operational Severity Score (0-10)
                          </label>
                          <input
                            type="number"
                            step="0.1"
                            min="0"
                            max="10"
                            value={modifiedScore}
                            onChange={(e) => setModifiedScore(parseFloat(e.target.value) || 0)}
                            className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                      </div>
                    )}

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Operational Notes & Justification
                      </label>
                      <textarea
                        rows={2}
                        value={reviewNotes}
                        onChange={(e) => setReviewNotes(e.target.value)}
                        placeholder="Add on-ground observations or reasons for modification/rejection..."
                        className="w-full px-3 py-1.5 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500"
                      />
                    </div>

                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setReviewMode(null)}
                        className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-lg"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSubmitReview}
                        disabled={actionLoading}
                        className="px-4 py-1.5 text-xs font-bold text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
                      >
                        {actionLoading ? 'Saving...' : 'Confirm Review'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {onOpenCoordination && data && (
                      <button
                        type="button"
                        onClick={() => onOpenCoordination(data.situation.situation_id, data.situation.title, data.situation.emergency_type)}
                        className="px-3.5 py-2 text-xs font-bold text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 rounded-lg flex items-center gap-1.5 transition-colors"
                      >
                        <Layers className="w-4 h-4 text-red-600" />
                        <span>Run AI Multi-Agent Coordination</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setShowVerificationModal(true)}
                      className="px-3.5 py-2 text-xs font-bold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-300 rounded-lg flex items-center gap-1.5 transition-colors"
                    >
                      <Eye className="w-4 h-4" />
                      <span>Live Ground Verification</span>
                    </button>
                    <button
                      onClick={() => {
                        setReviewMode('ACCEPT');
                        handleSubmitReview();
                      }}
                      disabled={actionLoading}
                      className="px-3.5 py-2 text-xs font-bold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-300 rounded-lg flex items-center gap-1.5 transition-colors"
                    >
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Accept Assessment</span>
                    </button>
                    <button
                      onClick={() => setReviewMode('MODIFY')}
                      disabled={actionLoading}
                      className="px-3.5 py-2 text-xs font-bold text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-300 rounded-lg flex items-center gap-1.5 transition-colors"
                    >
                      <Edit3 className="w-4 h-4" />
                      <span>Modify Operational Severity</span>
                    </button>
                    {data.situation.officer_override_severity && (
                      <button
                        onClick={handleResetOverride}
                        disabled={actionLoading}
                        title="Clear officer override and revert to AI/computed assessment"
                        className="px-3.5 py-2 text-xs font-bold text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-300 rounded-lg flex items-center gap-1.5 transition-colors"
                      >
                        <RotateCcw className="w-4 h-4" />
                        <span>Reset to AI Baseline</span>
                      </button>
                    )}
                    <button
                      onClick={() => setReviewMode('REJECT')}
                      disabled={actionLoading}
                      className="px-3.5 py-2 text-xs font-bold text-red-700 bg-red-50 hover:bg-red-100 border border-red-300 rounded-lg flex items-center gap-1.5 transition-colors"
                    >
                      <XCircle className="w-4 h-4" />
                      <span>Reject Assessment</span>
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>

        {/* Live Field Verification Modal */}
        {showVerificationModal && data && (
          <SubmitFieldVerificationModal
            isOpen={showVerificationModal}
            onClose={() => setShowVerificationModal(false)}
            targetId={data.situation.situation_id}
            targetType="SITUATION"
            targetTitle={data.situation.title}
            targetCoords={
              data.situation.center_location
                ? {
                    latitude: data.situation.center_location.latitude,
                    longitude: data.situation.center_location.longitude,
                  }
                : null
            }
            onSuccess={() => {
              fetchDetail();
            }}
          />
        )}

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
          <span className="text-xs text-slate-500">
            Resilience AI Emergency Response Platform • Situation Intelligence
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-200 rounded-lg transition-colors border border-slate-300"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
