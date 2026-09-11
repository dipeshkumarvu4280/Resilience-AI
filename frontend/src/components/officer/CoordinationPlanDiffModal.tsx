import React, { useState, useEffect } from 'react';
import {
  X,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowRight,
  ShieldAlert,
  Layers,
  FileText,
  GitBranch,
  RefreshCw,
  Building2,
  Truck,
  Users,
  HeartPulse,
  Package,
  Route as RouteIcon,
} from 'lucide-react';
import type {
  CoordinationPlan,
  PlanDiffResult,
  PlanApprovalRequest,
  PlanRejectRequest,
} from '../../types';
import {
  getPlanDiff,
  getSituationPlanHistory,
  approveAndActivatePlan,
  rejectRevisedPlan,
} from '../../services/api';

interface CoordinationPlanDiffModalProps {
  plan: CoordinationPlan;
  isOpen: boolean;
  onClose: () => void;
  onPlanActivated?: () => void;
  initialDiffResult?: PlanDiffResult | null;
}

export const CoordinationPlanDiffModal: React.FC<CoordinationPlanDiffModalProps> = ({
  plan,
  isOpen,
  onClose,
  onPlanActivated,
  initialDiffResult,
}) => {
  const [activeTab, setActiveTab] = useState<'diff' | 'history' | 'explanation'>('diff');
  const [filterType, setFilterType] = useState<string>('ALL');
  const [diffResult, setDiffResult] = useState<PlanDiffResult | null>(initialDiffResult || null);
  const [planHistory, setPlanHistory] = useState<CoordinationPlan[]>([]);
  const [loading, setLoading] = useState<boolean>(!initialDiffResult && !plan?.diff_summary);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Approval Dialog State
  const [showApproveModal, setShowApproveModal] = useState<boolean>(false);
  const [officerNotes, setOfficerNotes] = useState<string>('');

  // Rejection Dialog State
  const [showRejectModal, setShowRejectModal] = useState<boolean>(false);
  const [rejectionReason, setRejectionReason] = useState<string>('');

  useEffect(() => {
    if (isOpen && plan?.plan_id) {
      loadDiffAndHistory();
    }
  }, [isOpen, plan?.plan_id, initialDiffResult]);

  const loadDiffAndHistory = async () => {
    setErrorMsg(null);
    if (initialDiffResult) {
      setDiffResult(initialDiffResult);
    } else if (plan.diff_summary) {
      setDiffResult(plan.diff_summary as PlanDiffResult);
    } else {
      setLoading(true);
    }

    try {
      if (!initialDiffResult && !plan.diff_summary) {
        const diffData = await getPlanDiff(plan.plan_id);
        setDiffResult(diffData);
      }
      if (plan.situation_id) {
        const historyData = await getSituationPlanHistory(plan.situation_id).catch(() => []);
        setPlanHistory(historyData);
      }
    } catch (err: any) {
      if (!diffResult && !initialDiffResult && !plan.diff_summary) {
        setErrorMsg(err?.response?.data?.detail || 'Failed to load plan diff details.');
      }
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const handleApprove = async () => {
    setActionLoading(true);
    setErrorMsg(null);
    try {
      const payload: PlanApprovalRequest = {
        officer_notes: officerNotes || undefined,
        expected_state_fingerprint: plan.state_fingerprint || undefined,
      };
      await approveAndActivatePlan(plan.plan_id, payload);
      setSuccessMsg(`Plan ${plan.plan_id} (v${plan.version}) has been approved and ACTIVATED.`);
      setShowApproveModal(false);
      if (onPlanActivated) onPlanActivated();
      setTimeout(() => {
        onClose();
      }, 1500);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'Failed to activate plan.');
      setShowApproveModal(false);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!rejectionReason.trim()) {
      setErrorMsg('A rejection reason is required.');
      return;
    }
    setActionLoading(true);
    setErrorMsg(null);
    try {
      const payload: PlanRejectRequest = {
        rejection_reason: rejectionReason,
        officer_notes: officerNotes || undefined,
      };
      await rejectRevisedPlan(plan.plan_id, payload);
      setSuccessMsg(`Plan ${plan.plan_id} has been REJECTED. Previous active plan remains in effect.`);
      setShowRejectModal(false);
      if (onPlanActivated) onPlanActivated();
      setTimeout(() => {
        onClose();
      }, 1500);
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'Failed to reject plan.');
      setShowRejectModal(false);
    } finally {
      setActionLoading(false);
    }
  };

  const renderValue = (val: any) => {
    if (val === null || val === undefined) return 'None';
    if (typeof val === 'number') return `${val}`;
    if (typeof val === 'string') return val;
    if (typeof val === 'object') {
      return Object.entries(val)
        .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'number' ? v : String(v)}`)
        .join(' | ');
    }
    return String(val);
  };

  const filteredItems = (diffResult?.items || []).filter((item) => {
    if (filterType === 'ALL') return true;
    return item.diff_type === filterType;
  });

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'Resource':
        return <Package className="w-4 h-4 text-blue-600" />;
      case 'Shelter':
        return <Building2 className="w-4 h-4 text-amber-600" />;
      case 'Healthcare':
        return <HeartPulse className="w-4 h-4 text-emerald-600" />;
      case 'Volunteer':
        return <Users className="w-4 h-4 text-purple-600" />;
      case 'Transport':
        return <Truck className="w-4 h-4 text-indigo-600" />;
      case 'Route':
        return <RouteIcon className="w-4 h-4 text-teal-600" />;
      default:
        return <Layers className="w-4 h-4 text-slate-600" />;
    }
  };

  const getDiffBadge = (type: string) => {
    switch (type) {
      case 'ADDED':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
            ADDED
          </span>
        );
      case 'REMOVED':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-red-100 text-red-800 border border-red-200">
            REMOVED
          </span>
        );
      case 'CHANGED':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-amber-100 text-amber-800 border border-amber-200">
            CHANGED
          </span>
        );
      case 'UNCHANGED':
        return (
          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-slate-100 text-slate-700 border border-slate-200">
            PRESERVED
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-2 sm:p-4 md:p-6">
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-5xl max-h-[calc(100dvh-1rem)] sm:max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        
        {/* Header */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between min-w-0">
          <div className="flex items-center space-x-2.5 sm:space-x-3 min-w-0">
            <div className="p-2 bg-red-100 text-red-700 rounded-xl flex-shrink-0">
              <GitBranch className="w-5 h-5 sm:w-6 sm:h-6" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center space-x-2 flex-wrap">
                <h2 className="text-base sm:text-lg font-bold text-slate-900 truncate">
                  {plan.is_simulation || plan.status === 'SIMULATION_RESULT'
                    ? 'What-If Simulation Plan Diff'
                    : 'Response Plan Review & Lineage'}
                </h2>
                <span className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                  plan.is_simulation || plan.status === 'SIMULATION_RESULT'
                    ? 'bg-purple-100 text-purple-800 border border-purple-200'
                    : 'bg-red-100 text-red-700 border border-red-200'
                }`}>
                  v{plan.version}
                </span>
                <span className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                  plan.is_simulation || plan.status === 'SIMULATION_RESULT'
                    ? 'bg-purple-100 text-purple-800 border border-purple-300'
                    : plan.status === 'ACTIVE'
                    ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                    : plan.status === 'REJECTED'
                    ? 'bg-red-100 text-red-800 border border-red-200'
                    : 'bg-amber-100 text-amber-800 border border-amber-200'
                }`}>
                  {plan.is_simulation || plan.status === 'SIMULATION_RESULT'
                    ? 'SIMULATION'
                    : plan.status.replace(/_/g, ' ')}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5 truncate">
                Plan ID: <code className="font-mono text-slate-700">{plan.plan_id}</code> | Situation:{' '}
                <code className="font-mono text-slate-700">{plan.situation_id}</code>
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

        {/* Alerts / Error Banner */}
        {errorMsg && (
          <div className="px-6 py-3 bg-red-50 border-b border-red-200 flex items-center space-x-2 text-red-700 text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span className="font-medium">{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="px-6 py-3 bg-emerald-50 border-b border-emerald-200 flex items-center space-x-2 text-emerald-700 text-sm">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
            <span className="font-medium">{successMsg}</span>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="px-6 border-b border-slate-200 bg-white flex space-x-6">
          <button
            onClick={() => setActiveTab('diff')}
            className={`py-3 text-sm font-semibold border-b-2 flex items-center space-x-2 transition-colors ${
              activeTab === 'diff'
                ? 'border-red-600 text-red-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <Layers className="w-4 h-4" />
            <span>Plan Deltas & Comparison</span>
          </button>
          <button
            onClick={() => setActiveTab('explanation')}
            className={`py-3 text-sm font-semibold border-b-2 flex items-center space-x-2 transition-colors ${
              activeTab === 'explanation'
                ? 'border-red-600 text-red-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <FileText className="w-4 h-4" />
            <span>Change Explanation & Root Cause</span>
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`py-3 text-sm font-semibold border-b-2 flex items-center space-x-2 transition-colors ${
              activeTab === 'history'
                ? 'border-red-600 text-red-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            <Clock className="w-4 h-4" />
            <span>Version Lineage ({planHistory.length})</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 text-slate-400">
              <RefreshCw className="w-8 h-8 animate-spin mb-3 text-red-600" />
              <p className="text-sm font-medium">Computing deterministic plan diff and lineage...</p>
            </div>
          ) : (
            <>
              {/* TAB 1: PLAN DIFF */}
              {activeTab === 'diff' && (
                <div className="space-y-4">
                  {/* Summary Bar */}
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div>
                      <h4 className="text-sm font-bold text-slate-900">
                        {diffResult?.summary || 'Plan Deltas vs Previous Version'}
                      </h4>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Baseline:{' '}
                        <span className="font-semibold text-slate-700">
                          {diffResult?.previous_plan_id} (v{diffResult?.previous_version})
                        </span>{' '}
                        → Revised:{' '}
                        <span className="font-semibold text-slate-700">
                          {diffResult?.new_plan_id} (v{diffResult?.new_version})
                        </span>
                      </p>
                    </div>

                    {/* Filter Buttons */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      {['ALL', 'CHANGED', 'ADDED', 'REMOVED', 'UNCHANGED'].map((type) => (
                        <button
                          key={type}
                          onClick={() => setFilterType(type)}
                          className={`px-2.5 py-1 text-xs font-semibold rounded-lg transition-colors ${
                            filterType === type
                              ? 'bg-red-600 text-white shadow-sm'
                              : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                          }`}
                        >
                          {type === 'UNCHANGED' ? 'PRESERVED' : type}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Diff Items List */}
                  {filteredItems.length === 0 ? (
                    <div className="py-12 text-center text-slate-400 border-2 border-dashed border-slate-200 rounded-xl">
                      <Layers className="w-8 h-8 mx-auto mb-2 opacity-50" />
                      <p className="text-sm">No items matching the selected diff filter.</p>
                    </div>
                  ) : (
                    <div className="space-y-2.5">
                      {filteredItems.map((item, idx) => (
                        <div
                          key={idx}
                          className={`p-4 rounded-xl border transition-all ${
                            item.diff_type === 'CHANGED'
                              ? 'bg-amber-50/50 border-amber-200'
                              : item.diff_type === 'ADDED'
                              ? 'bg-emerald-50/50 border-emerald-200'
                              : item.diff_type === 'REMOVED'
                              ? 'bg-red-50/50 border-red-200'
                              : 'bg-white border-slate-200'
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex items-start space-x-3">
                              <div className="p-1.5 bg-white border border-slate-200 rounded-lg mt-0.5">
                                {getCategoryIcon(item.category)}
                              </div>
                              <div>
                                <div className="flex items-center space-x-2">
                                  <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                                    {item.category}
                                  </span>
                                  <span className="text-sm font-bold text-slate-900">
                                    {item.entity_name}
                                  </span>
                                  {getDiffBadge(item.diff_type)}
                                  {item.requires_officer_attention && (
                                    <span className="px-2 py-0.5 text-xs font-bold rounded-full bg-red-100 text-red-700 border border-red-200">
                                      Officer Attention
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-600 mt-1">{item.reason}</p>
                              </div>
                            </div>

                            {/* Value Delta Display */}
                            {(item.previous_value !== undefined || item.new_value !== undefined) && (
                              <div className="text-right flex items-center space-x-2 text-xs font-mono">
                                {item.previous_value !== null && item.previous_value !== undefined && (
                                  <span className="text-slate-500 line-through bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                                    {renderValue(item.previous_value)}
                                  </span>
                                )}
                                {item.previous_value !== null &&
                                  item.previous_value !== undefined &&
                                  item.new_value !== null &&
                                  item.new_value !== undefined && (
                                    <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                                  )}
                                {item.new_value !== null && item.new_value !== undefined && (
                                  <span className={`font-bold px-2 py-0.5 rounded border ${
                                    item.diff_type === 'CHANGED'
                                      ? 'text-amber-900 bg-amber-100 border-amber-300'
                                      : item.diff_type === 'ADDED'
                                      ? 'text-emerald-900 bg-emerald-100 border-emerald-300'
                                      : item.diff_type === 'REMOVED'
                                      ? 'text-red-900 bg-red-100 border-red-300'
                                      : 'text-slate-900 bg-white border-slate-200'
                                  }`}>
                                    {renderValue(item.new_value)}
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: EXPLANATION */}
              {activeTab === 'explanation' && (
                <div className="space-y-4">
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-4">
                    <div>
                      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                        Root Cause & Rationale
                      </h4>
                      <div className="text-sm text-slate-800 whitespace-pre-line leading-relaxed font-sans bg-white p-4 rounded-lg border border-slate-200">
                        {plan.change_explanation || plan.reasoning || 'No structured explanation available.'}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                      <div className="p-3 bg-white rounded-lg border border-slate-200">
                        <span className="text-xs font-semibold text-slate-500 block mb-1">Trigger Event</span>
                        <span className="text-xs font-mono font-bold text-slate-800">
                          {plan.trigger_event_id || 'Initial Orchestration'}
                        </span>
                      </div>
                      <div className="p-3 bg-white rounded-lg border border-slate-200">
                        <span className="text-xs font-semibold text-slate-500 block mb-1">Correlated Impact ID</span>
                        <span className="text-xs font-mono font-bold text-slate-800">
                          {plan.impact_id || 'N/A'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: VERSION HISTORY */}
              {activeTab === 'history' && (
                <div className="space-y-3">
                  {planHistory.map((hPlan) => (
                    <div
                      key={hPlan.plan_id}
                      className={`p-4 rounded-xl border flex items-center justify-between ${
                        hPlan.plan_id === plan.plan_id
                          ? 'bg-red-50/40 border-red-300 ring-1 ring-red-200'
                          : 'bg-white border-slate-200'
                      }`}
                    >
                      <div className="flex items-center space-x-3">
                        <div className="p-2 bg-slate-100 rounded-lg text-slate-600 font-bold text-xs">
                          v{hPlan.version}
                        </div>
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="text-sm font-bold text-slate-900">{hPlan.plan_id}</span>
                            <span className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                              hPlan.status === 'ACTIVE'
                                ? 'bg-emerald-100 text-emerald-800'
                                : hPlan.status === 'REJECTED'
                                ? 'bg-red-100 text-red-800'
                                : hPlan.status === 'SUPERSEDED'
                                ? 'bg-slate-100 text-slate-600'
                                : 'bg-amber-100 text-amber-800'
                            }`}>
                              {hPlan.status.replace(/_/g, ' ')}
                            </span>
                            {hPlan.plan_id === plan.plan_id && (
                              <span className="text-xs font-semibold text-red-600">(Current Selection)</span>
                            )}
                          </div>
                          <p className="text-xs text-slate-500 mt-0.5">
                            Generated: {new Date(hPlan.generated_at).toLocaleString()}
                          </p>
                        </div>
                      </div>

                      <div className="text-right text-xs text-slate-600">
                        {hPlan.officer_review ? (
                          <span>
                            Reviewed by {hPlan.officer_review.reviewed_by_name} (
                            {hPlan.officer_review.decision})
                          </span>
                        ) : (
                          <span className="text-amber-600 font-medium">Pending Officer Review</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Actions (Human-in-the-Loop or Simulation Notice) */}
        <div className="px-6 py-4 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
          <div className="text-xs text-slate-500 flex items-center space-x-2">
            <ShieldAlert className="w-4 h-4 text-slate-400 shrink-0" />
            <span>
              {plan.is_simulation || plan.status === 'SIMULATION_RESULT'
                ? 'What-If Simulation Result — In-memory hypothetical plan diff isolated from live operations (Read-Only).'
                : 'Human Emergency Officer verification required prior to operational activation.'}
            </span>
          </div>

          <div className="flex items-center space-x-3">
            {plan.is_simulation || plan.status === 'SIMULATION_RESULT' ? (
              <span className="text-xs font-bold text-purple-700 px-3 py-1.5 bg-purple-50 border border-purple-200 rounded-xl">
                SIMULATION RESULT
              </span>
            ) : plan.status === 'PENDING_OFFICER_REVIEW' || plan.status === 'MODIFIED' ? (
              <>
                <button
                  onClick={() => setShowRejectModal(true)}
                  disabled={actionLoading}
                  className="px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 border border-red-200 rounded-xl transition-colors disabled:opacity-50 cursor-pointer"
                >
                  Reject Plan
                </button>
                <button
                  onClick={() => setShowApproveModal(true)}
                  disabled={actionLoading}
                  className="px-5 py-2 text-sm font-bold text-white bg-emerald-600 hover:bg-emerald-700 rounded-xl shadow-sm transition-colors flex items-center space-x-2 disabled:opacity-50 cursor-pointer"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Approve & Activate</span>
                </button>
              </>
            ) : (
              <span className="text-xs font-semibold text-slate-500 px-3 py-1 bg-slate-200 rounded-lg">
                Status: {plan.status}
              </span>
            )}
          </div>
        </div>

      </div>

      {/* APPROVAL CONFIRMATION MODAL */}
      {showApproveModal && (
        <div className="fixed inset-0 z-60 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-2xl max-w-md w-full space-y-4">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 bg-emerald-100 text-emerald-700 rounded-xl">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">Approve & Activate Plan</h3>
                <p className="text-xs text-slate-500">Plan ID: {plan.plan_id} (v{plan.version})</p>
              </div>
            </div>

            <p className="text-xs text-slate-600">
              Approving will immediately set this revised plan as the authoritative <strong>ACTIVE</strong>{' '}
              operational plan and <strong>SUPERSEDE</strong> previous versions. Stale plan protection will verify
              conditions prior to activation.
            </p>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Officer Review Notes (Optional)
              </label>
              <textarea
                value={officerNotes}
                onChange={(e) => setOfficerNotes(e.target.value)}
                placeholder="Add operational notes or confirmation remarks..."
                rows={3}
                className="w-full text-xs p-2.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div className="flex justify-end space-x-2 pt-2">
              <button
                onClick={() => setShowApproveModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleApprove}
                disabled={actionLoading}
                className="px-4 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg flex items-center space-x-1.5 disabled:opacity-50"
              >
                {actionLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Confirm & Activate</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* REJECTION MODAL */}
      {showRejectModal && (
        <div className="fixed inset-0 z-60 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-2xl max-w-md w-full space-y-4">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 bg-red-100 text-red-700 rounded-xl">
                <XCircle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">Reject Revised Plan</h3>
                <p className="text-xs text-slate-500">Plan ID: {plan.plan_id}</p>
              </div>
            </div>

            <p className="text-xs text-slate-600">
              Rejecting will mark this version as <strong>REJECTED</strong>. The previous active plan will remain
              operational if valid.
            </p>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Rejection Reason <span className="text-red-500">*</span>
              </label>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="Explain why this revised plan is rejected..."
                rows={3}
                required
                className="w-full text-xs p-2.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-red-500"
              />
            </div>

            <div className="flex justify-end space-x-2 pt-2">
              <button
                onClick={() => setShowRejectModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={actionLoading || !rejectionReason.trim()}
                className="px-4 py-2 text-xs font-bold text-white bg-red-600 hover:bg-red-700 rounded-lg flex items-center space-x-1.5 disabled:opacity-50"
              >
                {actionLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Confirm Rejection</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
