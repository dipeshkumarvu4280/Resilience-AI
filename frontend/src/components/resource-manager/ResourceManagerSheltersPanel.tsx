import React, { useState, useEffect } from 'react';
import { Home, RefreshCw, MapPin, Phone, Plus, AlertTriangle } from 'lucide-react';
import { listResources } from '../../services/api';
import type { ResourceResponse } from '../../types';
import { OperationalEmptyState } from '../common/OperationalEmptyState';

interface ResourceManagerSheltersPanelProps {
  onOpenCreate: () => void;
  onAdjustStock: (resource: ResourceResponse) => void;
}

export const ResourceManagerSheltersPanel: React.FC<ResourceManagerSheltersPanelProps> = ({
  onOpenCreate,
  onAdjustStock,
}) => {
  const [shelters, setShelters] = useState<ResourceResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchShelters = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listResources({ resource_type: 'Shelter', limit: 100 });
      setShelters(res?.items || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load shelter capacities.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchShelters();
  }, []);

  const totalCapacitySum = shelters.reduce((acc, s) => acc + (s.quantity_total || 0), 0);
  const totalAvailableSum = shelters.reduce((acc, s) => acc + (s.quantity_available || 0), 0);
  const totalOccupiedSum = Math.max(0, totalCapacitySum - totalAvailableSum);

  return (
    <div className="space-y-6">
      {/* 4 Summary Telemetry Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm flex flex-col justify-between">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">ACTIVE SHELTERS</div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-slate-900">{shelters.length} Facilities</div>
          </div>
          <div className="text-[11px] text-slate-500">Designated evacuation sites</div>
        </div>

        <div className="p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm flex flex-col justify-between">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">TOTAL BED CAPACITY</div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-blue-600">{totalCapacitySum} Beds</div>
          </div>
          <div className="text-[11px] text-slate-500">Authoritative capacity sum</div>
        </div>

        <div className="p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm flex flex-col justify-between">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">CURRENT OCCUPANCY</div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-amber-600">{totalOccupiedSum} Evacuees</div>
          </div>
          <div className="text-[11px] text-slate-500">Occupied shelter slots</div>
        </div>

        <div className="p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm flex flex-col justify-between">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">REMAINING CAPACITY</div>
          <div className="my-2">
            <div className="text-2xl font-extrabold text-emerald-600">{totalAvailableSum} Available</div>
          </div>
          <div className="text-[11px] text-slate-500">Total - Occupancy</div>
        </div>
      </div>

      {/* Shelter Grid View */}
      <div className="bg-white border border-slate-200/90 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-3 border-b border-slate-100 gap-3">
          <div className="flex items-center gap-2">
            <Home className="w-4 h-4 text-emerald-600" />
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
              Designated Emergency Shelters & Evacuation Centers
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onOpenCreate}
              className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs flex items-center gap-1.5"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Register Shelter</span>
            </button>
            <button
              onClick={fetchShelters}
              disabled={loading}
              className="p-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-600 transition-colors"
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

        {loading && shelters.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-xs space-y-2">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto text-emerald-600" />
            <p>Loading authoritative shelter records...</p>
          </div>
        ) : shelters.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {shelters.map((shelter) => {
              const totalCap = shelter.quantity_total || 0;
              const availCap = shelter.quantity_available !== undefined ? shelter.quantity_available : totalCap;
              const currOcc = Math.max(0, totalCap - availCap);
              const percentOccupied = totalCap > 0 ? Math.round((currOcc / totalCap) * 100) : 0;

              return (
                <div
                  key={shelter.resource_id}
                  className="p-4 rounded-2xl border border-slate-200/90 bg-white hover:border-emerald-300 hover:shadow-md transition-all flex flex-col justify-between space-y-3"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <span className="text-[10px] font-mono font-bold text-slate-400 block">{shelter.resource_id}</span>
                        <h4 className="text-sm font-bold text-slate-900 mt-0.5">{shelter.name}</h4>
                      </div>
                      <span className={`px-2 py-0.5 rounded-md border text-[10px] font-bold ${
                        shelter.status === 'AVAILABLE'
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200'
                      }`}>
                        {shelter.status}
                      </span>
                    </div>

                    <div className="mt-3 p-3 rounded-xl bg-slate-50 border border-slate-100 space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-slate-500 font-medium">Occupancy:</span>
                        <span className="font-mono font-bold text-slate-800">
                          {currOcc} / {totalCap} {shelter.unit || 'Beds'} ({percentOccupied}%)
                        </span>
                      </div>
                      <div className="w-full bg-slate-200 rounded-full h-2 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            percentOccupied < 70 ? 'bg-emerald-600' : percentOccupied < 90 ? 'bg-amber-500' : 'bg-red-500'
                          }`}
                          style={{ width: `${percentOccupied}%` }}
                        />
                      </div>
                      <div className="text-[11px] text-emerald-700 font-semibold text-right">
                        Remaining Capacity: {availCap} {shelter.unit || 'Beds'}
                      </div>
                    </div>

                    <div className="mt-3 space-y-1 text-xs text-slate-600">
                      <div className="flex items-center gap-1.5 truncate">
                        <MapPin className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                        <span className="truncate">{shelter.location.address || `${shelter.location.latitude.toFixed(4)}, ${shelter.location.longitude.toFixed(4)}`}</span>
                      </div>
                      {shelter.contact && (
                        <div className="flex items-center gap-1.5 text-slate-500 text-[11px]">
                          <Phone className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                          <span>{shelter.contact}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                    <span className="text-[11px] text-slate-400 font-medium">Condition: {shelter.condition}</span>
                    <button
                      onClick={() => onAdjustStock(shelter)}
                      className="px-2.5 py-1 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold"
                    >
                      Update Occupancy
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <OperationalEmptyState
            icon={Home}
            title="NO SHELTER FACILITIES REGISTERED"
            description="Register designated emergency evacuation centers to track live bed capacity and occupancy."
            phaseBadge="SHELTERS READY"
            accentColor="emerald"
          />
        )}
      </div>
    </div>
  );
};
