import React, { useState, useEffect } from 'react';
import {
  Layers,
  Search,
  RefreshCw,
  Compass,
  AlertTriangle,
  ChevronRight,
  CheckCircle2,
} from 'lucide-react';
import type {
  SituationCluster,
  SituationStatsResponse,
  EmergencyType,
  SeverityLevel,
} from '../../types';
import {
  listSituations,
  getSituationStats,
  fuseAllReports,
} from '../../services/situationsApi';

interface SituationListPanelProps {
  onSelectSituation: (situationId: string) => void;
  onOpenCoordination?: (situation: SituationCluster) => void;
}

export const SituationListPanel: React.FC<SituationListPanelProps> = ({
  onSelectSituation,
  onOpenCoordination,
}) => {
  const [situations, setSituations] = useState<SituationCluster[]>([]);
  const [stats, setStats] = useState<SituationStatsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [syncLoading, setSyncLoading] = useState<boolean>(false);

  // Filters
  const [search, setSearch] = useState<string>('');
  const [selectedType, setSelectedType] = useState<string>('ALL');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('ALL');

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [listRes, statsRes] = await Promise.all([
        listSituations({
          search: search.trim() || undefined,
          emergency_type: selectedType !== 'ALL' ? (selectedType as EmergencyType) : undefined,
          severity_level: selectedSeverity !== 'ALL' ? (selectedSeverity as SeverityLevel) : undefined,
          limit: 50,
        }),
        getSituationStats(),
      ]);
      setSituations(listRes.items || []);
      setStats(statsRes);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load situations data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [selectedType, selectedSeverity]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchData();
  };

  const handleSyncClusters = async () => {
    try {
      setSyncLoading(true);
      await fuseAllReports();
      await fetchData();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to sync incident clusters.');
    } finally {
      setSyncLoading(false);
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
    <div className="space-y-6">
      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-sm">
            <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              Active Situations
            </div>
            <div className="text-xl font-bold text-slate-900 mt-0.5">{stats.active_situations}</div>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-red-200 shadow-sm">
            <div className="text-[11px] font-semibold text-red-600 uppercase tracking-wider">
              Critical Situations
            </div>
            <div className="text-xl font-bold text-red-700 mt-0.5">{stats.critical_situations}</div>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-amber-200 shadow-sm">
            <div className="text-[11px] font-semibold text-amber-600 uppercase tracking-wider">
              High Severity
            </div>
            <div className="text-xl font-bold text-amber-700 mt-0.5">{stats.high_situations}</div>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-blue-200 shadow-sm">
            <div className="text-[11px] font-semibold text-blue-600 uppercase tracking-wider">
              Fused Reports
            </div>
            <div className="text-xl font-bold text-blue-700 mt-0.5">{stats.total_clustered_reports}</div>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-emerald-200 shadow-sm">
            <div className="text-[11px] font-semibold text-emerald-600 uppercase tracking-wider">
              Avg Evidence Confidence
            </div>
            <div className="text-xl font-bold text-emerald-700 mt-0.5">
              {Math.round(stats.average_confidence * 100)}%
            </div>
          </div>
        </div>
      )}

      {/* Filter and Action Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-3 items-center justify-between">
        <form onSubmit={handleSearchSubmit} className="flex-1 w-full flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search situations by title, zone, location, ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs border border-slate-300 rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            type="submit"
            className="px-3 py-1.5 bg-slate-900 text-white text-xs font-semibold rounded-lg hover:bg-slate-800 transition"
          >
            Search
          </button>
        </form>

        <div className="flex items-center gap-2 w-full md:w-auto">
          {/* Emergency Type Filter */}
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white text-slate-700"
          >
            <option value="ALL">All Emergency Types</option>
            <option value="Flood">Flood</option>
            <option value="Fire">Fire</option>
            <option value="Building Collapse">Building Collapse</option>
            <option value="Landslide">Landslide</option>
            <option value="Medical Emergency">Medical Emergency</option>
            <option value="Road Accident">Road Accident</option>
            <option value="Cyclone / Storm">Cyclone / Storm</option>
            <option value="Missing / Trapped Person">Missing / Trapped Person</option>
            <option value="Other">Other</option>
          </select>

          {/* Severity Filter */}
          <select
            value={selectedSeverity}
            onChange={(e) => setSelectedSeverity(e.target.value)}
            className="text-xs border border-slate-300 rounded-lg px-2.5 py-1.5 bg-white text-slate-700"
          >
            <option value="ALL">All Severities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>

          {/* Sync Fusion Button */}
          <button
            onClick={handleSyncClusters}
            disabled={syncLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-50 text-blue-700 border border-blue-200 text-xs font-semibold rounded-lg hover:bg-blue-100 transition whitespace-nowrap disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncLoading ? 'animate-spin' : ''}`} />
            <span>Sync Fusion</span>
          </button>
        </div>
      </div>

      {/* Situations List */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center text-slate-500">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-600 mb-3" />
          <p className="text-sm font-medium">Loading Situation Clusters...</p>
        </div>
      ) : error ? (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      ) : situations.length === 0 ? (
        <div className="p-12 text-center bg-white rounded-xl border border-slate-200 shadow-sm">
          <Layers className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="text-sm font-bold text-slate-700">No Situation Clusters Found</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            No active situation clusters matched the current filters. Reports are automatically fused into clusters upon intake.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {situations.map((sit) => (
            <div
              key={sit.situation_id}
              className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:shadow-md hover:border-blue-300 transition-all flex flex-col justify-between"
            >
              <div>
                {/* Header Badge Row */}
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`px-2 py-0.5 rounded-full text-[11px] font-bold border ${getSeverityBadgeClass(
                        sit.severity_level
                      )}`}
                    >
                      {sit.severity_level} • {sit.severity_score.toFixed(1)}/10
                      {sit.officer_override_severity ? ' (Override)' : ''}
                    </span>
                    <span className="text-xs font-mono font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded">
                      {sit.situation_id}
                    </span>
                  </div>
                  <span className="text-[11px] font-medium text-slate-500 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
                    {sit.emergency_type}
                  </span>
                </div>

                {/* Title */}
                <h3 className="text-sm font-bold text-slate-900 mb-1 line-clamp-1">
                  {sit.title}
                </h3>

                {/* Summary */}
                <p className="text-xs text-slate-600 line-clamp-2 mb-3">
                  {sit.situation_summary}
                </p>

                {/* Impact Metrics Row */}
                <div className="grid grid-cols-3 gap-2 py-2 px-2.5 bg-slate-50 rounded-lg border border-slate-100 text-xs text-slate-700 mb-3">
                  <div>
                    <span className="text-[10px] text-slate-400 block font-medium">Impact Radius</span>
                    <span className="font-bold text-blue-700 flex items-center gap-1">
                      <Compass className="w-3 h-3" />
                      ~{sit.impact_zone.radius_km} km
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block font-medium">Reports Fused</span>
                    <span className="font-bold text-slate-800 flex items-center gap-1">
                      <Layers className="w-3 h-3 text-slate-500" />
                      {sit.report_count} reports
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block font-medium">Confidence</span>
                    <span className="font-bold text-emerald-700 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                      {Math.round(sit.confidence * 100)}%
                    </span>
                  </div>
                </div>
              </div>

              {/* Footer Actions */}
              <div className="pt-3 border-t border-slate-100 flex items-center justify-between text-xs gap-2">
                <span className="text-[11px] text-slate-400 truncate">
                  {sit.center_location.zone_or_district || sit.center_location.city || 'Coordinates Centroid'}
                </span>
                
                <div className="flex items-center gap-2">
                  {onOpenCoordination && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenCoordination(sit);
                      }}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-bold bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 transition"
                    >
                      <Layers className="w-3.5 h-3.5 text-red-600" />
                      <span>AI Coordination</span>
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => onSelectSituation(sit.situation_id)}
                    className="font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
                  >
                    <span>Inspect</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
