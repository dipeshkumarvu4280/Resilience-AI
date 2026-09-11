import React, { useState, useEffect } from 'react';
import {
  Boxes,
  Plus,
  Trash2,
  Sparkles,
  Zap,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Compass,
  Layers,
  ArrowRight,
  Info,
  Check,
} from 'lucide-react';
import type {
  EmergencyNeedItem,
  AINeedsSuggestionItem,
  ResourceMatchingResponse,
  AllocationResponse,
  ResourceType,
  NeedUrgency,
  ResourceMatchCandidate,
} from '../../types';
import {
  getReportNeeds,
  createOrUpdateReportNeeds,
  getAINeedsSuggestions,
  runResourceMatching,
  getReportAllocations,
  proposeAllocation,
  approveAllocation,
  rejectAllocation,
} from '../../services/api';

interface NeedsAndAllocationsPanelProps {
  reportId: string;
  onRefreshReport?: () => void;
}

const RESOURCE_TYPES: ResourceType[] = [
  'Water',
  'Food',
  'Medicine',
  'First Aid',
  'Medical Equipment',
  'Rescue Equipment',
  'Protective Equipment',
  'Blankets',
  'Clothing',
  'Generator',
  'Fuel',
  'Communication Equipment',
  'Transport',
  'Shelter',
  'Other',
];

const DEFAULT_UNITS: Record<string, string> = {
  Water: 'liters',
  Food: 'meals',
  Medicine: 'kits',
  'First Aid': 'kits',
  'Medical Equipment': 'units',
  'Rescue Equipment': 'units',
  'Protective Equipment': 'sets',
  Blankets: 'units',
  Clothing: 'sets',
  Generator: 'units',
  Fuel: 'liters',
  'Communication Equipment': 'units',
  Transport: 'vehicles',
  Shelter: 'tents',
  Other: 'units',
};

