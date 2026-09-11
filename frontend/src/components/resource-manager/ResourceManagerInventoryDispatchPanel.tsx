import React, { useState, useEffect, useCallback } from 'react';
import {
  Truck,
  CheckCircle2,
  AlertTriangle,
  MapPin,
  RefreshCw,
  Filter,
} from 'lucide-react';
import { getAllAllocations } from '../../services/api';
import type { AllocationResponse } from '../../types';
import { OperationalEmptyState } from '../common/OperationalEmptyState';

export const ResourceManagerInventoryDispatchPanel: React.FC = () => {
  const [allocations, setAllocations] = useState<AllocationResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [error, setError] = useState<string | null>(null);

  const loadAllocations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAllAllocations(statusFilter !== 'ALL' ? statusFilter : undefined);
      setAllocations(data || []);
    } catch (err: any) {
      console.error('Failed to load inventory dispatches:', err);
      setError(err?.response?.data?.detail || 'Failed to load inventory allocations.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadAllocations();
  }, [loadAllocations]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'APPROVED':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'PROPOSED':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'DISPATCHED':
        return 'bg-indigo-50 text-indigo-700 border-indigo-200';
      case 'COMPLETED':
        return 'bg-slate-100 text-slate-700 border-slate-200';
      case 'REJECTED':
        return 'bg-red-50 text-red-700 border-red-200';
      default:
        return 'bg-slate-50 text-slate-600 border-slate-200';
    }
  };

  const approvedCount = allocations.filter((a) => a.status === 'APPROVED').length;
  const proposedCount = allocations.filter((a) => a.status === 'PROPOSED').length;
  const totalAllocatedQty = allocations.reduce(
    (sum, a) => sum + (a.approved_quantity || a.requested_quantity || 0),
    0
  );

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Truck className="w-5 h-5 text-emerald-600" />
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">
              Operational Inventory Dispatches & Allocations
            </h2>
          </div>
          <p className="text-xs text-slate-500">
            Authoritative resource allocations matched against active emergency incidents with Human-in-the-Loop officer approval.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <span className="font-semibold text-slate-500">Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-slate-800 font-bold focus:outline-none"
            >
              <option value="ALL">All Statuses ({allocations.length})</option>
              <option value="APPROVED">Approved Only</option>
              <option value="PROPOSED">Proposed</option>
              <option value="DISPATCHED">Dispatched</option>
              <option value="COMPLETED">Completed</option>
              <option value="REJECTED">Rejected</option>
            </select>
          </div>

          <button
            onClick={loadAllocations}
            disabled={loading}
            className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl border border-slate-200 transition-colors shadow-2xs"
            title="Refresh dispatches"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-emerald-600' : ''}`} />
          </button>
        </div>
      </div>

      {/* 4 Dispatch Telemetry Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm flex flex-col justify-between">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">TOTAL ALLOCATIONS</div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-slate-900">{allocations.length}</div>
          </div>
          <div className="text-[11px] text-slate-500">Logged allocation records</div>
        </div>

        <div className="p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm flex flex-col justify-between">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">OFFICER APPROVED</div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-emerald-600">{approvedCount}</div>
          </div>
          <div className="text-[11px] text-slate-500">Ready for field deployment</div>
        </div>

        <div className="p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm flex flex-col justify-between">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">PENDING APPROVAL</div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-blue-600">{proposedCount}</div>
          </div>
          <div className="text-[11px] text-slate-500">Awaiting officer sign-off</div>
        </div>

        <div className="p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm flex flex-col justify-between">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">TOTAL UNITS ASSIGNED</div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-slate-900">{totalAllocatedQty}</div>
          </div>
          <div className="text-[11px] text-slate-500">Allocated stock quantities</div>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-2xl text-xs text-red-800 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-red-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Allocations Table / List */}
      {allocations.length > 0 ? (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                  <th className="py-3 px-3">Allocation ID</th>
                  <th className="py-3 px-3">Resource Asset</th>
                  <th className="py-3 px-3">Quantity</th>
                  <th className="py-3 px-3">Destination / Incident</th>
                  <th className="py-3 px-3">Status</th>
                  <th className="py-3 px-3">Officer Review</th>
                  <th className="py-3 px-3">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {allocations.map((alloc) => (
                  <tr key={alloc.allocation_id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3.5 px-3 font-mono font-bold text-slate-900">
                      {alloc.allocation_id}
                    </td>
                    <td className="py-3.5 px-3">
                      <div className="font-semibold text-slate-800">{alloc.resource_name}</div>
                      <span className="text-[10px] text-slate-400 font-mono">ID: {alloc.resource_id}</span>
                    </td>
                    <td className="py-3.5 px-3 font-mono font-bold text-slate-900">
                      {alloc.approved_quantity || alloc.requested_quantity} {alloc.unit}
                    </td>
                    <td className="py-3.5 px-3">
                      <div className="flex items-center gap-1 text-slate-700">
                        <MapPin className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                        <span className="font-mono text-[11px]">Report #{alloc.report_id}</span>
                      </div>
                    </td>
                    <td className="py-3.5 px-3">
                      <span
                        className={`px-2.5 py-0.5 rounded-full border text-[11px] font-bold ${getStatusBadge(
                          alloc.status
                        )}`}
                      >
                        {alloc.status}
                      </span>
                    </td>
                    <td className="py-3.5 px-3 text-slate-600 text-[11px]">
                      {alloc.approved_by ? (
                        <div className="flex items-center gap-1 text-emerald-700 font-medium">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>{alloc.approved_by}</span>
                        </div>
                      ) : (
                        <span className="text-slate-400 italic">Pending officer review</span>
                      )}
                    </td>
                    <td className="py-3.5 px-3 text-slate-400 text-[11px] font-mono">
                      {new Date(alloc.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="bg-white border border-slate-200/90 rounded-2xl p-8 shadow-sm">
          <OperationalEmptyState
            icon={Truck}
            title="NO ACTIVE INVENTORY DISPATCHES"
            description="Operational allocations and dispatch orders for incident needs will appear here when proposed or approved."
            phaseBadge="RESOURCE ALLOCATIONS"
            accentColor="emerald"
          />
        </div>
      )}
    </div>
  );
};
