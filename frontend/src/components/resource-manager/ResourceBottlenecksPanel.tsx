import React, { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle,
  Boxes,
  RefreshCw,
  Search,
  CheckCircle2,
  TrendingDown,
  Layers,
  ExternalLink,
  ShieldAlert,
  HelpCircle,
  X,
  Package,
  ChevronRight,
  Sparkles,
} from 'lucide-react';
import {
  getResourceBottlenecks,
  getResourceBottleneckDetail,
} from '../../services/api';
import type {
  ResourceBottleneckItem,
  ResourceBottleneckSummary,
  BottleneckSeverity,
  BottleneckType,
} from '../../types';
import { OperationalEmptyState } from '../common/OperationalEmptyState';

interface ResourceBottlenecksPanelProps {
  onInspectSituation?: (situationId: string) => void;
}

export const ResourceBottlenecksPanel: React.FC<ResourceBottlenecksPanelProps> = ({
  onInspectSituation,
}) => {
  const [bottlenecks, setBottlenecks] = useState<ResourceBottleneckItem[]>([]);
  const [summary, setSummary] = useState<ResourceBottleneckSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [resourceTypeFilter, setResourceTypeFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Selected Bottleneck Modal
  const [selectedBottleneck, setSelectedBottleneck] = useState<ResourceBottleneckItem | null>(null);

  const fetchBottlenecks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getResourceBottlenecks({
        severity: severityFilter !== 'ALL' ? severityFilter : undefined,
        resource_type: resourceTypeFilter !== 'ALL' ? resourceTypeFilter : undefined,
      });
      setBottlenecks(res.items || []);
      setSummary(res.summary || null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load resource bottleneck analysis.');
    } finally {
      setLoading(false);
    }
  }, [severityFilter, resourceTypeFilter]);

  useEffect(() => {
    fetchBottlenecks();
  }, [fetchBottlenecks]);

  const handleInspect = async (item: ResourceBottleneckItem) => {
    setSelectedBottleneck(item);
    try {
      const detail = await getResourceBottleneckDetail(item.bottleneck_id);
      if (detail) {
        setSelectedBottleneck(detail);
      }
    } catch (err) {
      console.warn('Failed to load deep bottleneck detail:', err);
    }
  };

  const filteredBottlenecks = bottlenecks.filter((b) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      b.resource_name?.toLowerCase().includes(q) ||
      b.resource_type.toLowerCase().includes(q) ||
      b.bottleneck_id.toLowerCase().includes(q) ||
      b.affected_situations.some((s) => s.situation_id.toLowerCase().includes(q) || s.title.toLowerCase().includes(q))
    );
  });

  const getSeverityBadge = (severity: BottleneckSeverity) => {
    switch (severity) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-black bg-red-100 text-red-800 border border-red-300 animate-pulse">
            <ShieldAlert className="w-3 h-3 text-red-600" />
            CRITICAL
          </span>
        );
      case 'HIGH':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300">
            <AlertTriangle className="w-3 h-3 text-amber-600" />
            HIGH
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-300">
            MEDIUM
          </span>
        );
      case 'LOW':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-300">
            LOW
          </span>
        );
    }
  };

  const getTypeBadge = (type: BottleneckType) => {
    switch (type) {
      case 'NO_ELIGIBLE_RESOURCE':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-50 text-red-700 border border-red-200">NO ELIGIBLE ASSET</span>;
      case 'RESOURCE_SHORTAGE':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">RESOURCE SHORTAGE</span>;
      case 'ALLOCATION_CONTENTION':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">MULTI-INCIDENT CONTENTION</span>;
      case 'CAPABILITY_CONSTRAINT':
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">CAPABILITY / CONDITION CONSTRAINT</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600">{type}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-black text-slate-900 flex items-center gap-2.5">
            <TrendingDown className="w-6 h-6 text-rose-600" />
            Resource Bottleneck & Shortfall Intelligence
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Deterministic supply vs demand analysis across active situations, MongoDB stockpiles, and task consumption.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={fetchBottlenecks}
            disabled={loading}
            className="p-2.5 rounded-xl border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition shadow-2xs cursor-pointer"
            title="Refresh Bottleneck Analysis"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-rose-600' : ''}`} />
          </button>
        </div>
      </div>

      {/* Summary KPI Cards (Zero Fake Data) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-white border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Active Bottlenecks</span>
            <Boxes className="w-4 h-4 text-slate-400" />
          </div>
          <div className="text-2xl font-black text-slate-900 mt-2">{summary?.total_bottlenecks ?? 0}</div>
          <div className="text-[10px] text-slate-400 mt-1">Resource constraint findings</div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-red-700 uppercase tracking-wider">Critical Shortfalls</span>
            <ShieldAlert className="w-4 h-4 text-red-500" />
          </div>
          <div className="text-2xl font-black text-red-700 mt-2">{summary?.critical_count ?? 0}</div>
          <div className="text-[10px] text-red-600 mt-1">Acute deficits &amp; missing assets</div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-purple-700 uppercase tracking-wider">Contended Categories</span>
            <Layers className="w-4 h-4 text-purple-500" />
          </div>
          <div className="text-2xl font-black text-purple-700 mt-2">{summary?.contention_count ?? 0}</div>
          <div className="text-[10px] text-purple-600 mt-1">Multi-situation resource competition</div>
        </div>

        <div className="p-4 rounded-2xl bg-white border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-amber-700 uppercase tracking-wider">High / Med Severities</span>
            <AlertTriangle className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-2xl font-black text-amber-700 mt-2">
            {(summary?.high_count ?? 0) + (summary?.medium_count ?? 0)}
          </div>
          <div className="text-[10px] text-amber-600 mt-1">Elevated operational monitoring</div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="relative w-full md:w-80">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search resource type, name, situation..."
            className="w-full rounded-xl border border-slate-200 pl-9 pr-4 py-2 text-xs text-slate-900 focus:border-rose-500 focus:outline-hidden"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2.5 w-full md:w-auto">
          {/* Severity Filter */}
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-700 bg-white font-medium focus:border-rose-500"
          >
            <option value="ALL">All Severities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>

          {/* Resource Type Filter */}
          <select
            value={resourceTypeFilter}
            onChange={(e) => setResourceTypeFilter(e.target.value)}
            className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-700 bg-white font-medium focus:border-rose-500"
          >
            <option value="ALL">All Resource Types</option>
            <option value="WATER">Water</option>
            <option value="FOOD">Food</option>
            <option value="MEDICINE">Medicine</option>
            <option value="FIRST_AID">First Aid</option>
            <option value="GENERATOR">Generator</option>
            <option value="TRANSPORT">Transport</option>
            <option value="SHELTER">Shelter</option>
            <option value="RESCUE_EQUIPMENT">Rescue Equipment</option>
          </select>
        </div>
      </div>

      {/* Bottlenecks Table */}
      <div className="rounded-2xl bg-white border border-slate-200 shadow-xs overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-400 flex flex-col items-center gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-rose-600" />
            <span className="text-xs font-bold text-slate-600">Computing real-time resource supply vs authoritative requirements...</span>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-red-600 text-xs">
            <AlertTriangle className="w-8 h-8 mx-auto mb-2 text-red-500" />
            {error}
          </div>
        ) : filteredBottlenecks.length === 0 ? (
          <OperationalEmptyState
            icon={CheckCircle2}
            title="No Resource Bottlenecks Detected"
            description="All active emergency needs assessments are currently covered by available inventory stockpiles, or no situations currently demand resources."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                  <th className="py-3.5 px-4">Resource &amp; Category</th>
                  <th className="py-3.5 px-3">Bottleneck Type</th>
                  <th className="py-3.5 px-3">Severity</th>
                  <th className="py-3.5 px-3 text-right">Required</th>
                  <th className="py-3.5 px-3 text-right">Available</th>
                  <th className="py-3.5 px-3 text-right">Shortfall</th>
                  <th className="py-3.5 px-3">Affected Situations</th>
                  <th className="py-3.5 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredBottlenecks.map((b) => (
                  <tr key={b.bottleneck_id} className="hover:bg-slate-50/70 transition group">
                    <td className="py-3 px-4">
                      <div className="font-bold text-slate-900 group-hover:text-rose-700 transition flex items-center gap-2">
                        <Package className="w-3.5 h-3.5 text-slate-400" />
                        {b.resource_name || b.resource_type}
                      </div>
                      <div className="text-[10px] font-mono text-slate-400">{b.resource_type}</div>
                    </td>

                    <td className="py-3 px-3">
                      {getTypeBadge(b.bottleneck_type)}
                    </td>

                    <td className="py-3 px-3">
                      {getSeverityBadge(b.severity)}
                    </td>

                    <td className="py-3 px-3 text-right font-mono font-bold text-slate-800">
                      {b.required} {b.unit}
                    </td>

                    <td className="py-3 px-3 text-right font-mono font-bold text-emerald-700">
                      {b.available} {b.unit}
                    </td>

                    <td className="py-3 px-3 text-right font-mono font-black text-rose-600">
                      {b.shortfall > 0 ? `-${b.shortfall} ${b.unit}` : '0'}
                    </td>

                    <td className="py-3 px-3">
                      <div className="flex flex-wrap items-center gap-1">
                        {b.affected_situations && b.affected_situations.length > 0 ? (
                          b.affected_situations.slice(0, 2).map((sit) => (
                            <span
                              key={sit.situation_id}
                              className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-mono text-[10px] border border-slate-200"
                              title={sit.title}
                            >
                              {sit.situation_id}
                            </span>
                          ))
                        ) : (
                          <span className="text-slate-400 italic text-[10px]">None</span>
                        )}
                        {b.affected_situations && b.affected_situations.length > 2 && (
                          <span className="text-[10px] text-slate-500 font-bold">
                            +{b.affected_situations.length - 2} more
                          </span>
                        )}
                      </div>
                    </td>

                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleInspect(b)}
                        className="px-3 py-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 text-xs font-bold transition flex items-center gap-1.5 ml-auto cursor-pointer"
                      >
                        <span>Inspect</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Deep Dive Bottleneck Drawer / Modal */}
      {selectedBottleneck && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40 backdrop-blur-2xs">
          <div className="w-full max-w-xl bg-white shadow-2xl h-full flex flex-col border-l border-slate-200 overflow-hidden animate-in slide-in-from-right duration-200">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/80">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center font-bold">
                  <TrendingDown className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">{selectedBottleneck.resource_name || selectedBottleneck.resource_type}</h3>
                  <p className="text-xs text-slate-500 font-mono">
                    {selectedBottleneck.resource_type} • Shortfall: {selectedBottleneck.shortfall} {selectedBottleneck.unit}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedBottleneck(null)}
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-200/60 hover:text-slate-700 transition cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Severity & Metrics Snapshot */}
              <div className="p-4 rounded-xl border border-rose-200 bg-rose-50/40 space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs font-bold text-slate-600 uppercase tracking-wider">Severity Level</span>
                  {getSeverityBadge(selectedBottleneck.severity)}
                </div>
                <div className="grid grid-cols-3 gap-2 text-center pt-2 border-t border-rose-100">
                  <div className="p-2 bg-white rounded-lg border border-slate-200">
                    <div className="text-[10px] text-slate-400 font-bold uppercase">Authoritative Need</div>
                    <div className="text-sm font-black text-slate-900 mt-0.5">
                      {selectedBottleneck.required} {selectedBottleneck.unit}
                    </div>
                  </div>
                  <div className="p-2 bg-white rounded-lg border border-slate-200">
                    <div className="text-[10px] text-slate-400 font-bold uppercase">Live Available</div>
                    <div className="text-sm font-black text-emerald-700 mt-0.5">
                      {selectedBottleneck.available} {selectedBottleneck.unit}
                    </div>
                  </div>
                  <div className="p-2 bg-white rounded-lg border border-rose-200">
                    <div className="text-[10px] text-rose-500 font-bold uppercase">Net Shortfall</div>
                    <div className="text-sm font-black text-rose-600 mt-0.5">
                      {selectedBottleneck.shortfall > 0 ? `-${selectedBottleneck.shortfall}` : '0'} {selectedBottleneck.unit}
                    </div>
                  </div>
                </div>
              </div>

              {/* Explainability & Reason */}
              <div>
                <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <HelpCircle className="w-3.5 h-3.5 text-rose-600" />
                  Deterministic Root Cause Diagnostic
                </h4>
                <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-2">
                  <p className="font-semibold text-slate-800">{selectedBottleneck.why_bottleneck}</p>
                  <div className="pt-2 border-t border-slate-200/60 flex items-start gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold text-slate-800 text-[11px] block">Recommended Action (Advisory):</span>
                      <span className="text-slate-600 text-[11px]">{selectedBottleneck.recommended_action}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Multi-Incident Contention */}
              {selectedBottleneck.contention && selectedBottleneck.contention.competing_situations.length > 1 && (
                <div className="p-4 rounded-xl border border-purple-200 bg-purple-50/50 space-y-2 text-xs">
                  <div className="flex items-center gap-2 font-bold text-purple-900">
                    <Layers className="w-4 h-4 text-purple-600" />
                    Multi-Incident Contention Breakdown
                  </div>
                  <p className="text-purple-800 text-[11px]">
                    {selectedBottleneck.contention.competing_situations.length} distinct active situations are currently competing for this limited stockpile.
                  </p>
                  <div className="pt-2 space-y-1.5">
                    {selectedBottleneck.contention.competing_situations.map((cs) => (
                      <div key={cs.situation_id} className="flex justify-between items-center text-[11px] bg-white/80 px-2.5 py-1.5 rounded-lg border border-purple-100">
                        <span className="font-semibold text-purple-950">{cs.title || cs.situation_id}</span>
                        <span className="font-mono font-bold text-purple-800">{cs.demanded} {selectedBottleneck.unit}</span>
                      </div>
                    ))}
                  </div>
                  <div className="pt-2 flex justify-between items-center font-mono text-[11px] text-purple-950 font-bold border-t border-purple-200">
                    <span>Total Aggregate Demand:</span>
                    <span>{selectedBottleneck.contention.total_demand} {selectedBottleneck.unit}</span>
                  </div>
                </div>
              )}

              {/* Affected Situations List */}
              <div>
                <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-2.5 flex items-center justify-between">
                  <span>Authoritative Situations Demanding Supply</span>
                  <span className="text-[10px] font-normal text-slate-400">
                    {selectedBottleneck.affected_situations?.length || 0} situations
                  </span>
                </h4>
                {selectedBottleneck.affected_situations && selectedBottleneck.affected_situations.length > 0 ? (
                  <div className="space-y-2">
                    {selectedBottleneck.affected_situations.map((sit) => (
                      <div
                        key={sit.situation_id}
                        className="p-3 rounded-xl border border-slate-200 bg-slate-50/60 flex items-center justify-between text-xs"
                      >
                        <div>
                          <div className="font-bold text-slate-900 flex items-center gap-2">
                            <span className="font-mono text-[11px] text-purple-700">{sit.situation_id}</span>
                            <span>{sit.title}</span>
                          </div>
                          <div className="text-[10px] text-slate-500 mt-0.5">
                            Demand: <strong>{sit.required_quantity} {selectedBottleneck.unit}</strong> • Urgency: <span className="font-semibold text-slate-700">{sit.urgency}</span>
                          </div>
                        </div>
                        {onInspectSituation && (
                          <button
                            onClick={() => onInspectSituation(sit.situation_id)}
                            className="text-xs font-bold text-purple-700 hover:text-purple-900 flex items-center gap-1 p-1 cursor-pointer"
                            title="Inspect situation details"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-4 text-center text-xs text-slate-400 bg-slate-50 rounded-xl border border-slate-200">
                    No individual situation linkages identified.
                  </div>
                )}
              </div>

              {/* Genuine Alternative Resources (Zero Hallucinated Recommendations) */}
              {selectedBottleneck.alternative_options && selectedBottleneck.alternative_options.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-2.5 flex items-center justify-between">
                    <span>Available Alternative Stockpiles</span>
                    <span className="text-[10px] font-normal text-slate-400">
                      {selectedBottleneck.alternative_options.length} discovered
                    </span>
                  </h4>
                  <div className="space-y-2">
                    {selectedBottleneck.alternative_options.map((alt) => (
                      <div
                        key={alt.resource_id}
                        className="p-3 rounded-xl border border-emerald-200 bg-emerald-50/40 text-xs flex items-center justify-between"
                      >
                        <div>
                          <div className="font-bold text-slate-900">{alt.name}</div>
                          <div className="text-[10px] text-slate-500 font-mono">
                            ID: {alt.resource_id} • Location: {alt.location_name || 'Depot'}
                          </div>
                          {alt.feasibility_notes && (
                            <div className="text-[10px] text-emerald-700 mt-0.5">{alt.feasibility_notes}</div>
                          )}
                        </div>
                        <div className="text-right">
                          <div className="font-mono font-bold text-emerald-800">
                            {alt.quantity_available} {alt.unit}
                          </div>
                          <div className="text-[9px] text-emerald-600 font-semibold">Available</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Safety & Authoritative Notice */}
              <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 text-[11px] text-slate-500 leading-relaxed">
                <strong>Operational Safety Notice:</strong> Needs assessments remain authoritative and are never mutated by bottleneck analysis. AI recommendations do not automatically consume inventory or reassign dispatches.
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default ResourceBottlenecksPanel;