export const NeedsAndAllocationsPanel: React.FC<NeedsAndAllocationsPanelProps> = ({
  reportId,
  onRefreshReport,
}) => {
  // State: Needs
  const [needs, setNeeds] = useState<EmergencyNeedItem[]>([]);
  const [loadingNeeds, setLoadingNeeds] = useState(true);
  const [savingNeeds, setSavingNeeds] = useState(false);
  const [needsSavedMsg, setNeedsSavedMsg] = useState<string | null>(null);

  // State: AI Suggestions
  const [aiSuggestions, setAiSuggestions] = useState<AINeedsSuggestionItem[] | null>(null);
  const [loadingAi, setLoadingAi] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  // State: Resource Matching
  const [matchingData, setMatchingData] = useState<ResourceMatchingResponse | null>(null);
  const [loadingMatching, setLoadingMatching] = useState(false);
  const [matchingError, setMatchingError] = useState<string | null>(null);

  // State: Allocations
  const [allocations, setAllocations] = useState<AllocationResponse[]>([]);
  const [loadingAllocations, setLoadingAllocations] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [processingAllocationId, setProcessingAllocationId] = useState<string | null>(null);

  // Proposed quantity override state per candidate (string-based during typing)
  const [proposedQuantities, setProposedQuantities] = useState<Record<string, string>>({});

  // Initial Load
  const fetchNeedsAndAllocations = async () => {
    setLoadingNeeds(true);
    setLoadingAllocations(true);
    try {
      const [needsRes, allocRes] = await Promise.all([
        getReportNeeds(reportId),
        getReportAllocations(reportId),
      ]);
      if (needsRes && needsRes.needs) {
        setNeeds(needsRes.needs);
      } else {
        setNeeds([]);
      }
      setAllocations(allocRes || []);
    } catch (err: any) {
      console.error('Failed loading needs/allocations:', err);
    } finally {
      setLoadingNeeds(false);
      setLoadingAllocations(false);
    }
  };

  useEffect(() => {
    fetchNeedsAndAllocations();
  }, [reportId]);

  // Needs item management
  const handleAddNeed = () => {
    const newItem: EmergencyNeedItem = {
      need_id: `NEED-${Date.now()}-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
      resource_type: 'Water',
      requested_quantity: 10,
      unit: 'liters',
      urgency: 'HIGH',
      reason: '',
    };
    setNeeds((prev) => [...prev, newItem]);
  };

  const handleUpdateNeed = (index: number, field: keyof EmergencyNeedItem, value: any) => {
    setNeeds((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      if (field === 'resource_type') {
        updated[index].unit = DEFAULT_UNITS[value] || 'units';
      }
      return updated;
    });
  };

  const handleRemoveNeed = (index: number) => {
    setNeeds((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSaveNeeds = async () => {
    setSavingNeeds(true);
    setActionError(null);
    setNeedsSavedMsg(null);
    try {
      const res = await createOrUpdateReportNeeds(reportId, needs);
      setNeeds(res.needs);
      setNeedsSavedMsg('Needs assessment recorded.');
      onRefreshReport?.();
      setTimeout(() => setNeedsSavedMsg(null), 3000);
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to save needs assessment.');
    } finally {
      setSavingNeeds(false);
    }
  };

  // AI Assistance
  const handleFetchAISuggestions = async () => {
    setLoadingAi(true);
    setAiError(null);
    try {
      const res = await getAINeedsSuggestions(reportId);
      setAiSuggestions(res.suggestions);
    } catch (err: any) {
      setAiError(
        err?.response?.data?.detail ||
          'AI assistance is currently unavailable. Manual needs assessment is available.'
      );
    } finally {
      setLoadingAi(false);
    }
  };

  const handleAcceptAISuggestion = (suggestion: AINeedsSuggestionItem) => {
    const newItem: EmergencyNeedItem = {
      need_id: `NEED-${Date.now()}-${Math.random().toString(36).substring(2, 6).toUpperCase()}`,
      resource_type: suggestion.resource_type,
      requested_quantity: suggestion.suggested_quantity,
      unit: suggestion.unit,
      urgency: suggestion.urgency,
      reason: `[AI Suggestion] ${suggestion.reasoning}`,
    };
    setNeeds((prev) => [...prev, newItem]);
  };

  // Matching Engine
  const handleRunMatching = async () => {
    setLoadingMatching(true);
    setMatchingError(null);
    try {
      const res = await runResourceMatching(reportId);
      setMatchingData(res);
      // Pre-populate proposed quantities with recommended amounts as strings
      const initialQtyMap: Record<string, string> = {};
      res.needs_matches.forEach((nm) => {
        nm.candidates.forEach((cand) => {
          const key = `${nm.need_id}_${cand.resource_id}`;
          initialQtyMap[key] = String(cand.recommended_allocation);
        });
      });
      setProposedQuantities(initialQtyMap);
    } catch (err: any) {
      setMatchingError(err?.response?.data?.detail || 'Matching calculation failed.');
    } finally {
      setLoadingMatching(false);
    }
  };

  // Allocation Proposals & Approvals
  const handleProposeAllocation = async (
    needId: string,
    candidate: ResourceMatchCandidate,
    maxRequested?: number
  ) => {
    const key = `${needId}_${candidate.resource_id}`;
    const rawVal =
      proposedQuantities[key] !== undefined
        ? proposedQuantities[key]
        : String(candidate.recommended_allocation);

    const trimmed = (rawVal ?? '').trim();
    if (!trimmed) {
      setActionError('Please enter a valid allocation quantity.');
      return;
    }

    const qty = Number(trimmed);
    if (isNaN(qty) || !Number.isInteger(qty)) {
      setActionError('Allocation quantity must be a whole integer number.');
      return;
    }

    if (qty <= 0) {
      setActionError('Allocation quantity must be greater than 0.');
      return;
    }

    if (qty > candidate.quantity_available) {
      setActionError(
        `Allocation quantity (${qty}) cannot exceed available stock (${candidate.quantity_available} ${candidate.unit}).`
      );
      return;
    }

    if (maxRequested !== undefined && qty > maxRequested) {
      setActionError(
        `Allocation quantity (${qty}) cannot exceed requested quantity (${maxRequested} ${candidate.unit}).`
      );
      return;
    }

    setActionError(null);
    setActionSuccess(null);
    setProcessingAllocationId(candidate.resource_id);

    try {
      const newAlloc = await proposeAllocation(reportId, {
        need_id: needId,
        resource_id: candidate.resource_id,
        requested_quantity: qty,
        notes: `Proposed via Resource Matcher (Score: ${Math.round(candidate.match_score * 100)}%)`,
      });
      setAllocations((prev) => [...prev, newAlloc]);
      setActionSuccess(`Allocation proposed: ${qty} ${candidate.unit} of ${candidate.name}.`);
      onRefreshReport?.();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to propose allocation.');
    } finally {
      setProcessingAllocationId(null);
    }
  };

  const handleApproveAllocation = async (allocationId: string) => {
    setActionError(null);
    setActionSuccess(null);
    setProcessingAllocationId(allocationId);

    try {
      const updated = await approveAllocation(allocationId);
      setAllocations((prev) =>
        prev.map((a) => (a.allocation_id === allocationId ? updated : a))
      );
      setActionSuccess(`Allocation ${allocationId} APPROVED. Inventory updated atomically.`);
      onRefreshReport?.();
      // Re-run matching if open to reflect new inventory
      if (matchingData) {
        handleRunMatching();
      }
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Allocation approval failed.');
    } finally {
      setProcessingAllocationId(null);
    }
  };

  const handleRejectAllocation = async (allocationId: string) => {
    setActionError(null);
    setActionSuccess(null);
    setProcessingAllocationId(allocationId);

    try {
      const updated = await rejectAllocation(allocationId, 'Rejected by Officer review');
      setAllocations((prev) =>
        prev.map((a) => (a.allocation_id === allocationId ? updated : a))
      );
      setActionSuccess(`Allocation ${allocationId} rejected.`);
      onRefreshReport?.();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Rejection failed.');
    } finally {
      setProcessingAllocationId(null);
    }
  };

  const getUrgencyBadge = (urgency: NeedUrgency) => {
    switch (urgency) {
      case 'CRITICAL':
        return 'bg-red-100 text-red-800 border-red-300 font-bold';
      case 'HIGH':
        return 'bg-orange-100 text-orange-800 border-orange-300 font-bold';
      case 'MEDIUM':
        return 'bg-amber-100 text-amber-800 border-amber-300 font-medium';
      case 'LOW':
        return 'bg-blue-100 text-blue-800 border-blue-300 font-medium';
    }
  };

  const getAllocationStatusBadge = (status: string) => {
    switch (status) {
      case 'APPROVED':
        return 'bg-emerald-100 text-emerald-800 border-emerald-300 font-bold';
      case 'PROPOSED':
        return 'bg-amber-100 text-amber-800 border-amber-300 font-medium';
      case 'REJECTED':
        return 'bg-rose-100 text-rose-800 border-rose-300';
      case 'DISPATCHED':
        return 'bg-blue-100 text-blue-800 border-blue-300';
      case 'COMPLETED':
        return 'bg-slate-100 text-slate-800 border-slate-300';
      default:
        return 'bg-slate-100 text-slate-600 border-slate-200';
    }
  };

  return (
    <div className="space-y-6">
      {/* Alert Messages */}
      {actionError && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-bold">Error: </span>
            {actionError}
          </div>
          <button onClick={() => setActionError(null)} className="text-red-400 hover:text-red-600">
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      )}

      {actionSuccess && (
        <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-700 flex items-start gap-2">
          <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-bold">Success: </span>
            {actionSuccess}
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-emerald-400 hover:text-emerald-600">
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* SECTION 1: NEEDS ASSESSMENT */}
      <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <Boxes className="w-5 h-5 text-red-600" />
              <h3 className="text-sm font-bold text-slate-900 tracking-wide uppercase">
                EMERGENCY NEEDS ASSESSMENT
              </h3>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Specify structured resource requirements for this incident. Officer confirmation is mandatory.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleFetchAISuggestions}
              disabled={loadingAi}
              className="px-3 py-1.5 rounded-xl bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
            >
              <Sparkles className="w-3.5 h-3.5 text-purple-600" />
              <span>{loadingAi ? 'Analyzing Report...' : 'Ask AI for Suggestions'}</span>
            </button>
            <button
              onClick={handleAddNeed}
              className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Need</span>
            </button>
          </div>
        </div>

        {/* AI Suggestions Tray */}
        {aiError && (
          <div className="p-3 rounded-xl bg-purple-50/50 border border-purple-100 text-xs text-purple-800">
            <span className="font-semibold">AI Advisory: </span>
            {aiError}
          </div>
        )}

        {aiSuggestions && aiSuggestions.length > 0 && (
          <div className="p-4 rounded-xl bg-purple-50/40 border border-purple-200 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-600" />
                <span className="text-xs font-bold text-purple-900 uppercase">
                  AI Suggested Needs (Advisory Only)
                </span>
              </div>
              <span className="text-[10px] text-purple-600 bg-purple-100/70 px-2 py-0.5 rounded font-mono">
                Human confirmation required
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {aiSuggestions.map((sug, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-white rounded-lg border border-purple-100 text-xs flex flex-col justify-between gap-2 shadow-2xs"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-800">{sug.resource_type}</span>
                      <span className="font-semibold text-purple-700">
                        {sug.suggested_quantity} {sug.unit}
                      </span>
                    </div>
                    <p className="text-slate-600 text-[11px] mt-1 line-clamp-2">{sug.reasoning}</p>
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                    <span className="text-[10px] text-slate-400">
                      Confidence: {Math.round(sug.confidence * 100)}%
                    </span>
                    <button
                      onClick={() => handleAcceptAISuggestion(sug)}
                      className="px-2 py-1 rounded bg-purple-600 hover:bg-purple-700 text-white text-[11px] font-semibold flex items-center gap-1 cursor-pointer transition-all"
                    >
                      <Plus className="w-3 h-3" />
                      <span>Add to Assessment</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Needs Table / Editor */}
        {loadingNeeds ? (
          <div className="py-8 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
            <RefreshCw className="w-4 h-4 animate-spin text-slate-400" />
            <span>Loading needs assessment...</span>
          </div>
        ) : needs.length === 0 ? (
          <div className="py-8 text-center rounded-xl bg-slate-50 border border-dashed border-slate-200">
            <Boxes className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <p className="text-xs font-semibold text-slate-600">No emergency needs recorded yet.</p>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Click &quot;Add Need&quot; or request AI suggestions to define requested resources.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-2">
              {needs.map((item, index) => (
                <div
                  key={item.need_id || index}
                  className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs grid grid-cols-1 md:grid-cols-12 gap-2 items-center"
                >
                  {/* Resource Type */}
                  <div className="md:col-span-3">
                    <label className="text-[10px] font-bold text-slate-500 uppercase block mb-0.5">
                      Resource Type
                    </label>
                    <select
                      value={item.resource_type}
                      onChange={(e) => handleUpdateNeed(index, 'resource_type', e.target.value)}
                      className="w-full px-2 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-800"
                    >
                      {RESOURCE_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Quantity & Unit */}
                  <div className="md:col-span-3 flex gap-1.5">
                    <div className="flex-1">
                      <label className="text-[10px] font-bold text-slate-500 uppercase block mb-0.5">
                        Qty
                      </label>
                      <input
                        type="number"
                        min="1"
                        value={item.requested_quantity}
                        onChange={(e) =>
                          handleUpdateNeed(index, 'requested_quantity', parseFloat(e.target.value) || 1)
                        }
                        className="w-full px-2 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-800"
                      />
                    </div>
                    <div className="w-20">
                      <label className="text-[10px] font-bold text-slate-500 uppercase block mb-0.5">
                        Unit
                      </label>
                      <input
                        type="text"
                        value={item.unit}
                        onChange={(e) => handleUpdateNeed(index, 'unit', e.target.value)}
                        className="w-full px-2 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-800"
                      />
                    </div>
                  </div>

                  {/* Urgency */}
                  <div className="md:col-span-2">
                    <label className="text-[10px] font-bold text-slate-500 uppercase block mb-0.5">
                      Urgency
                    </label>
                    <select
                      value={item.urgency}
                      onChange={(e) => handleUpdateNeed(index, 'urgency', e.target.value)}
                      className="w-full px-2 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-800"
                    >
                      <option value="LOW">LOW</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="HIGH">HIGH</option>
                      <option value="CRITICAL">CRITICAL</option>
                    </select>
                  </div>

                  {/* Reason / Notes */}
                  <div className="md:col-span-3">
                    <label className="text-[10px] font-bold text-slate-500 uppercase block mb-0.5">
                      Operational Reason
                    </label>
                    <input
                      type="text"
                      placeholder="Why required..."
                      value={item.reason || ''}
                      onChange={(e) => handleUpdateNeed(index, 'reason', e.target.value)}
                      className="w-full px-2 py-1.5 bg-white border border-slate-200 rounded-lg text-xs text-slate-800 placeholder-slate-400"
                    />
                  </div>

                  {/* Delete Button */}
                  <div className="md:col-span-1 flex justify-end">
                    <button
                      onClick={() => handleRemoveNeed(index)}
                      className="p-1.5 text-slate-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-all cursor-pointer"
                      title="Remove need item"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Save Button & Actions */}
            <div className="flex items-center justify-between pt-2">
              <div>
                {needsSavedMsg && (
                  <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1">
                    <Check className="w-3.5 h-3.5" />
                    {needsSavedMsg}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSaveNeeds}
                  disabled={savingNeeds}
                  className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  <span>{savingNeeds ? 'Saving...' : 'Save Needs Assessment'}</span>
                </button>
                <button
                  onClick={handleRunMatching}
                  disabled={loadingMatching || needs.length === 0}
                  className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-xs"
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>{loadingMatching ? 'Calculating Matches...' : 'Run Resource Matching'}</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* SECTION 2: DETERMINISTIC MATCHING RESULTS */}
      {matchingData && (
        <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Zap className="w-5 h-5 text-blue-600" />
              <h3 className="text-sm font-bold text-slate-900 tracking-wide uppercase">
                RESOURCE MATCHING ENGINE RESULTS
              </h3>
            </div>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 font-semibold">
              Deterministic Scoring
            </span>
          </div>

          {matchingError && (
            <div className="p-3 rounded-xl bg-red-50 text-xs text-red-700">{matchingError}</div>
          )}

          {matchingData.ai_explanation && (
            <div className="p-3.5 rounded-xl bg-blue-50/50 border border-blue-100 text-xs text-slate-700 space-y-1">
              <div className="flex items-center gap-1.5 font-bold text-blue-900">
                <Info className="w-3.5 h-3.5 text-blue-600" />
                <span>AI Coordination Summary</span>
              </div>
              <p className="text-slate-600 leading-relaxed">{matchingData.ai_explanation}</p>
            </div>
          )}

          <div className="space-y-4">
            {matchingData.needs_matches.map((nm) => (
              <div
                key={nm.need_id}
                className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-slate-900">{nm.resource_type}</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-slate-200 text-slate-700 font-semibold">
                      Required: {nm.requested_quantity} {nm.unit}
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded border ${getUrgencyBadge(nm.urgency)}`}>
                      {nm.urgency}
                    </span>
                  </div>

                  <div className="text-xs font-semibold">
                    {nm.is_fully_matchable ? (
                      <span className="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                        Fully Matchable ({nm.total_matched_available} available)
                      </span>
                    ) : nm.total_matched_available > 0 ? (
                      <span className="text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        Partially Matchable ({nm.total_matched_available}/{nm.requested_quantity} available)
                      </span>
                    ) : (
                      <span className="text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                        No Available Stock
                      </span>
                    )}
                  </div>
                </div>

                {/* Candidate Resources */}
                {nm.candidates.length === 0 ? (
                  <p className="text-xs text-slate-400 italic py-2">
                    No matching resources found in inventory for {nm.resource_type}.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {nm.candidates.map((cand) => {
                      const inputKey = `${nm.need_id}_${cand.resource_id}`;
                      const currentAllocQty =
                        proposedQuantities[inputKey] !== undefined
                          ? proposedQuantities[inputKey]
                          : String(cand.recommended_allocation);

                      return (
                        <div
                          key={cand.resource_id}
                          className="p-3 bg-white rounded-xl border border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs shadow-2xs hover:border-blue-300 transition-all"
                        >
                          <div className="space-y-1 flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-slate-900">{cand.name}</span>
                              <span className="font-mono text-[10px] text-slate-400">
                                {cand.resource_id}
                              </span>
                              <span className="text-[10px] font-bold px-1.5 py-0.2 rounded bg-blue-100 text-blue-800">
                                Score: {Math.round(cand.match_score * 100)}%
                              </span>
                            </div>

                            <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                              <span className="flex items-center gap-1">
                                <Compass className="w-3 h-3 text-slate-400" />
                                {cand.distance_km} km away
                              </span>
                              <span>
                                Available:{' '}
                                <strong className="text-slate-800">
                                  {cand.quantity_available} {cand.unit}
                                </strong>
                              </span>
                              <span>
                                Condition:{' '}
                                <strong className="text-slate-700">{cand.condition}</strong>
                              </span>
                              {cand.location?.district && (
                                <span>District: {cand.location.district}</span>
                              )}
                            </div>

                            <div className="flex flex-wrap gap-1 mt-1">
                              {cand.reasoning.map((r, i) => (
                                <span
                                  key={i}
                                  className="text-[10px] text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded"
                                >
                                  {r}
                                </span>
                              ))}
                            </div>
                          </div>

                          {/* Allocation Action */}
                          <div className="flex items-center gap-2 self-end md:self-center">
                            <div className="flex items-center gap-1">
                              <label className="text-[10px] font-bold text-slate-400 uppercase">
                                Allocate:
                              </label>
                              <input
                                type="number"
                                inputMode="numeric"
                                min="1"
                                max={cand.quantity_available}
                                value={currentAllocQty}
                                onChange={(e) => {
                                  const val = e.target.value;
                                  setProposedQuantities((prev) => ({
                                    ...prev,
                                    [inputKey]: val,
                                  }));
                                }}
                                className="w-16 px-2 py-1 bg-slate-50 border border-slate-200 rounded text-xs font-bold text-slate-800 text-center focus:bg-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                              />
                              <span className="text-[11px] text-slate-500">{cand.unit}</span>
                            </div>

                            <button
                              onClick={() => handleProposeAllocation(nm.need_id, cand, nm.requested_quantity)}
                              disabled={
                                processingAllocationId === cand.resource_id ||
                                cand.quantity_available <= 0
                              }
                              className="px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1 transition-all cursor-pointer"
                            >
                              <ArrowRight className="w-3.5 h-3.5" />
                              <span>
                                {processingAllocationId === cand.resource_id
                                  ? 'Proposing...'
                                  : 'Propose'}
                              </span>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SECTION 3: ALLOCATIONS & APPROVAL WORKFLOW */}
      <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-emerald-600" />
            <h3 className="text-sm font-bold text-slate-900 tracking-wide uppercase">
              RESOURCE ALLOCATIONS & HUMAN REVIEW
            </h3>
          </div>
          <span className="text-xs font-semibold text-slate-500">
            {allocations.length} Allocation(s)
          </span>
        </div>

        {loadingAllocations ? (
          <div className="py-6 text-center text-xs text-slate-400">Loading allocations...</div>
        ) : allocations.length === 0 ? (
          <div className="py-6 text-center rounded-xl bg-slate-50 border border-dashed border-slate-200 text-xs text-slate-400 font-semibold">
            No resource allocations proposed or approved for this incident yet.
          </div>
        ) : (
          <div className="space-y-3">
            {allocations.map((alloc) => (
              <div
                key={alloc.allocation_id}
                className="p-4 rounded-xl border border-slate-200 bg-white flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs shadow-2xs"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-slate-900 text-sm">
                      {alloc.resource_name} ({alloc.resource_type})
                    </span>
                    <span className="font-mono text-[10px] text-slate-400">
                      {alloc.allocation_id}
                    </span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded border ${getAllocationStatusBadge(
                        alloc.status
                      )}`}
                    >
                      {alloc.status}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-3 text-slate-600 text-[11px]">
                    <span>
                      Requested Quantity:{' '}
                      <strong className="text-slate-800">
                        {alloc.requested_quantity} {alloc.unit}
                      </strong>
                    </span>
                    {alloc.approved_quantity > 0 && (
                      <span>
                        Approved Quantity:{' '}
                        <strong className="text-emerald-700 font-bold">
                          {alloc.approved_quantity} {alloc.unit}
                        </strong>
                      </span>
                    )}
                    <span>
                      Proposed by: <strong className="text-slate-700">{alloc.proposed_by}</strong>
                    </span>
                    {alloc.approved_by && (
                      <span>
                        Approved by: <strong className="text-emerald-700">{alloc.approved_by}</strong>
                      </span>
                    )}
                  </div>

                  {alloc.notes && <p className="text-slate-500 text-[11px] italic">{alloc.notes}</p>}
                </div>

                {/* Review / Approval Actions */}
                {alloc.status === 'PROPOSED' && (
                  <div className="flex items-center gap-2 self-end md:self-center">
                    <button
                      onClick={() => handleApproveAllocation(alloc.allocation_id)}
                      disabled={processingAllocationId === alloc.allocation_id}
                      className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer shadow-2xs"
                    >
                      <CheckCircle className="w-3.5 h-3.5" />
                      <span>
                        {processingAllocationId === alloc.allocation_id ? 'Updating...' : 'Approve'}
                      </span>
                    </button>
                    <button
                      onClick={() => handleRejectAllocation(alloc.allocation_id)}
                      disabled={processingAllocationId === alloc.allocation_id}
                      className="px-3.5 py-1.5 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 disabled:opacity-50 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer"
                    >
                      <XCircle className="w-3.5 h-3.5 text-rose-600" />
                      <span>Reject</span>
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default NeedsAndAllocationsPanel;
