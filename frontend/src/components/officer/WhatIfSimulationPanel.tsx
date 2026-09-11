import React, { useState, useEffect, useCallback } from 'react';
import {
  FlaskConical,
  Play,
  Plus,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Eye,
  XCircle,
  Boxes,
  Layers,
  Sparkles,
  Check,
} from 'lucide-react';
import type {
  SimulationRun,
  SimulationEntityTarget,
  SimulationTargetLookupResponse,
  ScenarioType,
} from '../../types';
import {
  listSimulations,
  createSimulation,
  getSimulation,
  getSimulationTargets,
  addSimulationScenario,
  removeSimulationScenario,
  runSimulation,
  discardSimulation,
} from '../../services/api';
import { listSituations } from '../../services/situationsApi';
import { CoordinationPlanDiffModal } from './CoordinationPlanDiffModal';

interface WhatIfSimulationPanelProps {
  initialSituationId?: string;
  onInspectSituation?: (situationId: string) => void;
}

function formatApiError(err: any, fallback: string): string {
  if (!err) return fallback;
  const detail = err.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d: any) => d.msg || `${d.loc?.slice(-1)[0]}: ${d.type}`).join(', ');
  }
  if (err.message) return err.message;
  return fallback;
}

export const WhatIfSimulationPanel: React.FC<WhatIfSimulationPanelProps> = ({
  initialSituationId,
  onInspectSituation,
}) => {
  // Situations list for selection
  const [situations, setSituations] = useState<any[]>([]);
  const [selectedSituationId, setSelectedSituationId] = useState<string>(initialSituationId || '');
  
  // Simulations list & active simulation
  const [simulations, setSimulations] = useState<SimulationRun[]>([]);
  const [activeSimulation, setActiveSimulation] = useState<SimulationRun | null>(null);
  const [targetLookup, setTargetLookup] = useState<SimulationTargetLookupResponse | null>(null);
  
  // Loading states
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // New Simulation Form
  const [showNewSimModal, setShowNewSimModal] = useState<boolean>(false);
  const [newSimName, setNewSimName] = useState<string>('');

  // Scenario Builder Form State
  const [scenarioType, setScenarioType] = useState<ScenarioType>('RESOURCE_REDUCTION');
  const [scenarioTitle, setScenarioTitle] = useState<string>('');
  const [scenarioDesc, setScenarioDesc] = useState<string>('');
  const [selectedTargetType, setSelectedTargetType] = useState<string>('RESOURCE');
  const [selectedTargetId, setSelectedTargetId] = useState<string>('');
  const [reductionPct, setReductionPct] = useState<number>(50);
  const [surgePct, setSurgePct] = useState<number>(50);
  const [blockRoute] = useState<boolean>(true);

  // Diff Modal State
  const [isDiffModalOpen, setIsDiffModalOpen] = useState<boolean>(false);

  // Discard Dialog State
  const [showDiscardModal, setShowDiscardModal] = useState<boolean>(false);
  const [discardReason, setDiscardReason] = useState<string>('');

  // Load Situations
  const loadSituations = useCallback(async () => {
    try {
      const res = await listSituations({ limit: 50 });
      const items = res?.items || [];
      setSituations(items);
      if (!selectedSituationId && items.length > 0) {
        setSelectedSituationId(items[0].situation_id);
      }
    } catch (err: any) {
      console.warn('Failed to load situations:', err);
    }
  }, [selectedSituationId]);

  // Load Simulations for selected situation
  const loadSimulations = useCallback(async () => {
    if (!selectedSituationId) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const [sims, targets] = await Promise.all([
        listSimulations({ situation_id: selectedSituationId }),
        getSimulationTargets(selectedSituationId).catch(() => null),
      ]);
      setSimulations(sims || []);
      setTargetLookup(targets);
      
      // Keep active simulation or select the first one
      if (activeSimulation) {
        const found = (sims || []).find((s) => s.simulation_id === activeSimulation.simulation_id);
        if (found) {
          setActiveSimulation(found);
        } else if (sims && sims.length > 0) {
          setActiveSimulation(sims[0]);
        }
      } else if (sims && sims.length > 0) {
        setActiveSimulation(sims[0]);
      }
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to load simulations.'));
    } finally {
      setLoading(false);
    }
  }, [selectedSituationId, activeSimulation]);

  useEffect(() => {
    loadSituations();
  }, [loadSituations]);

  useEffect(() => {
    if (selectedSituationId) {
      loadSimulations();
    }
  }, [selectedSituationId]);

  // Handle Situation Change
  const handleSelectSituation = (sitId: string) => {
    setSelectedSituationId(sitId);
    setActiveSimulation(null);
  };

  // Create Simulation
  const handleCreateSimulation = async () => {
    if (!selectedSituationId) return;
    setActionLoading(true);
    setErrorMsg(null);
    try {
      const newSim = await createSimulation({
        situation_id: selectedSituationId,
        simulation_name: newSimName || undefined,
      });
      setSuccessMsg(`Simulation draft '${newSim.simulation_id}' initialized.`);
      setShowNewSimModal(false);
      setNewSimName('');
      await loadSimulations();
      setActiveSimulation(newSim);
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to initialize simulation.'));
    } finally {
      setActionLoading(false);
    }
  };

  // Add Scenario to Active Simulation
  const handleAddScenario = async () => {
    if (!activeSimulation) return;
    if (!selectedTargetId) {
      setErrorMsg('Select a valid operational target.');
      return;
    }
    setActionLoading(true);
    setErrorMsg(null);
    try {
      let targetEntityType = selectedTargetType;
      let targetDomain = 'RESOURCE_MANAGEMENT';
      let simulatedVal: Record<string, any> = {};

      if (scenarioType === 'RESOURCE_REDUCTION') {
        targetEntityType = 'RESOURCE';
        targetDomain = 'RESOURCE_MANAGEMENT';
        simulatedVal = {
          reduction_percentage: Number(reductionPct),
          reason: `Hypothetical ${reductionPct}% stock depletion`,
        };
      } else if (scenarioType === 'RESOURCE_UNAVAILABLE') {
        targetEntityType = 'RESOURCE';
        targetDomain = 'RESOURCE_MANAGEMENT';
        simulatedVal = {
          available_quantity: 0,
          status: 'UNAVAILABLE',
          reason: 'Depot flooded or out of commission',
        };
      } else if (scenarioType === 'DEMAND_SURGE') {
        targetEntityType = 'RESOURCE';
        targetDomain = 'RESOURCE_MANAGEMENT';
        simulatedVal = {
          surge_percentage: Number(surgePct),
          reason: `Surge in localized demand (+${surgePct}%)`,
        };
      } else if (scenarioType === 'FACILITY_OFFLINE') {
        targetEntityType = selectedTargetType === 'HEALTHCARE' ? 'HEALTHCARE_FACILITY' : 'SHELTER';
        targetDomain = selectedTargetType === 'HEALTHCARE' ? 'HEALTHCARE' : 'SHELTER';
        simulatedVal = {
          is_active: false,
          status: 'OFFLINE',
          capacity_available: 0,
          reason: 'Structural failure or severe inundation',
        };
      } else if (scenarioType === 'ROUTE_BLOCKED') {
        targetEntityType = 'ROUTE';
        targetDomain = 'TRANSPORT_LOGISTICS';
        simulatedVal = {
          is_blocked: blockRoute,
          status: 'BLOCKED',
          reason: 'Bridge collapsed / road washed away',
        };
      } else if (scenarioType === 'VOLUNTEER_DROPOUT') {
        targetEntityType = 'VOLUNTEER';
        targetDomain = 'VOLUNTEER_OPERATIONS';
        simulatedVal = {
          dropout_percentage: Number(reductionPct),
          status: 'UNAVAILABLE',
          reason: 'Responder fatigue / access blocked',
        };
      }

      const defaultTitle = `${scenarioType.replace(/_/g, ' ')}: ${selectedTargetId || 'Asset'}`;
      const defaultDesc = `Simulated perturbation: ${JSON.stringify(simulatedVal)}`;

      await addSimulationScenario(activeSimulation.simulation_id, {
        scenario_type: scenarioType,
        title: scenarioTitle || defaultTitle,
        description: scenarioDesc || defaultDesc,
        target_entity_type: targetEntityType,
        target_entity_id: selectedTargetId || 'DEFAULT',
        target_domain: targetDomain as any,
        simulated_value: simulatedVal,
      });

      // Reload full fresh simulation run
      const freshSim = await getSimulation(activeSimulation.simulation_id);
      setActiveSimulation(freshSim);
      setSuccessMsg('Hypothetical scenario added to simulation run.');
      setScenarioTitle('');
      setScenarioDesc('');
      await loadSimulations();
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to add scenario.'));
    } finally {
      setActionLoading(false);
    }
  };

  // Remove Scenario
  const handleRemoveScenario = async (scenarioId: string) => {
    if (!activeSimulation) return;
    setActionLoading(true);
    setErrorMsg(null);
    try {
      await removeSimulationScenario(activeSimulation.simulation_id, scenarioId);
      const freshSim = await getSimulation(activeSimulation.simulation_id);
      setActiveSimulation(freshSim);
      setSuccessMsg('Scenario removed.');
      await loadSimulations();
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to remove scenario.'));
    } finally {
      setActionLoading(false);
    }
  };

  // Run Simulation
  const handleRunSimulation = async () => {
    if (!activeSimulation) return;
    if (!activeSimulation.scenarios || activeSimulation.scenarios.length === 0) {
      setErrorMsg('Add at least one hypothetical change before running the simulation.');
      return;
    }
    setActionLoading(true);
    setErrorMsg(null);
    try {
      const res = await runSimulation(activeSimulation.simulation_id);
      setSuccessMsg(`Simulation '${activeSimulation.simulation_id}' evaluated successfully! ${res.total_changes} plan component deltas computed.`);
      const refreshedSim = await getSimulation(activeSimulation.simulation_id);
      setActiveSimulation(refreshedSim);
      await loadSimulations();
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to execute simulation.'));
    } finally {
      setActionLoading(false);
    }
  };

  // Discard Simulation
  const handleDiscardSimulation = async () => {
    if (!activeSimulation) return;
    setActionLoading(true);
    setErrorMsg(null);
    try {
      await discardSimulation(activeSimulation.simulation_id, discardReason);
      setSuccessMsg(`Simulation '${activeSimulation.simulation_id}' discarded.`);
      setShowDiscardModal(false);
      setDiscardReason('');
      const freshSim = await getSimulation(activeSimulation.simulation_id);
      setActiveSimulation(freshSim);
      await loadSimulations();
    } catch (err: any) {
      setErrorMsg(formatApiError(err, 'Failed to discard simulation.'));
    } finally {
      setActionLoading(false);
    }
  };

  // Helper to get available target entities based on chosen scenario type
  const getRelevantTargets = (): SimulationEntityTarget[] => {
    if (!targetLookup) return [];
    if (scenarioType === 'RESOURCE_REDUCTION' || scenarioType === 'RESOURCE_UNAVAILABLE' || scenarioType === 'DEMAND_SURGE') {
      return targetLookup.resources || [];
    }
    if (scenarioType === 'FACILITY_OFFLINE') {
      return [...(targetLookup.shelters || []), ...(targetLookup.healthcare || [])];
    }
    if (scenarioType === 'ROUTE_BLOCKED') {
      return [...(targetLookup.routes || []), ...(targetLookup.transports || [])];
    }
    if (scenarioType === 'VOLUNTEER_DROPOUT') {
      return targetLookup.volunteers || [];
    }
    return [
      ...(targetLookup.resources || []),
      ...(targetLookup.shelters || []),
      ...(targetLookup.healthcare || []),
      ...(targetLookup.routes || []),
      ...(targetLookup.volunteers || []),
    ];
  };

  const relevantTargets = getRelevantTargets();

  return (
    <div className="space-y-6">
      {/* ========================================================================= */}
      {/* 1. HEADER & SANDBOX SAFETY NOTICE */}
      {/* ========================================================================= */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-xl bg-purple-50 text-purple-700 flex items-center justify-center font-bold border border-purple-200">
              <FlaskConical className="w-4 h-4" />
            </div>
            <h1 className="text-lg font-bold text-slate-900">What-If Scenario Simulation Engine</h1>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-50 text-purple-700 border border-purple-200">
              PREDICTIVE TWIN
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" />
              Isolated Snapshot Safe
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1 max-w-2xl">
            Simulate hypothetical compound disruptions, inventory shocks, shelter closures, and route blockages.
            Calculates multi-agent plan adaptations in memory without mutating real operational data.
          </p>
        </div>

        {/* Situation Selector & Action */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5">
            <span className="text-[11px] font-bold text-slate-500 uppercase">Situation:</span>
            <select
              value={selectedSituationId}
              onChange={(e) => handleSelectSituation(e.target.value)}
              className="bg-transparent text-xs font-bold text-slate-900 focus:outline-hidden cursor-pointer"
            >
              {situations.map((sit) => (
                <option key={sit.situation_id} value={sit.situation_id}>
                  {sit.title || `Situation ${sit.situation_id}`} ({sit.situation_id})
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={() => setShowNewSimModal(true)}
            disabled={targetLookup ? !targetLookup.has_active_baseline && (!targetLookup.baseline_plan_id || targetLookup.baseline_plan_id === 'NONE') : false}
            className="px-3.5 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-xs cursor-pointer"
            title={targetLookup && !targetLookup.has_active_baseline ? "An active response plan is required to initialize a simulation" : "Initialize new simulation"}
          >
            <Plus className="w-4 h-4" />
            <span>New Simulation</span>
          </button>
        </div>
      </div>

      {/* Authoritative Live Baseline Ribbon */}
      {targetLookup && (
        <div className={`p-3.5 rounded-xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs ${
          targetLookup.has_active_baseline || (targetLookup.baseline_plan_id && targetLookup.baseline_plan_id !== 'NONE')
            ? 'bg-emerald-50/70 border-emerald-200/80 text-emerald-900'
            : 'bg-amber-50 border-amber-200 text-amber-900'
        }`}>
          <div className="flex items-center gap-2.5">
            {targetLookup.has_active_baseline || (targetLookup.baseline_plan_id && targetLookup.baseline_plan_id !== 'NONE') ? (
              <>
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shrink-0 animate-pulse" />
                <div>
                  <span className="font-bold uppercase tracking-wider text-[11px] text-emerald-800 mr-2">LIVE BASELINE:</span>
                  <span className="font-mono font-bold text-slate-900">{targetLookup.baseline_plan_id} (v{targetLookup.baseline_plan_version})</span>
                  <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                    {targetLookup.baseline_plan_status || 'ACTIVE'}
                  </span>
                  {targetLookup.baseline_plan_activated_at && (
                    <span className="ml-2 text-emerald-700 text-[11px]">
                      Activated {new Date(targetLookup.baseline_plan_activated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  )}
                </div>
              </>
            ) : (
              <>
                <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                <div>
                  <span className="font-bold">No active response plan is available for this situation.</span>
                  <p className="text-amber-800 text-[11px] mt-0.5">
                    Activate an authoritative response plan before creating and running What-If simulations.
                  </p>
                </div>
              </>
            )}
          </div>

          <div className="flex items-center gap-2">
            {(!targetLookup.has_active_baseline && (!targetLookup.baseline_plan_id || targetLookup.baseline_plan_id === 'NONE')) && onInspectSituation && (
              <button
                onClick={() => onInspectSituation(selectedSituationId)}
                className="px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1 shadow-xs cursor-pointer"
              >
                <span>Open Response Plan</span>
              </button>
            )}
            <button
              onClick={loadSimulations}
              className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-white/60 rounded-lg transition cursor-pointer"
              title="Refresh Baseline Status"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      )}

      {/* Alert Banners */}
      {errorMsg && (
        <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-red-500 hover:text-red-700">
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      )}

      {successMsg && (
        <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successMsg}</span>
          </div>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-500 hover:text-emerald-700">
            <Check className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. MAIN SPLIT VIEW: SIMULATION RUNS & ACTIVE WORKBENCH */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Simulations List (4 cols) */}
        <div className="lg:col-span-4 space-y-4">
          <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-xs">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <span className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-slate-500" />
                <span>Simulation Experiments</span>
              </span>
              <span className="text-[11px] font-mono font-bold px-2 py-0.5 bg-slate-100 text-slate-600 rounded">
                {simulations.length} Runs
              </span>
            </div>

            {loading ? (
              <div className="py-8 text-center text-slate-400 text-xs">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-purple-600" />
                Loading simulation runs...
              </div>
            ) : simulations.length > 0 ? (
              <div className="mt-3 space-y-2.5 max-h-[500px] overflow-y-auto pr-1">
                {simulations.map((sim) => {
                  const isSelected = activeSimulation?.simulation_id === sim.simulation_id;
                  const isCompleted = sim.status === 'COMPLETED';
                  const isStale = sim.status === 'STALE';
                  const isDiscarded = sim.status === 'DISCARDED';

                  return (
                    <div
                      key={sim.simulation_id}
                      onClick={() => setActiveSimulation(sim)}
                      className={`p-3 rounded-xl border transition cursor-pointer text-xs space-y-1.5 ${
                        isSelected
                          ? 'border-purple-300 bg-purple-50/50 shadow-xs ring-1 ring-purple-400'
                          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-bold text-slate-900 text-[11px]">
                          {sim.simulation_id}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            isCompleted
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : isStale
                              ? 'bg-amber-50 text-amber-700 border border-amber-200'
                              : isDiscarded
                              ? 'bg-slate-100 text-slate-500 border border-slate-200'
                              : 'bg-purple-50 text-purple-700 border border-purple-200'
                          }`}
                        >
                          {sim.status}
                        </span>
                      </div>

                      <div className="font-semibold text-slate-800 truncate">
                        {sim.simulation_name}
                      </div>

                      <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1">
                        <span>{sim.scenarios.length} Scenarios</span>
                        <span>v{sim.baseline_plan_version} Baseline</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-10 text-center text-slate-400 text-xs">
                <FlaskConical className="w-8 h-8 mx-auto mb-2 text-slate-300" />
                <p>No simulations created yet for this situation.</p>
                <button
                  onClick={() => setShowNewSimModal(true)}
                  className="mt-3 text-purple-600 hover:text-purple-700 font-bold underline cursor-pointer"
                >
                  Create your first simulation
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Simulation Workbench (8 cols) */}
        <div className="lg:col-span-8 space-y-5">
          {activeSimulation ? (
            <>
              {/* Simulation Meta Card */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-slate-100">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-base font-bold text-slate-900">
                        {activeSimulation.simulation_name}
                      </h2>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${
                          activeSimulation.status === 'COMPLETED'
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : activeSimulation.status === 'STALE'
                            ? 'bg-amber-50 text-amber-700 border border-amber-200'
                            : activeSimulation.status === 'DISCARDED'
                            ? 'bg-slate-100 text-slate-500 border border-slate-200'
                            : 'bg-purple-50 text-purple-700 border border-purple-200'
                        }`}
                      >
                        {activeSimulation.status}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
                      <span>ID: <strong className="font-mono text-slate-700">{activeSimulation.simulation_id}</strong></span>
                      <span>•</span>
                      <span>Baseline: <strong className="font-mono text-slate-700">{activeSimulation.baseline_plan_id} (v{activeSimulation.baseline_plan_version})</strong></span>
                      <span>•</span>
                      <span>Created by: <strong className="text-slate-700">{activeSimulation.created_by_name}</strong></span>
                    </div>
                  </div>

                  {/* Primary Actions */}
                  <div className="flex items-center gap-2">
                    {activeSimulation.status === 'DRAFT' && (
                      <button
                        onClick={handleRunSimulation}
                        disabled={actionLoading || activeSimulation.scenarios.length === 0}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-xs cursor-pointer"
                      >
                        <Play className="w-4 h-4 fill-white" />
                        <span>Run Simulation</span>
                      </button>
                    )}

                    {activeSimulation.status === 'COMPLETED' && (
                      <>
                        <button
                          onClick={handleRunSimulation}
                          disabled={actionLoading}
                          className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition flex items-center gap-1 cursor-pointer"
                        >
                          <RefreshCw className="w-3.5 h-3.5" />
                          <span>Re-evaluate</span>
                        </button>

                        <button
                          onClick={() => setIsDiffModalOpen(true)}
                          className="px-3.5 py-1.5 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-xs cursor-pointer"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>View Plan Diff</span>
                        </button>
                      </>
                    )}

                    {activeSimulation.status !== 'DISCARDED' && (
                      <button
                        onClick={() => setShowDiscardModal(true)}
                        className="p-2 text-slate-400 hover:text-red-600 rounded-xl hover:bg-red-50 transition cursor-pointer"
                        title="Discard Simulation"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Stale Warning Banner */}
                {activeSimulation.status === 'STALE' && (
                  <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
                      <span>
                        <strong>Baseline Outdated:</strong> Operational data or active plan for this situation has changed since this simulation was run.
                      </span>
                    </div>
                    <button
                      onClick={handleRunSimulation}
                      className="px-2.5 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-[11px] font-bold transition cursor-pointer"
                    >
                      Re-run on Latest State
                    </button>
                  </div>
                )}

                {/* Evaluation Results Banner (If Completed) */}
                {activeSimulation.status === 'COMPLETED' && activeSimulation.diff_summary && (
                  <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                        <Sparkles className="w-4 h-4 text-purple-600" />
                        <span>Simulation Outcome & Impact Assessment</span>
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                          activeSimulation.impact_level === 'CRITICAL'
                            ? 'bg-red-50 text-red-700 border border-red-200'
                            : activeSimulation.impact_level === 'HIGH'
                            ? 'bg-orange-50 text-orange-700 border border-orange-200'
                            : activeSimulation.impact_level === 'MEDIUM'
                            ? 'bg-amber-50 text-amber-700 border border-amber-200'
                            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        }`}
                      >
                        Impact: {activeSimulation.impact_level}
                      </span>
                    </div>

                    <p className="text-xs text-slate-700 leading-relaxed">
                      {activeSimulation.explanation || activeSimulation.diff_summary.summary}
                    </p>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-slate-200/60 text-xs">
                      <div className="p-2 bg-white rounded-lg border border-slate-200 text-center">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Total Deltas</span>
                        <strong className="text-slate-900 text-sm font-mono font-bold">
                          {activeSimulation.diff_summary.items.length}
                        </strong>
                      </div>
                      <div className="p-2 bg-white rounded-lg border border-slate-200 text-center">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Domains Affected</span>
                        <strong className="text-slate-900 text-sm font-mono font-bold">
                          {activeSimulation.affected_domains.length}
                        </strong>
                      </div>
                      <div className="p-2 bg-white rounded-lg border border-slate-200 text-center">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Agents Executed</span>
                        <strong className="text-purple-700 text-sm font-mono font-bold">
                          {activeSimulation.affected_agents.length}
                        </strong>
                      </div>
                      <div className="p-2 bg-white rounded-lg border border-slate-200 text-center">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">Eval Duration</span>
                        <strong className="text-emerald-700 text-sm font-mono font-bold">
                          {activeSimulation.execution_duration_ms || 120}ms
                        </strong>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Scenarios List in this Simulation */}
              <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wide flex items-center gap-1.5">
                    <Boxes className="w-4 h-4 text-purple-600" />
                    <span>Hypothetical Perturbations ({activeSimulation.scenarios.length})</span>
                  </h3>
                  <span className="text-[11px] text-slate-400">
                    Selective agent re-planning triggers automatically based on affected domains.
                  </span>
                </div>

                {activeSimulation.scenarios.length > 0 ? (
                  <div className="space-y-2.5">
                    {activeSimulation.scenarios.map((sc, idx) => (
                      <div
                        key={sc.scenario_id || idx}
                        className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl flex items-start justify-between gap-3 text-xs"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-purple-100 text-purple-800">
                              {sc.scenario_type}
                            </span>
                            <span className="font-bold text-slate-900">{sc.title}</span>
                            <span className="text-slate-400 font-mono">({sc.target_entity_id})</span>
                          </div>
                          <p className="text-slate-600 text-[11px]">{sc.description}</p>
                          <div className="flex items-center gap-3 text-[10px] text-slate-500 font-mono pt-0.5">
                            <span>Domain: <strong>{sc.target_domain}</strong></span>
                            <span>•</span>
                            <span>Target: <strong>{sc.target_entity_type}</strong></span>
                            <span>•</span>
                            <span>Value: {JSON.stringify(sc.simulated_value)}</span>
                          </div>
                        </div>

                        {activeSimulation.status === 'DRAFT' && (
                          <button
                            onClick={() => handleRemoveScenario(sc.scenario_id)}
                            className="p-1.5 text-slate-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition cursor-pointer"
                            title="Remove scenario"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="py-6 text-center text-slate-400 text-xs">
                    No hypothetical scenarios added yet. Build your first perturbation below.
                  </div>
                )}
              </div>

              {/* Scenario Builder (Only editable when DRAFT) */}
              {activeSimulation.status === 'DRAFT' && (
                <div className="bg-white border border-purple-200/80 rounded-2xl p-5 shadow-xs space-y-4">
                  <div className="flex items-center justify-between pb-2 border-purple-100">
                    <h3 className="text-xs font-bold text-purple-900 uppercase tracking-wide flex items-center gap-1.5">
                      <Plus className="w-4 h-4 text-purple-600" />
                      <span>Add Hypothetical Scenario</span>
                    </h3>
                    <span className="text-[11px] text-purple-600 font-medium">
                      Select real target entities from authoritative database
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                    {/* Scenario Type */}
                    <div>
                      <label className="block font-bold text-slate-700 mb-1">Scenario Type</label>
                      <select
                        value={scenarioType}
                        onChange={(e) => {
                          const val = e.target.value as ScenarioType;
                          setScenarioType(val);
                          if (val === 'FACILITY_OFFLINE') setSelectedTargetType('SHELTER');
                          else if (val === 'ROUTE_BLOCKED') setSelectedTargetType('ROUTE');
                          else if (val === 'VOLUNTEER_DROPOUT') setSelectedTargetType('VOLUNTEER');
                          else setSelectedTargetType('RESOURCE');
                        }}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs text-slate-900 focus:outline-hidden focus:border-purple-500"
                      >
                        <option value="RESOURCE_REDUCTION">Resource Reduction (% Stock Loss)</option>
                        <option value="RESOURCE_UNAVAILABLE">Resource Stock Out / Depot Flooded</option>
                        <option value="DEMAND_SURGE">Demand Surge (+% localized need)</option>
                        <option value="FACILITY_OFFLINE">Shelter / Healthcare Facility Offline</option>
                        <option value="ROUTE_BLOCKED">Evacuation / Transport Route Blocked</option>
                        <option value="VOLUNTEER_DROPOUT">Volunteer Responder Dropout</option>
                      </select>
                    </div>

                    {/* Target Entity Selector */}
                    <div>
                      <label className="block font-bold text-slate-700 mb-1">Target Entity (Authoritative DB)</label>
                      <select
                        value={selectedTargetId}
                        onChange={(e) => setSelectedTargetId(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs text-slate-900 focus:outline-hidden focus:border-purple-500"
                      >
                        {relevantTargets.length > 0 ? (
                          <>
                            <option value="">-- Select Target Asset --</option>
                            {relevantTargets.map((t) => (
                              <option key={t.entity_id} value={t.entity_id}>
                                [{t.entity_type}] {t.name || t.entity_name} ({t.entity_id}) - {t.available_capacity_or_quantity ?? t.current_value ?? ''} {t.unit_or_type ?? t.unit ?? ''}
                              </option>
                            ))}
                          </>
                        ) : (
                          <option value="" disabled>No eligible real operational targets available for this situation.</option>
                        )}
                      </select>
                    </div>

                    {/* Dynamic Perturbation Controls */}
                    {(scenarioType === 'RESOURCE_REDUCTION' || scenarioType === 'VOLUNTEER_DROPOUT') && (
                      <div className="md:col-span-2 space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <label className="font-bold text-slate-700">Reduction Percentage: {reductionPct}%</label>
                          <span className="text-slate-400 font-mono">0% to 100% loss</span>
                        </div>
                        <input
                          type="range"
                          min="10"
                          max="100"
                          step="10"
                          value={reductionPct}
                          onChange={(e) => setReductionPct(Number(e.target.value))}
                          className="w-full accent-purple-600 cursor-pointer"
                        />
                      </div>
                    )}

                    {scenarioType === 'DEMAND_SURGE' && (
                      <div className="md:col-span-2 space-y-1">
                        <div className="flex items-center justify-between text-xs">
                          <label className="font-bold text-slate-700">Surge Percentage: +{surgePct}%</label>
                          <span className="text-slate-400 font-mono">+10% to +300% increase</span>
                        </div>
                        <input
                          type="range"
                          min="10"
                          max="300"
                          step="10"
                          value={surgePct}
                          onChange={(e) => setSurgePct(Number(e.target.value))}
                          className="w-full accent-purple-600 cursor-pointer"
                        />
                      </div>
                    )}

                    {/* Title & Notes */}
                    <div>
                      <label className="block font-bold text-slate-700 mb-1">Scenario Title (Optional)</label>
                      <input
                        type="text"
                        placeholder="e.g., Flood in Central Water Depot"
                        value={scenarioTitle}
                        onChange={(e) => setScenarioTitle(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs text-slate-900 focus:outline-hidden focus:border-purple-500"
                      />
                    </div>

                    <div>
                      <label className="block font-bold text-slate-700 mb-1">Hypothetical Notes / Context</label>
                      <input
                        type="text"
                        placeholder="e.g., Severe water contamination detected"
                        value={scenarioDesc}
                        onChange={(e) => setScenarioDesc(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs text-slate-900 focus:outline-hidden focus:border-purple-500"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end pt-2">
                    <button
                      onClick={handleAddScenario}
                      disabled={actionLoading || !selectedTargetId}
                      className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5 shadow-xs cursor-pointer"
                    >
                      <Plus className="w-4 h-4" />
                      <span>Add Scenario to Simulation</span>
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center text-slate-400 space-y-3">
              <FlaskConical className="w-10 h-10 mx-auto text-purple-300" />
              <h3 className="text-sm font-bold text-slate-700">No Simulation Selected</h3>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Select an existing simulation run from the left or create a new what-if experiment to model disaster dynamics.
              </p>
              <button
                onClick={() => setShowNewSimModal(true)}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl text-xs font-bold transition inline-flex items-center gap-1.5 shadow-xs cursor-pointer"
              >
                <Plus className="w-4 h-4" />
                <span>Initialize Simulation Draft</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 3. MODAL: CREATE NEW SIMULATION */}
      {/* ========================================================================= */}
      {showNewSimModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 p-6 max-w-md w-full shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <FlaskConical className="w-4 h-4 text-purple-600" />
                <span>Initialize New What-If Simulation</span>
              </h3>
              <button onClick={() => setShowNewSimModal(false)} className="text-slate-400 hover:text-slate-600 cursor-pointer">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block font-bold text-slate-700 mb-1">Target Situation</label>
                <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl font-mono text-slate-800">
                  {selectedSituationId}
                </div>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Active Response Plan Baseline</label>
                {targetLookup && (targetLookup.has_active_baseline || (targetLookup.baseline_plan_id && targetLookup.baseline_plan_id !== 'NONE')) ? (
                  <div className="p-2.5 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-900 flex items-center justify-between">
                    <div>
                      <span className="font-mono font-bold">{targetLookup.baseline_plan_id} (v{targetLookup.baseline_plan_version})</span>
                      <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
                        {targetLookup.baseline_plan_status || 'ACTIVE'}
                      </span>
                    </div>
                    <span className="text-[11px] text-emerald-700 font-semibold">Authoritative Baseline</span>
                  </div>
                ) : (
                  <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 text-[11px]">
                    <AlertTriangle className="w-3.5 h-3.5 inline mr-1 text-amber-600" />
                    <strong>No Active Plan:</strong> An active coordination plan is required before creating a simulation.
                  </div>
                )}
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Simulation Name (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g., Flood Surge & Route Collapse Drill"
                  value={newSimName}
                  onChange={(e) => setNewSimName(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs text-slate-900 focus:outline-hidden focus:border-purple-500"
                />
              </div>

              <div className="p-3 bg-purple-50 border border-purple-200 rounded-xl text-purple-800 text-[11px] leading-relaxed">
                <strong>Zero-Mutation Invariant:</strong> Simulations snapshot the baseline coordination plan and evaluate in memory. No active resources or assignments will be altered.
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                onClick={() => setShowNewSimModal(false)}
                className="px-3.5 py-2 text-slate-600 hover:bg-slate-100 rounded-xl text-xs font-semibold cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateSimulation}
                disabled={actionLoading || (targetLookup ? !targetLookup.has_active_baseline && (!targetLookup.baseline_plan_id || targetLookup.baseline_plan_id === 'NONE') : false)}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition cursor-pointer"
              >
                {actionLoading ? 'Initializing...' : 'Create Draft'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. MODAL: DISCARD CONFIRMATION */}
      {/* ========================================================================= */}
      {showDiscardModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 p-6 max-w-md w-full shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2 text-red-600">
                <Trash2 className="w-4 h-4" />
                <span>Discard Simulation Experiment</span>
              </h3>
              <button onClick={() => setShowDiscardModal(false)} className="text-slate-400 hover:text-slate-600 cursor-pointer">
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <p className="text-slate-600">
                Are you sure you want to discard simulation <strong>{activeSimulation?.simulation_id}</strong>?
                The experiment will be marked discarded in audit history.
              </p>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Discard Reason (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g., Testing completed, hypothetical scenario superseded"
                  value={discardReason}
                  onChange={(e) => setDiscardReason(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs text-slate-900 focus:outline-hidden focus:border-red-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                onClick={() => setShowDiscardModal(false)}
                className="px-3.5 py-2 text-slate-600 hover:bg-slate-100 rounded-xl text-xs font-semibold cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleDiscardSimulation}
                disabled={actionLoading}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-xs font-bold transition cursor-pointer"
              >
                {actionLoading ? 'Discarding...' : 'Confirm Discard'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5. MODAL: PLAN DIFF VIEWER (FOR SIMULATED PLAN) */}
      {/* ========================================================================= */}
      {isDiffModalOpen && (activeSimulation?.result_plan || activeSimulation?.simulated_plan) && (
        <CoordinationPlanDiffModal
          plan={(activeSimulation.result_plan || activeSimulation.simulated_plan)!}
          initialDiffResult={activeSimulation.diff_result || activeSimulation.diff_summary || (activeSimulation.result_plan?.diff_summary as any)}
          isOpen={isDiffModalOpen}
          onClose={() => setIsDiffModalOpen(false)}
        />
      )}
    </div>
  );
};
