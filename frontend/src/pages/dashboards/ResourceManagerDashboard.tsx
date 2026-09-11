import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { OperationalHeader } from '../../components/layout/OperationalHeader';
import { CommandSidebar } from '../../components/layout/CommandSidebar';
import { OperationalEmptyState } from '../../components/common/OperationalEmptyState';
import { ResourceManagerDispatchesPanel } from '../../components/resource-manager/ResourceManagerDispatchesPanel';
import { ResourceManagerSheltersPanel } from '../../components/resource-manager/ResourceManagerSheltersPanel';
import { ResourceManagerSettingsPanel } from '../../components/resource-manager/ResourceManagerSettingsPanel';
import { ResourceManagerInventoryDispatchPanel } from '../../components/resource-manager/ResourceManagerInventoryDispatchPanel';
import { HealthcareFacilitiesPanel } from '../../components/resource-manager/HealthcareFacilitiesPanel';
import { ResourceBottlenecksPanel } from '../../components/resource-manager/ResourceBottlenecksPanel';
import {
  Truck,
  Boxes,
  PackagePlus,
  Search,
  RefreshCw,
  Edit2,
  CheckCircle2,
  AlertTriangle,
  X,
  MapPin,
  Phone,
  SlidersHorizontal,
  Layers,
  HeartPulse,
  Droplets,
} from 'lucide-react';
import type {
  ResourceResponse,
  ResourceStatsResponse,
  ResourceType,
  ResourceStatus,
  ResourceCondition,
  ResourceCreatePayload,
} from '../../types';
import {
  getResources,
  getResourceStats,
  createResource,
  updateResourceQuantity,
  updateResourceStatus,
} from '../../services/api';

const ALL_RESOURCE_TYPES: ResourceType[] = [
  'Water',
  'Food',
  'Medicine',
  'First Aid',
  'Medical Equipment',
  'Rescue Equipment',
  'Protective Equipment',
  'Blankets',
  'Clothing',
  'Generator',
  'Fuel',
  'Communication Equipment',
  'Transport',
  'Shelter',
  'Other',
];

interface DomainConfig {
  tabId: string;
  title: string;
  subtitle: string;
  badge: string;
  icon: any;
  resourceTypes?: string[];
  emptyTitle: string;
  emptyDescription: string;
  defaultCreateType: ResourceType;
  allowedCreateTypes: ResourceType[];
  kpiLabels: {
    total: string;
    available: string;
    partially: string;
    unavailable: string;
  };
}

const DEFAULT_DOMAIN: DomainConfig = {
  tabId: 'operations',
  title: 'Resource Stockpile & Logistics Operations',
  subtitle: 'Unified operational inventory, strategic logistics reserves, and disaster response assets.',
  badge: 'LIVE INVENTORY',
  icon: Boxes,
  emptyTitle: 'NO ACTIVE RESOURCES FOUND',
  emptyDescription: 'Emergency provisions, logistics assets, and supplies registered in the system will appear here.',
  defaultCreateType: 'Water',
  allowedCreateTypes: ALL_RESOURCE_TYPES,
  kpiLabels: {
    total: 'TOTAL LOGISTICS ASSETS',
    available: 'AVAILABLE & MISSION READY',
    partially: 'PARTIALLY ALLOCATED',
    unavailable: 'UNAVAILABLE / DEPLETED',
  },
};

