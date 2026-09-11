import React, { useState, useEffect } from 'react';
import {
  X,
  Shield,
  Bot,
  Layers,
  Sparkles,
  AlertTriangle,
  CheckCircle2,
  Edit3,
  XCircle,
  Clock,
  Package,
  MapPin,
  RefreshCw,
  Check,
  AlertCircle,
  FileCheck2,
  Split,
  Home,
  HeartPulse,
  Users,
  Truck,
  Navigation,
  Phone,
} from 'lucide-react';
import type {
  CoordinationPlan,
  CoordinationPlanStatus,
  PlanReviewAction,
  AgentRunRecord,
  PlanRecommendedResource,
  RecommendedShelter,
  RecommendedHealthcareFacility,
  RecommendedVolunteerAssignment,
  RecommendedTransport,
  RecommendedRoute,
  DetectedConflict,
} from '../../types';
import {
  orchestrateSituation,
  reviewCoordinationPlan,
  listSituationCoordinationPlans,
  listSituationAgentRuns,
} from '../../services/coordinationApi';

interface CoordinationPlanModalProps {
  situationId: string;
  situationTitle: string;
  emergencyType: string;
  onClose: () => void;
  onPlanUpdated?: (plan: CoordinationPlan) => void;
}

type TabType = 'plan' | 'healthcare' | 'volunteers' | 'routes' | 'shelters' | 'conflicts' | 'agents' | 'history';

