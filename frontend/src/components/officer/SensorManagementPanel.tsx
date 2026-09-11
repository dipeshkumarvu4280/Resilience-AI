import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Radio,
  Plus,
  RefreshCw,
  Search,
  Pause,
  Power,
  Gauge,
  AlertTriangle,
  CheckCircle,
  Activity,
  Layers,
  MapPin,
  Clock,
  Send,
  X,
  ChevronRight,
  ExternalLink,
  Edit3,
  Wind,
  Map as MapIcon,
  Globe,
  Table as TableIcon,
} from 'lucide-react';
import {
  getSensors,
  getSensorStats,
  getSensorsHealth,
  activateSensor,
  pauseSensor,
  resumeSensor,
  deactivateSensor,
  getSensorReadings,
  getSensorEvents,
} from '../../services/api';
import type {
  Sensor,
  SensorStatsResponse,
  SensorReading,
  SensorAlert,
  SensorType,
  SensorStatus,
  SensorHealthDetail,
  SensorHealthSummary,
} from '../../types';
import { CreateSensorModal } from './CreateSensorModal';
import { EditSensorModal } from './EditSensorModal';
import { SensorReadingModal } from './SensorReadingModal';
import { OperationalEmptyState } from '../common/OperationalEmptyState';
import { loadGoogleMaps, hasGoogleMapsApiKey } from '../../utils/googleMapsLoader';