const DOMAIN_CONFIGS: Record<string, DomainConfig> = {
  operations: DEFAULT_DOMAIN,
  overview: DEFAULT_DOMAIN,
  inventory: {
    tabId: 'inventory',
    title: 'Supply Stockpile & Strategic Reserves',
    subtitle: 'Emergency food rations, water reserves, blankets, and essential relief items.',
    badge: 'STRATEGIC RESERVES',
    icon: Boxes,
    resourceTypes: ['Water', 'Food', 'Blankets', 'Clothing'],
    emptyTitle: 'NO STRATEGIC STOCKPILES REGISTERED',
    emptyDescription: 'Emergency food, water, bedding, and relief consumables registered in depots will appear here.',
    defaultCreateType: 'Water',
    allowedCreateTypes: ['Water', 'Food', 'Blankets', 'Clothing'],
    kpiLabels: {
      total: 'STOCKPILE ASSETS',
      available: 'READY FOR DISPATCH',
      partially: 'STAGED FOR DELIVERY',
      unavailable: 'DEPLETED STOCK',
    },
  },
  stockpile: {
    tabId: 'stockpile',
    title: 'Supply Stockpile & Strategic Reserves',
    subtitle: 'Emergency food rations, water reserves, blankets, and essential relief items.',
    badge: 'STRATEGIC RESERVES',
    icon: Boxes,
    resourceTypes: ['Water', 'Food', 'Blankets', 'Clothing'],
    emptyTitle: 'NO STRATEGIC STOCKPILES REGISTERED',
    emptyDescription: 'Emergency food, water, bedding, and relief consumables registered in depots will appear here.',
    defaultCreateType: 'Water',
    allowedCreateTypes: ['Water', 'Food', 'Blankets', 'Clothing'],
    kpiLabels: {
      total: 'STOCKPILE ASSETS',
      available: 'READY FOR DISPATCH',
      partially: 'STAGED FOR DELIVERY',
      unavailable: 'DEPLETED STOCK',
    },
  },
  vehicles: {
    tabId: 'vehicles',
    title: 'Fleet, Transport & Logistics Vehicles',
    subtitle: 'Ambulances, cargo trucks, rescue boats, 4x4 response vehicles, and heavy logistics transports.',
    badge: 'FLEET & TRANSPORT',
    icon: Truck,
    resourceTypes: ['Transport'],
    emptyTitle: 'NO TRANSPORT VEHICLES REGISTERED',
    emptyDescription: 'Ambulances, logistics trucks, and rescue fleet assets will appear here.',
    defaultCreateType: 'Transport',
    allowedCreateTypes: ['Transport'],
    kpiLabels: {
      total: 'FLEET VEHICLES',
      available: 'ACTIVE & READY',
      partially: 'ON MISSION DISPATCH',
      unavailable: 'MAINTENANCE / OFFLINE',
    },
  },
  fleet: {
    tabId: 'fleet',
    title: 'Fleet, Transport & Logistics Vehicles',
    subtitle: 'Ambulances, cargo trucks, rescue boats, 4x4 response vehicles, and heavy logistics transports.',
    badge: 'FLEET & TRANSPORT',
    icon: Truck,
    resourceTypes: ['Transport'],
    emptyTitle: 'NO TRANSPORT VEHICLES REGISTERED',
    emptyDescription: 'Ambulances, logistics trucks, and rescue fleet assets will appear here.',
    defaultCreateType: 'Transport',
    allowedCreateTypes: ['Transport'],
    kpiLabels: {
      total: 'FLEET VEHICLES',
      available: 'ACTIVE & READY',
      partially: 'ON MISSION DISPATCH',
      unavailable: 'MAINTENANCE / OFFLINE',
    },
  },
  medical: {
    tabId: 'medical',
    title: 'Medical Supplies & Healthcare Assets',
    subtitle: 'Trauma kits, pharmaceuticals, oxygen cylinders, medical devices, and triage equipment.',
    badge: 'HEALTHCARE INVENTORY',
    icon: HeartPulse,
    resourceTypes: ['Medicine', 'First Aid', 'Medical Equipment', 'Healthcare'],
    emptyTitle: 'NO MEDICAL SUPPLIES FOUND',
    emptyDescription: 'Pharmaceuticals, first aid kits, and hospital equipment will appear here.',
    defaultCreateType: 'Medicine',
    allowedCreateTypes: ['Medicine', 'First Aid', 'Medical Equipment'],
    kpiLabels: {
      total: 'MEDICAL ASSETS',
      available: 'AVAILABLE SUPPLIES',
      partially: 'ALLOCATED IN USE',
      unavailable: 'EXHAUSTED / RESTOCK',
    },
  },
  'food-water': {
    tabId: 'food-water',
    title: 'Rations, Food & Potable Water Supplies',
    subtitle: 'Potable water bowsers, hydration packets, dry rations, and family meal parcels.',
    badge: 'RATIONS INVENTORY',
    icon: Droplets,
    resourceTypes: ['Water', 'Food'],
    emptyTitle: 'NO FOOD OR WATER STOCKPILES',
    emptyDescription: 'Emergency hydration and nutrition stocks registered in storage depots will appear here.',
    defaultCreateType: 'Water',
    allowedCreateTypes: ['Water', 'Food'],
    kpiLabels: {
      total: 'RATION & WATER ASSETS',
      available: 'AVAILABLE LITRES / MEALS',
      partially: 'PARTIALLY ALLOCATED',
      unavailable: 'DEPLETED STOCK',
    },
  },
  equipment: {
    tabId: 'equipment',
    title: 'Heavy Equipment & Rescue Machinery',
    subtitle: 'Power generators, hydraulic tools, high-capacity pumps, fuel reserves, and radio units.',
    badge: 'RESCUE MACHINERY',
    icon: Layers,
    resourceTypes: ['Rescue Equipment', 'Protective Equipment', 'Generator', 'Fuel', 'Communication Equipment'],
    emptyTitle: 'NO HEAVY RESCUE EQUIPMENT FOUND',
    emptyDescription: 'Machinery, generators, and heavy rescue gear registered in depots will appear here.',
    defaultCreateType: 'Rescue Equipment',
    allowedCreateTypes: ['Rescue Equipment', 'Protective Equipment', 'Generator', 'Fuel', 'Communication Equipment'],
    kpiLabels: {
      total: 'HEAVY EQUIPMENT ASSETS',
      available: 'OPERATIONAL & READY',
      partially: 'DEPLOYED ON SCENE',
      unavailable: 'DAMAGED / IN REPAIR',
    },
  },
};