export const CoordinationPlanModal: React.FC<CoordinationPlanModalProps> = ({
  situationId,
  situationTitle,
  emergencyType,
  onClose,
  onPlanUpdated,
}) => {
  const [activePlan, setActivePlan] = useState<CoordinationPlan | null>(null);
  const [allPlans, setAllPlans] = useState<CoordinationPlan[]>([]);
  const [agentRuns, setAgentRuns] = useState<AgentRunRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('plan');

  // Emergency Officer HITL Workflow States: 'view' | 'edit' | 'diff_review'
  const [workflowMode, setWorkflowMode] = useState<'view' | 'edit' | 'diff_review'>('view');
  const [editErrors, setEditErrors] = useState<string[]>([]);
  const [rejectModalOpen, setRejectModalOpen] = useState<boolean>(false);
  const [rejectNotes, setRejectNotes] = useState<string>('');
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  // Human Review Form State
  const [officerNotes, setOfficerNotes] = useState<string>('');
  const [modifiedAllocations, setModifiedAllocations] = useState<PlanRecommendedResource[]>([]);
  const [modifiedShelters, setModifiedShelters] = useState<RecommendedShelter[]>([]);
  const [modifiedFacilities, setModifiedFacilities] = useState<RecommendedHealthcareFacility[]>([]);
  const [modifiedVolunteers, setModifiedVolunteers] = useState<RecommendedVolunteerAssignment[]>([]);
  const [modifiedTransports, setModifiedTransports] = useState<RecommendedTransport[]>([]);
  const [modifiedRoutes, setModifiedRoutes] = useState<RecommendedRoute[]>([]);

  const inFlightRef = React.useRef<boolean>(false);

  const fetchPlansAndRuns = async (forceGenerate: boolean = false) => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      setLoading(true);
      setError(null);

      // 1. Fetch existing situation coordination plans & agent runs (Read-Only)
      const [history, runs] = await Promise.all([
        listSituationCoordinationPlans(situationId).catch(() => []),
        listSituationAgentRuns(situationId).catch(() => []),
      ]);
      setAllPlans(history || []);
      setAgentRuns(runs || []);

      let plan: CoordinationPlan | null = null;

      // If not force-generating and history has plans, select the active/approved or latest plan
      if (!forceGenerate && history && history.length > 0) {
        plan = history.find((p) => p.status === 'ACTIVE') ||
               history.find((p) => p.status === 'APPROVED') ||
               history.find((p) => p.status === 'PENDING_OFFICER_REVIEW') ||
               history[0];
      }

      // If no plans exist or forceGenerate explicitly requested by user button, trigger orchestration
      if (!plan || forceGenerate) {
        plan = await orchestrateSituation(situationId, forceGenerate);
        const refreshedHistory = await listSituationCoordinationPlans(situationId).catch(() => [plan!]);
        setAllPlans(refreshedHistory);
      }

      if (plan) {
        setActivePlan(plan);
        setModifiedAllocations(plan.recommended_allocations || []);
        setModifiedShelters(plan.recommended_shelters || []);
        setModifiedFacilities(plan.recommended_facilities || []);
        setModifiedVolunteers(plan.recommended_volunteers || []);
        setModifiedTransports(plan.recommended_transports || []);
        setModifiedRoutes(plan.recommended_routes || []);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to retrieve multi-agent coordination plan.');
    } finally {
      setLoading(false);
      inFlightRef.current = false;
    }
  };

  useEffect(() => {
    if (situationId) {
      fetchPlansAndRuns();
    }
  }, [situationId]);

  const handleRefreshOrchestration = async () => {
    try {
      setActionLoading(true);
      await fetchPlansAndRuns(true);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStartEdit = () => {
    if (!activePlan) return;
    setModifiedAllocations(JSON.parse(JSON.stringify(activePlan.recommended_allocations || [])));
    setModifiedShelters(JSON.parse(JSON.stringify(activePlan.recommended_shelters || [])));
    setModifiedFacilities(JSON.parse(JSON.stringify(activePlan.recommended_facilities || [])));
    setModifiedVolunteers(JSON.parse(JSON.stringify(activePlan.recommended_volunteers || [])));
    setModifiedTransports(JSON.parse(JSON.stringify(activePlan.recommended_transports || [])));
    setModifiedRoutes(JSON.parse(JSON.stringify(activePlan.recommended_routes || [])));
    setOfficerNotes(activePlan.officer_review?.officer_notes || '');
    setEditErrors([]);
    setSuccessNotice(null);
    setWorkflowMode('edit');
  };

  const handleCancelEdit = () => {
    if (!activePlan) return;
    setModifiedAllocations(activePlan.recommended_allocations || []);
    setModifiedShelters(activePlan.recommended_shelters || []);
    setModifiedFacilities(activePlan.recommended_facilities || []);
    setModifiedVolunteers(activePlan.recommended_volunteers || []);
    setModifiedTransports(activePlan.recommended_transports || []);
    setModifiedRoutes(activePlan.recommended_routes || []);
    setEditErrors([]);
    setWorkflowMode('view');
  };

  const handleProceedToDiffReview = () => {
    const errors: string[] = [];

    modifiedAllocations.forEach((alloc) => {
      const qty = Number(alloc.allocated_quantity ?? 0);
      const avail = Number(alloc.available_in_inventory ?? 0);
      if (qty < 0) {
        errors.push(`Allocation for ${alloc.resource_type} cannot be negative.`);
      }
      if (avail > 0 && qty > avail) {
        errors.push(`Allocation of ${qty} ${alloc.unit} exceeds depot stock of ${avail} ${alloc.unit} for ${alloc.matched_resource_name || alloc.resource_type}.`);
      }
    });

    modifiedShelters.forEach((sh) => {
      const occ = Number(sh.recommended_occupancy ?? 0);
      const rem = Number(sh.remaining_capacity ?? (sh.total_capacity - sh.current_occupancy));
      if (occ < 0) {
        errors.push(`Occupancy for shelter ${sh.shelter_name} cannot be negative.`);
      }
      if (rem > 0 && occ > rem) {
        errors.push(`Occupancy of ${occ} exceeds remaining capacity (${rem}) for shelter ${sh.shelter_name}.`);
      }
    });

    modifiedFacilities.forEach((fac) => {
      const pts = Number(fac.allocated_patients ?? 0);
      const beds = Number(fac.available_beds ?? fac.total_beds ?? 0);
      if (pts < 0) {
        errors.push(`Casualties for ${fac.facility_name} cannot be negative.`);
      }
      if (beds > 0 && pts > beds) {
        errors.push(`Allocated casualties (${pts}) exceeds available beds (${beds}) for ${fac.facility_name}.`);
      }
    });

    modifiedVolunteers.forEach((vol) => {
      if (!vol.assigned_operation || vol.assigned_operation.trim() === '') {
        errors.push(`Assigned operation for volunteer ${vol.volunteer_name} cannot be empty.`);
      }
    });

    if (errors.length > 0) {
      setEditErrors(errors);
      return;
    }

    setEditErrors([]);
    setWorkflowMode('diff_review');
  };

  const handleApprovePlan = async (isModified: boolean) => {
    if (!activePlan) return;
    try {
      setActionLoading(true);
      setError(null);

      const payload = {
        action: 'APPROVE' as PlanReviewAction,
        notes: officerNotes.trim() || (isModified ? 'Officer approved modified coordination plan.' : 'Officer approved plan as-is.'),
        modified_allocations: isModified ? modifiedAllocations : undefined,
        modified_shelters: isModified ? modifiedShelters : undefined,
        modified_facilities: isModified ? modifiedFacilities : undefined,
        modified_volunteers: isModified ? modifiedVolunteers : undefined,
        modified_transports: isModified ? modifiedTransports : undefined,
        modified_routes: isModified ? modifiedRoutes : undefined,
      };

      const updated = await reviewCoordinationPlan(activePlan.plan_id, payload);
      setActivePlan(updated);
      setWorkflowMode('view');
      setSuccessNotice(`Coordination Plan ${updated.plan_id} is now ACTIVE.`);

      const history = await listSituationCoordinationPlans(situationId).catch(() => []);
      setAllPlans(history);

      if (onPlanUpdated) {
        onPlanUpdated(updated);
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 409 || (detail && String(detail).includes('STALE_PLAN'))) {
        setError(detail || 'STALE PLAN CONFLICT: Operational conditions changed since this plan was generated. Please refresh and review the newly generated plan.');
      } else {
        setError(detail || 'Failed to approve coordination plan.');
      }
    } finally {
      setActionLoading(false);
    }
  };

  const handleRejectPlanSubmit = async () => {
    if (!activePlan) return;
    try {
      setActionLoading(true);
      setError(null);

      const payload = {
        action: 'REJECT' as PlanReviewAction,
        notes: rejectNotes.trim() || 'Officer rejected coordination plan.',
      };

      const updated = await reviewCoordinationPlan(activePlan.plan_id, payload);
      setActivePlan(updated);
      setRejectModalOpen(false);
      setRejectNotes('');
      setWorkflowMode('view');
      setSuccessNotice(`Coordination Plan ${updated.plan_id} has been REJECTED.`);

      const history = await listSituationCoordinationPlans(situationId).catch(() => []);
      setAllPlans(history);

      if (onPlanUpdated) {
        onPlanUpdated(updated);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to reject coordination plan.');
    } finally {
      setActionLoading(false);
    }
  };

  // Helper to compute structured diff between AI proposal and officer modifications
  const computeDiffSummary = () => {
    if (!activePlan) return { changes: [], unchangedCount: 0, allocationsChanged: 0, shortfallCount: 0 };

    const changes: Array<{
      category: string;
      title: string;
      originalValue: string;
      modifiedValue: string;
      detail?: string;
    }> = [];

    let unchangedCount = 0;
    let allocationsChanged = 0;
    let shortfallCount = 0;

    // 1. Allocations Diff
    (activePlan.recommended_allocations || []).forEach((orig, idx) => {
      const mod = modifiedAllocations[idx];
      const origQty = Number(orig.allocated_quantity ?? orig.quantity_required ?? 0);
      const modQty = Number(mod?.allocated_quantity ?? origQty);

      if (Math.abs(origQty - modQty) > 0.001) {
        allocationsChanged++;
        const delta = modQty - origQty;
        changes.push({
          category: 'SUPPLY ALLOCATION',
          title: `${orig.resource_type} (${orig.matched_resource_name || 'Regional Depot'})`,
          originalValue: `${origQty} ${orig.unit}`,
          modifiedValue: `${modQty} ${orig.unit} (${delta > 0 ? `+${delta}` : delta} ${orig.unit})`,
          detail: `Authoritative requirement: ${orig.quantity_required} ${orig.unit}`,
        });
      } else {
        unchangedCount++;
      }
    });

    // Check supply shortfalls against authoritative needs
    (activePlan.assessed_needs || []).forEach((need) => {
      const req = Number(need.requested_quantity || need.quantity || 0);
      const allocSum = modifiedAllocations
        .filter((a) => (a.resource_type || '').toUpperCase() === (need.resource_type || '').toUpperCase())
        .reduce((sum, a) => sum + (Number(a.allocated_quantity) || 0), 0);
      if (allocSum < req) {
        shortfallCount++;
      }
    });

    // 2. Shelters Diff
    (activePlan.recommended_shelters || []).forEach((orig, idx) => {
      const mod = modifiedShelters[idx];
      const origOcc = Number(orig.recommended_occupancy ?? 0);
      const modOcc = Number(mod?.recommended_occupancy ?? origOcc);

      if (Math.abs(origOcc - modOcc) > 0.001) {
        const delta = modOcc - origOcc;
        changes.push({
          category: 'EMERGENCY SHELTER',
          title: orig.shelter_name,
          originalValue: `${origOcc} evacuees`,
          modifiedValue: `${modOcc} evacuees (${delta > 0 ? `+${delta}` : delta})`,
          detail: `Capacity: ${orig.total_capacity}, remaining: ${orig.remaining_capacity}`,
        });
      } else {
        unchangedCount++;
      }
    });

    // 3. Healthcare Diff
    (activePlan.recommended_facilities || []).forEach((orig, idx) => {
      const mod = modifiedFacilities[idx];
      const origPts = Number(orig.allocated_patients ?? 0);
      const modPts = Number(mod?.allocated_patients ?? origPts);

      if (Math.abs(origPts - modPts) > 0.001) {
        const delta = modPts - origPts;
        changes.push({
          category: 'HEALTHCARE ROUTING',
          title: orig.facility_name,
          originalValue: `${origPts} casualties`,
          modifiedValue: `${modPts} casualties (${delta > 0 ? `+${delta}` : delta})`,
          detail: `Available beds: ${orig.available_beds}`,
        });
      } else {
        unchangedCount++;
      }
    });

    // 4. Volunteers Diff
    (activePlan.recommended_volunteers || []).forEach((orig, idx) => {
      const mod = modifiedVolunteers[idx];
      const origOp = orig.assigned_operation || '';
      const modOp = mod?.assigned_operation || origOp;
      const origRole = orig.role_or_skill || '';
      const modRole = mod?.role_or_skill || origRole;

      if (origOp !== modOp || origRole !== modRole) {
        changes.push({
          category: 'VOLUNTEER RESPONDER',
          title: orig.volunteer_name,
          originalValue: `${origRole} → ${origOp}`,
          modifiedValue: `${modRole} → ${modOp}`,
        });
      } else {
        unchangedCount++;
      }
    });

    return { changes, unchangedCount, allocationsChanged, shortfallCount };
  };

  const getStatusBadge = (status: CoordinationPlanStatus) => {
    switch (status) {
      case 'ACTIVE':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-800 border border-emerald-300 shadow-2xs">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> ACTIVE
          </span>
        );
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Approved
          </span>
        );
      case 'MODIFIED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <Edit3 className="w-3.5 h-3.5 text-amber-600" /> Modified & Approved
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
            <XCircle className="w-3.5 h-3.5 text-red-600" /> Rejected
          </span>
        );
      case 'SUPERSEDED':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
            <Clock className="w-3.5 h-3.5 text-slate-500" /> Superseded
          </span>
        );
      case 'PENDING_OFFICER_REVIEW':
      default:
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            <Clock className="w-3.5 h-3.5 text-blue-600" /> Pending Officer Review
          </span>
        );
    }
  };

  const getAgentStatusBadge = (status?: string) => {
    switch (status) {
      case 'COMPLETED':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">COMPLETED</span>;
      case 'FALLBACK':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">SAFE FALLBACK</span>;
      case 'FAILED':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-red-50 text-red-700 border border-red-200">FAILED</span>;
      case 'RUNNING':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">RUNNING</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">NOT REQUIRED</span>;
    }
  };

  const formatScore = (val?: number | null): string => {
    if (val === undefined || val === null || isNaN(Number(val))) return '100.0';
    return Number(val).toFixed(1);
  };

  const formatDate = (val?: string | null): string => {
    if (!val) return 'N/A';
    try {
      const d = new Date(val);
      if (isNaN(d.getTime())) return String(val);
      return d.toLocaleString();
    } catch {
      return String(val);
    }
  };

  const formatTime = (val?: string | null): string => {
    if (!val) return 'N/A';
    try {
      const d = new Date(val);
      if (isNaN(d.getTime())) return String(val);
      return d.toLocaleTimeString();
    } catch {
      return String(val);
    }
  };

  // Safe normalized conflicts list handling both structured DetectedConflict objects and string codes
  const normalizedConflicts: DetectedConflict[] = (activePlan?.conflicts || []).map((conf: any, idx: number) => {
    if (typeof conf === 'string') {
      return {
        conflict_id: `CNF-GEN-${idx + 1}`,
        conflict_type: conf as any,
        severity: 'HIGH' as any,
        description: conf.replace(/_/g, ' '),
        affected_need: 'Operational Coordination Requirement',
        affected_resource: 'Emergency Resources',
        detected_quantity: null,
        available_quantity: null,
        shortfall: null,
        resolution_strategy: 'ESCALATED' as any,
        resolution_status: 'UNRESOLVED' as any,
        officer_attention_required: true,
        explanation: `Cross-domain conflict detected: ${conf.replace(/_/g, ' ')}. Requires Emergency Officer review.`,
        alternative_options: ['Authorize emergency procurement', 'Request mutual aid'],
      };
    }
    return {
      conflict_id: conf.conflict_id || `CNF-${idx + 1}`,
      conflict_type: conf.conflict_type || 'RESOURCE_SHORTAGE',
      severity: conf.severity || 'HIGH',
      description: conf.description || 'Cross-domain resource shortfall or capacity constraint detected.',
      affected_need: conf.affected_need || 'Emergency Supply/Capacity',
      affected_resource: conf.affected_resource || 'Regional Resources',
      detected_quantity: conf.detected_quantity ?? null,
      available_quantity: conf.available_quantity ?? null,
      shortfall: conf.shortfall ?? null,
      resolution_strategy: conf.resolution_strategy || 'UNRESOLVED_ESCALATION',
      resolution_status: conf.resolution_status || 'UNRESOLVED',
      officer_attention_required: conf.officer_attention_required ?? true,
      explanation: conf.explanation || conf.description || 'Shortfall escalated to Emergency Officer.',
      alternative_options: conf.alternative_options || [],
    };
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/60 backdrop-blur-xs overflow-y-auto">
      <div className="relative w-full max-w-6xl my-2 sm:my-8 bg-white border border-slate-200 rounded-2xl shadow-2xl flex flex-col max-h-[calc(100dvh-1rem)] sm:max-h-[92vh] overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-slate-200 bg-slate-50/90 rounded-t-2xl">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="p-2 sm:p-2.5 rounded-xl bg-red-50 border border-red-200 text-red-600 flex-shrink-0">
              <Bot className="w-5 h-5 sm:w-6 sm:h-6" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-base sm:text-xl font-bold text-slate-900 tracking-tight truncate">
                  Central Orchestrator Response Plan
                </h2>
                {activePlan && getStatusBadge(activePlan.status)}
              </div>
              <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-1.5 truncate">
                <span>Situation:</span>
                <span className="text-slate-800 font-mono font-bold bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">
                  {situationId}
                </span>
                <span className="truncate hidden xs:inline">— {situationTitle} ({emergencyType})</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
            <button
              onClick={handleRefreshOrchestration}
              disabled={actionLoading || loading}
              className="flex items-center gap-1.5 px-2.5 sm:px-3.5 py-1.5 text-xs font-semibold rounded-xl bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 shadow-2xs transition disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${actionLoading ? 'animate-spin text-red-600' : ''}`} />
              <span className="hidden sm:inline">Re-run Orchestration</span>
            </button>
            <button
              onClick={onClose}
              className="p-1.5 sm:p-2 text-slate-400 hover:text-slate-700 rounded-xl hover:bg-slate-100 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Sub-Navigation Tabs across 8 Domain Capabilities */}
        <div className="flex items-center gap-1.5 px-3 sm:px-6 pt-2 border-b border-slate-200 bg-slate-50/50 overflow-x-auto no-scrollbar touch-scroll whitespace-nowrap">
          <button
            onClick={() => setActiveTab('plan')}
            className={`px-3 sm:px-3.5 py-2 sm:py-2.5 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'plan'
                ? 'border-red-600 text-red-700 bg-white shadow-2xs'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100/60'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Active Plan
          </button>
          <button
            onClick={() => setActiveTab('healthcare')}
            className={`px-3 sm:px-3.5 py-2 sm:py-2.5 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'healthcare'
                ? 'border-red-600 text-red-700 bg-white shadow-2xs'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100/60'
            }`}
          >
            <HeartPulse className="w-3.5 h-3.5" />
            Healthcare
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
              {activePlan?.recommended_facilities?.length || 0}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('volunteers')}
            className={`px-3 sm:px-3.5 py-2 sm:py-2.5 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'volunteers'
                ? 'border-red-600 text-red-700 bg-white shadow-2xs'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100/60'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            Volunteers
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
              {activePlan?.recommended_volunteers?.length || 0}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('routes')}
            className={`px-3 sm:px-3.5 py-2 sm:py-2.5 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'routes'
                ? 'border-red-600 text-red-700 bg-white shadow-2xs'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100/60'
            }`}
          >
            <Truck className="w-3.5 h-3.5" />
            Routes & Fleet
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
              {activePlan?.recommended_transports?.length || 0}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('shelters')}
            className={`px-3 sm:px-3.5 py-2 sm:py-2.5 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'shelters'
                ? 'border-red-600 text-red-700 bg-white shadow-2xs'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100/60'
            }`}
          >
            <Home className="w-3.5 h-3.5" />
            Shelters
            <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
              {activePlan?.recommended_shelters?.length || 0}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('conflicts')}
            className={`px-3 sm:px-3.5 py-2 sm:py-2.5 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'conflicts'
                ? 'border-red-600 text-red-700 bg-white shadow-2xs'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100/60'
            }`}
          >
            <Split className="w-3.5 h-3.5" />
            Conflicts
            {normalizedConflicts.length > 0 ? (
              <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                {normalizedConflicts.length}
              </span>
            ) : (
              <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-200 text-slate-700">
                0
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('agents')}
            className={`px-3 sm:px-3.5 py-2 sm:py-2.5 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'agents'
                ? 'border-red-600 text-red-700 bg-white shadow-2xs'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100/60'
            }`}
          >
            <Bot className="w-3.5 h-3.5" />
            Pipeline ({agentRuns.length})
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`px-3 sm:px-3.5 py-2 sm:py-2.5 text-xs font-bold rounded-t-xl transition border-b-2 flex items-center gap-1.5 whitespace-nowrap ${
              activeTab === 'history'
                ? 'border-red-600 text-red-700 bg-white shadow-2xs'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100/60'
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            Revisions ({allPlans.length})
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-3 sm:p-6 space-y-4 sm:space-y-6 bg-white touch-scroll">
          {error && (
            <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-600" />
              <div>
                <p className="font-semibold">Coordination Error</p>
                <p className="text-xs text-red-600/80 mt-0.5">{error}</p>
              </div>
            </div>
          )}

          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center text-slate-500 space-y-3">
              <RefreshCw className="w-8 h-8 animate-spin text-red-600" />
              <p className="text-sm font-semibold text-slate-800">Loading multi-agent coordination plan...</p>
              <p className="text-xs text-slate-500">Retrieving Priority, Needs, Resource, Shelter, Healthcare, Volunteer, Route, and Conflict records.</p>
            </div>
          ) : !activePlan ? (
            <div className="py-16 text-center text-slate-500">
              <AlertCircle className="w-10 h-10 mx-auto text-slate-400 mb-2" />
              <p className="text-sm font-semibold text-slate-700">No coordination plan available for this situation cluster.</p>
            </div>
          ) : (
            <>
              {activeTab === 'plan' && (
                <div className="space-y-6">
                  {/* Top Orchestrator Summary */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/90 shadow-2xs">
                      <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Assessed Priority</span>
                      <div className="flex items-center gap-2 mt-1.5">
                        <Shield className="w-5 h-5 text-amber-600" />
                        <span className="text-lg font-bold text-slate-900 tracking-wide">{activePlan.assessed_priority || 'MEDIUM'}</span>
                      </div>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/90 shadow-2xs">
                      <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Active Domain Agents</span>
                      <div className="flex items-center gap-2 mt-1.5">
                        <Bot className="w-5 h-5 text-red-600" />
                        <span className="text-lg font-bold text-slate-900 tracking-wide">
                          {Array.isArray(activePlan.participating_agents) ? activePlan.participating_agents.length : (activePlan.participating_agents ? Object.keys(activePlan.participating_agents).length : 8)} Coordinated
                        </span>
                      </div>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/90 shadow-2xs">
                      <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">AI Confidence</span>
                      <div className="flex items-center gap-2 mt-1.5">
                        <Sparkles className="w-5 h-5 text-blue-600" />
                        <span className="text-lg font-bold text-slate-900 tracking-wide">
                          {Math.round((activePlan.confidence ?? 0.95) * 100)}%
                        </span>
                      </div>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/90 shadow-2xs">
                      <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Plan Identifier</span>
                      <div className="flex items-center gap-2 mt-1.5">
                        <FileCheck2 className="w-5 h-5 text-emerald-600" />
                        <span className="text-sm font-mono font-bold text-slate-900">{activePlan.plan_id}</span>
                      </div>
                    </div>
                  </div>

                  {/* Multi-Domain Executive Status Strip */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {/* Healthcare Summary Strip */}
                    <div
                      onClick={() => setActiveTab('healthcare')}
                      className="p-3.5 rounded-xl bg-rose-50/50 border border-rose-200 cursor-pointer hover:bg-rose-50 transition space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-rose-800 uppercase tracking-wider flex items-center gap-1">
                          <HeartPulse className="w-3 h-3 text-rose-600" /> Healthcare
                        </span>
                        <span className="text-xs font-bold text-rose-900 font-mono">
                          {activePlan.recommended_facilities?.length || 0} Hospitals
                        </span>
                      </div>
                      <p className="text-[11px] text-rose-700 truncate">
                        {activePlan.healthcare_summary?.medical_required
                          ? `${Math.round(activePlan.healthcare_summary.total_patients_covered ?? 0)} casualties covered`
                          : 'Medical routing not required'}
                      </p>
                    </div>

                    {/* Volunteers Summary Strip */}
                    <div
                      onClick={() => setActiveTab('volunteers')}
                      className="p-3.5 rounded-xl bg-emerald-50/50 border border-emerald-200 cursor-pointer hover:bg-emerald-50 transition space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider flex items-center gap-1">
                          <Users className="w-3 h-3 text-emerald-600" /> Volunteers
                        </span>
                        <span className="text-xs font-bold text-emerald-900 font-mono">
                          {activePlan.recommended_volunteers?.length || 0} Assigned
                        </span>
                      </div>
                      <p className="text-[11px] text-emerald-700 truncate">
                        {activePlan.volunteer_summary?.volunteers_required
                          ? `${activePlan.volunteer_summary.total_volunteers_assigned ?? 0} responders matched`
                          : 'Volunteer dispatch not required'}
                      </p>
                    </div>

                    {/* Fleet & Routes Summary Strip */}
                    <div
                      onClick={() => setActiveTab('routes')}
                      className="p-3.5 rounded-xl bg-indigo-50/50 border border-indigo-200 cursor-pointer hover:bg-indigo-50 transition space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-indigo-800 uppercase tracking-wider flex items-center gap-1">
                          <Truck className="w-3 h-3 text-indigo-600" /> Fleet & Routes
                        </span>
                        <span className="text-xs font-bold text-indigo-900 font-mono">
                          {activePlan.recommended_transports?.length || 0} Transports
                        </span>
                      </div>
                      <p className="text-[11px] text-indigo-700 truncate">
                        {activePlan.route_summary?.transport_required
                          ? `${activePlan.recommended_routes?.length || 0} corridors evaluated`
                          : 'Fleet transit not required'}
                      </p>
                    </div>

                    {/* Shelters Summary Strip */}
                    <div
                      onClick={() => setActiveTab('shelters')}
                      className="p-3.5 rounded-xl bg-blue-50/50 border border-blue-200 cursor-pointer hover:bg-blue-50 transition space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-blue-800 uppercase tracking-wider flex items-center gap-1">
                          <Home className="w-3 h-3 text-blue-600" /> Shelters
                        </span>
                        <span className="text-xs font-bold text-blue-900 font-mono">
                          {activePlan.recommended_shelters?.length || 0} Shelters
                        </span>
                      </div>
                      <p className="text-[11px] text-blue-700 truncate">
                        {activePlan.shelter_summary?.shelter_required
                          ? `${Math.round(activePlan.shelter_summary.total_population_covered ?? 0)} evacuees housed`
                          : 'Shelter routing not required'}
                      </p>
                    </div>
                  </div>

                  {/* Conflict Intelligence Status Callout */}
                  {normalizedConflicts.length > 0 ? (
                    <div className="p-4 rounded-xl bg-amber-50/80 border border-amber-200 text-amber-900 flex items-start justify-between gap-3 shadow-2xs">
                      <div className="flex items-start gap-3">
                        <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="text-xs font-bold text-amber-950">
                            {normalizedConflicts.length} Cross-Domain Conflict(s) Detected
                          </p>
                          <p className="text-xs text-amber-800 mt-0.5">
                            {activePlan.conflict_summary?.explanation || 'Supply deficits, hospital bed shortages, volunteer deficits, or transit bottlenecks require officer review.'}
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => setActiveTab('conflicts')}
                        className="px-3 py-1.5 text-xs font-bold bg-amber-600 hover:bg-amber-700 text-white rounded-lg shadow-2xs transition whitespace-nowrap"
                      >
                        Inspect Conflicts
                      </button>
                    </div>
                  ) : (
                    <div className="p-3.5 rounded-xl bg-emerald-50/70 border border-emerald-200 text-emerald-800 text-xs flex items-center justify-between shadow-2xs">
                      <div className="flex items-center gap-2.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                        <span>
                          <strong className="font-bold text-emerald-950">Zero Operational Conflicts:</strong> All requirements across supplies, hospital beds, volunteers, shelters, and transit routes are fully satisfied.
                        </span>
                      </div>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">
                        VERIFIED
                      </span>
                    </div>
                  )}

                  {/* Multi-Agent Contribution Breakdown (8 Agents in Topological Flow) */}
                  <div className="space-y-3">
                    <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                      <Bot className="w-4 h-4 text-red-600" />
                      8-Agent Pipeline Topological Execution
                    </h3>

                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                      {/* Priority Agent */}
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-800">1. Priority Agent</span>
                          {getAgentStatusBadge(activePlan.agent_results?.priority_agent?.status)}
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-2">
                          {activePlan.agent_results?.priority_agent?.recommendation || 'Evaluated severity & hazard category.'}
                        </p>
                      </div>

                      {/* Needs Agent */}
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-800">2. Needs Agent</span>
                          {getAgentStatusBadge(activePlan.agent_results?.needs_agent?.status)}
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-2">
                          {activePlan.agent_results?.needs_agent?.recommendation || 'Calculated essential supply demands.'}
                        </p>
                      </div>

                      {/* Resource Coordination Agent */}
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-800">3. Resource Agent</span>
                          {getAgentStatusBadge(activePlan.agent_results?.resource_agent?.status)}
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-2">
                          {activePlan.agent_results?.resource_agent?.recommendation || 'Matched supplies to regional inventory.'}
                        </p>
                      </div>

                      {/* Shelter Coordination Agent */}
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-800">4. Shelter Agent</span>
                          {getAgentStatusBadge(activePlan.agent_results?.shelter_agent?.status)}
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-2">
                          {activePlan.agent_results?.shelter_agent?.recommendation || 'Evaluated evacuation facility beds.'}
                        </p>
                      </div>

                      {/* Healthcare Coordination Agent */}
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-800">5. Healthcare Agent</span>
                          {getAgentStatusBadge(activePlan.agent_results?.healthcare_agent?.status)}
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-2">
                          {activePlan.agent_results?.healthcare_agent?.recommendation || 'Assessed trauma capacity & ICU readiness.'}
                        </p>
                      </div>

                      {/* Volunteer Coordination Agent */}
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-800">6. Volunteer Agent</span>
                          {getAgentStatusBadge(activePlan.agent_results?.volunteer_agent?.status)}
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-2">
                          {activePlan.agent_results?.volunteer_agent?.recommendation || 'Matched verified responder skills & zones.'}
                        </p>
                      </div>

                      {/* Route & Transport Coordination Agent */}
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-800">7. Route Agent</span>
                          {getAgentStatusBadge(activePlan.agent_results?.route_agent?.status)}
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-2">
                          {activePlan.agent_results?.route_agent?.recommendation || 'Calculated fleet ingress/egress routes.'}
                        </p>
                      </div>

                      {/* Conflict Resolution Agent */}
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-800">8. Conflict Agent</span>
                          {getAgentStatusBadge(activePlan.agent_results?.conflict_agent?.status)}
                        </div>
                        <p className="text-xs text-slate-600 line-clamp-2">
                          {activePlan.agent_results?.conflict_agent?.recommendation || 'Consolidated cross-domain shortfalls.'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Authoritative Assessed Needs Section */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <Package className="w-4 h-4 text-blue-600" />
                        Authoritative Incident Needs & Operational Requirements
                      </h3>
                      <span className="text-[11px] font-semibold text-slate-500">
                        {activePlan.assessed_needs?.length || 0} Need Item(s)
                      </span>
                    </div>

                    {(!activePlan.assessed_needs || activePlan.assessed_needs.length === 0) ? (
                      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-slate-500 text-xs text-center">
                        No specific supply needs evaluated for this incident.
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                        {activePlan.assessed_needs.map((need, nIdx) => {
                          const isOfficer = need.officer_assessed !== false && need.source !== 'AI_INFERRED_ADVISORY' && need.source !== 'HEURISTIC_NEEDS_ENGINE';
                          const reqQty = need.requested_quantity || need.quantity || 1;
                          return (
                            <div key={nIdx} className="p-3.5 rounded-xl bg-slate-50/90 border border-slate-200/90 space-y-1.5 shadow-2xs">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-bold text-slate-900">{need.resource_type}</span>
                                {isOfficer ? (
                                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                    From Needs Assessment
                                  </span>
                                ) : (
                                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
                                    AI Advisory Suggestion
                                  </span>
                                )}
                              </div>
                              <div className="flex items-baseline gap-1.5">
                                <span className="text-lg font-mono font-extrabold text-slate-900">{reqQty}</span>
                                <span className="text-xs font-semibold text-slate-600">{need.unit || 'Units'}</span>
                                <span className="text-[10px] text-slate-400 ml-auto">Required</span>
                              </div>
                              {need.reasoning && (
                                <p className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed">{need.reasoning}</p>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Recommended Regional Resource Allocations Table */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <Truck className="w-4 h-4 text-emerald-600" />
                        AI Recommended Depot Allocations & Inventory Matching
                      </h3>
                      <span className="text-[11px] font-semibold text-slate-500">
                        {activePlan.recommended_allocations?.length || 0} Recommended Match(es)
                      </span>
                    </div>

                    <div className="border border-slate-200 rounded-xl overflow-hidden bg-white shadow-2xs">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 font-semibold">
                          <tr>
                            <th className="px-4 py-3">Resource Type</th>
                            <th className="px-4 py-3">Required Qty</th>
                            <th className="px-4 py-3">Matched Regional Depot</th>
                            <th className="px-4 py-3">Available Stock</th>
                            <th className="px-4 py-3">Allocated Qty</th>
                            <th className="px-4 py-3">Shortfall</th>
                            <th className="px-4 py-3">Distance</th>
                            <th className="px-4 py-3">Urgency</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 text-slate-700">
                          {(!activePlan.recommended_allocations || activePlan.recommended_allocations.length === 0) ? (
                            <tr>
                              <td colSpan={8} className="px-4 py-6 text-center text-slate-500">
                                No depot allocations generated for this plan.
                              </td>
                            </tr>
                          ) : (
                            activePlan.recommended_allocations.map((alloc, idx) => {
                              const currentAllocQty = alloc.allocated_quantity ?? alloc.quantity_required;
                              const shortfallQty = Math.max(0, alloc.quantity_required - currentAllocQty);

                              return (
                                <tr key={idx} className="hover:bg-slate-50/80 transition">
                                  <td className="px-4 py-3 font-semibold text-slate-900">{alloc.resource_type}</td>
                                  <td className="px-4 py-3 font-mono font-bold text-slate-800">{alloc.quantity_required} {alloc.unit}</td>
                                  <td className="px-4 py-3">
                                    {alloc.matched_resource_name ? (
                                      <div className="space-y-0.5">
                                        <p className="font-semibold text-slate-800">{alloc.matched_resource_name}</p>
                                        <p className="text-[10px] text-slate-500 flex items-center gap-1">
                                          <MapPin className="w-3 h-3 text-slate-400" />
                                          {alloc.depot_location || 'Regional Depot'}
                                        </p>
                                      </div>
                                    ) : (
                                      <span className="text-amber-700 italic font-medium">Unmet Need (Out of Stock)</span>
                                    )}
                                  </td>
                                  <td className="px-4 py-3 font-mono text-slate-600">
                                    {alloc.available_in_inventory !== undefined && alloc.available_in_inventory !== null ? `${alloc.available_in_inventory} ${alloc.unit}` : 'N/A'}
                                  </td>
                                  <td className="px-4 py-3">
                                    <span className="font-mono font-bold text-emerald-700">
                                      {alloc.allocated_quantity ?? alloc.quantity_required} {alloc.unit}
                                    </span>
                                  </td>
                                  <td className="px-4 py-3 font-mono">
                                    {shortfallQty > 0 ? (
                                      <span className="font-bold text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                                        {shortfallQty} {alloc.unit}
                                      </span>
                                    ) : (
                                      <span className="text-emerald-700 font-bold">0 {alloc.unit}</span>
                                    )}
                                  </td>
                                  <td className="px-4 py-3 text-slate-600">
                                    {alloc.distance_km ? `${alloc.distance_km} km` : '—'}
                                  </td>
                                  <td className="px-4 py-3">
                                    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                                      alloc.urgency === 'CRITICAL' ? 'bg-red-50 text-red-700 border-red-200' :
                                      alloc.urgency === 'HIGH' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                                      'bg-blue-50 text-blue-700 border-blue-200'
                                    }`}>
                                      {alloc.urgency}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Safety Guardrail Notice */}
                  <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-slate-700 text-xs flex items-start gap-2.5">
                    <Shield className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-slate-900">Advisory Multi-Agent Safety Control: </span>
                      All agent outputs across resource allocations, hospitals, volunteers, and fleet routes are purely advisory suggestions. Real databases and registries are NEVER automatically mutated. Decisions remain strictly with the authorized Emergency Officer.
                    </div>
                  </div>

                  {/* Success Notice Banner */}
                  {successNotice && (
                    <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-300 text-emerald-800 text-xs flex items-center justify-between shadow-xs">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                        <span className="font-semibold">{successNotice}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setSuccessNotice(null)}
                        className="text-emerald-600 hover:text-emerald-800 p-1"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  )}

                  {/* Human-in-the-Loop Emergency Officer Decision Controls */}
                  {workflowMode === 'view' && (
                    <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200 space-y-4">
                      <div className="flex items-center justify-between">
                        <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                          <Shield className="w-4 h-4 text-red-600" />
                          Human-in-the-Loop Emergency Officer Review
                        </h3>
                        {activePlan.officer_review && (
                          <span className="text-xs text-slate-500">
                            Reviewed by <strong className="text-slate-800">{activePlan.officer_review.reviewed_by_name}</strong> ({activePlan.officer_review.reviewed_by_role})
                          </span>
                        )}
                      </div>

                      {activePlan.status === 'PENDING_OFFICER_REVIEW' || activePlan.status === 'MODIFIED' || activePlan.status === 'DRAFT' ? (
                        <div className="space-y-4">
                          <p className="text-xs text-slate-600">
                            You may approve the AI coordination proposal as-is, urgently modify the resource allocations, shelter capacities, and responder assignments before approval, or reject the recommendation.
                          </p>

                          <div className="flex flex-wrap items-center gap-3 pt-1">
                            <button
                              type="button"
                              onClick={handleStartEdit}
                              disabled={actionLoading}
                              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold bg-amber-500 hover:bg-amber-600 text-white shadow-xs transition disabled:opacity-50"
                            >
                              <Edit3 className="w-4 h-4" />
                              EDIT PLAN
                            </button>

                            <button
                              type="button"
                              onClick={() => handleApprovePlan(false)}
                              disabled={actionLoading}
                              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs transition disabled:opacity-50"
                            >
                              {actionLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                              APPROVE PLAN AS-IS
                            </button>

                            <button
                              type="button"
                              onClick={() => setRejectModalOpen(true)}
                              disabled={actionLoading}
                              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold bg-white hover:bg-red-50 text-red-700 border border-red-300 transition disabled:opacity-50"
                            >
                              <XCircle className="w-4 h-4" />
                              REJECT PLAN
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="p-4 rounded-xl bg-white border border-slate-200 space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-slate-500">Formal Decision</span>
                            <span className="text-xs font-bold text-slate-900 uppercase">{activePlan.officer_review?.decision || activePlan.status}</span>
                          </div>
                          {activePlan.officer_review?.officer_notes && (
                            <div className="text-xs text-slate-700 italic pt-1">
                              &ldquo;{activePlan.officer_review.officer_notes}&rdquo;
                            </div>
                          )}
                          <p className="text-[11px] text-slate-400 pt-1 font-mono">
                            Recorded at {formatDate(activePlan.officer_review?.reviewed_at || activePlan.generated_at)}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Stage 2: EMERGENCY OFFICER PLAN MODIFICATION MODE */}
                  {workflowMode === 'edit' && (
                    <div className="p-6 rounded-2xl bg-amber-50/40 border-2 border-amber-300 space-y-6 animate-in fade-in duration-200">
                      <div className="flex items-start justify-between gap-4 pb-3 border-b border-amber-200">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold bg-amber-600 text-white uppercase tracking-wider">
                              HITL EDIT MODE
                            </span>
                            <h3 className="text-base font-bold text-slate-900">
                              Modify AI Coordination Plan
                            </h3>
                          </div>
                          <p className="text-xs text-slate-600 mt-1">
                            <strong className="text-slate-800">Clear Separation of Concerns: </strong>
                            Authoritative Need (<span className="font-semibold text-blue-700">WHAT IS REQUIRED</span>) is established by Needs Assessment and remains fixed.
                            Modify the Proposed Fulfillment (<span className="font-semibold text-amber-700">HOW IT IS DELIVERED</span>) below.
                          </p>
                        </div>

                        <button
                          type="button"
                          onClick={handleCancelEdit}
                          className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-900 rounded-lg hover:bg-amber-100/50 transition font-medium"
                        >
                          Cancel
                        </button>
                      </div>

                      {/* Error Banner */}
                      {editErrors.length > 0 && (
                        <div className="p-4 rounded-xl bg-red-50 border border-red-300 text-red-800 text-xs space-y-1">
                          <p className="font-bold flex items-center gap-1.5 text-red-900">
                            <AlertTriangle className="w-4 h-4 text-red-600" />
                            Please resolve the following allocation validation errors before proceeding:
                          </p>
                          <ul className="list-disc list-inside space-y-0.5 pl-2 text-red-700">
                            {editErrors.map((err, errIdx) => (
                              <li key={errIdx}>{err}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* 1. Supply Allocations Modification */}
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                            <Package className="w-4 h-4 text-blue-600" />
                            1. Regional Resource & Supply Allocations
                          </h4>
                          <span className="text-[11px] text-slate-500 font-medium">
                            {modifiedAllocations.length} Allocation Item(s)
                          </span>
                        </div>

                        <div className="space-y-3">
                          {modifiedAllocations.map((alloc, idx) => {
                            const availStock = alloc.available_in_inventory !== undefined && alloc.available_in_inventory !== null ? alloc.available_in_inventory : 0;
                            const currentAllocQty = Number(alloc.allocated_quantity ?? alloc.quantity_required ?? 0);
                            const isOverallocated = availStock > 0 && currentAllocQty > availStock;
                            const isNegative = currentAllocQty < 0;

                            // Total allocated for this resource type across all matched depots
                            const matchingAllocs = modifiedAllocations.filter(
                              (a) => (a.resource_type || '').toUpperCase() === (alloc.resource_type || '').toUpperCase()
                            );
                            const totalAllocatedForResource = matchingAllocs.reduce(
                              (sum, a) => sum + (Number(a.allocated_quantity) || 0),
                              0
                            );
                            const shortfall = Math.max(0, alloc.quantity_required - totalAllocatedForResource);

                            return (
                              <div
                                key={idx}
                                className={`p-4 rounded-xl bg-white border transition ${
                                  isOverallocated || isNegative
                                    ? 'border-red-400 bg-red-50/20 shadow-xs'
                                    : 'border-slate-200 shadow-2xs'
                                }`}
                              >
                                <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
                                  {/* Resource Info */}
                                  <div className="md:col-span-3 space-y-0.5">
                                    <span className="text-xs font-bold text-slate-900 block">{alloc.resource_type}</span>
                                    <span className="text-[11px] text-slate-500 flex items-center gap-1">
                                      <MapPin className="w-3 h-3 text-slate-400" />
                                      {alloc.matched_resource_name || alloc.depot_location || 'Regional Depot'}
                                    </span>
                                  </div>

                                  {/* Authoritative Need */}
                                  <div className="md:col-span-2 p-2 rounded-lg bg-slate-50 border border-slate-200/80">
                                    <span className="text-[10px] font-semibold text-slate-500 block uppercase">Authoritative Need</span>
                                    <span className="text-xs font-mono font-bold text-slate-900">
                                      {alloc.quantity_required} {alloc.unit}
                                    </span>
                                  </div>

                                  {/* Available Stock */}
                                  <div className="md:col-span-2 p-2 rounded-lg bg-slate-50 border border-slate-200/80">
                                    <span className="text-[10px] font-semibold text-slate-500 block uppercase">Depot Stock</span>
                                    <span className="text-xs font-mono font-bold text-slate-700">
                                      {availStock > 0 ? `${availStock} ${alloc.unit}` : 'Out of Stock'}
                                    </span>
                                  </div>

                                  {/* Officer Input Field */}
                                  <div className="md:col-span-3 space-y-1">
                                    <label className="text-[10px] font-semibold text-slate-700 block uppercase">
                                      Officer Allocation
                                    </label>
                                    <div className="flex items-center gap-2">
                                      <input
                                        type="number"
                                        min={0}
                                        max={availStock > 0 ? availStock : undefined}
                                        step="any"
                                        value={alloc.allocated_quantity ?? ''}
                                        onChange={(e) => {
                                          const val = e.target.value === '' ? 0 : parseFloat(e.target.value);
                                          const newAllocations = [...modifiedAllocations];
                                          newAllocations[idx] = {
                                            ...newAllocations[idx],
                                            allocated_quantity: isNaN(val) ? 0 : val,
                                          };
                                          setModifiedAllocations(newAllocations);
                                        }}
                                        className={`w-full px-3 py-1.5 text-xs bg-white border rounded-lg text-slate-900 font-mono font-bold focus:outline-none focus:ring-2 ${
                                          isOverallocated || isNegative
                                            ? 'border-red-500 focus:ring-red-500/20 bg-red-50/50 text-red-900'
                                            : 'border-slate-300 focus:ring-amber-500/20 focus:border-amber-500'
                                        }`}
                                      />
                                      <span className="text-xs text-slate-600 font-semibold">{alloc.unit}</span>
                                    </div>
                                    {isOverallocated && (
                                      <p className="text-[10px] text-red-600 font-bold">Exceeds available stock ({availStock} {alloc.unit})</p>
                                    )}
                                  </div>

                                  {/* Live Math Status */}
                                  <div className="md:col-span-2 space-y-1">
                                    <span className="text-[10px] font-semibold text-slate-500 block uppercase">Live Balance</span>
                                    {shortfall > 0 ? (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300">
                                        Shortfall: {shortfall} {alloc.unit}
                                      </span>
                                    ) : (
                                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                                        <Check className="w-3 h-3 text-emerald-600" /> 0 Shortfall
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* 2. Shelter Occupancy Modification (If present) */}
                      {modifiedShelters.length > 0 && (
                        <div className="space-y-3 pt-3 border-t border-amber-200">
                          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                            <Home className="w-4 h-4 text-blue-600" />
                            2. Emergency Shelter Evacuation Distribution
                          </h4>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {modifiedShelters.map((sh, sIdx) => {
                              const remCap = Number(sh.remaining_capacity ?? (sh.total_capacity - sh.current_occupancy));
                              const curOcc = Number(sh.recommended_occupancy ?? 0);
                              const isOver = remCap > 0 && curOcc > remCap;

                              return (
                                <div key={sIdx} className="p-3.5 rounded-xl bg-white border border-slate-200 space-y-2 shadow-2xs">
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs font-bold text-slate-900">{sh.shelter_name}</span>
                                    <span className="text-[10px] text-slate-500 font-mono">Remaining Cap: {remCap}</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <label className="text-[11px] text-slate-600 font-medium">Recommended Evacuees:</label>
                                    <input
                                      type="number"
                                      min={0}
                                      max={remCap > 0 ? remCap : undefined}
                                      value={sh.recommended_occupancy ?? 0}
                                      onChange={(e) => {
                                        const val = parseInt(e.target.value, 10) || 0;
                                        const newSh = [...modifiedShelters];
                                        newSh[sIdx] = { ...newSh[sIdx], recommended_occupancy: val };
                                        setModifiedShelters(newSh);
                                      }}
                                      className={`w-24 px-2.5 py-1 text-xs bg-white border rounded-lg font-mono font-bold ${
                                        isOver ? 'border-red-500 text-red-700 bg-red-50' : 'border-slate-300 text-slate-900'
                                      }`}
                                    />
                                    <span className="text-[10px] text-slate-500">persons</span>
                                  </div>
                                  {isOver && (
                                    <p className="text-[10px] text-red-600 font-semibold flex items-center gap-1">
                                      <AlertTriangle className="w-3 h-3" /> Exceeds remaining capacity ({remCap})
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* 3. Healthcare Facility Evacuation Distribution */}
                      {modifiedFacilities.length > 0 && (
                        <div className="space-y-3 pt-3 border-t border-amber-200">
                          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                            <HeartPulse className="w-4 h-4 text-rose-600" />
                            3. Emergency Healthcare Casualties & Facility Routing
                          </h4>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {modifiedFacilities.map((fac, fIdx) => {
                              const availBeds = Number(fac.available_beds ?? fac.total_beds ?? 0);
                              const curPts = Number(fac.allocated_patients ?? 0);
                              const isOver = availBeds > 0 && curPts > availBeds;

                              return (
                                <div key={fIdx} className="p-3.5 rounded-xl bg-white border border-slate-200 space-y-2 shadow-2xs">
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs font-bold text-slate-900">{fac.facility_name}</span>
                                    <span className="text-[10px] text-slate-500 font-mono">Available Beds: {availBeds}</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <label className="text-[11px] text-slate-600 font-medium">Allocated Casualties:</label>
                                    <input
                                      type="number"
                                      min={0}
                                      max={availBeds > 0 ? availBeds : undefined}
                                      value={fac.allocated_patients ?? 0}
                                      onChange={(e) => {
                                        const val = parseInt(e.target.value, 10) || 0;
                                        const newFac = [...modifiedFacilities];
                                        newFac[fIdx] = { ...newFac[fIdx], allocated_patients: val };
                                        setModifiedFacilities(newFac);
                                      }}
                                      className={`w-24 px-2.5 py-1 text-xs bg-white border rounded-lg font-mono font-bold ${
                                        isOver ? 'border-red-500 text-red-700 bg-red-50' : 'border-slate-300 text-slate-900'
                                      }`}
                                    />
                                    <span className="text-[10px] text-slate-500">patients</span>
                                  </div>
                                  {isOver && (
                                    <p className="text-[10px] text-red-600 font-semibold flex items-center gap-1">
                                      <AlertTriangle className="w-3 h-3" /> Exceeds available beds ({availBeds})
                                    </p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* 4. Volunteer Responder Assignments */}
                      {modifiedVolunteers.length > 0 && (
                        <div className="space-y-3 pt-3 border-t border-amber-200">
                          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                            <Users className="w-4 h-4 text-emerald-600" />
                            4. Volunteer Responder Assignments
                          </h4>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {modifiedVolunteers.map((vol, vIdx) => (
                              <div key={vIdx} className="p-3.5 rounded-xl bg-white border border-slate-200 space-y-2 shadow-2xs">
                                <div className="flex items-center justify-between">
                                  <span className="text-xs font-bold text-slate-900">{vol.volunteer_name}</span>
                                  <span className="text-[10px] text-slate-500">{vol.role_or_skill}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                  <label className="text-[11px] text-slate-600 font-medium">Assigned Operation:</label>
                                  <input
                                    type="text"
                                    value={vol.assigned_operation || ''}
                                    onChange={(e) => {
                                      const newVol = [...modifiedVolunteers];
                                      newVol[vIdx] = { ...newVol[vIdx], assigned_operation: e.target.value };
                                      setModifiedVolunteers(newVol);
                                    }}
                                    className="flex-1 px-2.5 py-1 text-xs bg-white border border-slate-300 rounded-lg text-slate-900"
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* 5. Officer Operational Justification Notes */}
                      <div className="space-y-2 pt-3 border-t border-amber-200">
                        <label className="block text-xs font-bold text-slate-900 uppercase tracking-wider">
                          Officer Operational Rationale & Modification Notes
                        </label>
                        <textarea
                          rows={2}
                          value={officerNotes}
                          onChange={(e) => setOfficerNotes(e.target.value)}
                          placeholder="Document operational reasoning (e.g. road access clearance, priority triage adjustments)..."
                          className="w-full px-3 py-2 text-xs bg-white border border-slate-300 rounded-xl text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500"
                        />
                      </div>

                      {/* Edit Footer Action Bar */}
                      <div className="flex items-center justify-between pt-4 border-t border-amber-200">
                        <button
                          type="button"
                          onClick={handleCancelEdit}
                          className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 rounded-xl hover:bg-slate-100 transition"
                        >
                          Cancel Modification
                        </button>

                        <button
                          type="button"
                          onClick={handleProceedToDiffReview}
                          className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold bg-amber-600 hover:bg-amber-700 text-white shadow-xs transition"
                        >
                          REVIEW CHANGES (DIFF)
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Stage 3: REVIEW CHANGES BEFORE FINAL APPROVAL */}
                  {workflowMode === 'diff_review' && (() => {
                    const diff = computeDiffSummary();
                    return (
                      <div className="p-6 rounded-2xl bg-slate-50 border-2 border-slate-300 space-y-6 animate-in fade-in duration-200">
                        <div className="flex items-start justify-between gap-4 pb-3 border-b border-slate-200">
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold bg-blue-600 text-white uppercase tracking-wider">
                                PLAN DIFF REVIEW
                              </span>
                              <h3 className="text-base font-bold text-slate-900">
                                Review Coordination Plan Modifications
                              </h3>
                            </div>
                            <p className="text-xs text-slate-600 mt-1">
                              Verify all adjustments below. Approving will activate this candidate as the authoritative Active Response Plan.
                            </p>
                          </div>

                          <button
                            type="button"
                            onClick={() => setWorkflowMode('edit')}
                            className="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-200/60 transition font-medium"
                          >
                            Back to Edit
                          </button>
                        </div>

                        {/* Diff Summary Cards */}
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                          <div className="p-3.5 rounded-xl bg-white border border-slate-200 shadow-2xs">
                            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Total Changes</span>
                            <span className="text-base font-bold font-mono text-slate-900 mt-1 block">
                              {diff.changes.length} Component(s) Modified
                            </span>
                          </div>

                          <div className="p-3.5 rounded-xl bg-white border border-slate-200 shadow-2xs">
                            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Shortfall Status</span>
                            <span className={`text-base font-bold font-mono mt-1 block ${diff.shortfallCount > 0 ? 'text-amber-600' : 'text-emerald-700'}`}>
                              {diff.shortfallCount > 0 ? `${diff.shortfallCount} Supply Deficit(s)` : '0 Shortfall (Balanced)'}
                            </span>
                          </div>

                          <div className="p-3.5 rounded-xl bg-white border border-slate-200 shadow-2xs">
                            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Pre-Validation</span>
                            <span className="text-base font-bold font-mono text-emerald-700 mt-1 block flex items-center gap-1">
                              <CheckCircle2 className="w-4 h-4 text-emerald-600" /> PASS (Capacity Verified)
                            </span>
                          </div>
                        </div>

                        {/* Itemized Changes List */}
                        <div className="space-y-3">
                          <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                            Itemized Modifications ({diff.changes.length})
                          </h4>

                          {diff.changes.length === 0 ? (
                            <div className="p-6 rounded-xl bg-white border border-slate-200 text-center text-xs text-slate-500">
                              No components were modified. Plan is identical to AI proposal.
                            </div>
                          ) : (
                            <div className="space-y-2.5">
                              {diff.changes.map((ch, cIdx) => (
                                <div key={cIdx} className="p-3.5 rounded-xl bg-white border border-slate-200 space-y-1 shadow-2xs">
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
                                        CHANGED
                                      </span>
                                      <span className="text-xs font-bold text-slate-900">{ch.title}</span>
                                    </div>
                                    <span className="text-[10px] text-slate-400 uppercase font-mono">{ch.category}</span>
                                  </div>
                                  <div className="flex items-center gap-3 text-xs pt-1">
                                    <div className="text-slate-500">
                                      <span>AI Proposed: </span>
                                      <span className="font-mono line-through text-slate-400">{ch.originalValue}</span>
                                    </div>
                                    <span className="text-slate-400">&rarr;</span>
                                    <div className="font-bold text-emerald-700">
                                      <span>Officer Modified: </span>
                                      <span className="font-mono">{ch.modifiedValue}</span>
                                    </div>
                                  </div>
                                  {ch.detail && (
                                    <p className="text-[10px] text-slate-500 italic mt-0.5">{ch.detail}</p>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}

                          {diff.unchangedCount > 0 && (
                            <p className="text-[11px] text-slate-500 italic pl-1">
                              + {diff.unchangedCount} other plan components remained unchanged.
                            </p>
                          )}
                        </div>

                        {/* Officer Notes Preview */}
                        {officerNotes.trim() && (
                          <div className="p-3.5 rounded-xl bg-white border border-slate-200 space-y-1">
                            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Officer Notes to Record</span>
                            <p className="text-xs text-slate-800 italic">&ldquo;{officerNotes}&rdquo;</p>
                          </div>
                        )}

                        {/* Diff Review Footer Action Bar */}
                        <div className="flex items-center justify-between pt-4 border-t border-slate-200">
                          <button
                            type="button"
                            onClick={() => setWorkflowMode('edit')}
                            disabled={actionLoading}
                            className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 rounded-xl hover:bg-slate-200/60 transition disabled:opacity-50"
                          >
                            &larr; Back to Edit
                          </button>

                          <button
                            type="button"
                            onClick={() => handleApprovePlan(true)}
                            disabled={actionLoading}
                            className="flex items-center gap-2 px-6 py-2.5 rounded-xl text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs transition disabled:opacity-50"
                          >
                            {actionLoading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                            APPROVE MODIFIED PLAN
                          </button>
                        </div>
                      </div>
                    );
                  })()}

                  {/* Rejection Confirmation Modal */}
                  {rejectModalOpen && (
                    <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-2xs">
                      <div className="w-full max-w-md bg-white rounded-2xl p-6 border border-slate-200 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
                        <div className="flex items-center gap-2.5 text-red-600">
                          <XCircle className="w-6 h-6" />
                          <h3 className="text-base font-bold text-slate-900">Reject Coordination Plan</h3>
                        </div>
                        <p className="text-xs text-slate-600">
                          Please provide operational justification for rejecting this plan. The plan will remain inactive in the permanent audit trail.
                        </p>
                        <textarea
                          rows={3}
                          value={rejectNotes}
                          onChange={(e) => setRejectNotes(e.target.value)}
                          placeholder="Reason for rejection (e.g. invalid hazard assessment, access corridor impassable)..."
                          className="w-full px-3 py-2 text-xs bg-white border border-slate-300 rounded-xl text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
                        />
                        <div className="flex items-center justify-end gap-3 pt-2">
                          <button
                            type="button"
                            onClick={() => setRejectModalOpen(false)}
                            disabled={actionLoading}
                            className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={handleRejectPlanSubmit}
                            disabled={actionLoading}
                            className="flex items-center gap-1.5 px-5 py-2 rounded-xl text-xs font-bold bg-red-600 hover:bg-red-700 text-white shadow-xs disabled:opacity-50"
                          >
                            {actionLoading ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <XCircle className="w-3.5 h-3.5" />}
                            Confirm Rejection
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'healthcare' && (
                <div className="space-y-6">
                  {/* Healthcare Coordination Header Summary */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <HeartPulse className="w-4 h-4 text-rose-600" />
                        Healthcare & Hospital Coordination Intelligence
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Deterministic trauma matching, ICU readiness, oxygen supply verification, and multi-facility casualty routing.
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                        {activePlan.healthcare_summary?.facilities_evaluated ?? (activePlan.recommended_facilities?.length || 0)} Evaluated
                      </span>
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
                        {activePlan.recommended_facilities?.length || 0} Recommended
                      </span>
                      {activePlan.healthcare_summary?.total_shortfall ? (
                        <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                          {Math.round(activePlan.healthcare_summary.total_shortfall)} Deficit
                        </span>
                      ) : null}
                    </div>
                  </div>

                  {/* Top Healthcare KPI Metrics Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Estimated Casualties</span>
                      <span className="text-base font-bold font-mono text-slate-900 mt-1 block">
                        {activePlan.healthcare_summary?.estimated_casualties ? `${activePlan.healthcare_summary.estimated_casualties} Patients` : 'Unassessed'}
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Available Hospital Beds</span>
                      <span className="text-base font-bold font-mono text-slate-900 mt-1 block">
                        {Math.round(activePlan.healthcare_summary?.total_beds_available ?? 0)} Beds
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Routed Casualties</span>
                      <span className="text-base font-bold font-mono text-emerald-700 mt-1 block">
                        {Math.round(activePlan.healthcare_summary?.total_patients_covered ?? 0)} Patients
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Capacity Deficit</span>
                      <span className={`text-base font-bold font-mono mt-1 block ${
                        (activePlan.healthcare_summary?.total_shortfall || 0) > 0 ? 'text-red-600' : 'text-slate-700'
                      }`}>
                        {Math.round(activePlan.healthcare_summary?.total_shortfall ?? 0)} Patients
                      </span>
                    </div>
                  </div>

                  {/* Healthcare Summary Narrative Box */}
                  {activePlan.healthcare_summary?.explanation && (
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-1 shadow-2xs">
                      <span className="font-bold text-slate-900 uppercase tracking-wider text-[10px]">Healthcare Coordination Rationale</span>
                      <p className="text-slate-800 leading-relaxed font-medium">
                        {activePlan.healthcare_summary.explanation}
                      </p>
                    </div>
                  )}

                  {/* Recommended Healthcare Facilities List */}
                  {(!activePlan.recommended_facilities || activePlan.recommended_facilities.length === 0) ? (
                    <div className="py-14 text-center rounded-2xl bg-slate-50/60 border border-slate-200/80 p-8 space-y-3">
                      <div className="w-12 h-12 rounded-full bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center mx-auto shadow-2xs">
                        <HeartPulse className="w-6 h-6" />
                      </div>
                      <h4 className="text-sm font-bold text-slate-900">
                        {activePlan.healthcare_summary?.medical_required
                          ? 'Zero Available Medical Facilities Matched'
                          : 'Emergency Medical Routing Not Required'}
                      </h4>
                      <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
                        {activePlan.healthcare_summary?.medical_required
                          ? 'No hospital facilities with available bed or trauma capacity found within response radius. Escalated for officer attention.'
                          : 'Incident assessment indicates zero casualty demand for this operational profile.'}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {activePlan.recommended_facilities.map((fac, idx) => (
                        <div
                          key={idx}
                          className="p-5 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3 hover:border-slate-300 transition"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-100">
                            <div className="flex items-center gap-2">
                              <span className="px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-rose-50 text-rose-800 border border-rose-200">
                                {fac.facility_name}
                              </span>
                              <span className="text-[10px] font-mono text-slate-400">
                                {fac.facility_id}
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                {fac.status || 'AVAILABLE'}
                              </span>
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-800 border border-rose-200">
                                Score: {formatScore(fac.suitability_score)}/100
                              </span>
                            </div>
                          </div>

                          <div className="text-xs text-slate-600 space-y-1">
                            <div className="flex items-center gap-1.5">
                              <MapPin className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                              <span>{fac.location_address || 'Regional Hospital Center'}</span>
                            </div>
                            <p className="text-slate-800 font-medium pt-1">
                              {fac.recommendation_reason || 'Designated medical transfer facility.'}
                            </p>
                          </div>

                          {/* Hospital Metrics Bar */}
                          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-1">
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Available Beds</span>
                              <span className="text-xs font-bold text-slate-900 font-mono">
                                {Math.round(fac.available_beds ?? 0)} / {Math.round(fac.total_beds ?? 0)}
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Allocated Patients</span>
                              <span className="text-xs font-bold text-rose-700 font-mono">
                                {Math.round(fac.allocated_patients ?? 0)} Patients
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">ICU Beds</span>
                              <span className="text-xs font-bold text-slate-900 font-mono">
                                {fac.icu_available ?? 0} ICU Available
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Oxygen & Trauma</span>
                              <span className="text-xs font-bold text-emerald-700 font-mono">
                                {fac.oxygen_available ? 'Oxygen OK' : 'No O2'} • {fac.trauma_capable ? 'Trauma Center' : 'Basic'}
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Transit Distance</span>
                              <span className="text-xs font-bold text-slate-800 font-mono">
                                {fac.distance_km ? `${fac.distance_km} km` : '0 km'}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'volunteers' && (
                <div className="space-y-6">
                  {/* Volunteer Coordination Header Summary */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <Users className="w-4 h-4 text-emerald-600" />
                        Volunteer & Field Responder Operations
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Deterministic matching of verified volunteer skills, operational zones, and immediate availability.
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                        {activePlan.volunteer_summary?.volunteers_evaluated ?? (activePlan.recommended_volunteers?.length || 0)} Evaluated
                      </span>
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                        {activePlan.recommended_volunteers?.length || 0} Assigned
                      </span>
                      {activePlan.volunteer_summary?.total_shortfall ? (
                        <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                          {activePlan.volunteer_summary.total_shortfall} Shortfall
                        </span>
                      ) : null}
                    </div>
                  </div>

                  {/* Top Volunteer KPI Metrics Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Estimated Demand</span>
                      <span className="text-base font-bold font-mono text-slate-900 mt-1 block">
                        {activePlan.volunteer_summary?.estimated_volunteers_needed ?? 0} Responders
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Evaluated Responders</span>
                      <span className="text-base font-bold font-mono text-slate-900 mt-1 block">
                        {activePlan.volunteer_summary?.volunteers_evaluated ?? (activePlan.recommended_volunteers?.length || 0)} Registered
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Assigned Responders</span>
                      <span className="text-base font-bold font-mono text-emerald-700 mt-1 block">
                        {activePlan.volunteer_summary?.total_volunteers_assigned ?? (activePlan.recommended_volunteers?.length || 0)} Personnel
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Personnel Shortfall</span>
                      <span className={`text-base font-bold font-mono mt-1 block ${
                        (activePlan.volunteer_summary?.total_shortfall || 0) > 0 ? 'text-red-600' : 'text-slate-700'
                      }`}>
                        {activePlan.volunteer_summary?.total_shortfall ?? 0} Responders
                      </span>
                    </div>
                  </div>

                  {/* Volunteer Summary Narrative Box */}
                  {activePlan.volunteer_summary?.explanation && (
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-1 shadow-2xs">
                      <span className="font-bold text-slate-900 uppercase tracking-wider text-[10px]">Volunteer Coordination Rationale</span>
                      <p className="text-slate-800 leading-relaxed font-medium">
                        {activePlan.volunteer_summary.explanation}
                      </p>
                    </div>
                  )}

                  {/* Recommended Volunteers List */}
                  {(!activePlan.recommended_volunteers || activePlan.recommended_volunteers.length === 0) ? (
                    <div className="py-14 text-center rounded-2xl bg-slate-50/60 border border-slate-200/80 p-8 space-y-3">
                      <div className="w-12 h-12 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center mx-auto shadow-2xs">
                        <Users className="w-6 h-6" />
                      </div>
                      <h4 className="text-sm font-bold text-slate-900">
                        {activePlan.volunteer_summary?.volunteers_required
                          ? 'Zero Available Qualified Volunteers'
                          : 'Field Volunteer Activation Not Required'}
                      </h4>
                      <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
                        {activePlan.volunteer_summary?.volunteers_required
                          ? 'No active verified volunteer responders with required skill profiles located within response zone. Escalated for officer attention.'
                          : 'Incident assessment indicates zero field volunteer requirement for current operational profile.'}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {activePlan.recommended_volunteers.map((vol, idx) => (
                        <div
                          key={idx}
                          className="p-5 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3 hover:border-slate-300 transition"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-100">
                            <div className="flex items-center gap-2">
                              <span className="px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                                {vol.volunteer_name}
                              </span>
                              <span className="text-[10px] font-mono text-slate-400">
                                {vol.volunteer_id}
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                                {vol.role_or_skill}
                              </span>
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                                Score: {formatScore(vol.suitability_score)}/100
                              </span>
                            </div>
                          </div>

                          <div className="text-xs text-slate-600 space-y-1">
                            <div className="flex items-center gap-3">
                              <div className="flex items-center gap-1.5">
                                <MapPin className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                <span>Zone: <strong>{vol.location_zone || 'Operational Sector'}</strong></span>
                              </div>
                              {vol.phone && (
                                <div className="flex items-center gap-1.5">
                                  <Phone className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                  <span>{vol.phone}</span>
                                </div>
                              )}
                            </div>
                            <p className="text-slate-800 font-medium pt-1">
                              <strong>Assigned Mission:</strong> {vol.assigned_operation || 'Emergency Support Operations'}
                            </p>
                            <p className="text-slate-600 text-[11px]">
                              {vol.recommendation_reason || 'Verified volunteer skills matched to operational requirements.'}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'routes' && (
                <div className="space-y-6">
                  {/* Route & Transport Header Summary */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <Truck className="w-4 h-4 text-indigo-600" />
                        Transit Corridors & Fleet Coordination
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Deterministic route analysis, road clearance verification, transit corridors, and fleet unit allocation.
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                        {activePlan.route_summary?.routes_evaluated ?? (activePlan.recommended_routes?.length || 0)} Routes Evaluated
                      </span>
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                        {activePlan.recommended_transports?.length || 0} Transports
                      </span>
                      {activePlan.route_summary?.transport_shortfall ? (
                        <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                          {activePlan.route_summary.transport_shortfall} Fleet Shortfall
                        </span>
                      ) : null}
                    </div>
                  </div>

                  {/* Route Summary Narrative Box */}
                  {activePlan.route_summary?.explanation && (
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-1 shadow-2xs">
                      <span className="font-bold text-slate-900 uppercase tracking-wider text-[10px]">Route Logistics Rationale</span>
                      <p className="text-slate-800 leading-relaxed font-medium">
                        {activePlan.route_summary.explanation}
                      </p>
                    </div>
                  )}

                  {/* Recommended Vehicles & Routes Grid */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Fleet Transports List */}
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                        <Truck className="w-3.5 h-3.5 text-indigo-600" />
                        Allocated Fleet Units ({activePlan.recommended_transports?.length || 0})
                      </h4>

                      {(!activePlan.recommended_transports || activePlan.recommended_transports.length === 0) ? (
                        <div className="p-6 rounded-xl bg-slate-50 text-center text-xs text-slate-500">
                          No fleet vehicles assigned to this plan.
                        </div>
                      ) : (
                        activePlan.recommended_transports.map((veh, idx) => (
                          <div key={idx} className="p-4 rounded-xl bg-white border border-slate-200 space-y-2 shadow-2xs">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-slate-900">{veh.vehicle_name}</span>
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                                {veh.vehicle_type}
                              </span>
                            </div>
                            <p className="text-xs text-slate-600">
                              <strong>Mission:</strong> {veh.assigned_mission}
                            </p>
                            <div className="flex items-center gap-4 text-[11px] text-slate-500 font-mono">
                              <span>Capacity: {veh.capacity} Units</span>
                              <span>Status: {veh.current_status}</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>

                    {/* Transit Routes List */}
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                        <Navigation className="w-3.5 h-3.5 text-indigo-600" />
                        Transit Clearance Corridors ({activePlan.recommended_routes?.length || 0})
                      </h4>

                      {(!activePlan.recommended_routes || activePlan.recommended_routes.length === 0) ? (
                        <div className="p-6 rounded-xl bg-slate-50 text-center text-xs text-slate-500">
                          No transit corridors mapped for this plan.
                        </div>
                      ) : (
                        activePlan.recommended_routes.map((rot, idx) => (
                          <div key={idx} className="p-4 rounded-xl bg-white border border-slate-200 space-y-2 shadow-2xs">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-slate-900">{rot.origin_name} &rarr; {rot.destination_name}</span>
                              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                                rot.road_condition_status === 'PASSABLE' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-amber-50 text-amber-700 border-amber-200'
                              }`}>
                                {rot.road_condition_status}
                              </span>
                            </div>
                            <p className="text-xs text-slate-600">{rot.recommendation_reason}</p>
                            <div className="flex items-center gap-4 text-[11px] text-slate-500 font-mono">
                              <span>Distance: {rot.distance_km} km</span>
                              <span>Est. Time: {rot.estimated_duration_minutes} mins</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'shelters' && (
                <div className="space-y-6">
                  {/* Shelter Coordination Header Summary */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <Home className="w-4 h-4 text-blue-600" />
                        Emergency Shelter Coordination Intelligence
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Deterministic capacity assessment, proximity analysis, and multi-shelter distribution for affected evacuees.
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                        {activePlan.shelter_summary?.shelters_evaluated ?? (activePlan.recommended_shelters?.length || 0)} Evaluated
                      </span>
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                        {activePlan.recommended_shelters?.length || 0} Allocated
                      </span>
                      {activePlan.shelter_summary?.total_shortfall ? (
                        <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                          {Math.round(activePlan.shelter_summary.total_shortfall)} Shortfall
                        </span>
                      ) : null}
                    </div>
                  </div>

                  {/* Top Shelter KPI Metrics Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Estimated Evacuees</span>
                      <span className="text-base font-bold font-mono text-slate-900 mt-1 block">
                        {activePlan.shelter_summary?.affected_population ? `${activePlan.shelter_summary.affected_population} Persons` : 'Unassessed'}
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Regional Capacity</span>
                      <span className="text-base font-bold font-mono text-slate-900 mt-1 block">
                        {Math.round(activePlan.shelter_summary?.total_capacity_available ?? 0)} Beds Available
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Covered Population</span>
                      <span className="text-base font-bold font-mono text-emerald-700 mt-1 block">
                        {Math.round(activePlan.shelter_summary?.total_population_covered ?? 0)} Evacuees
                      </span>
                    </div>

                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs">
                      <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">Unaccommodated Shortfall</span>
                      <span className={`text-base font-bold font-mono mt-1 block ${
                        (activePlan.shelter_summary?.total_shortfall || 0) > 0 ? 'text-red-600' : 'text-slate-700'
                      }`}>
                        {Math.round(activePlan.shelter_summary?.total_shortfall ?? 0)} Persons
                      </span>
                    </div>
                  </div>

                  {/* Narrative Rationale Box */}
                  {activePlan.shelter_summary?.explanation && (
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-1 shadow-2xs">
                      <span className="font-bold text-slate-900 uppercase tracking-wider text-[10px]">Shelter Coordination Summary</span>
                      <p className="text-slate-800 leading-relaxed font-medium">
                        {activePlan.shelter_summary.explanation}
                      </p>
                    </div>
                  )}

                  {/* Shelter Facilities Cards List */}
                  {(!activePlan.recommended_shelters || activePlan.recommended_shelters.length === 0) ? (
                    <div className="py-14 text-center rounded-2xl bg-slate-50/60 border border-slate-200/80 p-8 space-y-3">
                      <div className="w-12 h-12 rounded-full bg-blue-50 border border-blue-200 text-blue-600 flex items-center justify-center mx-auto shadow-2xs">
                        <Home className="w-6 h-6" />
                      </div>
                      <h4 className="text-sm font-bold text-slate-900">
                        {activePlan.shelter_summary?.shelter_required
                          ? 'Zero Available Shelters Within Response Radius'
                          : 'Shelter Coordination Not Required'}
                      </h4>
                      <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
                        {activePlan.shelter_summary?.shelter_required
                          ? 'No active shelters with available capacity could be matched for this incident location. Escalated for officer attention.'
                          : 'Disaster assessment indicates zero displacement risk for current incident profile.'}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {activePlan.recommended_shelters.map((shl, idx) => (
                        <div
                          key={idx}
                          className="p-5 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3 hover:border-slate-300 transition"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-100">
                            <div className="flex items-center gap-2">
                              <span className="px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-blue-50 text-blue-800 border border-blue-200">
                                {shl.shelter_name}
                              </span>
                              <span className="text-[10px] font-mono text-slate-400">
                                {shl.shelter_id}
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                                {shl.status || 'AVAILABLE'}
                              </span>
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-blue-800 border border-blue-200">
                                Score: {formatScore(shl.suitability_score)}/100
                              </span>
                            </div>
                          </div>

                          <div className="text-xs text-slate-600 space-y-1">
                            <div className="flex items-center gap-1.5">
                              <MapPin className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                              <span>{shl.location_address || 'Designated Regional Center'}</span>
                            </div>
                            <p className="text-slate-800 font-medium pt-1">
                              {shl.recommendation_reason || 'Verified shelter facility for displaced evacuees.'}
                            </p>
                          </div>

                          {/* Metrics Bar */}
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Total Capacity</span>
                              <span className="text-xs font-bold text-slate-900 font-mono">
                                {Math.round(shl.total_capacity ?? 0)} Beds
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Current Occupancy</span>
                              <span className="text-xs font-bold text-slate-900 font-mono">
                                {Math.round(shl.current_occupancy ?? 0)} ({Math.round((shl.total_capacity ?? 0) - (shl.remaining_capacity ?? 0))} used)
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Remaining Capacity</span>
                              <span className="text-xs font-bold text-emerald-700 font-mono">
                                {Math.round(shl.remaining_capacity ?? 0)} Beds Free
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Transit Distance</span>
                              <span className="text-xs font-bold text-slate-800 font-mono">
                                {shl.distance_km ? `${shl.distance_km} km` : '0 km'}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'conflicts' && (
                <div className="space-y-6">
                  {/* Conflict Resolution Header Summary */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                        <Split className="w-4 h-4 text-red-600" />
                        Cross-Domain Conflict Resolution & Constraint Intelligence
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Deterministic multi-agent evaluation of inventory shortages, hospital deficits, volunteer shortfalls, and blocked transit corridors.
                      </p>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                        {normalizedConflicts.length} Total Evaluated
                      </span>
                      {activePlan.conflict_summary && (
                        <>
                          <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            {activePlan.conflict_summary.resolved_conflicts ?? 0} Resolved
                          </span>
                          {(activePlan.conflict_summary.unresolved_conflicts || 0) > 0 && (
                            <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                              {activePlan.conflict_summary.unresolved_conflicts} Escalated
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  </div>

                  {/* Summary Narrative Banner */}
                  {activePlan.conflict_summary?.explanation && (
                    <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-1 shadow-2xs">
                      <span className="font-bold text-slate-900 uppercase tracking-wider text-[10px]">Orchestrator Conflict Summary</span>
                      <p className="text-slate-800 leading-relaxed font-medium">
                        {activePlan.conflict_summary.explanation}
                      </p>
                    </div>
                  )}

                  {/* Conflict List */}
                  {normalizedConflicts.length === 0 ? (
                    <div className="py-14 text-center rounded-2xl bg-slate-50/60 border border-slate-200/80 p-8 space-y-3">
                      <div className="w-12 h-12 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center mx-auto shadow-2xs">
                        <CheckCircle2 className="w-6 h-6" />
                      </div>
                      <h4 className="text-sm font-bold text-slate-900">No Coordination Conflicts Detected</h4>
                      <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
                        All assessed emergency requirements across supplies, hospital beds, volunteers, shelters, and fleet corridors are fully satisfied.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {normalizedConflicts.map((conf, idx) => (
                        <div
                          key={idx}
                          className="p-5 rounded-xl bg-white border border-slate-200 shadow-2xs space-y-3 hover:border-slate-300 transition"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-100">
                            <div className="flex items-center gap-2">
                              <span className="px-2.5 py-0.5 rounded-md text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                                {String(conf.conflict_type || 'CONFLICT').replace(/_/g, ' ')}
                              </span>
                              <span className="text-[10px] font-mono text-slate-400">
                                {conf.conflict_id}
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                                conf.severity === 'CRITICAL' ? 'bg-red-50 text-red-700 border-red-200' :
                                conf.severity === 'HIGH' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                                'bg-slate-50 text-slate-700 border-slate-200'
                              }`}>
                                {conf.severity}
                              </span>

                              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                                conf.resolution_status === 'RESOLVED' || conf.resolution_status === 'PARTIALLY_RESOLVED'
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                  : 'bg-red-50 text-red-700 border-red-200'
                              }`}>
                                {String(conf.resolution_status || 'UNRESOLVED').replace(/_/g, ' ')}
                              </span>
                            </div>
                          </div>

                          <div>
                            <p className="text-xs font-semibold text-slate-900 leading-snug">
                              {conf.description}
                            </p>
                            <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                              {conf.explanation}
                            </p>
                          </div>

                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Required</span>
                              <span className="text-xs font-bold text-slate-900 font-mono">
                                {conf.detected_quantity !== undefined && conf.detected_quantity !== null ? conf.detected_quantity : 'Unavailable'}
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Available</span>
                              <span className="text-xs font-bold text-slate-900 font-mono">
                                {conf.available_quantity !== undefined && conf.available_quantity !== null ? conf.available_quantity : 'Unavailable'}
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Shortfall</span>
                              <span className={`text-xs font-bold font-mono ${
                                conf.shortfall && conf.shortfall > 0 ? 'text-red-600' : 'text-slate-600'
                              }`}>
                                {conf.shortfall !== undefined && conf.shortfall !== null ? conf.shortfall : 'Unavailable'}
                              </span>
                            </div>
                            <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200/80">
                              <span className="text-[10px] font-medium text-slate-500 block">Resolution Strategy</span>
                              <span className="text-xs font-bold text-slate-800 truncate block">
                                {conf.resolution_strategy ? String(conf.resolution_strategy).replace(/_/g, ' ') : 'None'}
                              </span>
                            </div>
                          </div>

                          {conf.officer_attention_required && (
                            <div className="p-2.5 rounded-lg bg-red-50/70 border border-red-200/80 flex items-center justify-between text-xs text-red-800">
                              <span className="flex items-center gap-1.5 font-semibold">
                                <AlertTriangle className="w-3.5 h-3.5 text-red-600" />
                                Officer Attention Required
                              </span>
                              <span className="text-[10px] text-red-600">Requires review before dispatch</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'agents' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-900">
                      Raw Agent Run Records ({agentRuns.length})
                    </h3>
                    <span className="text-xs text-slate-500 font-mono">Collection `ai_agent_runs`</span>
                  </div>

                  <div className="space-y-3">
                    {agentRuns.length === 0 ? (
                      <div className="p-8 text-center text-slate-400 text-xs">
                        No individual agent runs recorded yet.
                      </div>
                    ) : (
                      agentRuns.map((run, idx) => (
                        <div key={idx} className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <Bot className="w-4 h-4 text-red-600" />
                              <span className="text-xs font-bold text-slate-900 font-mono">{run.agent_name}</span>
                              <span className="text-[10px] text-slate-400">({run.run_id})</span>
                            </div>
                            {getAgentStatusBadge(run.status)}
                          </div>
                          <p className="text-xs text-slate-700">
                            {run.result?.recommendation || 'Execution completed.'}
                          </p>
                          <div className="flex items-center gap-4 text-[11px] text-slate-500 font-mono">
                            <span>Started: {formatTime(run.started_at)}</span>
                            <span>Confidence: {Math.round((run.confidence ?? 1) * 100)}%</span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'history' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-900">
                      Coordination Plan Revision History ({allPlans.length})
                    </h3>
                    <span className="text-xs text-slate-500 font-mono">Collection `coordination_plans`</span>
                  </div>

                  <div className="space-y-3">
                    {allPlans.map((p, idx) => (
                      <div
                        key={idx}
                        onClick={() => {
                          setActivePlan(p);
                          setActiveTab('plan');
                        }}
                        className={`p-4 rounded-xl border cursor-pointer transition ${
                          activePlan.plan_id === p.plan_id
                            ? 'bg-red-50/40 border-red-300 shadow-2xs'
                            : 'bg-white border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <FileCheck2 className="w-4 h-4 text-red-600" />
                            <span className="text-xs font-mono font-bold text-slate-900">{p.plan_id}</span>
                            <span className="text-[11px] text-slate-500 font-mono">v{p.version}</span>
                          </div>
                          {getStatusBadge(p.status)}
                        </div>
                        <p className="text-xs text-slate-600 mt-1">{p.reasoning}</p>
                        <p className="text-[10px] text-slate-400 mt-2 font-mono">
                          Generated: {formatDate(p.generated_at)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
