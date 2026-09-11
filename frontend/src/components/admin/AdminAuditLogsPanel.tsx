import React, { useState, useEffect } from 'react';
import { FileCheck, RefreshCw, Search, Filter, AlertCircle } from 'lucide-react';
import { getAdminAuditLogs } from '../../services/api';

export const AdminAuditLogsPanel: React.FC = () => {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedEventType, setSelectedEventType] = useState('ALL');

  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAdminAuditLogs({
        limit: 100,
        event_type: selectedEventType !== 'ALL' ? selectedEventType : undefined,
      });
      setLogs(data || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load security audit logs.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [selectedEventType]);

  const filteredLogs = logs.filter((log) => {
    if (!searchTerm.trim()) return true;
    const q = searchTerm.toLowerCase();
    return (
      (log.action && log.action.toLowerCase().includes(q)) ||
      (log.actor_name && log.actor_name.toLowerCase().includes(q)) ||
      (log.details && log.details.toLowerCase().includes(q)) ||
      (log.event_id && log.event_id.toLowerCase().includes(q))
    );
  });

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-4 border-b border-slate-100 gap-3">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <FileCheck className="w-4 h-4 text-purple-600" />
            <span>Immutable Security & Operations Audit Trail</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Chronological cryptographic record of administrative provisioning, role modifications, plan activations, and system state transitions in MongoDB Atlas.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-bold px-2.5 py-1 bg-purple-50 text-purple-700 rounded-lg border border-purple-200">
            {filteredLogs.length} Events
          </span>
          <button
            onClick={fetchLogs}
            disabled={loading}
            className="p-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 transition-colors"
            title="Refresh Audit Logs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-purple-600' : ''}`} />
          </button>
        </div>
      </div>

      {/* Filter & Search Ribbon */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative flex-1 w-full">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search audit trail by event type, actor, or details..."
            className="w-full pl-8 pr-3.5 py-2 rounded-xl border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500/20"
          />
        </div>

        <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs w-full sm:w-auto">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-[11px] font-bold text-slate-500">Filter:</span>
          <select
            value={selectedEventType}
            onChange={(e) => setSelectedEventType(e.target.value)}
            className="bg-transparent border-none text-xs font-semibold text-slate-800 focus:ring-0 outline-none cursor-pointer"
          >
            <option value="ALL">All Event Types</option>
            <option value="OPERATOR_GOOGLE_PROVISIONED">Operator Google Provisioned</option>
            <option value="USER_PROFILE_UPDATED">User Profile Updated</option>
            <option value="PLATFORM_CONFIG_UPDATED">Platform Config Updated</option>
            <option value="RESOURCE_CREATED">Resource Created</option>
            <option value="RESOURCE_UPDATED">Resource Updated</option>
            <option value="PLAN_APPROVED">Plan Approved</option>
          </select>
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs font-semibold flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Log Feed */}
      {loading && logs.length === 0 ? (
        <div className="py-12 text-center text-slate-400 text-xs space-y-2">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto text-purple-600" />
          <p>Retrieving immutable audit records from MongoDB Atlas...</p>
        </div>
      ) : filteredLogs.length > 0 ? (
        <div className="border border-slate-200/90 rounded-2xl divide-y divide-slate-100 max-h-[600px] overflow-y-auto">
          {filteredLogs.map((log, idx) => {
            const isSecurity = log.source === 'security_auth' || log.event?.includes('GOOGLE') || log.action?.includes('AUTH');
            return (
              <div key={log._id || idx} className="p-4 hover:bg-slate-50/70 transition-colors flex items-start justify-between gap-4 text-xs">
                <div className="space-y-1.5 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`font-mono text-[10px] font-bold px-2 py-0.5 rounded border ${
                      isSecurity
                        ? 'bg-purple-50 text-purple-700 border-purple-200'
                        : 'bg-slate-100 text-slate-700 border-slate-200'
                    }`}>
                      {log.action || log.event || log.event_type || 'AUDIT_RECORD'}
                    </span>
                    {log.event_id && (
                      <span className="font-mono text-[10px] text-slate-400 font-bold">{log.event_id}</span>
                    )}
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-50 text-emerald-700 font-bold border border-emerald-200">
                      IMMUTABLE
                    </span>
                  </div>

                  <p className="text-slate-800 font-medium leading-relaxed">
                    {log.details || log.message || 'Audit event logged.'}
                  </p>

                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
                    {log.actor_name && (
                      <span>Actor: <strong className="text-slate-700">{log.actor_name}</strong> ({log.actor_role || 'ADMIN'})</span>
                    )}
                    {log.admin_phone && (
                      <span>Admin Phone: <strong className="text-slate-700">{log.admin_phone}</strong></span>
                    )}
                    {log.resource_id && (
                      <span>Target: <strong className="font-mono text-slate-700">{log.resource_id}</strong></span>
                    )}
                  </div>
                </div>

                <div className="text-[11px] font-mono text-slate-400 whitespace-nowrap text-right">
                  {log.timestamp ? new Date(log.timestamp).toLocaleString() : 'Recent'}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="py-12 text-center text-slate-400 text-xs">
          No audit records found matching criteria.
        </div>
      )}
    </div>
  );
};