export const ResourceManagerDashboard: React.FC = () => {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = searchParams.get('tab') || 'operations';
  const [activeTab, setActiveTab] = useState<string>(initialTab);

  // Sync tab with URL search parameter
  useEffect(() => {
    const tabFromUrl = searchParams.get('tab');
    if (tabFromUrl && tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
  }, [searchParams]);

  // Mobile drawer state
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  const handleTabSelect = (tabId: string) => {
    setIsMobileSidebarOpen(false);
    const params = new URLSearchParams(searchParams);
    params.set('tab', tabId);
    setSearchParams(params);
  };

  const currentDomain = DOMAIN_CONFIGS[activeTab] || DEFAULT_DOMAIN;

  // Data State
  const [resources, setResources] = useState<ResourceResponse[]>([]);
  const [stats, setStats] = useState<ResourceStatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Search within domain
  const [selectedType, setSelectedType] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');

  // Modals
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isAdjustModalOpen, setIsAdjustModalOpen] = useState(false);
  const [selectedResource, setSelectedResource] = useState<ResourceResponse | null>(null);
  const [quickQty, setQuickQty] = useState<number>(0);
  const [quickQtyReason, setQuickQtyReason] = useState<string>('');

  // Action Feedback
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // New Resource Form
  const [formData, setFormData] = useState<ResourceCreatePayload>({
    name: '',
    resource_type: currentDomain.defaultCreateType,
    category: 'Essential Relief',
    quantity_total: 100,
    quantity_available: 100,
    unit: 'Litres',
    location: {
      latitude: 16.5062,
      longitude: 80.648,
      address: 'Central Emergency Depot, Sector 4',
      zone_or_district: 'Krishna District',
      city: 'Vijayawada',
      state: 'Andhra Pradesh',
    },
    status: 'AVAILABLE',
    condition: 'GOOD',
    owner: 'National Disaster Supply Hub',
    contact: '+91 98000 11223',
    notes: 'Standard relief stock ready for deployment.',
  });

  // Reset selectedType filter when changing active tab
  useEffect(() => {
    setSelectedType('all');
    setSearchTerm('');
    setStatusFilter('all');
  }, [activeTab]);

  const fetchData = useCallback(async () => {
    // Only fetch domain resources if we are on a resource inventory tab
    if (activeTab === 'dispatch' || activeTab === 'shelters' || activeTab === 'settings' || activeTab === 'resources') {
      return;
    }

    setLoading(true);
    setError(null);

    // Determine query parameters based on current domain and user filter
    let queryTypes: string[] | undefined = undefined;
    let singleType: string | undefined = undefined;

    if (selectedType !== 'all') {
      singleType = selectedType;
    } else if (currentDomain.resourceTypes && currentDomain.resourceTypes.length > 0) {
      if (currentDomain.resourceTypes.length === 1) {
        singleType = currentDomain.resourceTypes[0];
      } else {
        queryTypes = currentDomain.resourceTypes;
      }
    }

    const domainParam = (selectedType === 'all' && currentDomain.tabId !== 'operations' && currentDomain.tabId !== 'overview') ? currentDomain.tabId : undefined;

    try {
      const [resData, statsData] = await Promise.all([
        getResources({
          domain: domainParam,
          resource_type: singleType,
          resource_types: queryTypes,
          status: statusFilter !== 'all' ? statusFilter : undefined,
          search: searchTerm.trim() || undefined,
          limit: 50,
        }),
        getResourceStats({
          domain: domainParam,
          resource_type: singleType,
          resource_types: queryTypes,
        }),
      ]);
      setResources(resData.items || []);
      setStats(statsData);
    } catch (err: any) {
      console.error('Failed to load live resource inventory:', err);
      setError(err?.response?.data?.detail || 'Failed to load live resource inventory.');
      // Prevent stale data leakage on failure
      setResources([]);
    } finally {
      setLoading(false);
    }
  }, [activeTab, currentDomain, selectedType, statusFilter, searchTerm]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchData();
  };

  const handleOpenCreateModal = () => {
    setActionError(null);
    setFormData((prev) => ({
      ...prev,
      name: '',
      resource_type: currentDomain.defaultCreateType,
      unit:
        currentDomain.defaultCreateType === 'Transport'
          ? 'Vehicles'
          : currentDomain.defaultCreateType === 'Water'
          ? 'Litres'
          : currentDomain.defaultCreateType === 'Food'
          ? 'Ration Packs'
          : 'Units',
    }));
    setIsCreateModalOpen(true);
  };

  const handleCreateResource = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setActionError('Resource name is required.');
      return;
    }
    if (formData.quantity_available > formData.quantity_total) {
      setActionError('Available quantity cannot exceed total quantity.');
      return;
    }

    setSubmitting(true);
    setActionError(null);
    try {
      await createResource(formData);
      setActionSuccess(`Resource '${formData.name}' registered into live inventory successfully.`);
      setIsCreateModalOpen(false);
      fetchData();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to create resource.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleQuickQuantityUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedResource) return;
    if (quickQty < 0 || quickQty > selectedResource.quantity_total) {
      setActionError(`Available quantity must be between 0 and ${selectedResource.quantity_total}.`);
      return;
    }

    setSubmitting(true);
    setActionError(null);
    try {
      await updateResourceQuantity(
        selectedResource.resource_id,
        quickQty,
        selectedResource.quantity_total,
        quickQtyReason.trim() || 'Logistics field inventory recount'
      );
      setActionSuccess(`Quantity for '${selectedResource.name}' updated to ${quickQty} ${selectedResource.unit}.`);
      setIsAdjustModalOpen(false);
      setSelectedResource(null);
      fetchData();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to adjust quantity.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatusChange = async (resource: ResourceResponse, newStatus: ResourceStatus) => {
    try {
      await updateResourceStatus(resource.resource_id, newStatus, 'Manager status toggle');
      setActionSuccess(`Status of '${resource.name}' set to ${newStatus}.`);
      fetchData();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to update resource status.');
    }
  };

  const getStatusBadgeClass = (status: ResourceStatus) => {
    switch (status) {
      case 'AVAILABLE':
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
      case 'PARTIALLY_AVAILABLE':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'UNAVAILABLE':
        return 'bg-red-50 text-red-700 border-red-200';
      default:
        return 'bg-slate-50 text-slate-700 border-slate-200';
    }
  };

  const getConditionBadgeClass = (condition: ResourceCondition) => {
    switch (condition) {
      case 'GOOD':
        return 'bg-blue-50 text-blue-700 border-blue-200';
      case 'LIMITED':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'DAMAGED':
        return 'bg-red-50 text-red-700 border-red-200';
      default:
        return 'bg-slate-50 text-slate-600 border-slate-200';
    }
  };

  const DomainIcon = currentDomain.icon;

  return (
    <div className="relative h-screen max-h-screen bg-[#EEF2F6] text-slate-900 flex flex-col font-sans overflow-hidden">
      <TacticalBackground />

      {/* Operational Header with Emerald Accent */}
      <div className="flex-shrink-0 z-20">
        <OperationalHeader
          portalTitle="RESOURCE OPERATIONS"
          portalSubtitle="Disaster Logistics, Shelter Inventory & Emergency Supply Mesh"
          onToggleMobileMenu={() => setIsMobileSidebarOpen(true)}
        />
      </div>

      {/* Body Area */}
      <div className="flex-1 flex overflow-hidden min-h-0 z-10">
        {/* Command Navigation Sidebar */}
        <CommandSidebar
          role="RESOURCE_MANAGER"
          activeTab={activeTab}
          isOpenMobile={isMobileSidebarOpen}
          onCloseMobile={() => setIsMobileSidebarOpen(false)}
          onSelectTab={handleTabSelect}
          className="hidden md:flex flex-shrink-0 w-64 h-full overflow-y-auto border-r border-slate-200/80 bg-white"
        />

        {/* Main Operational Viewport */}
        <main className="flex-1 h-full overflow-y-auto p-3 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 max-w-7xl mx-auto w-full touch-scroll">
          {/* Feedback Banners */}
          {actionSuccess && (
            <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center justify-between shadow-xs animate-in fade-in">
              <span className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                {actionSuccess}
              </span>
              <button onClick={() => setActionSuccess(null)} className="text-emerald-700 hover:text-emerald-900 cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {(actionError || error) && (
            <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs font-semibold flex items-center justify-between shadow-xs animate-in fade-in">
              <span className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
                {actionError || error}
              </span>
              <button
                onClick={() => {
                  setActionError(null);
                  setError(null);
                }}
                className="text-red-700 hover:text-red-900 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Welcome Hero Card */}
          {activeTab !== 'resources' &&
            activeTab !== 'dispatch' &&
            activeTab !== 'shelters' &&
            activeTab !== 'settings' &&
            activeTab !== 'healthcare' &&
            activeTab !== 'healthcare-facilities' &&
            activeTab !== 'bottlenecks' && (
              <div className="bg-white border border-slate-200/90 rounded-2xl p-4 sm:p-6 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
                <div className="flex items-center gap-3 sm:gap-4">
                  <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center flex-shrink-0 shadow-xs">
                    <DomainIcon className="w-5 h-5 sm:w-6 sm:h-6" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h1 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">{currentDomain.title}</h1>
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-pulse" />
                        {currentDomain.badge}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      Logged in as <strong className="text-slate-700 font-semibold">{user?.full_name || 'Elena Rostova'}</strong>{' '}
                      ({user?.email || 'elena.rostova@resilience.gov'}) • Facility:{' '}
                      <span className="font-semibold text-slate-700">
                        {user?.department_or_agency || user?.department || 'Emergency Logistics & Disaster Supply'}
                      </span>
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2.5 w-full md:w-auto">
                  <button
                    onClick={fetchData}
                    disabled={loading}
                    className="p-2.5 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 hover:text-slate-900 transition-colors shadow-2xs cursor-pointer"
                    title="Refresh Live Data"
                  >
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-emerald-600' : ''}`} />
                  </button>
                  <button
                    onClick={handleOpenCreateModal}
                    className="inline-flex items-center justify-center gap-2 px-4 py-2.5 min-h-[44px] rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs transition-all w-full md:w-auto cursor-pointer"
                  >
                    <PackagePlus className="w-4 h-4" />
                    <span>Register New Asset</span>
                  </button>
                </div>
              </div>
            )}

          {/* Conditional View Switching */}
          {activeTab === 'resources' && <ResourceManagerInventoryDispatchPanel />}

          {activeTab === 'dispatch' && <ResourceManagerDispatchesPanel />}

          {activeTab === 'shelters' && (
            <ResourceManagerSheltersPanel
              onOpenCreate={() => {
                setFormData({
                  ...formData,
                  name: '',
                  resource_type: 'Shelter',
                  unit: 'Beds',
                  quantity_total: 250,
                  quantity_available: 250,
                });
                setIsCreateModalOpen(true);
              }}
              onAdjustStock={(r) => {
                setSelectedResource(r);
                setQuickQty(r.quantity_available);
                setIsAdjustModalOpen(true);
              }}
            />
          )}

          {(activeTab === 'healthcare' || activeTab === 'healthcare-facilities') && (
            <HealthcareFacilitiesPanel />
          )}

          {activeTab === 'bottlenecks' && <ResourceBottlenecksPanel />}

          {activeTab === 'settings' && <ResourceManagerSettingsPanel />}

          {/* Domain-specific Inventory Views: operations, inventory, vehicles, medical, food-water, equipment */}
          {activeTab !== 'resources' &&
            activeTab !== 'dispatch' &&
            activeTab !== 'shelters' &&
            activeTab !== 'settings' &&
            activeTab !== 'healthcare' &&
            activeTab !== 'healthcare-facilities' &&
            activeTab !== 'bottlenecks' && (
              <>
                {/* Top Operational Telemetry Bar - 4 Live Domain-Specific KPI Cards with Interactive Drill-Down */}
                <div className="grid grid-cols-1 xs:grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                  <div
                    onClick={() => {
                      setStatusFilter('all');
                      setSelectedType('all');
                    }}
                    className="group p-4 rounded-2xl border border-slate-200/90 bg-white shadow-sm hover:shadow-md hover:border-slate-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500 uppercase tracking-wider group-hover:text-slate-800 transition-colors">
                      <span>{currentDomain.kpiLabels.total}</span>
                      <Boxes className="w-3.5 h-3.5 text-slate-400 group-hover:scale-110 transition-transform" />
                    </div>
                    <div className="my-2">
                      <div className="text-2xl font-extrabold text-slate-900 group-hover:scale-105 transition-transform origin-left">
                        {stats ? stats.total_resources : '...'}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span>Authoritative domain records</span>
                      <span className="text-slate-700 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                    </div>
                  </div>

                  <div
                    onClick={() => setStatusFilter('AVAILABLE')}
                    className="group p-4 rounded-2xl border border-emerald-200/90 bg-white shadow-sm hover:shadow-md hover:border-emerald-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between text-[11px] font-semibold text-emerald-700 uppercase tracking-wider group-hover:text-emerald-800 transition-colors">
                      <span>{currentDomain.kpiLabels.available}</span>
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 group-hover:scale-110 transition-transform" />
                    </div>
                    <div className="my-2">
                      <div className="text-2xl font-extrabold text-emerald-600 group-hover:scale-105 transition-transform origin-left">
                        {stats ? stats.available_resources : '...'}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span>Fully ready for allocation</span>
                      <span className="text-emerald-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                    </div>
                  </div>

                  <div
                    onClick={() => setStatusFilter('PARTIALLY_AVAILABLE')}
                    className="group p-4 rounded-2xl border border-amber-200/90 bg-white shadow-sm hover:shadow-md hover:border-amber-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between text-[11px] font-semibold text-amber-700 uppercase tracking-wider group-hover:text-amber-800 transition-colors">
                      <span>{currentDomain.kpiLabels.partially}</span>
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-600 group-hover:scale-110 transition-transform" />
                    </div>
                    <div className="my-2">
                      <div className="text-2xl font-extrabold text-amber-600 group-hover:scale-105 transition-transform origin-left">
                        {stats ? stats.partially_available : '...'}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span>Active allocations / in use</span>
                      <span className="text-amber-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                    </div>
                  </div>

                  <div
                    onClick={() => setStatusFilter('UNAVAILABLE')}
                    className="group p-4 rounded-2xl border border-red-200/90 bg-white shadow-sm hover:shadow-md hover:border-red-300 transition-all duration-200 cursor-pointer flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between text-[11px] font-semibold text-red-700 uppercase tracking-wider group-hover:text-red-800 transition-colors">
                      <span>{currentDomain.kpiLabels.unavailable}</span>
                      <X className="w-3.5 h-3.5 text-red-600 group-hover:scale-110 transition-transform" />
                    </div>
                    <div className="my-2">
                      <div className="text-2xl font-extrabold text-red-600 group-hover:scale-105 transition-transform origin-left">
                        {stats ? stats.unavailable : '...'}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-500">
                      <span>Zero stock or offline</span>
                      <span className="text-red-600 font-bold opacity-80 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-[11px]">View →</span>
                    </div>
                  </div>
                </div>

                {/* Search & Filter Ribbon */}
                <div className="bg-white border border-slate-200/90 rounded-2xl p-4 shadow-sm flex flex-col md:flex-row items-center justify-between gap-3">
                  <form onSubmit={handleSearchSubmit} className="flex-1 w-full flex items-center gap-2">
                    <div className="relative flex-1">
                      <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                      <input
                        type="text"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        placeholder={`Search ${currentDomain.title.toLowerCase()} by name, location, owner...`}
                        className="w-full pl-9 pr-3.5 py-2 rounded-xl border border-slate-200 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500"
                      />
                    </div>
                    <button
                      type="submit"
                      className="px-4 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold shadow-2xs transition-colors"
                    >
                      Filter
                    </button>
                  </form>

                  <div className="flex items-center gap-2 w-full md:w-auto">
                    {/* Sub-type filter for current domain */}
                    {currentDomain.allowedCreateTypes.length > 1 && (
                      <select
                        value={selectedType}
                        onChange={(e) => setSelectedType(e.target.value)}
                        className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 w-full md:w-auto"
                      >
                        <option value="all">All {currentDomain.badge} Types</option>
                        {currentDomain.allowedCreateTypes.map((t) => (
                          <option key={t} value={t}>
                            {t}
                          </option>
                        ))}
                      </select>
                    )}

                    {/* Status Filter */}
                    <select
                      value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                      className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 w-full md:w-auto"
                    >
                      <option value="all">All Statuses</option>
                      <option value="AVAILABLE">Available</option>
                      <option value="PARTIALLY_AVAILABLE">Partially Available</option>
                      <option value="UNAVAILABLE">Unavailable</option>
                    </select>
                  </div>
                </div>

                {/* Resource List / Grid */}
                {loading && resources.length === 0 ? (
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-12 shadow-sm text-center">
                    <RefreshCw className="w-8 h-8 text-emerald-600 animate-spin mx-auto mb-3" />
                    <h3 className="text-sm font-bold text-slate-800">Loading {currentDomain.title}...</h3>
                    <p className="text-xs text-slate-500 mt-1">Retrieving authoritative records from MongoDB Atlas.</p>
                  </div>
                ) : resources.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {resources.map((resource) => (
                      <div
                        key={resource.resource_id}
                        className="bg-white border border-slate-200/90 rounded-2xl p-5 shadow-sm space-y-4 hover:border-slate-300 transition-all flex flex-col justify-between"
                      >
                        <div className="space-y-3">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="flex items-center gap-1.5">
                                <span className="font-mono text-[10px] text-slate-400 font-bold">
                                  {resource.resource_id}
                                </span>
                                <span className="text-slate-300">•</span>
                                <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-100">
                                  {resource.resource_type}
                                </span>
                              </div>
                              <h3 className="text-sm font-bold text-slate-900 mt-1">{resource.name}</h3>
                            </div>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${getStatusBadgeClass(
                                resource.status
                              )}`}
                            >
                              {resource.status.replace(/_/g, ' ')}
                            </span>
                          </div>

                          <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 space-y-2 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="text-slate-500 font-medium">Available Quantity:</span>
                              <span className="font-mono font-bold text-slate-900 text-sm">
                                {resource.quantity_available} / {resource.quantity_total} {resource.unit}
                              </span>
                            </div>

                            {/* Progress bar */}
                            <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  resource.quantity_available / (resource.quantity_total || 1) > 0.5
                                    ? 'bg-emerald-500'
                                    : resource.quantity_available / (resource.quantity_total || 1) > 0.2
                                    ? 'bg-amber-500'
                                    : 'bg-red-500'
                                }`}
                                style={{
                                  width: `${Math.min(
                                    100,
                                    Math.max(
                                      0,
                                      (resource.quantity_available / (resource.quantity_total || 1)) * 100
                                    )
                                  )}%`,
                                }}
                              />
                            </div>

                            <div className="flex items-center justify-between text-[11px] pt-1 text-slate-500">
                              <span>Condition:</span>
                              <span
                                className={`font-semibold px-1.5 py-0.2 rounded border text-[10px] ${getConditionBadgeClass(
                                  resource.condition
                                )}`}
                              >
                                {resource.condition}
                              </span>
                            </div>
                          </div>

                          <div className="space-y-1.5 text-xs text-slate-600">
                            {resource.location?.address && (
                              <div className="flex items-center gap-1.5 truncate">
                                <MapPin className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                                <span className="truncate">{resource.location.address}</span>
                              </div>
                            )}
                            {resource.contact && (
                              <div className="flex items-center gap-1.5 truncate">
                                <Phone className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                                <span className="truncate">{resource.contact}</span>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div className="pt-3 border-t border-slate-100 flex items-center justify-between gap-2">
                          <button
                            onClick={() => {
                              setSelectedResource(resource);
                              setQuickQty(resource.quantity_available);
                              setQuickQtyReason('');
                              setIsAdjustModalOpen(true);
                            }}
                            className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1"
                          >
                            <Edit2 className="w-3 h-3" />
                            <span>Adjust Stock</span>
                          </button>

                          <div className="flex items-center gap-1">
                            {resource.status !== 'AVAILABLE' && (
                              <button
                                onClick={() => handleStatusChange(resource, 'AVAILABLE' as ResourceStatus)}
                                className="px-2.5 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 text-[11px] font-bold rounded-lg border border-emerald-200 transition-colors"
                              >
                                Mark Available
                              </button>
                            )}
                            {resource.status === 'AVAILABLE' && (
                              <button
                                onClick={() => handleStatusChange(resource, 'UNAVAILABLE' as ResourceStatus)}
                                className="px-2.5 py-1.5 bg-red-50 hover:bg-red-100 text-red-700 text-[11px] font-bold rounded-lg border border-red-200 transition-colors"
                              >
                                Mark Offline
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="bg-white border border-slate-200/90 rounded-2xl p-8 shadow-sm">
                    <OperationalEmptyState
                      icon={currentDomain.icon}
                      title={currentDomain.emptyTitle}
                      description={currentDomain.emptyDescription}
                      phaseBadge={currentDomain.badge}
                      accentColor="emerald"
                    />
                  </div>
                )}
              </>
            )}
        </main>
      </div>

      {/* Adjust Quantity Modal */}
      {isAdjustModalOpen && selectedResource && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="w-5 h-5 text-emerald-600" />
                <h3 className="text-sm font-bold text-slate-900">Adjust Available Stock</h3>
              </div>
              <button
                onClick={() => setIsAdjustModalOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleQuickQuantityUpdate} className="space-y-4 text-xs">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 space-y-1">
                <div className="font-bold text-slate-900">{selectedResource.name}</div>
                <div className="text-slate-500">
                  Total Capacity: <strong className="text-slate-700">{selectedResource.quantity_total} {selectedResource.unit}</strong>
                </div>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">
                  New Available Quantity ({selectedResource.unit})
                </label>
                <input
                  type="number"
                  min="0"
                  max={selectedResource.quantity_total}
                  value={quickQty}
                  onChange={(e) => setQuickQty(parseFloat(e.target.value) || 0)}
                  className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono font-bold"
                />
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Audit Recount Reason</label>
                <input
                  type="text"
                  placeholder="e.g. Depot audit count, deployed to field, stock replenishment"
                  value={quickQtyReason}
                  onChange={(e) => setQuickQtyReason(e.target.value)}
                  className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="pt-2 border-t border-slate-100 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAdjustModalOpen(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl shadow-xs disabled:opacity-50"
                >
                  {submitting ? 'Saving...' : 'Save Stock Quantity'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Register New Asset Modal */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-lg w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <PackagePlus className="w-5 h-5 text-emerald-600" />
                <h3 className="text-sm font-bold text-slate-900">Register Asset into {currentDomain.title}</h3>
              </div>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateResource} className="space-y-4 text-xs">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="md:col-span-2">
                  <label className="block font-bold text-slate-700 mb-1">Asset / Resource Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Heavy Duty Rescue Boat 04, Potable Water Tanker A"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">Resource Type *</label>
                  <select
                    value={formData.resource_type}
                    onChange={(e) => setFormData({ ...formData, resource_type: e.target.value as ResourceType })}
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 font-bold text-emerald-800"
                  >
                    {currentDomain.allowedCreateTypes.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">Unit of Measure *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Litres, Vehicles, Beds, Kits"
                    value={formData.unit}
                    onChange={(e) => setFormData({ ...formData, unit: e.target.value })}
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">Total Quantity *</label>
                  <input
                    type="number"
                    min="1"
                    required
                    value={formData.quantity_total}
                    onChange={(e) => {
                      const val = parseFloat(e.target.value) || 0;
                      setFormData({
                        ...formData,
                        quantity_total: val,
                        quantity_available: val,
                      });
                    }}
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono font-bold"
                  />
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">Available Quantity *</label>
                  <input
                    type="number"
                    min="0"
                    max={formData.quantity_total}
                    required
                    value={formData.quantity_available}
                    onChange={(e) => setFormData({ ...formData, quantity_available: parseFloat(e.target.value) || 0 })}
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono font-bold"
                  />
                </div>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Depot / Staging Address</label>
                <input
                  type="text"
                  placeholder="e.g. Central Emergency Depot, Sector 4"
                  value={formData.location.address}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      location: { ...formData.location, address: e.target.value },
                    })
                  }
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">District / Zone</label>
                  <input
                    type="text"
                    placeholder="e.g. Krishna District"
                    value={formData.location.zone_or_district}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        location: { ...formData.location, zone_or_district: e.target.value },
                      })
                    }
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Contact Phone</label>
                  <input
                    type="text"
                    placeholder="+91 98000 11223"
                    value={formData.contact}
                    onChange={(e) => setFormData({ ...formData, contact: e.target.value })}
                    className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl shadow-xs disabled:opacity-50"
                >
                  {submitting ? 'Registering...' : 'Register Asset'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default ResourceManagerDashboard;
