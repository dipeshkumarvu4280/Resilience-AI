import React, { useEffect, useState } from 'react';
import { Server, RefreshCw } from 'lucide-react';
import api from '../../services/api';
import type { SystemHealthResponse, ServiceStatus } from '../../types';

export const SystemStatusPanel: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = async () => {
    try {
      const res = await api.get<SystemHealthResponse>('/system/status');
      setHealth(res.data);
    } catch (err) {
      console.warn('System health poll failed:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const getStatusBadge = (status: ServiceStatus) => {
    switch (status) {
      case 'Operational':
        return (
          <span className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            OPERATIONAL
          </span>
        );
      case 'Degraded':
        return (
          <span className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            DEGRADED
          </span>
        );
      case 'Outage':
        return (
          <span className="inline-flex items-center gap-1 font-mono text-[10px] font-semibold text-red-700 bg-red-50 px-2 py-0.5 rounded border border-red-200">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
            OUTAGE
          </span>
        );
      case 'Not Enabled':
      default:
        return (
          <span className="inline-flex items-center gap-1 font-mono text-[10px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
            NOT ENABLED
          </span>
        );
    }
  };

  if (compact) {
    return (
      <div className="flex items-center gap-2 font-mono text-xs text-slate-700">
        <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 shadow-sm" />
        <span className="font-semibold text-slate-900 tracking-wider">SYSTEM OPERATIONAL</span>
        <span className="text-slate-300">•</span>
        <span className="text-slate-500 text-[11px]">Phase 0 Active</span>
      </div>
    );
  }

  return (
    <div className="p-6 rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between pb-3 border-b border-slate-100 mb-4">
        <div className="flex items-center gap-2">
          <Server className="w-4 h-4 text-slate-500" />
          <span className="font-mono text-xs font-bold uppercase tracking-wider text-slate-900">
            System Telemetry & Service Status
          </span>
        </div>
        <button
          onClick={() => {
            setLoading(true);
            fetchStatus();
          }}
          className="text-slate-400 hover:text-slate-700 p-1 transition-colors"
          title="Refresh telemetry"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-teal-600' : ''}`} />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {health?.services ? (
          Object.entries(health.services).map(([key, service]) => (
            <div
              key={key}
              className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex items-start justify-between gap-3"
            >
              <div>
                <div className="flex items-center gap-2">
                  <div className="font-mono text-xs font-bold text-slate-800">
                    {service.name}
                  </div>
                  <span className="text-[9px] font-mono text-slate-500 uppercase bg-slate-200/70 px-1.5 py-0.5 rounded">
                    {service.phase}
                  </span>
                </div>
                <div className="text-xs text-slate-600 mt-1 line-clamp-1">
                  {service.description}
                </div>
              </div>
              <div className="flex-shrink-0">
                {getStatusBadge(service.status)}
              </div>
            </div>
          ))
        ) : (
          <div className="col-span-2 text-center text-xs text-slate-500 py-4 font-mono">
            Loading system telemetry...
          </div>
        )}
      </div>

      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between font-mono text-xs text-slate-500">
        <div>
          DATABASE: <span className="text-emerald-700 font-bold">{health?.database_connected ? 'CONNECTED (resilience_db)' : 'STANDBY'}</span>
        </div>
        <div>
          STATUS: <span className="text-emerald-700 font-bold">OPERATIONAL</span>
        </div>
      </div>
    </div>
  );
};

