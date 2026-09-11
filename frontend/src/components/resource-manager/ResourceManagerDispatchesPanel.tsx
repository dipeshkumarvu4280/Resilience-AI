import React, { useState, useEffect } from 'react';
import { Send, RefreshCw, Truck, MapPin, Clock, AlertTriangle } from 'lucide-react';
import { listTasks } from '../../services/fieldOperationsApi';
import type { ResponseTask } from '../../types';
import { OperationalEmptyState } from '../common/OperationalEmptyState';

export const ResourceManagerDispatchesPanel: React.FC = () => {
  const [tasks, setTasks] = useState<ResponseTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDispatches = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listTasks({ limit: 50 });
      // Filter tasks related to resource delivery or fleet
      const filtered = (res?.items || []).filter(
        (t) => t.task_type === 'RESOURCE_DELIVERY' || ((t.assigned_resources || t.allocated_resources) && (t.assigned_resources?.length || t.allocated_resources?.length)) || t.assigned_vehicle_id || t.assigned_vehicle_ids?.length
      );
      setTasks(filtered.length > 0 ? filtered : res?.items || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load live dispatches.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDispatches();
  }, []);

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-4 border-b border-slate-100 gap-3">
        <div>
          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <Send className="w-4 h-4 text-emerald-600" />
            <span>Live Inventory Dispatches & Field Convoys</span>
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time tracking of active resource delivery missions, assigned transport vehicles, and destination status.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-bold px-2.5 py-1 bg-emerald-50 text-emerald-700 rounded-lg border border-emerald-200">
            {tasks.length} Dispatches Active
          </span>
          <button
            onClick={fetchDispatches}
            disabled={loading}
            className="p-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 transition-colors"
            title="Refresh Dispatches"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-emerald-600' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs font-semibold flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {loading && tasks.length === 0 ? (
        <div className="py-12 text-center text-slate-400 text-xs space-y-2">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto text-emerald-600" />
          <p>Loading live dispatch operations from MongoDB Atlas...</p>
        </div>
      ) : tasks.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {tasks.map((task) => (
            <div
              key={task.task_id}
              className="p-4 rounded-2xl border border-slate-200/90 bg-white hover:border-emerald-300 hover:shadow-md transition-all space-y-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700">
                    <Truck className="w-4 h-4" />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-slate-900">{task.title}</h4>
                    <span className="text-[10px] font-mono text-slate-400">Task: {task.task_id}</span>
                  </div>
                </div>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${
                  task.status === 'COMPLETED'
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : task.status === 'IN_PROGRESS'
                    ? 'bg-blue-50 text-blue-700 border-blue-200'
                    : 'bg-amber-50 text-amber-700 border-amber-200'
                }`}>
                  {task.status.replace(/_/g, ' ')}
                </span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">{task.description}</p>

              {task.destination && (
                <div className="text-xs text-slate-600 flex items-center gap-1.5 p-2 bg-slate-50 rounded-xl border border-slate-100">
                  <MapPin className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                  <span className="truncate">Destination: <strong>{task.destination.name || task.destination.address}</strong></span>
                </div>
              )}

              {(task.assigned_resources || task.allocated_resources) && ((task.assigned_resources?.length || 0) > 0 || (task.allocated_resources?.length || 0) > 0) && (
                <div className="p-2.5 rounded-xl bg-emerald-50/50 border border-emerald-100 space-y-1 text-xs">
                  <div className="text-[10px] font-mono font-bold text-emerald-700 uppercase">Allocated Cargo:</div>
                  <div className="flex flex-wrap gap-1.5">
                    {(task.assigned_resources || task.allocated_resources || []).map((r: any, idx: number) => (
                      <span key={idx} className="px-2 py-0.5 rounded bg-white border border-emerald-200 text-emerald-800 text-[11px] font-semibold">
                        {r.resource_name || r.resource_id}: {r.quantity_allocated || r.quantity} {r.unit || 'units'}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  Priority: <strong className="text-slate-700">{task.priority}</strong>
                </span>
                <span>Situation: <strong className="font-mono text-slate-700">{task.situation_id}</strong></span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <OperationalEmptyState
          icon={Truck}
          title="NO LIVE DISPATCHES ACTIVE"
          description="When response plans are approved and field logistics tasks are dispatched, they will appear here in real time."
          phaseBadge="DISPATCH ACTIVE"
          accentColor="emerald"
        />
      )}
    </div>
  );
};
