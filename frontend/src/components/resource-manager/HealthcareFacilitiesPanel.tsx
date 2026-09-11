import React, { useState, useEffect, useCallback } from 'react';
import {
  Building2,
  Activity,
  Plus,
  Search,
  RefreshCw,
  Edit2,
  HeartPulse,
  Bed,
  ShieldAlert,
  Wind,
  Ambulance,
  MapPin,
  CheckCircle2,
  AlertTriangle,
  X,
  ChevronRight,
  Scissors,
  Baby,
  Flame,
} from 'lucide-react';
import type {
  HealthcareFacility,
  HealthcareStatsResponse,
  HealthcareFacilityCreatePayload,
  HealthcareCapacityUpdatePayload,
  HealthcareFacilityType,
  HealthcareOperationalStatus,
} from '../../types';
import {
  getHealthcareFacilities,
  getHealthcareFacilityStats,
  createHealthcareFacility,
  updateHealthcareCapacity,
  updateHealthcareStatus,
} from '../../services/healthcareApi';

export const HealthcareFacilitiesPanel: React.FC = () => {
  const [facilities, setFacilities] = useState<HealthcareFacility[]>([]);
  const [stats, setStats] = useState<HealthcareStatsResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Filters
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [districtFilter, setDistrictFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [traumaOnly, setTraumaOnly] = useState<boolean>(false);
  const [icuOnly, setIcuOnly] = useState<boolean>(false);
  const [oxygenOnly, setOxygenOnly] = useState<boolean>(false);

  // Modals
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [isCapacityModalOpen, setIsCapacityModalOpen] = useState<boolean>(false);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState<boolean>(false);
  const [selectedFacility, setSelectedFacility] = useState<HealthcareFacility | null>(null);

  // Form states
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Registration form
  const [newFacility, setNewFacility] = useState<HealthcareFacilityCreatePayload>({
    facility_name: '',
    facility_type: 'Hospital',
    location: {
      latitude: 12.9716,
      longitude: 77.5946,
      address: '',
      city: 'Bangalore',
      district: 'Urban',
      state: 'Karnataka',
      country: 'India',
      postal_code: '560001',
      zone: 'Central',
    },
    total_beds: 100,
    occupied_beds: 0,
    total_icu_beds: 10,
    occupied_icu_beds: 0,
    total_emergency_beds: 15,
    occupied_emergency_beds: 0,
    ventilators_total: 5,
    ventilators_available: 5,
    oxygen_supported_beds: 40,
    oxygen_available_capacity: 40,
    capabilities: {
      emergency_care: true,
      trauma_care: false,
      icu: true,
      surgery: false,
      oxygen_support: true,
      ventilator_support: true,
      ambulance_support: false,
      pediatric_care: false,
      burn_unit: false,
      other_capabilities: [],
    },
    status: 'ACTIVE',
    condition: 'EXCELLENT',
    accessibility: 'FULLY_ACCESSIBLE',
    contact_phone: '',
    contact_email: '',
    operating_hours: '24/7',
  });

  // Capacity update form
  const [capacityUpdate, setCapacityUpdate] = useState<HealthcareCapacityUpdatePayload>({
    occupied_beds: 0,
    occupied_icu_beds: 0,
    occupied_emergency_beds: 0,
    ventilators_available: 0,
    oxygen_available_capacity: 0,
    reason: '',
  });

  const loadData = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) setIsRefreshing(true);
    else setIsLoading(true);
    setError(null);

    try {
      const [facData, statsData] = await Promise.all([
        getHealthcareFacilities({
          search: searchTerm || undefined,
          district: districtFilter || undefined,
          facility_type: (typeFilter as HealthcareFacilityType) || undefined,
          status: (statusFilter as HealthcareOperationalStatus) || undefined,
          trauma_capable: traumaOnly ? true : undefined,
          icu_capable: icuOnly ? true : undefined,
          oxygen_capable: oxygenOnly ? true : undefined,
          limit: 50,
        }),
        getHealthcareFacilityStats(districtFilter || undefined),
      ]);

      setFacilities(facData.items || []);
      setStats(statsData);
    } catch (err: any) {
      console.error('Error fetching healthcare facilities:', err);
      setError(err?.response?.data?.detail || 'Failed to load healthcare facilities.');
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [searchTerm, districtFilter, typeFilter, statusFilter, traumaOnly, icuOnly, oxygenOnly]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRegisterFacility = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setIsSubmitting(true);

    try {
      if (!newFacility.facility_name.trim()) {
        throw new Error('Facility name is required.');
      }
      if (!newFacility.location.address.trim()) {
        throw new Error('Facility address is required.');
      }
      if (newFacility.occupied_beds > newFacility.total_beds) {
        throw new Error('Occupied general beds cannot exceed total beds.');
      }
      if (newFacility.occupied_icu_beds > newFacility.total_icu_beds) {
        throw new Error('Occupied ICU beds cannot exceed total ICU beds.');
      }
      if (newFacility.occupied_emergency_beds > newFacility.total_emergency_beds) {
        throw new Error('Occupied emergency beds cannot exceed total emergency beds.');
      }

      await createHealthcareFacility(newFacility);
      setSuccessMessage(`Facility "${newFacility.facility_name}" registered successfully.`);
      setIsCreateModalOpen(false);
      
      // Reset form
      setNewFacility({
        facility_name: '',
        facility_type: 'Hospital',
        location: {
          latitude: 12.9716,
          longitude: 77.5946,
          address: '',
          city: 'Bangalore',
          district: 'Urban',
          state: 'Karnataka',
          country: 'India',
          postal_code: '560001',
          zone: 'Central',
        },
        total_beds: 100,
        occupied_beds: 0,
        total_icu_beds: 10,
        occupied_icu_beds: 0,
        total_emergency_beds: 15,
        occupied_emergency_beds: 0,
        ventilators_total: 5,
        ventilators_available: 5,
        oxygen_supported_beds: 40,
        oxygen_available_capacity: 40,
        capabilities: {
          emergency_care: true,
          trauma_care: false,
          icu: true,
          surgery: false,
          oxygen_support: true,
          ventilator_support: true,
          ambulance_support: false,
          pediatric_care: false,
          burn_unit: false,
          other_capabilities: [],
        },
        status: 'ACTIVE',
        condition: 'EXCELLENT',
        accessibility: 'FULLY_ACCESSIBLE',
        contact_phone: '',
        contact_email: '',
        operating_hours: '24/7',
      });

      await loadData();
      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || err.message || 'Failed to register facility.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOpenCapacityModal = (fac: HealthcareFacility) => {
    setSelectedFacility(fac);
    setCapacityUpdate({
      occupied_beds: fac.occupied_beds,
      occupied_icu_beds: fac.occupied_icu_beds,
      occupied_emergency_beds: fac.occupied_emergency_beds,
      ventilators_available: fac.ventilators_available,
      oxygen_available_capacity: fac.oxygen_available_capacity,
      reason: '',
    });
    setFormError(null);
    setIsCapacityModalOpen(true);
  };

  const handleUpdateCapacity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFacility) return;
    setFormError(null);
    setIsSubmitting(true);

    try {
      if ((capacityUpdate.occupied_beds ?? 0) > selectedFacility.total_beds) {
        throw new Error(`Occupied beds cannot exceed total beds (${selectedFacility.total_beds}).`);
      }
      if ((capacityUpdate.occupied_icu_beds ?? 0) > selectedFacility.total_icu_beds) {
        throw new Error(`Occupied ICU beds cannot exceed total ICU beds (${selectedFacility.total_icu_beds}).`);
      }
      if ((capacityUpdate.occupied_emergency_beds ?? 0) > selectedFacility.total_emergency_beds) {
        throw new Error(`Occupied emergency beds cannot exceed total emergency beds (${selectedFacility.total_emergency_beds}).`);
      }

      const updated = await updateHealthcareCapacity(selectedFacility.facility_id, capacityUpdate);
      setSuccessMessage(`Capacity updated for ${updated.facility_name}. Available beds: ${updated.available_beds}.`);
      setIsCapacityModalOpen(false);
      setSelectedFacility(null);
      await loadData();
      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || err.message || 'Failed to update capacity.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStatusChange = async (fac: HealthcareFacility, newStatus: HealthcareOperationalStatus) => {
    try {
      await updateHealthcareStatus(fac.facility_id, newStatus, `Operational status updated to ${newStatus}`);
      setSuccessMessage(`Status updated for ${fac.facility_name} to ${newStatus}.`);
      await loadData();
      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update facility status.');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header & Action Bar */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white p-5 rounded-xl border border-slate-200 shadow-xs">
        <div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-50 text-emerald-700 border border-emerald-200">
              HEALTHCARE NETWORK
            </span>
            <span className="text-xs font-medium text-slate-500">Live Hospital & Bed Registry</span>
          </div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight mt-1 flex items-center gap-2">
            <Building2 className="w-6 h-6 text-emerald-600" />
            Healthcare Facilities & Bed Capacities
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            Register genuine medical facilities, track real-time bed & ICU occupancy, and coordinate casualty intake.
          </p>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <button
            onClick={() => loadData(true)}
            disabled={isRefreshing}
            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>

          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="flex items-center justify-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-lg shadow-sm transition-colors flex-1 sm:flex-none"
          >
            <Plus className="w-4 h-4" />
            Register Facility
          </button>
        </div>
      </div>

      {/* Alert Banners */}
      {successMessage && (
        <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl flex items-center gap-3 animate-fadeIn">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
          <p className="text-sm font-semibold">{successMessage}</p>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-800 rounded-xl flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
          <p className="text-sm font-semibold">{error}</p>
        </div>
      )}

      {/* KPI Cards (Aggregated from real MongoDB records) */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Total Facilities</div>
          <div className="text-2xl font-black text-slate-900 mt-1">
            {stats ? stats.total_facilities : facilities.length}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">Registered institutions</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-emerald-200 bg-emerald-50/20 shadow-xs">
          <div className="text-xs font-bold text-emerald-700 uppercase tracking-wider">Active Facilities</div>
          <div className="text-2xl font-black text-emerald-700 mt-1">
            {stats ? stats.active_facilities : facilities.filter(f => f.status === 'ACTIVE').length}
          </div>
          <div className="text-xs text-emerald-600 mt-0.5">Mission ready & receiving</div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Available Beds</div>
          <div className="text-2xl font-black text-blue-600 mt-1">
            {stats ? stats.total_available_beds : facilities.reduce((sum, f) => sum + f.available_beds, 0)}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            of {stats ? stats.total_beds : facilities.reduce((sum, f) => sum + f.total_beds, 0)} total general beds
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-purple-200 bg-purple-50/20 shadow-xs">
          <div className="text-xs font-bold text-purple-700 uppercase tracking-wider">Available ICU</div>
          <div className="text-2xl font-black text-purple-700 mt-1">
            {stats ? stats.available_icu_beds : facilities.reduce((sum, f) => sum + f.available_icu_beds, 0)}
          </div>
          <div className="text-xs text-purple-600 mt-0.5">
            of {stats ? stats.total_icu_beds : facilities.reduce((sum, f) => sum + f.total_icu_beds, 0)} critical care beds
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-amber-200 bg-amber-50/20 shadow-xs col-span-2 md:col-span-1">
          <div className="text-xs font-bold text-amber-700 uppercase tracking-wider">Available Emergency</div>
          <div className="text-2xl font-black text-amber-700 mt-1">
            {stats ? stats.available_emergency_beds : facilities.reduce((sum, f) => sum + f.available_emergency_beds, 0)}
          </div>
          <div className="text-xs text-amber-600 mt-0.5">
            Triage & trauma beds
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
            <input
              type="text"
              placeholder="Search facility name, address..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>

          <div>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
            >
              <option value="">All Facility Types</option>
              <option value="Hospital">Hospital</option>
              <option value="Trauma Center">Trauma Center</option>
              <option value="Clinic">Clinic</option>
              <option value="Specialty Center">Specialty Center</option>
              <option value="Field Hospital">Field Hospital</option>
            </select>
          </div>

          <div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
            >
              <option value="">All Statuses</option>
              <option value="ACTIVE">ACTIVE</option>
              <option value="LIMITED">LIMITED</option>
              <option value="CLOSED">CLOSED</option>
              <option value="MAINTENANCE">MAINTENANCE</option>
            </select>
          </div>

          <div>
            <input
              type="text"
              placeholder="Filter by district (e.g. Urban)"
              value={districtFilter}
              onChange={(e) => setDistrictFilter(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
        </div>

        {/* Capability toggle filters */}
        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-100 text-xs font-semibold text-slate-600">
          <span className="text-slate-400 font-bold uppercase tracking-wider mr-1">Capabilities:</span>
          
          <button
            type="button"
            onClick={() => setTraumaOnly(!traumaOnly)}
            className={`px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 ${
              traumaOnly
                ? 'bg-rose-50 text-rose-700 border-rose-300 font-bold'
                : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            Trauma Capable
          </button>

          <button
            type="button"
            onClick={() => setIcuOnly(!icuOnly)}
            className={`px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 ${
              icuOnly
                ? 'bg-purple-50 text-purple-700 border-purple-300 font-bold'
                : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
            }`}
          >
            <HeartPulse className="w-3.5 h-3.5" />
            ICU Ready
          </button>

          <button
            type="button"
            onClick={() => setOxygenOnly(!oxygenOnly)}
            className={`px-3 py-1.5 rounded-lg border transition-colors flex items-center gap-1.5 ${
              oxygenOnly
                ? 'bg-cyan-50 text-cyan-700 border-cyan-300 font-bold'
                : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
            }`}
          >
            <Wind className="w-3.5 h-3.5" />
            Oxygen Support
          </button>

          {(searchTerm || districtFilter || typeFilter || statusFilter || traumaOnly || icuOnly || oxygenOnly) && (
            <button
              type="button"
              onClick={() => {
                setSearchTerm('');
                setDistrictFilter('');
                setTypeFilter('');
                setStatusFilter('');
                setTraumaOnly(false);
                setIcuOnly(false);
                setOxygenOnly(false);
              }}
              className="ml-auto text-xs text-rose-600 hover:text-rose-700 font-bold underline"
            >
              Clear Filters
            </button>
          )}
        </div>
      </div>

      {/* Facilities List / Grid */}
      {isLoading ? (
        <div className="bg-white p-12 rounded-xl border border-slate-200 text-center shadow-xs">
          <RefreshCw className="w-8 h-8 text-emerald-600 animate-spin mx-auto mb-3" />
          <p className="text-sm font-semibold text-slate-700">Loading healthcare facilities...</p>
        </div>
      ) : facilities.length === 0 ? (
        <div className="bg-white p-12 rounded-xl border border-slate-200 text-center shadow-xs">
          <Building2 className="w-12 h-12 text-slate-300 mx-auto mb-3" />
          <h3 className="text-base font-bold text-slate-800 uppercase tracking-wide">
            NO HEALTHCARE FACILITIES REGISTERED
          </h3>
          <p className="text-sm text-slate-500 max-w-md mx-auto mt-1">
            There are currently no healthcare facilities registered matching your query. Register genuine hospitals and medical centers to enable AI casualty coordination.
          </p>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-lg shadow-sm transition-colors"
          >
            <Plus className="w-4 h-4" />
            Register First Facility
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {facilities.map((fac) => {
            const bedOccPercent = fac.total_beds > 0 ? Math.round((fac.occupied_beds / fac.total_beds) * 100) : 0;
            const isHighOcc = bedOccPercent >= 85;

            return (
              <div
                key={fac.facility_id || fac._id}
                className="bg-white rounded-xl border border-slate-200 hover:border-emerald-300 transition-all shadow-xs hover:shadow-md flex flex-col justify-between overflow-hidden"
              >
                {/* Card Top */}
                <div className="p-5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                          {fac.facility_id}
                        </span>
                        <span
                          className={`text-xs font-bold px-2 py-0.5 rounded-full border ${
                            fac.status === 'ACTIVE'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : fac.status === 'LIMITED'
                              ? 'bg-amber-50 text-amber-700 border-amber-200'
                              : 'bg-rose-50 text-rose-700 border-rose-200'
                          }`}
                        >
                          {fac.status}
                        </span>
                      </div>
                      <h3 className="text-lg font-bold text-slate-900 mt-1.5 leading-snug">
                        {fac.facility_name}
                      </h3>
                      <div className="text-xs font-medium text-slate-500 mt-0.5">
                        {fac.facility_type} &bull; {fac.location.district}, {fac.location.city}
                      </div>
                    </div>
                  </div>

                  {/* Address & Contact */}
                  <div className="mt-3 text-xs text-slate-600 flex items-start gap-1.5">
                    <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5" />
                    <span className="line-clamp-1">{fac.location.address}</span>
                  </div>

                  {/* Bed Capacity Progress */}
                  <div className="mt-4 pt-3 border-t border-slate-100">
                    <div className="flex justify-between items-baseline text-xs mb-1.5">
                      <span className="font-bold text-slate-700 flex items-center gap-1">
                        <Bed className="w-3.5 h-3.5 text-slate-500" />
                        General Beds
                      </span>
                      <span className="font-mono">
                        <strong className="text-emerald-700 text-sm font-black">{fac.available_beds}</strong>
                        <span className="text-slate-400"> / {fac.total_beds} avail ({bedOccPercent}% occ)</span>
                      </span>
                    </div>
                    <div className="w-full bg-slate-100 h-2.5 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-300 ${
                          isHighOcc ? 'bg-rose-500' : bedOccPercent > 60 ? 'bg-amber-500' : 'bg-emerald-500'
                        }`}
                        style={{ width: `${Math.min(100, bedOccPercent)}%` }}
                      />
                    </div>
                  </div>

                  {/* ICU & Emergency Metrics */}
                  <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-slate-100 text-xs">
                    <div className="bg-purple-50/50 p-2 rounded-lg border border-purple-100">
                      <div className="text-purple-700 font-semibold flex items-center gap-1">
                        <HeartPulse className="w-3 h-3" />
                        ICU Beds
                      </div>
                      <div className="text-sm font-black text-purple-900 mt-0.5 font-mono">
                        {fac.available_icu_beds} <span className="text-xs font-normal text-purple-600">/ {fac.total_icu_beds}</span>
                      </div>
                    </div>

                    <div className="bg-amber-50/50 p-2 rounded-lg border border-amber-100">
                      <div className="text-amber-700 font-semibold flex items-center gap-1">
                        <Activity className="w-3 h-3" />
                        Emergency
                      </div>
                      <div className="text-sm font-black text-amber-900 mt-0.5 font-mono">
                        {fac.available_emergency_beds} <span className="text-xs font-normal text-amber-600">/ {fac.total_emergency_beds}</span>
                      </div>
                    </div>
                  </div>

                  {/* Capability Badges */}
                  <div className="flex flex-wrap gap-1 mt-3">
                    {fac.capabilities.trauma_care && (
                      <span className="px-2 py-0.5 bg-rose-50 text-rose-700 border border-rose-200 rounded text-[10px] font-bold">
                        Trauma
                      </span>
                    )}
                    {fac.capabilities.oxygen_support && (
                      <span className="px-2 py-0.5 bg-cyan-50 text-cyan-700 border border-cyan-200 rounded text-[10px] font-bold">
                        Oxygen ({fac.oxygen_available_capacity || fac.oxygen_supported_beds})
                      </span>
                    )}
                    {fac.capabilities.ventilator_support && (
                      <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 border border-indigo-200 rounded text-[10px] font-bold">
                        Ventilators ({fac.ventilators_available || fac.ventilators_total})
                      </span>
                    )}
                    {fac.capabilities.ambulance_support && (
                      <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded text-[10px] font-bold">
                        Ambulances
                      </span>
                    )}
                    {fac.capabilities.surgery && (
                      <span className="px-2 py-0.5 bg-slate-100 text-slate-700 border border-slate-200 rounded text-[10px] font-bold">
                        Surgical
                      </span>
                    )}
                  </div>
                </div>

                {/* Card Footer Actions */}
                <div className="p-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between gap-2">
                  <button
                    onClick={() => {
                      setSelectedFacility(fac);
                      setIsDetailModalOpen(true);
                    }}
                    className="text-xs font-bold text-slate-700 hover:text-emerald-700 transition-colors flex items-center gap-1"
                  >
                    View Details
                    <ChevronRight className="w-3.5 h-3.5" />
                  </button>

                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleOpenCapacityModal(fac)}
                      className="px-2.5 py-1 bg-white hover:bg-emerald-50 text-emerald-700 border border-emerald-300 rounded text-xs font-bold transition-colors flex items-center gap-1 shadow-2xs"
                    >
                      <Edit2 className="w-3 h-3" />
                      Update Capacity
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* MODAL 1: REGISTER HEALTHCARE FACILITY */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl max-w-2xl w-full border border-slate-200 shadow-2xl overflow-hidden animate-scaleIn my-8">
            <div className="p-5 border-b border-slate-100 flex justify-between items-center bg-slate-50">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-emerald-700 bg-emerald-100/50 px-2 py-0.5 rounded">
                  AUTHENTIC DATA ENTRY
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-1">Register Healthcare Facility</h3>
              </div>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleRegisterFacility} className="p-6 space-y-6 max-h-[80vh] overflow-y-auto">
              {formError && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs font-semibold rounded-lg flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {formError}
                </div>
              )}

              {/* Section A: Facility Info */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 border-b pb-1">
                  A. Facility Information
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="col-span-2">
                    <label className="block text-xs font-bold text-slate-700 mb-1">Facility Name *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Manipal Hospital Central"
                      value={newFacility.facility_name}
                      onChange={(e) => setNewFacility({ ...newFacility, facility_name: e.target.value })}
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Facility Type</label>
                    <select
                      value={newFacility.facility_type}
                      onChange={(e) => setNewFacility({ ...newFacility, facility_type: e.target.value as HealthcareFacilityType })}
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500 bg-white"
                    >
                      <option value="Hospital">General Hospital</option>
                      <option value="Trauma Center">Trauma Center</option>
                      <option value="Clinic">Emergency Clinic</option>
                      <option value="Specialty Center">Specialty Center</option>
                      <option value="Field Hospital">Field Hospital</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Contact Phone</label>
                    <input
                      type="text"
                      placeholder="+91 80 2502 4444"
                      value={newFacility.contact_phone || ''}
                      onChange={(e) => setNewFacility({ ...newFacility, contact_phone: e.target.value })}
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>

                  <div className="col-span-2">
                    <label className="block text-xs font-bold text-slate-700 mb-1">Street Address *</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. 98 HAL Old Airport Rd, Kodihalli"
                      value={newFacility.location.address}
                      onChange={(e) =>
                        setNewFacility({
                          ...newFacility,
                          location: { ...newFacility.location, address: e.target.value },
                        })
                      }
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">District</label>
                    <input
                      type="text"
                      value={newFacility.location.district}
                      onChange={(e) =>
                        setNewFacility({
                          ...newFacility,
                          location: { ...newFacility.location, district: e.target.value },
                        })
                      }
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Zone / Sector</label>
                    <input
                      type="text"
                      value={newFacility.location.zone || ''}
                      onChange={(e) =>
                        setNewFacility({
                          ...newFacility,
                          location: { ...newFacility.location, zone: e.target.value },
                        })
                      }
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Latitude</label>
                    <input
                      type="number"
                      step="any"
                      required
                      value={newFacility.location.latitude}
                      onChange={(e) =>
                        setNewFacility({
                          ...newFacility,
                          location: { ...newFacility.location, latitude: parseFloat(e.target.value) || 0 },
                        })
                      }
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Longitude</label>
                    <input
                      type="number"
                      step="any"
                      required
                      value={newFacility.location.longitude}
                      onChange={(e) =>
                        setNewFacility({
                          ...newFacility,
                          location: { ...newFacility.location, longitude: parseFloat(e.target.value) || 0 },
                        })
                      }
                      className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                </div>
              </div>

              {/* Section B, C, D: Capacities with live derived calculations */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 border-b pb-1">
                  B. Bed & Critical Care Capacity (Derived Available Beds)
                </h4>
                
                {/* General Beds */}
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 grid grid-cols-3 gap-3 items-center">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Total Beds</label>
                    <input
                      type="number"
                      min="0"
                      required
                      value={newFacility.total_beds}
                      onChange={(e) =>
                        setNewFacility({ ...newFacility, total_beds: Math.max(0, parseInt(e.target.value) || 0) })
                      }
                      className="w-full px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">Occupied Beds</label>
                    <input
                      type="number"
                      min="0"
                      max={newFacility.total_beds}
                      required
                      value={newFacility.occupied_beds}
                      onChange={(e) =>
                        setNewFacility({ ...newFacility, occupied_beds: Math.max(0, parseInt(e.target.value) || 0) })
                      }
                      className="w-full px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white"
                    />
                  </div>
                  <div className="text-center">
                    <span className="block text-xs font-bold text-slate-500">Calculated Available</span>
                    <span className="text-lg font-black text-emerald-700 font-mono">
                      {Math.max(0, newFacility.total_beds - newFacility.occupied_beds)}
                    </span>
                  </div>
                </div>

                {/* ICU Beds */}
                <div className="p-3 bg-purple-50/50 rounded-xl border border-purple-200 grid grid-cols-3 gap-3 items-center">
                  <div>
                    <label className="block text-xs font-bold text-purple-900 mb-1">Total ICU Beds</label>
                    <input
                      type="number"
                      min="0"
                      required
                      value={newFacility.total_icu_beds}
                      onChange={(e) =>
                        setNewFacility({ ...newFacility, total_icu_beds: Math.max(0, parseInt(e.target.value) || 0) })
                      }
                      className="w-full px-3 py-1.5 text-sm border border-purple-200 rounded-lg bg-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-purple-900 mb-1">Occupied ICU</label>
                    <input
                      type="number"
                      min="0"
                      max={newFacility.total_icu_beds}
                      required
                      value={newFacility.occupied_icu_beds}
                      onChange={(e) =>
                        setNewFacility({ ...newFacility, occupied_icu_beds: Math.max(0, parseInt(e.target.value) || 0) })
                      }
                      className="w-full px-3 py-1.5 text-sm border border-purple-200 rounded-lg bg-white"
                    />
                  </div>
                  <div className="text-center">
                    <span className="block text-xs font-bold text-purple-600">Available ICU</span>
                    <span className="text-lg font-black text-purple-800 font-mono">
                      {Math.max(0, newFacility.total_icu_beds - newFacility.occupied_icu_beds)}
                    </span>
                  </div>
                </div>

                {/* Emergency Beds */}
                <div className="p-3 bg-amber-50/50 rounded-xl border border-amber-200 grid grid-cols-3 gap-3 items-center">
                  <div>
                    <label className="block text-xs font-bold text-amber-900 mb-1">Emergency Beds</label>
                    <input
                      type="number"
                      min="0"
                      required
                      value={newFacility.total_emergency_beds}
                      onChange={(e) =>
                        setNewFacility({ ...newFacility, total_emergency_beds: Math.max(0, parseInt(e.target.value) || 0) })
                      }
                      className="w-full px-3 py-1.5 text-sm border border-amber-200 rounded-lg bg-white"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-amber-900 mb-1">Occupied Emergency</label>
                    <input
                      type="number"
                      min="0"
                      max={newFacility.total_emergency_beds}
                      required
                      value={newFacility.occupied_emergency_beds}
                      onChange={(e) =>
                        setNewFacility({ ...newFacility, occupied_emergency_beds: Math.max(0, parseInt(e.target.value) || 0) })
                      }
                      className="w-full px-3 py-1.5 text-sm border border-amber-200 rounded-lg bg-white"
                    />
                  </div>
                  <div className="text-center">
                    <span className="block text-xs font-bold text-amber-600">Available Emergency</span>
                    <span className="text-lg font-black text-amber-800 font-mono">
                      {Math.max(0, newFacility.total_emergency_beds - newFacility.occupied_emergency_beds)}
                    </span>
                  </div>
                </div>
              </div>

              {/* Section E: Capabilities Checklist */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 border-b pb-1">
                  C. Medical Capabilities
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {[
                    { key: 'emergency_care', label: '24/7 Emergency Care', icon: Activity },
                    { key: 'trauma_care', label: 'Trauma Stabilization', icon: ShieldAlert },
                    { key: 'icu', label: 'ICU Unit', icon: HeartPulse },
                    { key: 'surgery', label: 'Surgical Theaters', icon: Scissors },
                    { key: 'oxygen_support', label: 'Piped Oxygen Supply', icon: Wind },
                    { key: 'ventilator_support', label: 'Ventilator Units', icon: Wind },
                    { key: 'ambulance_support', label: 'Dedicated Ambulances', icon: Ambulance },
                    { key: 'pediatric_care', label: 'Pediatric / Neonatal', icon: Baby },
                    { key: 'burn_unit', label: 'Burn Care Unit', icon: Flame },
                  ].map(({ key, label, icon: Icon }) => (
                    <label
                      key={key}
                      className={`p-2.5 rounded-lg border text-xs font-semibold cursor-pointer flex items-center gap-2 transition-colors ${
                        (newFacility.capabilities as any)[key]
                          ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                          : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={(newFacility.capabilities as any)[key]}
                        onChange={(e) =>
                          setNewFacility({
                            ...newFacility,
                            capabilities: {
                              ...newFacility.capabilities,
                              [key]: e.target.checked,
                            },
                          })
                        }
                        className="rounded text-emerald-600 focus:ring-emerald-500"
                      />
                      <Icon className="w-3.5 h-3.5 shrink-0" />
                      <span>{label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Section F: Status */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 border-b pb-1">
                  D. Operational Status
                </h4>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {['ACTIVE', 'LIMITED', 'CLOSED', 'MAINTENANCE'].map((st) => (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setNewFacility({ ...newFacility, status: st as HealthcareOperationalStatus })}
                      className={`p-2 rounded-lg text-xs font-bold border transition-colors ${
                        newFacility.status === st
                          ? 'bg-slate-900 text-white border-slate-900'
                          : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>
              </div>

              {/* Form Buttons */}
              <div className="pt-4 border-t border-slate-100 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-lg shadow-sm transition-colors flex items-center gap-2"
                >
                  {isSubmitting && <RefreshCw className="w-4 h-4 animate-spin" />}
                  Register Facility
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: UPDATE BED OCCUPANCY */}
      {isCapacityModalOpen && selectedFacility && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl max-w-lg w-full border border-slate-200 shadow-2xl overflow-hidden animate-scaleIn">
            <div className="p-5 border-b border-slate-100 flex justify-between items-center bg-slate-50">
              <div>
                <span className="text-xs font-mono font-bold text-slate-500">
                  {selectedFacility.facility_id}
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-0.5">
                  Update Occupancy: {selectedFacility.facility_name}
                </h3>
              </div>
              <button
                onClick={() => setIsCapacityModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleUpdateCapacity} className="p-6 space-y-4">
              {formError && (
                <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs font-semibold rounded-lg flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" />
                  {formError}
                </div>
              )}

              {/* General Beds Occupancy */}
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                <div className="flex justify-between items-center text-xs font-bold text-slate-700 mb-2">
                  <span>General Beds (Total: {selectedFacility.total_beds})</span>
                  <span className="text-emerald-700 font-mono">
                    Available: {Math.max(0, selectedFacility.total_beds - (capacityUpdate.occupied_beds ?? 0))}
                  </span>
                </div>
                <input
                  type="number"
                  min="0"
                  max={selectedFacility.total_beds}
                  required
                  value={capacityUpdate.occupied_beds}
                  onChange={(e) =>
                    setCapacityUpdate({
                      ...capacityUpdate,
                      occupied_beds: Math.max(0, parseInt(e.target.value) || 0),
                    })
                  }
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white"
                />
              </div>

              {/* ICU Occupancy */}
              <div className="p-3 bg-purple-50/50 rounded-xl border border-purple-200">
                <div className="flex justify-between items-center text-xs font-bold text-purple-900 mb-2">
                  <span>ICU Beds (Total: {selectedFacility.total_icu_beds})</span>
                  <span className="text-purple-700 font-mono">
                    Available: {Math.max(0, selectedFacility.total_icu_beds - (capacityUpdate.occupied_icu_beds ?? 0))}
                  </span>
                </div>
                <input
                  type="number"
                  min="0"
                  max={selectedFacility.total_icu_beds}
                  required
                  value={capacityUpdate.occupied_icu_beds}
                  onChange={(e) =>
                    setCapacityUpdate({
                      ...capacityUpdate,
                      occupied_icu_beds: Math.max(0, parseInt(e.target.value) || 0),
                    })
                  }
                  className="w-full px-3 py-2 text-sm border border-purple-200 rounded-lg bg-white"
                />
              </div>

              {/* Emergency Occupancy */}
              <div className="p-3 bg-amber-50/50 rounded-xl border border-amber-200">
                <div className="flex justify-between items-center text-xs font-bold text-amber-900 mb-2">
                  <span>Emergency Beds (Total: {selectedFacility.total_emergency_beds})</span>
                  <span className="text-amber-700 font-mono">
                    Available: {Math.max(0, selectedFacility.total_emergency_beds - (capacityUpdate.occupied_emergency_beds ?? 0))}
                  </span>
                </div>
                <input
                  type="number"
                  min="0"
                  max={selectedFacility.total_emergency_beds}
                  required
                  value={capacityUpdate.occupied_emergency_beds}
                  onChange={(e) =>
                    setCapacityUpdate({
                      ...capacityUpdate,
                      occupied_emergency_beds: Math.max(0, parseInt(e.target.value) || 0),
                    })
                  }
                  className="w-full px-3 py-2 text-sm border border-amber-200 rounded-lg bg-white"
                />
              </div>

              {/* Reason */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Update Reason / Shift Handover Note
                </label>
                <input
                  type="text"
                  placeholder="e.g. Mass casualty triage shift intake"
                  value={capacityUpdate.reason || ''}
                  onChange={(e) => setCapacityUpdate({ ...capacityUpdate, reason: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              {/* Form Buttons */}
              <div className="pt-4 border-t border-slate-100 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsCapacityModalOpen(false)}
                  className="px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-lg shadow-sm transition-colors flex items-center gap-2"
                >
                  {isSubmitting && <RefreshCw className="w-4 h-4 animate-spin" />}
                  Save Capacity Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 3: FACILITY DETAILS VIEW */}
      {isDetailModalOpen && selectedFacility && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-white rounded-2xl max-w-xl w-full border border-slate-200 shadow-2xl overflow-hidden animate-scaleIn my-8">
            <div className="p-5 border-b border-slate-100 flex justify-between items-center bg-slate-50">
              <div>
                <span className="text-xs font-mono font-bold text-slate-500">
                  {selectedFacility.facility_id}
                </span>
                <h3 className="text-lg font-black text-slate-900 mt-0.5">
                  {selectedFacility.facility_name}
                </h3>
              </div>
              <button
                onClick={() => setIsDetailModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto text-sm">
              {/* Status and Info */}
              <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-slate-50 rounded-xl border border-slate-200">
                <div>
                  <span className="text-xs font-bold text-slate-500 uppercase">Operational Status</span>
                  <div className="flex items-center gap-1 mt-1">
                    {(['ACTIVE', 'LIMITED', 'CLOSED'] as HealthcareOperationalStatus[]).map((st) => (
                      <button
                        key={st}
                        type="button"
                        onClick={async () => {
                          await handleStatusChange(selectedFacility, st);
                          setSelectedFacility({ ...selectedFacility, status: st });
                        }}
                        className={`px-2 py-0.5 rounded text-xs font-bold border transition-colors ${
                          selectedFacility.status === st
                            ? 'bg-emerald-600 text-white border-emerald-600'
                            : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-100'
                        }`}
                      >
                        {st}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="text-xs font-bold text-slate-500 uppercase">Facility Type</span>
                  <div className="text-sm font-bold text-slate-800 mt-0.5">{selectedFacility.facility_type}</div>
                </div>
                <div>
                  <span className="text-xs font-bold text-slate-500 uppercase">Operating Hours</span>
                  <div className="text-sm font-bold text-slate-800 mt-0.5">{selectedFacility.operating_hours}</div>
                </div>
              </div>

              {/* Location & Coordinates */}
              <div className="space-y-1.5 p-3 bg-white rounded-xl border border-slate-200">
                <span className="text-xs font-bold text-slate-500 uppercase">Physical Location & GIS</span>
                <div className="font-medium text-slate-800">{selectedFacility.location.address}</div>
                <div className="text-xs text-slate-500">
                  {selectedFacility.location.district}, {selectedFacility.location.city}, {selectedFacility.location.state} - {selectedFacility.location.postal_code}
                </div>
                <div className="text-xs font-mono text-emerald-700 font-semibold pt-1">
                  GPS: {selectedFacility.location.latitude.toFixed(4)}, {selectedFacility.location.longitude.toFixed(4)} &bull; Zone: {selectedFacility.location.zone}
                </div>
              </div>

              {/* Capacity Matrix */}
              <div className="space-y-2">
                <span className="text-xs font-bold text-slate-500 uppercase">Capacity Telemetry</span>
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
                    <div className="text-xs text-slate-500 font-bold">General Beds</div>
                    <div className="text-xl font-black text-emerald-700 font-mono mt-1">
                      {selectedFacility.available_beds}
                    </div>
                    <div className="text-[11px] text-slate-500">of {selectedFacility.total_beds} total</div>
                  </div>
                  <div className="p-3 bg-purple-50 rounded-xl border border-purple-200">
                    <div className="text-xs text-purple-700 font-bold">ICU Units</div>
                    <div className="text-xl font-black text-purple-900 font-mono mt-1">
                      {selectedFacility.available_icu_beds}
                    </div>
                    <div className="text-[11px] text-purple-600">of {selectedFacility.total_icu_beds} total</div>
                  </div>
                  <div className="p-3 bg-amber-50 rounded-xl border border-amber-200">
                    <div className="text-xs text-amber-700 font-bold">Emergency</div>
                    <div className="text-xl font-black text-amber-900 font-mono mt-1">
                      {selectedFacility.available_emergency_beds}
                    </div>
                    <div className="text-[11px] text-amber-600">of {selectedFacility.total_emergency_beds} total</div>
                  </div>
                </div>
              </div>

              {/* Capabilities */}
              <div className="space-y-2">
                <span className="text-xs font-bold text-slate-500 uppercase">Medical Readiness</span>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {Object.entries(selectedFacility.capabilities).map(([key, val]) => {
                    if (key === 'other_capabilities') return null;
                    return (
                      <div
                        key={key}
                        className={`p-2 rounded-lg border flex items-center justify-between ${
                          val ? 'bg-emerald-50/60 border-emerald-200 text-emerald-900' : 'bg-slate-50 border-slate-200 text-slate-400'
                        }`}
                      >
                        <span className="capitalize">{key.replace('_', ' ')}</span>
                        <span className="font-bold">{val ? 'YES' : 'NO'}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Audit & Timestamps */}
              <div className="pt-2 border-t border-slate-100 text-xs text-slate-500 flex justify-between">
                <span>Last updated: {new Date(selectedFacility.last_updated).toLocaleString()}</span>
                {selectedFacility.last_updated_by_name && (
                  <span>By: {selectedFacility.last_updated_by_name}</span>
                )}
              </div>
            </div>

            <div className="p-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
              <button
                onClick={() => {
                  setIsDetailModalOpen(false);
                  handleOpenCapacityModal(selectedFacility);
                }}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 shadow-xs"
              >
                <Edit2 className="w-3.5 h-3.5" />
                Update Bed Occupancy
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