const PREVIEW_LIGHT_STYLES: google.maps.MapTypeStyle[] = [
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#cce5ff' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#f8fafc' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#ffffff' }] },
  { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#e2e8f0' }] },
  { featureType: 'poi', elementType: 'geometry', stylers: [{ color: '#f1f5f9' }] },
  { featureType: 'administrative', elementType: 'labels.text.fill', stylers: [{ color: '#475569' }] },
];

interface SensorManagementPanelProps {
  onInspectSituation?: (situationId: string) => void;
}

export const SensorManagementPanel: React.FC<SensorManagementPanelProps> = ({
  onInspectSituation,
}) => {
  const [sensors, setSensors] = useState<Sensor[]>([]);
  const [stats, setStats] = useState<SensorStatsResponse | null>(null);
  const [healthDetails, setHealthDetails] = useState<Record<string, SensorHealthDetail>>({});
  const [healthSummary, setHealthSummary] = useState<SensorHealthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // View Mode: 'table' | 'map'
  const [viewMode, setViewMode] = useState<'table' | 'map'>('table');
  const [mapType, setMapType] = useState<'roadmap' | 'satellite'>('roadmap');

  // Google Maps State & Refs
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const googleObjRef = useRef<typeof google | null>(null);
  const sensorMarkersRef = useRef<{ [key: string]: google.maps.Marker }>({});
  const sensorCirclesRef = useRef<{ [key: string]: google.maps.Circle }>({});
  const activeInfoWindowRef = useRef<google.maps.InfoWindow | null>(null);
  const initialMapFittedRef = useRef<boolean>(false);
  const userInteractedMapRef = useRef<boolean>(false);

  // Filters & Pagination
  const [typeFilter, setTypeFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [alertFilter, setAlertFilter] = useState<string>('ALL');
  const [healthFilter, setHealthFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Selected Sensor for Details Drawer
  const [selectedSensor, setSelectedSensor] = useState<Sensor | null>(null);
  const [selectedReadings, setSelectedReadings] = useState<SensorReading[]>([]);
  const [selectedAlerts, setSelectedAlerts] = useState<SensorAlert[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  // Modals
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingSensor, setEditingSensor] = useState<Sensor | null>(null);
  const [readingModalSensor, setReadingModalSensor] = useState<Sensor | null>(null);

  const fetchSensors = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const [sensorsRes, statsRes, healthRes] = await Promise.all([
        getSensors({
          sensor_type: typeFilter !== 'ALL' ? typeFilter : undefined,
          status: statusFilter !== 'ALL' ? statusFilter : undefined,
          in_alert: alertFilter === 'ALERT' ? true : alertFilter === 'NORMAL' ? false : undefined,
          search: searchQuery.trim() || undefined,
          page,
          limit: 15,
        }),
        getSensorStats(),
        getSensorsHealth().catch(() => null),
      ]);

      setSensors(sensorsRes.items || []);
      setTotalPages(sensorsRes.total_pages || 1);
      setTotalCount(sensorsRes.total || 0);
      setStats(statsRes);

      if (healthRes) {
        setHealthSummary(healthRes.summary);
        const map: Record<string, SensorHealthDetail> = {};
        healthRes.items?.forEach((s: SensorHealthDetail) => {
          map[s.sensor_id] = s;
        });
        setHealthDetails(map);
      }
    } catch (err: any) {
      setFetchError(err?.response?.data?.detail || 'Failed to load sensor catalog.');
    } finally {
      setLoading(false);
    }
  }, [typeFilter, statusFilter, alertFilter, searchQuery, page]);

  useEffect(() => {
    fetchSensors();
  }, [fetchSensors]);

  // Load drawer history when selected sensor changes
  useEffect(() => {
    if (selectedSensor) {
      setDrawerLoading(true);
      Promise.all([
        getSensorReadings(selectedSensor.sensor_id, { limit: 20 }),
        getSensorEvents(selectedSensor.sensor_id, { limit: 10 }),
      ])
        .then(([readingsRes, alertsRes]) => {
          setSelectedReadings(readingsRes.items || []);
          setSelectedAlerts(alertsRes.items || []);
        })
        .catch(() => {})
        .finally(() => setDrawerLoading(false));
    } else {
      setSelectedReadings([]);
      setSelectedAlerts([]);
    }
  }, [selectedSensor]);

  const handleActivate = async (sensorId: string) => {
    try {
      await activateSensor(sensorId);
      fetchSensors();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to activate sensor.');
    }
  };

  const handlePause = async (sensorId: string) => {
    try {
      await pauseSensor(sensorId);
      fetchSensors();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to pause sensor.');
    }
  };

  const handleResume = async (sensorId: string) => {
    try {
      await resumeSensor(sensorId);
      fetchSensors();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to resume sensor.');
    }
  };

  const handleDeactivate = async (sensorId: string) => {
    if (!window.confirm('Are you sure you want to deactivate this sensor? It will no longer process readings.')) return;
    try {
      await deactivateSensor(sensorId);
      fetchSensors();
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to deactivate sensor.');
    }
  };

  const getStatusBadge = (status: SensorStatus) => {
    switch (status) {
      case 'ACTIVE':
        return <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">ACTIVE</span>;
      case 'PAUSED':
        return <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">PAUSED</span>;
      case 'INACTIVE':
        return <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">INACTIVE</span>;
      case 'DRAFT':
      default:
        return <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">DRAFT</span>;
    }
  };

  const getHealthBadge = (health?: SensorHealthDetail) => {
    if (!health) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
          <Clock className="w-3 h-3 text-slate-400" />
          UNKNOWN
        </span>
      );
    }
    switch (health.health_state) {
      case 'HEALTHY':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle className="w-3 h-3 text-emerald-500" />
            HEALTHY
          </span>
        );
      case 'STALE':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-300 animate-pulse">
            <Clock className="w-3 h-3 text-amber-600" />
            STALE ({health.reading_age_human})
          </span>
        );
      case 'NEVER_REPORTED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
            <Clock className="w-3 h-3 text-slate-400" />
            NEVER REPORTED
          </span>
        );
      case 'INACTIVE':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-500 border border-slate-200">
            INACTIVE
          </span>
        );
      case 'UNAVAILABLE':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-zinc-100 text-zinc-600 border border-zinc-200">
            UNAVAILABLE
          </span>
        );
    }
  };

  const getTypeIcon = (type: SensorType) => {
    switch (type) {
      case 'WATER_LEVEL':
        return <Radio className="w-3.5 h-3.5 text-blue-600" />;
      case 'RAINFALL':
        return <Activity className="w-3.5 h-3.5 text-cyan-600" />;
      case 'TEMPERATURE':
        return <Gauge className="w-3.5 h-3.5 text-amber-600" />;
      case 'SMOKE_AIR_QUALITY':
        return <Layers className="w-3.5 h-3.5 text-purple-600" />;
      case 'AQI':
        return <Wind className="w-3.5 h-3.5 text-emerald-600" />;
      default:
        return <Activity className="w-3.5 h-3.5 text-slate-600" />;
    }
  };

  const handleToggleMapType = (type: 'roadmap' | 'satellite') => {
    setMapType(type);
    if (googleMapRef.current) {
      googleMapRef.current.setMapTypeId(type);
      if (type === 'roadmap') {
        googleMapRef.current.setOptions({ styles: PREVIEW_LIGHT_STYLES });
      } else {
        googleMapRef.current.setOptions({ styles: [] });
      }
    }
  };

  const createSensorMarkerSvg = (sensor: Sensor) => {
    let strokeColor = '#2563eb';
    let fillColor = '#3b82f6';
    if (sensor.in_alert) {
      strokeColor = '#b91c1c';
      fillColor = '#dc2626';
    } else if (sensor.status === 'PAUSED') {
      strokeColor = '#d97706';
      fillColor = '#f59e0b';
    } else if (sensor.status === 'INACTIVE') {
      strokeColor = '#64748b';
      fillColor = '#94a3b8';
    }

    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="0 0 38 38">
        <defs>
          <filter id="shadow-sns" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000000" flood-opacity="0.35"/>
          </filter>
        </defs>
        <circle cx="19" cy="19" r="17" fill="${fillColor}" fill-opacity="0.22" stroke="${strokeColor}" stroke-width="1.5" stroke-dasharray="3 2"/>
        <circle cx="19" cy="19" r="13" fill="${fillColor}" stroke="#ffffff" stroke-width="2.5" filter="url(#shadow-sns)"/>
        <circle cx="19" cy="19" r="4.5" fill="#ffffff"/>
      </svg>
    `;
    return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
  };

  // Initialize Map when Map View is active
  useEffect(() => {
    let isMounted = true;
    if (viewMode !== 'map') return;

    const initMap = async () => {
      if (!mapContainerRef.current) return;
      if (googleMapRef.current) return;
      if (!hasGoogleMapsApiKey()) return;

      try {
        const googleObj = await loadGoogleMaps();
        if (!isMounted || !mapContainerRef.current) return;

        googleObjRef.current = googleObj;

        const map = new googleObj.maps.Map(mapContainerRef.current, {
          center: { lat: 16.5062, lng: 80.6480 },
          zoom: 12,
          minZoom: 4,
          maxZoom: 18,
          mapTypeId: mapType,
          disableDefaultUI: true,
          zoomControl: true,
          gestureHandling: 'greedy',
          scrollwheel: true,
          isFractionalZoomEnabled: true,
          clickableIcons: false,
          styles: mapType === 'roadmap' ? PREVIEW_LIGHT_STYLES : [],
        });

        map.addListener('dragstart', () => {
          userInteractedMapRef.current = true;
        });
        map.addListener('zoom_changed', () => {
          if (initialMapFittedRef.current) {
            userInteractedMapRef.current = true;
          }
        });

        googleMapRef.current = map;
      } catch (err) {
        console.warn('Could not initialize Google Map for Sensor Management:', err);
      }
    };

    initMap();
    return () => {
      isMounted = false;
    };
  }, [viewMode]);

  // Synchronize Sensor Markers & Coverage Circles (Decoupled from Camera)
  useEffect(() => {
    if (viewMode !== 'map') return;
    const map = googleMapRef.current;
    const googleObj = googleObjRef.current;
    if (!map || !googleObj) return;

    // Clear previous markers
    Object.values(sensorMarkersRef.current).forEach((m) => m.setMap(null));
    sensorMarkersRef.current = {};

    // Clear previous circles
    Object.values(sensorCirclesRef.current).forEach((c) => c.setMap(null));
    sensorCirclesRef.current = {};

    if (activeInfoWindowRef.current) {
      activeInfoWindowRef.current.close();
    }

    if (sensors.length === 0) return;

    const bounds = new googleObj.maps.LatLngBounds();
    let validCount = 0;

    sensors.forEach((s) => {
      const lat = s.latitude;
      const lng = s.longitude;
      if (typeof lat !== 'number' || typeof lng !== 'number' || isNaN(lat) || isNaN(lng)) return;

      bounds.extend({ lat, lng });
      validCount++;

      const radiusMeters = s.coverage?.radius_meters || 2000;
      let circleColor = '#2563eb';
      if (s.in_alert) circleColor = '#dc2626';
      else if (s.status === 'PAUSED') circleColor = '#d97706';

      // Coverage radius circle (authoritative radius_meters preserved)
      const circle = new googleObj.maps.Circle({
        map,
        center: { lat, lng },
        radius: radiusMeters,
        fillColor: circleColor,
        fillOpacity: 0.12,
        strokeColor: circleColor,
        strokeOpacity: 0.75,
        strokeWeight: 1.5,
      });
      sensorCirclesRef.current[s.sensor_id] = circle;

      // Marker
      const marker = new googleObj.maps.Marker({
        map,
        position: { lat, lng },
        title: `${s.name} (${s.sensor_id})`,
        icon: {
          url: createSensorMarkerSvg(s),
          scaledSize: new googleObj.maps.Size(36, 36),
          anchor: new googleObj.maps.Point(18, 18),
        },
        zIndex: s.in_alert ? 100 : 50,
      });

      const infoContent = document.createElement('div');
      infoContent.className = 'p-3 font-sans max-w-xs';
      infoContent.innerHTML = `
        <div style="font-family: system-ui, -apple-system, sans-serif;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px;">
            <span style="font-size: 11px; font-weight: 800; color: #0f172a; font-family: monospace;">${s.sensor_id}</span>
            <span style="font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 9999px; ${
              s.in_alert
                ? 'background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;'
                : 'background: #dcfce7; color: #166534; border: 1px solid #bbf7d0;'
            }">
              ${s.in_alert ? 'ALERT BREACH' : s.status}
            </span>
          </div>
          <h4 style="font-size: 13px; font-weight: 700; color: #0f172a; margin: 0 0 4px 0;">${s.name}</h4>
          <div style="font-size: 11px; color: #475569; margin-bottom: 6px;">
            <strong>Type:</strong> ${s.sensor_type.replace('_', ' ')} • <strong>Zone:</strong> ${s.location_name}
          </div>
          <div style="font-size: 11px; color: #0f172a; margin-bottom: 6px;">
            <strong>Telemetry:</strong> ${s.current_reading !== null && s.current_reading !== undefined ? `${s.current_reading} ${s.unit}` : 'No readings'} (Threshold: &gt; ${s.threshold} ${s.unit})
          </div>
          <div style="font-size: 10px; color: #64748b; margin-bottom: 8px;">
            Coverage radius: ${(radiusMeters / 1000).toFixed(2)} km (${radiusMeters}m)
          </div>
          <button id="btn-inspect-${s.sensor_id}" style="width: 100%; padding: 6px 12px; background: #0f172a; color: white; border: none; border-radius: 8px; font-size: 11px; font-weight: 700; cursor: pointer;">
            Inspect Telemetry Details →
          </button>
        </div>
      `;

      const infoWindow = new googleObj.maps.InfoWindow({
        content: infoContent,
      });

      googleObj.maps.event.addListener(infoWindow, 'domready', () => {
        const btn = document.getElementById(`btn-inspect-${s.sensor_id}`);
        if (btn) {
          btn.onclick = () => {
            setSelectedSensor(s);
          };
        }
      });

      marker.addListener('click', () => {
        if (activeInfoWindowRef.current) activeInfoWindowRef.current.close();
        infoWindow.open(map, marker);
        activeInfoWindowRef.current = infoWindow;
      });

      sensorMarkersRef.current[s.sensor_id] = marker;
    });

    if (validCount > 0 && map && !initialMapFittedRef.current && !userInteractedMapRef.current) {
      map.fitBounds(bounds);
      if (map.getZoom() && map.getZoom()! > 14) {
        map.setZoom(14);
      }
      initialMapFittedRef.current = true;
    }
  }, [viewMode, sensors]);

  return (
    <div className="space-y-6">
      {/* Top Header & Provision Action */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-black text-slate-900 flex items-center gap-2.5">
            <Radio className="w-6 h-6 text-red-600" />
            IoT Sensor Network & Live Intake
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Simulated IoT telemetry intelligence source with real-time threshold monitoring and dynamic replanning triggers.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {/* View Mode Switcher: Table vs Map */}
          <div className="flex items-center rounded-xl border border-slate-200 bg-white p-1 text-xs font-bold shadow-2xs">
            <button
              type="button"
              onClick={() => setViewMode('table')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                viewMode === 'table'
                  ? 'bg-slate-900 text-white shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <TableIcon className="w-3.5 h-3.5" />
              <span>Table View</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode('map')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all ${
                viewMode === 'map'
                  ? 'bg-red-600 text-white shadow-2xs'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <MapIcon className="w-3.5 h-3.5" />
              <span>Network Map</span>
            </button>
          </div>

          <button
            onClick={fetchSensors}
            disabled={loading}
            className="p-2.5 rounded-xl border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition shadow-2xs"
            title="Refresh sensor data"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-red-600' : ''}`} />
          </button>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="px-4 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold shadow-xs transition flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Provision IoT Sensor
          </button>
        </div>
      </div>

      {/* KPI Cards (Zero Hardcoded Counts) */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <div className="p-3.5 rounded-2xl bg-white border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Total Sensors</span>
            <Radio className="w-3.5 h-3.5 text-slate-400" />
          </div>
          <div className="text-xl font-black text-slate-900 mt-1.5">{stats?.total_sensors ?? 0}</div>
          <div className="text-[9px] text-slate-400 mt-0.5">Configured endpoints</div>
        </div>

        <div className="p-3.5 rounded-2xl bg-white border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-emerald-700 uppercase tracking-wider">Healthy / Fresh</span>
            <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
          </div>
          <div className="text-xl font-black text-emerald-700 mt-1.5">{healthSummary?.healthy_count ?? 0}</div>
          <div className="text-[9px] text-emerald-600 mt-0.5">Live reporting within SLA</div>
        </div>

        <div className="p-3.5 rounded-2xl bg-white border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-amber-700 uppercase tracking-wider">Stale Telemetry</span>
            <Clock className="w-3.5 h-3.5 text-amber-500" />
          </div>
          <div className="text-xl font-black text-amber-700 mt-1.5">{healthSummary?.stale_count ?? 0}</div>
          <div className="text-[9px] text-amber-600 mt-0.5">&gt; 300s since last ping</div>
        </div>

        <div className="p-3.5 rounded-2xl bg-white border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-slate-600 uppercase tracking-wider">Never Reported</span>
            <Clock className="w-3.5 h-3.5 text-slate-400" />
          </div>
          <div className="text-xl font-black text-slate-700 mt-1.5">{healthSummary?.never_reported_count ?? 0}</div>
          <div className="text-[9px] text-slate-400 mt-0.5">Zero telemetry ingested</div>
        </div>

        <div className="p-3.5 rounded-2xl bg-white border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-red-700 uppercase tracking-wider">In Breach Alert</span>
            <AlertTriangle className="w-3.5 h-3.5 text-red-500" />
          </div>
          <div className="text-xl font-black text-red-700 mt-1.5">{stats?.sensors_in_alert ?? 0}</div>
          <div className="text-[9px] text-red-600 mt-0.5">Threshold breached</div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="p-4 rounded-2xl bg-white border border-slate-200 shadow-xs space-y-3">
        <div className="flex flex-col md:flex-row items-center justify-between gap-3">
          <div className="relative w-full md:w-80">
            <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by sensor name, location, ID..."
              className="w-full rounded-xl border border-slate-200 pl-9 pr-4 py-2 text-xs text-slate-900 focus:border-red-500 focus:outline-hidden"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2.5 w-full md:w-auto">
            {/* Health Filter */}
            <select
              value={healthFilter}
              onChange={(e) => setHealthFilter(e.target.value)}
              className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-700 bg-white font-medium focus:border-red-500"
            >
              <option value="ALL">All Health States</option>
              <option value="HEALTHY">Healthy (Fresh)</option>
              <option value="STALE">Stale (&gt; 300s)</option>
              <option value="NEVER_REPORTED">Never Reported</option>
              <option value="INACTIVE">Inactive</option>
            </select>

            {/* Type Filter */}
            <select
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value);
                setPage(1);
              }}
              className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-700 bg-white font-medium focus:border-red-500"
            >
              <option value="ALL">All Sensor Types</option>
              <option value="WATER_LEVEL">Water Level</option>
              <option value="RAINFALL">Rainfall</option>
              <option value="TEMPERATURE">Temperature</option>
              <option value="SMOKE_AIR_QUALITY">Smoke & Air Quality</option>
              <option value="AQI">AQI</option>
            </select>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-700 bg-white font-medium focus:border-red-500"
            >
              <option value="ALL">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="PAUSED">Paused</option>
              <option value="DRAFT">Draft</option>
              <option value="INACTIVE">Inactive</option>
            </select>

            {/* Alert Filter */}
            <select
              value={alertFilter}
              onChange={(e) => {
                setAlertFilter(e.target.value);
                setPage(1);
              }}
              className="rounded-xl border border-slate-200 px-3 py-2 text-xs text-slate-700 bg-white font-medium focus:border-red-500"
            >
              <option value="ALL">All Conditions</option>
              <option value="ALERT">In Alert (Breached)</option>
              <option value="NORMAL">Normal</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main View: Table View vs Sensor Network Map View */}
      {viewMode === 'map' ? (
        <div className="relative w-full h-[540px] rounded-2xl border border-slate-200 bg-white shadow-xl overflow-hidden flex flex-col">
          {/* Map Top Bar */}
          <div className="px-4 py-3 bg-slate-50/90 border-b border-slate-200/80 flex items-center justify-between z-20">
            <div className="flex items-center gap-2 font-sans text-xs font-bold text-slate-800">
              <Radio className="w-4 h-4 text-red-600" />
              <span className="font-mono text-[11px] font-extrabold uppercase text-slate-900">
                IOT SENSOR COVERAGE & TELEMETRY MAP
              </span>
              <span className="text-slate-300 hidden sm:inline">—</span>
              <span className="text-slate-500 font-mono text-[10px] hidden sm:inline">
                GOOGLE MAPS PLATFORM
              </span>
            </div>

            <div className="flex items-center gap-2">
              {/* Roadmap vs Satellite Toggle */}
              <div className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5 text-[10px] font-semibold">
                <button
                  type="button"
                  onClick={() => handleToggleMapType('roadmap')}
                  className={`flex items-center gap-1 px-2.5 py-0.5 rounded transition-all ${
                    mapType === 'roadmap'
                      ? 'bg-slate-900 text-white font-bold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Layers className="w-3 h-3" />
                  <span>Roadmap</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleToggleMapType('satellite')}
                  className={`flex items-center gap-1 px-2.5 py-0.5 rounded transition-all ${
                    mapType === 'satellite'
                      ? 'bg-blue-600 text-white font-bold'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Globe className="w-3 h-3" />
                  <span>Satellite</span>
                </button>
              </div>

              <div className="flex items-center gap-1.5 font-mono text-[11px] font-bold px-2.5 py-0.5 rounded-md border border-slate-200 bg-white text-slate-700">
                <span>{sensors.length} SENSORS</span>
              </div>
            </div>
          </div>

          {/* Map Area */}
          <div className="relative flex-1 bg-slate-100">
            <div ref={mapContainerRef} className="absolute inset-0 w-full h-full" />

            {/* Map Legend Overlay */}
            <div className="absolute bottom-4 left-4 z-10 flex flex-col gap-1.5 p-3 bg-white/95 backdrop-blur-md rounded-xl border border-slate-200 shadow-lg text-[10px] max-w-xs">
              <div className="font-bold text-slate-900 font-mono uppercase">Coverage Radius Legend</div>
              <div className="flex items-center gap-2 text-slate-600">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
                <span>Normal Active Sensor Radius</span>
              </div>
              <div className="flex items-center gap-2 text-slate-600">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-pulse" />
                <span>Threshold Breached Alert Radius</span>
              </div>
              <div className="text-[9px] text-slate-400 mt-0.5 italic">
                Circles represent authoritative observation radius in meters.
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Sensor Data Table */
        <div className="rounded-2xl bg-white border border-slate-200 shadow-xs overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-400 flex flex-col items-center gap-3">
            <RefreshCw className="w-8 h-8 animate-spin text-red-600" />
            <span className="text-xs font-bold text-slate-600">Loading IoT sensor telemetry catalog...</span>
          </div>
        ) : fetchError ? (
          <div className="p-8 text-center text-red-600 text-xs">
            <AlertTriangle className="w-8 h-8 mx-auto mb-2 text-red-500" />
            {fetchError}
          </div>
        ) : sensors.length === 0 ? (
          <OperationalEmptyState
            icon={Radio}
            title="No Sensors Configured"
            description="There are currently zero IoT sensors provisioned. Click 'Provision IoT Sensor' to register a new telemetry source."
            actionText="Provision First Sensor"
            onAction={() => setIsCreateOpen(true)}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                  <th className="py-3.5 px-4">Sensor Name & ID</th>
                  <th className="py-3.5 px-3">Type</th>
                  <th className="py-3.5 px-3">Health & Freshness</th>
                  <th className="py-3.5 px-3">Lifecycle</th>
                  <th className="py-3.5 px-3">Current Telemetry</th>
                  <th className="py-3.5 px-3">Threshold</th>
                  <th className="py-3.5 px-3">Zone / Location</th>
                  <th className="py-3.5 px-3">Condition</th>
                  <th className="py-3.5 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sensors
                  .filter((sensor) => {
                    if (healthFilter === 'ALL') return true;
                    const h = healthDetails[sensor.sensor_id];
                    return h ? h.health_state === healthFilter : true;
                  })
                  .map((sensor) => {
                    const isBreached = sensor.in_alert;
                    const hasReading = sensor.current_reading !== null && sensor.current_reading !== undefined;
                    const health = healthDetails[sensor.sensor_id];

                    return (
                      <tr key={sensor.sensor_id} className="hover:bg-slate-50/70 transition group">
                        <td className="py-3 px-4">
                          <div className="font-bold text-slate-900 group-hover:text-red-700 transition">
                            {sensor.name}
                          </div>
                          <div className="text-[10px] font-mono text-slate-400">{sensor.sensor_id}</div>
                        </td>

                        <td className="py-3 px-3">
                          <div className="flex items-center gap-1.5 font-medium text-slate-700">
                            {getTypeIcon(sensor.sensor_type)}
                            <span className="capitalize">{sensor.sensor_type.replace('_', ' ').toLowerCase()}</span>
                          </div>
                        </td>

                        <td className="py-3 px-3">
                          {getHealthBadge(health)}
                        </td>

                        <td className="py-3 px-3">
                          <div className="flex items-center gap-1.5">
                            {getStatusBadge(sensor.status)}
                            {sensor.is_streaming && (
                              <span className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-black bg-cyan-100 text-cyan-800 animate-pulse">
                                STREAM
                              </span>
                            )}
                          </div>
                        </td>

                        <td className="py-3 px-3">
                          {hasReading ? (
                            <div className={`font-mono font-bold text-xs ${isBreached ? 'text-red-600' : 'text-slate-900'}`}>
                              {sensor.current_reading} {sensor.unit}
                            </div>
                          ) : (
                            <span className="text-slate-400 italic text-[11px]">No readings</span>
                          )}
                          {sensor.last_updated && (
                            <div className="text-[9px] text-slate-400">
                              {new Date(sensor.last_updated).toLocaleTimeString()}
                            </div>
                          )}
                        </td>

                        <td className="py-3 px-3 font-mono font-medium text-slate-600">
                          &gt; {sensor.threshold} {sensor.unit}
                        </td>

                        <td className="py-3 px-3">
                          <div className="flex items-center gap-1 text-slate-700 truncate max-w-[160px]" title={sensor.location_name}>
                            <MapPin className="w-3 h-3 text-slate-400 shrink-0" />
                            <span className="truncate">{sensor.location_name}</span>
                          </div>
                          <div className="text-[10px] font-mono text-slate-400 mt-0.5">
                            Range: {((sensor.coverage?.radius_meters || 2000) / 1000).toFixed(1)} km
                          </div>
                          {sensor.linked_situation_id && (
                            <button
                              onClick={() => onInspectSituation && onInspectSituation(sensor.linked_situation_id!)}
                              className="text-[10px] text-purple-600 hover:underline flex items-center gap-0.5 mt-0.5"
                            >
                              <ExternalLink className="w-2.5 h-2.5" />
                              {sensor.linked_situation_id}
                            </button>
                          )}
                        </td>

                        <td className="py-3 px-3">
                          {isBreached ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-black bg-red-100 text-red-800 border border-red-200 animate-pulse">
                              <AlertTriangle className="w-3 h-3 text-red-600" />
                              BREACHED
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              <CheckCircle className="w-3 h-3 text-emerald-500" />
                              NORMAL
                            </span>
                          )}
                        </td>

                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Edit Sensor Action */}
                          <button
                            onClick={() => setEditingSensor(sensor)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-amber-700 hover:bg-amber-50 transition"
                            title="Edit sensor location, range, or threshold"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>

                          {/* Contextual Actions */}
                          {sensor.status === 'DRAFT' && (
                            <button
                              onClick={() => handleActivate(sensor.sensor_id)}
                              className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-bold shadow-2xs transition"
                            >
                              Activate
                            </button>
                          )}

                          {sensor.status === 'PAUSED' && (
                            <button
                              onClick={() => handleResume(sensor.sensor_id)}
                              className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-bold shadow-2xs transition"
                            >
                              Resume
                            </button>
                          )}

                          {sensor.status === 'ACTIVE' && (
                            <>
                              <button
                                onClick={() => setReadingModalSensor(sensor)}
                                className="px-2.5 py-1 rounded-lg bg-cyan-700 hover:bg-cyan-800 text-white text-[11px] font-bold shadow-2xs transition flex items-center gap-1"
                                title="Send live reading or configure stream"
                              >
                                <Send className="w-3 h-3" />
                                Transmit
                              </button>

                              <button
                                onClick={() => handlePause(sensor.sensor_id)}
                                className="p-1 rounded-lg text-slate-400 hover:text-amber-700 hover:bg-amber-50 transition"
                                title="Pause sensor"
                              >
                                <Pause className="w-3.5 h-3.5" />
                              </button>

                              <button
                                onClick={() => handleDeactivate(sensor.sensor_id)}
                                className="p-1 rounded-lg text-slate-400 hover:text-red-700 hover:bg-red-50 transition"
                                title="Deactivate sensor"
                              >
                                <Power className="w-3.5 h-3.5" />
                              </button>
                            </>
                          )}

                          <button
                            onClick={() => setSelectedSensor(sensor)}
                            className="p-1 rounded-lg text-slate-400 hover:text-slate-800 hover:bg-slate-100 transition"
                            title="View sensor telemetry history & details"
                          >
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="px-6 py-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
            <div>
              Showing page <strong>{page}</strong> of <strong>{totalPages}</strong> ({totalCount} total sensors)
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1 rounded-lg border border-slate-200 bg-white font-bold text-slate-700 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="px-3 py-1 rounded-lg border border-slate-200 bg-white font-bold text-slate-700 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
      )}

      {/* Sensor Details & Reading History Drawer */}
      {selectedSensor && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40 backdrop-blur-2xs">
          <div className="w-full max-w-xl bg-white shadow-2xl h-full flex flex-col border-l border-slate-200 overflow-hidden animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-slate-50/80">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-100 text-red-600 flex items-center justify-center font-bold">
                  <Radio className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">{selectedSensor.name}</h3>
                  <p className="text-xs text-slate-500 font-mono">{selectedSensor.sensor_id} • {selectedSensor.sensor_type}</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedSensor(null)}
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-200/60 hover:text-slate-700 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Sensor Health & Telemetry Quality Diagnostics */}
              {(() => {
                const health = healthDetails[selectedSensor.sensor_id];
                return (
                  <div className={`p-4 rounded-xl border space-y-2.5 text-xs ${
                    health?.health_state === 'HEALTHY'
                      ? 'bg-emerald-50/50 border-emerald-200'
                      : health?.health_state === 'STALE'
                      ? 'bg-amber-50/50 border-amber-300'
                      : 'bg-slate-50 border-slate-200'
                  }`}>
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-slate-700 uppercase tracking-wider text-[10px]">
                        Telemetry Freshness & Health
                      </span>
                      {getHealthBadge(health)}
                    </div>
                    <div className="grid grid-cols-2 gap-2 pt-1 border-t border-slate-200/60 text-[11px]">
                      <div>
                        <span className="text-slate-500 block">Reporting State:</span>
                        <strong className="text-slate-800 font-mono">{health?.reporting_state || 'NEVER_REPORTED'}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Telemetry Age:</span>
                        <strong className="text-slate-800">{health?.reading_age_human || 'Never reported'}</strong>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Stale Threshold:</span>
                        <span className="font-mono text-slate-700">{health?.stale_threshold_seconds || 300}s (5 min)</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">Corroboration Reliability:</span>
                        <strong className={health?.health_state === 'HEALTHY' ? 'text-emerald-700' : 'text-amber-700'}>
                          {health?.health_state === 'HEALTHY' ? '0.90 (Active/Verified)' : health?.health_state === 'STALE' ? '0.35 (Reduced / Stale)' : '0.00 (Unverified)'}
                        </strong>
                      </div>
                    </div>
                    {health?.health_state === 'STALE' && (
                      <p className="text-[10px] text-amber-800 font-medium bg-amber-100/70 p-2 rounded-lg border border-amber-200">
                        Notice: Telemetry data has exceeded the 5-minute freshness threshold. Corroboration engine discounts stale data and requires secondary citizen reports.
                      </p>
                    )}
                  </div>
                );
              })()}

              {/* Snapshot Cards */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                  <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Current Reading</div>
                  <div className={`text-lg font-black mt-1 ${selectedSensor.in_alert ? 'text-red-600' : 'text-slate-900'}`}>
                    {selectedSensor.current_reading !== null && selectedSensor.current_reading !== undefined
                      ? `${selectedSensor.current_reading} ${selectedSensor.unit}`
                      : 'No readings recorded'}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                  <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Alert Threshold</div>
                  <div className="text-lg font-black text-red-600 mt-1">
                    &gt; {selectedSensor.threshold} {selectedSensor.unit}
                  </div>
                </div>
              </div>

              {/* Status & Location Info */}
              <div className="p-4 rounded-xl border border-slate-200 space-y-2.5 text-xs bg-slate-50/50">
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Lifecycle Status:</span>
                  <div className="flex items-center gap-2">
                    {getStatusBadge(selectedSensor.status)}
                    <button
                      onClick={() => setEditingSensor(selectedSensor)}
                      className="px-2 py-0.5 rounded-md bg-amber-50 text-amber-800 border border-amber-200 text-[10px] font-bold flex items-center gap-1 hover:bg-amber-100 transition"
                    >
                      <Edit3 className="w-3 h-3" />
                      Edit Config
                    </button>
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Zone Location:</span>
                  <span className="font-bold text-slate-900">{selectedSensor.location_name}</span>
                </div>
                {selectedSensor.location?.street_address && (
                  <div className="flex justify-between items-center">
                    <span className="text-slate-500 font-medium">Street Address:</span>
                    <span className="text-slate-800">{selectedSensor.location.street_address}</span>
                  </div>
                )}
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">GPS Coordinates:</span>
                  <span className="font-mono text-slate-700">{selectedSensor.latitude.toFixed(6)}, {selectedSensor.longitude.toFixed(6)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-slate-500 font-medium">Coverage Radius:</span>
                  <span className="font-bold font-mono text-red-700">
                    {((selectedSensor.coverage?.radius_meters || 2000) / 1000).toFixed(2)} km ({selectedSensor.coverage?.radius_meters || 2000} meters)
                  </span>
                </div>
                {selectedSensor.linked_situation_id && (
                  <div className="flex justify-between items-center">
                    <span className="text-slate-500 font-medium">Linked Situation:</span>
                    <button
                      onClick={() => onInspectSituation && onInspectSituation(selectedSensor.linked_situation_id!)}
                      className="font-bold text-purple-600 hover:underline flex items-center gap-1"
                    >
                      <ExternalLink className="w-3 h-3" />
                      {selectedSensor.linked_situation_id}
                    </button>
                  </div>
                )}
              </div>

              {/* Transmit Action in Drawer */}
              {selectedSensor.status === 'ACTIVE' && (
                <button
                  onClick={() => setReadingModalSensor(selectedSensor)}
                  className="w-full py-2.5 rounded-xl bg-cyan-700 hover:bg-cyan-800 text-white text-xs font-bold shadow-xs transition flex items-center justify-center gap-2"
                >
                  <Send className="w-4 h-4" />
                  Transmit Live Reading / Stream Controls
                </button>
              )}

              {/* Genuine Persisted Reading History Table */}
              <div>
                <h4 className="text-xs font-bold text-slate-900 uppercase tracking-wider mb-2.5 flex items-center justify-between">
                  <span>Persisted Reading History</span>
                  <span className="text-[10px] font-normal text-slate-400">{selectedReadings.length} records</span>
                </h4>

                {drawerLoading ? (
                  <div className="p-6 text-center text-slate-400 text-xs flex justify-center items-center gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin text-red-600" />
                    Loading history...
                  </div>
                ) : selectedReadings.length === 0 ? (
                  <div className="p-6 rounded-xl bg-slate-50 border border-slate-200 text-center text-slate-400 text-xs">
                    No readings have been submitted for this sensor yet.
                  </div>
                ) : (
                  <div className="rounded-xl border border-slate-200 overflow-hidden">
                    <table className="w-full text-left text-[11px]">
                      <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold">
                        <tr>
                          <th className="py-2 px-3">Timestamp</th>
                          <th className="py-2 px-2">Reading</th>
                          <th className="py-2 px-2">Source</th>
                          <th className="py-2 px-3 text-right">State</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {selectedReadings.map((r) => (
                          <tr key={r.reading_id} className="hover:bg-slate-50/60">
                            <td className="py-2 px-3 text-slate-500 font-mono text-[10px]">
                              {new Date(r.timestamp).toLocaleTimeString()}
                            </td>
                            <td className="py-2 px-2 font-bold font-mono">
                              <span className={r.is_breach ? 'text-red-600' : 'text-slate-800'}>
                                {r.value} {r.unit}
                              </span>
                            </td>
                            <td className="py-2 px-2 text-slate-500 text-[10px]">
                              {r.source_type === 'LIVE_SIMULATION' ? 'Stream' : 'Manual'}
                            </td>
                            <td className="py-2 px-3 text-right">
                              {r.is_breach ? (
                                <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-red-100 text-red-800">
                                  BREACH
                                </span>
                              ) : (
                                <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-50 text-emerald-700">
                                  OK
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Threshold Alerts History */}
              {selectedAlerts.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold text-red-600 uppercase tracking-wider mb-2 flex items-center justify-between">
                    <span>Threshold Alert History</span>
                    <span className="text-[10px] font-normal text-slate-400">{selectedAlerts.length} alerts</span>
                  </h4>
                  <div className="space-y-2">
                    {selectedAlerts.map((a) => (
                      <div key={a.alert_id} className="p-3 rounded-xl border border-red-200 bg-red-50/50 text-xs space-y-1">
                        <div className="flex justify-between items-center font-bold">
                          <span className="text-red-700">{a.status}</span>
                          <span className="text-slate-500 font-mono text-[10px]">{new Date(a.created_at).toLocaleTimeString()}</span>
                        </div>
                        <p className="text-slate-700 text-[11px]">{a.message}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Provisioning Modal */}
      <CreateSensorModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSensorCreated={(newSensor) => {
          fetchSensors();
          setSelectedSensor(newSensor);
        }}
      />

      {/* Editing Modal */}
      <EditSensorModal
        isOpen={!!editingSensor}
        sensor={editingSensor}
        onClose={() => setEditingSensor(null)}
        onSensorUpdated={(updated) => {
          fetchSensors();
          if (selectedSensor && selectedSensor.sensor_id === updated.sensor_id) {
            setSelectedSensor(updated);
          }
        }}
      />

      {/* Reading / Stream Modal */}
      <SensorReadingModal
        isOpen={!!readingModalSensor}
        sensor={readingModalSensor}
        onClose={() => setReadingModalSensor(null)}
        onReadingSubmitted={() => {
          fetchSensors();
        }}
      />
    </div>
  );
};
export default SensorManagementPanel;
