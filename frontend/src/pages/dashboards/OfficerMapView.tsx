import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { OperationalHeader } from '../../components/layout/OperationalHeader';
import { CommandSidebar } from '../../components/layout/CommandSidebar';
import { ReportDetailsModal } from '../../components/officer/ReportDetailsModal';
import { SituationDetailsModal } from '../../components/officer/SituationDetailsModal';
import { getOfficerMapData } from '../../services/api';
import { loadGoogleMaps, hasGoogleMapsApiKey } from '../../utils/googleMapsLoader';
import type {
  OfficerReportDetailResponse,
  SituationCluster,
  SeverityLevel,
  ResourceResponse,
  OfficerMapDataResponse,
} from '../../types';
import {
  Map as MapIcon,
  RefreshCw,
  ArrowLeft,
  Search,
  Layers,
  Globe,
  Eye,
  Maximize2,
  AlertTriangle,
  Archive,
  Radio,
  List,
  X,
} from 'lucide-react';

const EMERGENCY_LIGHT_MAP_STYLES: google.maps.MapTypeStyle[] = [
  {
    featureType: 'water',
    elementType: 'geometry',
    stylers: [{ color: '#cce5ff' }],
  },
  {
    featureType: 'landscape',
    elementType: 'geometry',
    stylers: [{ color: '#f8fafc' }],
  },
  {
    featureType: 'road',
    elementType: 'geometry',
    stylers: [{ color: '#ffffff' }],
  },
  {
    featureType: 'road.arterial',
    elementType: 'geometry',
    stylers: [{ color: '#e2e8f0' }],
  },
  {
    featureType: 'poi',
    elementType: 'geometry',
    stylers: [{ color: '#f1f5f9' }],
  },
  {
    featureType: 'administrative',
    elementType: 'labels.text.fill',
    stylers: [{ color: '#475569' }],
  },
];

export const OfficerMapView: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const targetedReportId = searchParams.get('report');

  // Partitioning View Mode: 'active' | 'history' | 'all'
  const [viewMode, setViewMode] = useState<'active' | 'history' | 'all'>('active');

  const [reports, setReports] = useState<OfficerReportDetailResponse[]>([]);
  const [situations, setSituations] = useState<SituationCluster[]>([]);
  const [shelters, setShelters] = useState<ResourceResponse[]>([]);
  const [stats, setStats] = useState<{
    activeSituations: number;
    resolvedSituations: number;
    activeReports: number;
    resolvedReports: number;
  }>({
    activeSituations: 0,
    resolvedSituations: 0,
    activeReports: 0,
    resolvedReports: 0,
  });

  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState<string>('ALL');
  const [sidebarTab, setSidebarTab] = useState<'situations' | 'reports'>('situations');

  // Map Type Selection: Roadmap vs Satellite vs Hybrid
  const [mapType, setMapType] = useState<'roadmap' | 'satellite' | 'hybrid'>('roadmap');

  // Layer Visibility Controls
  const [showIncidents, setShowIncidents] = useState<boolean>(true);
  const [showSituations, setShowSituations] = useState<boolean>(true);
  const [showImpactZones, setShowImpactZones] = useState<boolean>(true);
  const [showShelters, setShowShelters] = useState<boolean>(true);

  // Modals
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [selectedSituationId, setSelectedSituationId] = useState<string | null>(null);

  // Mobile Navigation & Drawer States
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState<boolean>(false);
  const [isMobileListOpen, setIsMobileListOpen] = useState<boolean>(false);

  // Google Maps State & Refs
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const googleInstanceRef = useRef<typeof google | null>(null);
  const incidentMarkersRef = useRef<{ [key: string]: google.maps.Marker }>({});
  const situationMarkersRef = useRef<{ [key: string]: google.maps.Marker }>({});
  const situationCirclesRef = useRef<{ [key: string]: google.maps.Circle }>({});
  const shelterMarkersRef = useRef<{ [key: string]: google.maps.Marker }>({});
  const activeInfoWindowRef = useRef<google.maps.InfoWindow | null>(null);

  const [mapLoading, setMapLoading] = useState<boolean>(true);
  const [mapError, setMapError] = useState<string | null>(null);
  const [isKeyMissing, setIsKeyMissing] = useState<boolean>(!hasGoogleMapsApiKey());

  // Helper to validate coordinates
  const hasValidCoordinates = (lat?: number, lng?: number): boolean => {
    return (
      typeof lat === 'number' &&
      typeof lng === 'number' &&
      !isNaN(lat) &&
      !isNaN(lng) &&
      lat >= -90 &&
      lat <= 90 &&
      lng >= -180 &&
      lng <= 180 &&
      !(lat === 0 && lng === 0)
    );
  };

  // Fetch operational map data partitioned by view_mode
  const fetchMapData = useCallback(async () => {
    setLoading(true);
    try {
      const data: OfficerMapDataResponse = await getOfficerMapData({
        view_mode: viewMode,
      });

      setSituations(data.situations || []);
      setReports(data.reports || []);
      setShelters(data.shelters || []);
      setStats({
        activeSituations: data.total_active_situations || 0,
        resolvedSituations: data.total_resolved_situations || 0,
        activeReports: data.total_active_reports || 0,
        resolvedReports: data.total_resolved_reports || 0,
      });
    } catch (err) {
      console.warn('Failed to load officer map data:', err);
    } finally {
      setLoading(false);
    }
  }, [viewMode]);

  useEffect(() => {
    fetchMapData();
  }, [fetchMapData]);

  // Safe 20s polling for live map updates
  useEffect(() => {
    const timer = setInterval(() => {
      fetchMapData();
    }, 20000);
    return () => clearInterval(timer);
  }, [fetchMapData]);

  // Map Type Change Handler
  const handleSetMapType = (type: 'roadmap' | 'satellite' | 'hybrid') => {
    setMapType(type);
    const map = googleMapRef.current;
    if (map) {
      map.setMapTypeId(type);
      if (type === 'roadmap') {
        map.setOptions({ styles: EMERGENCY_LIGHT_MAP_STYLES });
      } else {
        map.setOptions({ styles: [] });
      }
    }
  };

  // Explicit Recenter / Fit All Visible Markers Handler
  const handleFitAllBounds = useCallback(() => {
    const map = googleMapRef.current;
    const googleObj = googleInstanceRef.current;
    if (!map || !googleObj) return;

    const bounds = new googleObj.maps.LatLngBounds();
    let count = 0;

    if (showSituations || showImpactZones) {
      situations.forEach((sit) => {
        const lat = sit.center_location?.latitude;
        const lng = sit.center_location?.longitude;
        if (hasValidCoordinates(lat, lng)) {
          bounds.extend({ lat, lng });
          count++;
        }
      });
    }

    if (showIncidents) {
      reports.forEach((rep) => {
        const lat = rep.location?.latitude;
        const lng = rep.location?.longitude;
        if (hasValidCoordinates(lat, lng)) {
          bounds.extend({ lat, lng });
          count++;
        }
      });
    }

    if (showShelters) {
      shelters.forEach((shl) => {
        const lat = shl.location?.latitude;
        const lng = shl.location?.longitude;
        if (hasValidCoordinates(lat, lng)) {
          bounds.extend({ lat, lng });
          count++;
        }
      });
    }

    if (count > 0) {
      map.fitBounds(bounds);
      if (map.getZoom() && map.getZoom()! > 15) {
        map.setZoom(15);
      }
    } else {
      map.setCenter({ lat: 16.2954, lng: 80.6482 });
      map.setZoom(12);
    }
  }, [reports, situations, shelters, showIncidents, showSituations, showImpactZones, showShelters]);

  // Initialize Google Maps
  useEffect(() => {
    let isMounted = true;

    const initMap = async () => {
      if (!mapContainerRef.current) return;
      if (googleMapRef.current) return;

      if (!hasGoogleMapsApiKey()) {
        setIsKeyMissing(true);
        setMapLoading(false);
        setMapError('Google Maps API key is not configured.');
        return;
      }

      try {
        setMapLoading(true);
        setMapError(null);
        setIsKeyMissing(false);
        const googleObj = await loadGoogleMaps();
        if (!isMounted || !mapContainerRef.current) return;

        googleInstanceRef.current = googleObj;

        const defaultCenter = { lat: 16.2954, lng: 80.6482 };
        const map = new googleObj.maps.Map(mapContainerRef.current, {
          center: defaultCenter,
          zoom: 12,
          mapTypeId: mapType,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
          zoomControl: true,
          gestureHandling: 'greedy',
          scrollwheel: true,
          isFractionalZoomEnabled: true,
          clickableIcons: false,
          keyboardShortcuts: true,
          disableDoubleClickZoom: false,
          tilt: 0,
          controlSize: 28,
          styles: mapType === 'roadmap' ? EMERGENCY_LIGHT_MAP_STYLES : [],
        });

        googleMapRef.current = map;
        setMapLoading(false);
      } catch (err: any) {
        if (!isMounted) return;
        setMapLoading(false);
        setMapError(err?.message || 'Google Maps could not be loaded.');
      }
    };

    initMap();

    return () => {
      isMounted = false;
    };
  }, []);

  // Helper to create custom SVG incident pin data URI
  const createIncidentMarkerSvg = (priority?: string, isResolved: boolean = false) => {
    if (isResolved) {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg" width="34" height="44" viewBox="0 0 34 44">
          <defs>
            <filter id="shadow-res" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000000" flood-opacity="0.25"/>
            </filter>
          </defs>
          <path d="M17 0C7.6 0 0 7.6 0 17c0 12.5 17 27 17 27s17-14.5 17-27C34 7.6 26.4 0 17 0z" fill="#64748b" filter="url(#shadow-res)"/>
          <circle cx="17" cy="17" r="13" fill="#ffffff"/>
          <path d="M12 17l3 3 7-7" stroke="#64748b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
        </svg>
      `;
      return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
    }

    let color = '#dc2626';
    if (priority === 'CRITICAL') color = '#dc2626';
    else if (priority === 'HIGH') color = '#ea580c';
    else if (priority === 'MEDIUM') color = '#d97706';
    else if (priority === 'LOW') color = '#2563eb';

    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="36" height="46" viewBox="0 0 36 46">
        <defs>
          <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#000000" flood-opacity="0.3"/>
          </filter>
        </defs>
        <path d="M18 0C8.059 0 0 8.059 0 18c0 13.5 18 28 18 28s18-14.5 18-28C36 8.059 27.941 0 18 0z" fill="${color}" filter="url(#shadow)"/>
        <circle cx="18" cy="18" r="14" fill="#ffffff"/>
        <circle cx="18" cy="18" r="10" fill="${color}"/>
      </svg>
    `;
    return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
  };

  const createSituationClusterSvg = (level: SeverityLevel, score: number, isResolved: boolean = false) => {
    if (isResolved) {
      const svg = `
        <svg xmlns="http://www.w3.org/2000/svg" width="46" height="46" viewBox="0 0 46 46">
          <defs>
            <filter id="shadow-sit-res" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#000000" flood-opacity="0.25"/>
            </filter>
          </defs>
          <circle cx="23" cy="23" r="21" fill="#64748b" fill-opacity="0.15" stroke="#64748b" stroke-width="2" stroke-dasharray="3 2"/>
          <circle cx="23" cy="23" r="16" fill="#64748b" stroke="#ffffff" stroke-width="2" filter="url(#shadow-sit-res)"/>
          <path d="M17 23l4 4 8-8" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
        </svg>
      `;
      return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
    }

    let color = '#dc2626';
    if (level === 'CRITICAL') color = '#dc2626';
    else if (level === 'HIGH') color = '#d97706';
    else if (level === 'MEDIUM') color = '#ca8a04';
    else if (level === 'LOW') color = '#2563eb';

    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
        <defs>
          <filter id="shadow-sit" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#000000" flood-opacity="0.35"/>
          </filter>
        </defs>
        <circle cx="24" cy="24" r="22" fill="${color}" fill-opacity="0.2" stroke="${color}" stroke-width="2" stroke-dasharray="4 2"/>
        <circle cx="24" cy="24" r="17" fill="${color}" stroke="#ffffff" stroke-width="2.5" filter="url(#shadow-sit)"/>
        <text x="24" y="28" font-size="12" font-weight="900" font-family="Arial, sans-serif" fill="#ffffff" text-anchor="middle">${score.toFixed(1)}</text>
      </svg>
    `;
    return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
  };

  const createShelterMarkerSvg = () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="36" height="46" viewBox="0 0 36 46">
        <defs>
          <filter id="shadow-shl" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#000000" flood-opacity="0.3"/>
          </filter>
        </defs>
        <path d="M18 0C8.059 0 0 8.059 0 18c0 13.5 18 28 18 28s18-14.5 18-28C36 8.059 27.941 0 18 0z" fill="#059669" filter="url(#shadow-shl)"/>
        <circle cx="18" cy="18" r="14" fill="#ffffff"/>
        <path d="M18 10L10 17v8h5v-5h6v5h5v-8z" fill="#059669"/>
      </svg>
    `;
    return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
  };

  // Synchronize Markers and Circles with Google Map
  useEffect(() => {
    const map = googleMapRef.current;
    const googleObj = googleInstanceRef.current;
    if (!map || !googleObj) return;

    // 1. Clear existing incident markers
    Object.values(incidentMarkersRef.current).forEach((m) => m.setMap(null));
    incidentMarkersRef.current = {};

    // 2. Clear existing situation markers and circles
    Object.values(situationMarkersRef.current).forEach((m) => m.setMap(null));
    situationMarkersRef.current = {};

    Object.values(situationCirclesRef.current).forEach((c) => c.setMap(null));
    situationCirclesRef.current = {};

    // 3. Clear existing shelter markers
    Object.values(shelterMarkersRef.current).forEach((m) => m.setMap(null));
    shelterMarkersRef.current = {};

    if (activeInfoWindowRef.current) {
      activeInfoWindowRef.current.close();
    }

    const bounds = new googleObj.maps.LatLngBounds();
    let validCount = 0;

    // 4. Render Situation Clusters & Impact Zones
    if (showSituations || showImpactZones) {
      situations.forEach((sit) => {
        const lat = sit.center_location?.latitude;
        const lng = sit.center_location?.longitude;
        if (!hasValidCoordinates(lat, lng)) return;

        bounds.extend({ lat, lng });
        validCount++;

        const isSitResolved = sit.status === 'RESOLVED' || sit.status === 'CLOSED';

        // Draw Impact Radius Zone (Only for active situations or in all mode if enabled)
        if (showImpactZones && !isSitResolved) {
          const radiusMeters = (sit.impact_zone?.radius_km || 1.5) * 1000;
          let circleColor = '#dc2626';
          if (sit.severity_level === 'HIGH') circleColor = '#d97706';
          else if (sit.severity_level === 'MEDIUM') circleColor = '#ca8a04';
          else if (sit.severity_level === 'LOW') circleColor = '#2563eb';

          const circle = new googleObj.maps.Circle({
            map,
            center: { lat, lng },
            radius: radiusMeters,
            fillColor: circleColor,
            fillOpacity: 0.14,
            strokeColor: circleColor,
            strokeOpacity: 0.85,
            strokeWeight: 1.5,
          });
          situationCirclesRef.current[sit.situation_id] = circle;
        }

        // Draw Centroid Situation Marker
        if (showSituations) {
          const sitMarker = new googleObj.maps.Marker({
            map,
            position: { lat, lng },
            title: `${sit.title} (${sit.status})`,
            icon: {
              url: createSituationClusterSvg(sit.severity_level, sit.severity_score, isSitResolved),
              scaledSize: new googleObj.maps.Size(44, 44),
              anchor: new googleObj.maps.Point(22, 22),
            },
            zIndex: isSitResolved ? 40 : 100,
          });

          const infoContent = document.createElement('div');
          infoContent.className = 'p-3 font-sans max-w-xs';
          infoContent.innerHTML = `
            <div style="font-family: system-ui, -apple-system, sans-serif;">
              <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px;">
                <span style="font-size: 11px; font-weight: 800; color: #0f172a; font-family: monospace;">${sit.situation_id}</span>
                <span style="font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 9999px; ${
                  isSitResolved
                    ? 'background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1;'
                    : 'background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;'
                }">
                  ${isSitResolved ? 'RESOLVED ARCHIVE' : `${sit.severity_level} • ${sit.severity_score.toFixed(1)}/10`}
                </span>
              </div>
              <h4 style="font-size: 13px; font-weight: 700; color: #0f172a; margin: 0 0 6px 0; line-height: 1.3;">${sit.title}</h4>
              <p style="font-size: 11px; color: #475569; margin: 0 0 8px 0; line-height: 1.4;">${sit.situation_summary}</p>
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 11px; background: #f8fafc; padding: 6px 8px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e2e8f0;">
                <div><span style="color: #64748b; font-size: 10px;">Impact Radius:</span><br/><strong>~${sit.impact_zone?.radius_km || 1.5} km</strong></div>
                <div><span style="color: #64748b; font-size: 10px;">Fused Reports:</span><br/><strong>${sit.report_count} Reports</strong></div>
              </div>
              <button id="btn-inspect-sit-${sit.situation_id}" style="width: 100%; padding: 6px 12px; font-size: 11px; font-weight: 700; color: #ffffff; background: #2563eb; border: none; border-radius: 6px; cursor: pointer;">
                Inspect Situation Intelligence
              </button>
            </div>
          `;

          const infoWindow = new googleObj.maps.InfoWindow({
            content: infoContent,
          });

          googleObj.maps.event.addListener(infoWindow, 'domready', () => {
            const btn = document.getElementById(`btn-inspect-sit-${sit.situation_id}`);
            if (btn) {
              btn.onclick = () => setSelectedSituationId(sit.situation_id);
            }
          });

          sitMarker.addListener('click', () => {
            if (activeInfoWindowRef.current) activeInfoWindowRef.current.close();
            infoWindow.open(map, sitMarker);
            activeInfoWindowRef.current = infoWindow;
          });

          situationMarkersRef.current[sit.situation_id] = sitMarker;
        }
      });
    }

    // 5. Render Citizen Incident Markers
    if (showIncidents) {
      reports.forEach((rep) => {
        const lat = rep.location?.latitude;
        const lng = rep.location?.longitude;
        if (!hasValidCoordinates(lat, lng)) return;

        bounds.extend({ lat, lng });
        validCount++;

        const isRepResolved = rep.status === 'RESOLVED';

        const incMarker = new googleObj.maps.Marker({
          map,
          position: { lat, lng },
          title: `${rep.emergency_type} - ${rep.report_id} (${rep.status})`,
          icon: {
            url: createIncidentMarkerSvg(rep.priority, isRepResolved),
            scaledSize: new googleObj.maps.Size(32, 40),
            anchor: new googleObj.maps.Point(16, 40),
          },
          zIndex: isRepResolved ? 30 : 50,
        });

        const infoContent = document.createElement('div');
        infoContent.className = 'p-3 font-sans max-w-xs';
        infoContent.innerHTML = `
          <div style="font-family: system-ui, -apple-system, sans-serif;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px;">
              <span style="font-size: 11px; font-weight: 800; color: #0f172a; font-family: monospace;">${rep.report_id}</span>
              <span style="font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 9999px; ${
                isRepResolved
                  ? 'background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1;'
                  : 'background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;'
              }">
                ${isRepResolved ? 'RESOLVED' : rep.status}
              </span>
            </div>
            <h4 style="font-size: 13px; font-weight: 700; color: #0f172a; margin: 0 0 4px 0;">${rep.emergency_type}</h4>
            <p style="font-size: 11px; color: #475569; margin: 0 0 8px 0; line-height: 1.4;">${rep.description}</p>
            <div style="font-size: 11px; background: #f8fafc; padding: 6px 8px; border-radius: 6px; margin-bottom: 8px; border: 1px solid #e2e8f0;">
              <div><span style="color: #64748b; font-size: 10px;">Reporter:</span> <strong>${rep.citizen_name}</strong></div>
              <div><span style="color: #64748b; font-size: 10px;">Location:</span> <strong>${rep.location?.address || 'Operational Sector'}</strong></div>
            </div>
            <button id="btn-inspect-rep-${rep.report_id}" style="width: 100%; padding: 6px 12px; font-size: 11px; font-weight: 700; color: #ffffff; background: #dc2626; border: none; border-radius: 6px; cursor: pointer;">
              Open Incident Record
            </button>
          </div>
        `;

        const infoWindow = new googleObj.maps.InfoWindow({
          content: infoContent,
        });

        googleObj.maps.event.addListener(infoWindow, 'domready', () => {
          const btn = document.getElementById(`btn-inspect-rep-${rep.report_id}`);
          if (btn) {
            btn.onclick = () => setSelectedReportId(rep.report_id);
          }
        });

        incMarker.addListener('click', () => {
          if (activeInfoWindowRef.current) activeInfoWindowRef.current.close();
          infoWindow.open(map, incMarker);
          activeInfoWindowRef.current = infoWindow;
        });

        incidentMarkersRef.current[rep.report_id] = incMarker;
      });
    }

    // 6. Render Shelters Layer
    if (showShelters) {
      shelters.forEach((shl) => {
        const lat = shl.location?.latitude;
        const lng = shl.location?.longitude;
        if (!hasValidCoordinates(lat, lng)) return;

        const shlMarker = new googleObj.maps.Marker({
          map,
          position: { lat, lng },
          title: `Shelter: ${shl.name}`,
          icon: {
            url: createShelterMarkerSvg(),
            scaledSize: new googleObj.maps.Size(32, 40),
            anchor: new googleObj.maps.Point(16, 40),
          },
          zIndex: 20,
        });

        const infoContent = document.createElement('div');
        infoContent.className = 'p-3 font-sans max-w-xs';
        infoContent.innerHTML = `
          <div style="font-family: system-ui, -apple-system, sans-serif;">
            <div style="font-size: 10px; font-weight: 800; color: #047857; text-transform: uppercase;">Shelter Facility</div>
            <h4 style="font-size: 13px; font-weight: 700; color: #0f172a; margin: 2px 0 4px 0;">${shl.name}</h4>
            <p style="font-size: 11px; color: #475569; margin: 0 0 6px 0;">Capacity: ${shl.quantity_total || shl.quantity_available || (shl as any).quantity || 0} ${shl.unit || 'spaces'}</p>
            <div style="font-size: 10px; color: #64748b;">${shl.location?.address || 'Operational Zone'}</div>
          </div>
        `;

        const infoWindow = new googleObj.maps.InfoWindow({ content: infoContent });
        shlMarker.addListener('click', () => {
          if (activeInfoWindowRef.current) activeInfoWindowRef.current.close();
          infoWindow.open(map, shlMarker);
          activeInfoWindowRef.current = infoWindow;
        });

        shelterMarkersRef.current[shl.resource_id || (shl as any).id] = shlMarker;
      });
    }
  }, [situations, reports, shelters, showSituations, showImpactZones, showIncidents, showShelters]);

  // Handle targeting from URL search param
  useEffect(() => {
    if (targetedReportId && reports.length > 0) {
      const rep = reports.find((r) => r.report_id === targetedReportId);
      if (rep && rep.location?.latitude && rep.location?.longitude) {
        if (googleMapRef.current) {
          googleMapRef.current.panTo({ lat: rep.location.latitude, lng: rep.location.longitude });
          googleMapRef.current.setZoom(15);
        }
        setSelectedReportId(targetedReportId);
      }
    }
  }, [targetedReportId, reports]);

  const handlePanToSituation = (sit: SituationCluster) => {
    setIsMobileListOpen(false);
    const lat = sit.center_location?.latitude;
    const lng = sit.center_location?.longitude;
    if (hasValidCoordinates(lat, lng) && googleMapRef.current) {
      googleMapRef.current.panTo({ lat, lng });
      googleMapRef.current.setZoom(14);
      const marker = situationMarkersRef.current[sit.situation_id];
      if (marker && googleInstanceRef.current) {
        googleInstanceRef.current.maps.event.trigger(marker, 'click');
      }
    }
  };

  const handlePanToReport = (rep: OfficerReportDetailResponse) => {
    setIsMobileListOpen(false);
    const lat = rep.location?.latitude;
    const lng = rep.location?.longitude;
    if (hasValidCoordinates(lat, lng) && googleMapRef.current) {
      googleMapRef.current.panTo({ lat, lng });
      googleMapRef.current.setZoom(15);
      const marker = incidentMarkersRef.current[rep.report_id];
      if (marker && googleInstanceRef.current) {
        googleInstanceRef.current.maps.event.trigger(marker, 'click');
      }
    }
  };

  // Filtered lists for sidebar
  const filteredSituations = situations.filter((sit) => {
    if (selectedType !== 'ALL' && sit.emergency_type !== selectedType) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        sit.title.toLowerCase().includes(q) ||
        sit.situation_id.toLowerCase().includes(q) ||
        (sit.center_location?.city && sit.center_location.city.toLowerCase().includes(q)) ||
        (sit.center_location?.zone_or_district && sit.center_location.zone_or_district.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const filteredReports = reports.filter((rep) => {
    if (selectedType !== 'ALL' && rep.emergency_type !== selectedType) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        rep.report_id.toLowerCase().includes(q) ||
        rep.emergency_type.toLowerCase().includes(q) ||
        rep.description.toLowerCase().includes(q) ||
        (rep.location?.address && rep.location.address.toLowerCase().includes(q))
      );
    }
    return true;
  });

  return (
    <div className="relative h-screen max-h-screen bg-[#EEF2F6] flex flex-col font-sans overflow-hidden">
      <TacticalBackground />

      <div className="flex-shrink-0 z-20">
        <OperationalHeader
          portalTitle="GIS COMMAND MAP"
          portalSubtitle="Google Maps Operational GIS • Real-Time Spatial Command & Resolution Tracking"
          onToggleMobileMenu={() => setIsMobileSidebarOpen(true)}
        />
      </div>

      {/* Main Layout Body */}
      <div className="flex-1 flex overflow-hidden min-h-0 z-10">
        {/* Command Sidebar */}
        <CommandSidebar
          role="EMERGENCY_OFFICER"
          activeTab="live-map"
          isOpenMobile={isMobileSidebarOpen}
          onCloseMobile={() => setIsMobileSidebarOpen(false)}
          onSelectTab={(tabId) => {
            setIsMobileSidebarOpen(false);
            if (tabId === 'command-center' || tabId === 'reports' || tabId === 'incidents') {
              navigate('/operations/officer');
            } else {
              navigate(`/command-center?tab=${tabId}`);
            }
          }}
          className="hidden md:flex flex-shrink-0 w-64 h-full overflow-y-auto border-r border-slate-200/80 bg-white"
        />

        {/* Viewport Area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Top GIS Action Toolbar */}
          <div className="bg-white border-b border-slate-200 px-3 sm:px-4 py-2 sm:py-2.5 flex flex-wrap items-center justify-between gap-2 sm:gap-3 shadow-xs">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              <button
                onClick={() => navigate('/operations/officer')}
                className="p-1.5 min-h-[36px] rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 flex items-center gap-1 text-xs font-semibold"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Console</span>
              </button>
              <div className="hidden sm:block h-4 w-px bg-slate-200" />
              <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800">
                <MapIcon className="w-4 h-4 text-red-600" />
                <span className="hidden xs:inline">Operational GIS Map</span>
              </div>

              {/* Mobile Entities Toggle Button */}
              <button
                type="button"
                onClick={() => setIsMobileListOpen(!isMobileListOpen)}
                className="md:hidden flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-blue-200 bg-blue-50 text-blue-800 text-xs font-bold shadow-2xs"
              >
                <List className="w-3.5 h-3.5 text-blue-600" />
                <span>{sidebarTab === 'situations' ? `Situations (${situations.length})` : `Reports (${reports.length})`}</span>
              </button>

              {/* View Mode Filter Tabs (Active vs History vs All) */}
              <div className="flex items-center rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs font-bold shadow-2xs overflow-x-auto no-scrollbar">
                <button
                  type="button"
                  onClick={() => setViewMode('active')}
                  className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-md transition-all whitespace-nowrap ${
                    viewMode === 'active'
                      ? 'bg-red-600 text-white shadow-xs font-black'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
                  }`}
                >
                  <Radio className="w-3 h-3" />
                  <span>LIVE ACTIVE ({stats.activeSituations + stats.activeReports})</span>
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode('history')}
                  className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-md transition-all whitespace-nowrap ${
                    viewMode === 'history'
                      ? 'bg-slate-800 text-white shadow-xs font-black'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
                  }`}
                >
                  <Archive className="w-3 h-3" />
                  <span>RESOLVED ({stats.resolvedSituations + stats.resolvedReports})</span>
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode('all')}
                  className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-md transition-all whitespace-nowrap ${
                    viewMode === 'all'
                      ? 'bg-blue-600 text-white shadow-xs font-black'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
                  }`}
                >
                  <Layers className="w-3 h-3" />
                  <span>ALL</span>
                </button>
              </div>
            </div>

            {/* Map View Switcher: Roadmap vs Satellite vs Hybrid */}
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
              <div className="flex items-center rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs font-semibold shadow-2xs">
                <button
                  type="button"
                  onClick={() => handleSetMapType('roadmap')}
                  className={`flex items-center gap-1 px-2 sm:px-2.5 py-1 rounded-md transition-all ${
                    mapType === 'roadmap'
                      ? 'bg-white text-slate-900 shadow-xs font-bold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
                  }`}
                  title="Standard Roadmap View"
                >
                  <Layers className="w-3.5 h-3.5 text-slate-600" />
                  <span className="hidden xs:inline">Roadmap</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleSetMapType('satellite')}
                  className={`flex items-center gap-1 px-2 sm:px-2.5 py-1 rounded-md transition-all ${
                    mapType === 'satellite'
                      ? 'bg-white text-blue-900 shadow-xs font-bold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
                  }`}
                  title="Google Satellite Imagery"
                >
                  <Globe className="w-3.5 h-3.5 text-blue-600" />
                  <span className="hidden xs:inline">Satellite</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleSetMapType('hybrid')}
                  className={`flex items-center gap-1 px-2 sm:px-2.5 py-1 rounded-md transition-all ${
                    mapType === 'hybrid'
                      ? 'bg-white text-emerald-900 shadow-xs font-bold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/50'
                  }`}
                  title="Google Satellite Imagery with Road Labels"
                >
                  <Eye className="w-3.5 h-3.5 text-emerald-600" />
                  <span className="hidden xs:inline">Hybrid</span>
                </button>
              </div>

              {/* Recenter / Fit All Button */}
              <button
                type="button"
                onClick={handleFitAllBounds}
                title="Fit All Visible Entities into View"
                className="flex items-center gap-1 px-2 sm:px-2.5 py-1 text-xs font-semibold rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-2xs transition-all"
              >
                <Maximize2 className="w-3.5 h-3.5" />
                <span>Fit All</span>
              </button>

              {/* Manual Refresh Button */}
              <button
                onClick={fetchMapData}
                disabled={loading}
                title="Refresh Map Data"
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700"
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Map & Live Entities Content */}
          <div className="flex-1 flex overflow-hidden relative">
            {/* Operational Drawer / Entities List (Responsive: Full drawer on mobile, sidebar on desktop) */}
            <div className={`${isMobileListOpen ? 'fixed inset-x-0 bottom-0 top-[110px] z-30 flex' : 'hidden'} md:flex md:static md:w-80 w-full bg-white border-r border-slate-200 flex-col flex-shrink-0 shadow-lg md:shadow-none`}>
              {/* Drawer Header & Tabs */}
              <div className="p-3 border-b border-slate-200 space-y-2.5 bg-slate-50">
                <div className="flex items-center justify-between md:hidden pb-1 border-b border-slate-200">
                  <span className="text-xs font-bold text-slate-700">Active Operational Map Entities</span>
                  <button
                    onClick={() => setIsMobileListOpen(false)}
                    className="p-1 rounded-md text-slate-500 hover:bg-slate-200"
                    aria-label="Close entity list"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  <button
                    onClick={() => setSidebarTab('situations')}
                    className={`py-1.5 text-xs font-bold rounded-lg transition-all ${
                      sidebarTab === 'situations'
                        ? 'bg-blue-600 text-white shadow-xs'
                        : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
                    }`}
                  >
                    Situations ({situations.length})
                  </button>
                  <button
                    onClick={() => setSidebarTab('reports')}
                    className={`py-1.5 text-xs font-bold rounded-lg transition-all ${
                      sidebarTab === 'reports'
                        ? 'bg-slate-900 text-white shadow-xs'
                        : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
                    }`}
                  >
                    Reports ({reports.length})
                  </button>
                </div>

                {/* Filter & Search Box */}
                <div className="space-y-1.5">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
                    <input
                      type="text"
                      placeholder="Filter map entities..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                  <select
                    value={selectedType}
                    onChange={(e) => setSelectedType(e.target.value)}
                    className="w-full px-2.5 py-1 text-[11px] font-semibold rounded-lg border border-slate-200 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="ALL">All Hazard / Emergency Types</option>
                    <option value="Flood">Flood</option>
                    <option value="Fire">Fire</option>
                    <option value="Medical Emergency">Medical Emergency</option>
                    <option value="Road Accident">Road Accident</option>
                    <option value="Cyclone / Storm">Cyclone / Storm</option>
                    <option value="Landslide">Landslide</option>
                    <option value="Building Collapse">Building Collapse</option>
                    <option value="Missing / Trapped Person">Missing / Trapped Person</option>
                    <option value="Other">Other</option>
                  </select>
                </div>
              </div>

              {/* Items List */}
              <div className="flex-1 overflow-y-auto p-2.5 space-y-2 touch-scroll">
                {sidebarTab === 'situations' ? (
                  filteredSituations.length > 0 ? (
                    filteredSituations.map((sit) => {
                      const isSitResolved = sit.status === 'RESOLVED' || sit.status === 'CLOSED';
                      return (
                        <div
                          key={sit.situation_id}
                          onClick={() => handlePanToSituation(sit)}
                          className={`p-3 rounded-xl border transition-all cursor-pointer shadow-2xs space-y-1.5 group ${
                            isSitResolved
                              ? 'bg-slate-50/80 border-slate-200 hover:border-slate-300'
                              : 'bg-white border-slate-200 hover:border-blue-300 hover:bg-blue-50/50'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1">
                            <span className="text-xs font-bold text-slate-900 font-mono">
                              {sit.situation_id}
                            </span>
                            <span
                              className={`text-[10px] font-bold px-2 py-0.2 rounded-full border ${
                                isSitResolved
                                  ? 'bg-slate-100 text-slate-600 border-slate-300'
                                  : sit.severity_level === 'CRITICAL'
                                  ? 'bg-red-50 text-red-700 border-red-200'
                                  : sit.severity_level === 'HIGH'
                                  ? 'bg-amber-50 text-amber-700 border-amber-200'
                                  : 'bg-blue-50 text-blue-700 border-blue-200'
                              }`}
                            >
                              {isSitResolved ? 'RESOLVED' : `${sit.severity_level} • ${sit.severity_score.toFixed(1)}`}
                            </span>
                          </div>
                          <h4 className="text-xs font-bold text-slate-800 line-clamp-1 group-hover:text-blue-700">
                            {sit.title}
                          </h4>
                          <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-100">
                            <span>~{sit.impact_zone?.radius_km || 1.5} km radius</span>
                            <span>{sit.report_count} Reports</span>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="py-12 text-center text-slate-400 text-xs">
                      {viewMode === 'active'
                        ? 'Zero active situation clusters. Map is clear.'
                        : 'No matching situation clusters on map.'}
                    </div>
                  )
                ) : filteredReports.length > 0 ? (
                  filteredReports.map((rep) => {
                    const isRepResolved = rep.status === 'RESOLVED';
                    return (
                      <div
                        key={rep.report_id}
                        onClick={() => handlePanToReport(rep)}
                        className={`p-3 rounded-xl border transition-all cursor-pointer shadow-2xs space-y-1 group ${
                          isRepResolved
                            ? 'bg-slate-50/80 border-slate-200 hover:border-slate-300'
                            : 'bg-white border-slate-200 hover:border-red-300 hover:bg-red-50/40'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1">
                          <span className="text-xs font-bold text-slate-900 font-mono">
                            {rep.report_id}
                          </span>
                          <span
                            className={`text-[10px] font-bold px-2 py-0.2 rounded border ${
                              isRepResolved
                                ? 'bg-slate-100 text-slate-600 border-slate-300'
                                : rep.priority === 'CRITICAL'
                                ? 'bg-red-50 text-red-700 border-red-200'
                                : 'bg-slate-100 text-slate-700 border-slate-200'
                            }`}
                          >
                            {isRepResolved ? 'RESOLVED' : rep.priority || 'UNASSESSED'}
                          </span>
                        </div>
                        <div className="text-xs font-semibold text-slate-800">{rep.emergency_type}</div>
                        <p className="text-[11px] text-slate-500 truncate">{rep.description}</p>
                      </div>
                    );
                  })
                ) : (
                  <div className="py-12 text-center text-slate-400 text-xs">
                    {viewMode === 'active'
                      ? 'Zero active reports on map. All incidents resolved.'
                      : 'No matching citizen reports on map.'}
                  </div>
                )}
              </div>
            </div>

            {/* Map Canvas & Dynamic States */}
            <div className="flex-1 relative flex flex-col overflow-hidden bg-slate-100">
              <div ref={mapContainerRef} className="w-full h-full" />

              {/* State A: Missing API Key */}
              {isKeyMissing && (
                <div className="absolute inset-0 z-20 flex flex-col items-center justify-center p-6 bg-slate-900/60 backdrop-blur-xs text-center">
                  <div className="max-w-md bg-white p-6 rounded-2xl border border-slate-200 shadow-2xl space-y-4">
                    <div className="w-12 h-12 rounded-xl bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center mx-auto">
                      <AlertTriangle className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-slate-900">Google Maps API Key Missing</h3>
                      <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                        Configure <code className="px-1.5 py-0.5 rounded bg-slate-100 font-mono text-red-600">VITE_GOOGLE_MAPS_API_KEY</code> in <code className="font-mono">frontend/.env</code> to activate Google Maps GIS imagery and real-time spatial overlays.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* State B: Map Error */}
              {!isKeyMissing && mapError && (
                <div className="absolute inset-0 z-20 flex flex-col items-center justify-center p-6 bg-slate-900/60 backdrop-blur-xs text-center">
                  <div className="max-w-md bg-white p-6 rounded-2xl border border-red-200 shadow-2xl space-y-4">
                    <div className="w-12 h-12 rounded-xl bg-red-50 border border-red-200 text-red-600 flex items-center justify-center mx-auto">
                      <AlertTriangle className="w-6 h-6" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-slate-900">Geospatial Platform Error</h3>
                      <p className="text-xs text-slate-600 mt-1 leading-relaxed">{mapError}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* State C: Map Loading */}
              {!isKeyMissing && !mapError && mapLoading && (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-100/70 backdrop-blur-xs">
                  <div className="flex items-center gap-2 px-4 py-2 bg-white rounded-xl shadow-md border border-slate-200 text-xs font-semibold text-slate-700">
                    <RefreshCw className="w-4 h-4 text-red-600 animate-spin" />
                    <span>Initializing Geospatial Engine...</span>
                  </div>
                </div>
              )}

              {/* Active Map Layer Control Pills (Floating bottom-right) */}
              <div className="absolute bottom-3 right-3 sm:bottom-4 sm:right-4 z-10 max-w-[calc(100vw-1.5rem)] flex flex-wrap items-center justify-end gap-1.5 bg-white/95 backdrop-blur-md p-1.5 rounded-xl border border-slate-200 shadow-lg text-xs font-semibold">
                <button
                  type="button"
                  onClick={() => setShowSituations(!showSituations)}
                  className={`min-h-[32px] px-2.5 py-1 rounded-lg transition-all ${
                    showSituations
                      ? 'bg-blue-600 text-white font-bold shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  Situations ({situations.length})
                </button>
                <button
                  type="button"
                  onClick={() => setShowImpactZones(!showImpactZones)}
                  className={`min-h-[32px] px-2.5 py-1 rounded-lg transition-all ${
                    showImpactZones
                      ? 'bg-red-600 text-white font-bold shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  Impact Zones
                </button>
                <button
                  type="button"
                  onClick={() => setShowIncidents(!showIncidents)}
                  className={`min-h-[32px] px-2.5 py-1 rounded-lg transition-all ${
                    showIncidents
                      ? 'bg-amber-600 text-white font-bold shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  Incidents ({reports.length})
                </button>
                <button
                  type="button"
                  onClick={() => setShowShelters(!showShelters)}
                  className={`min-h-[32px] px-2.5 py-1 rounded-lg transition-all ${
                    showShelters
                      ? 'bg-emerald-600 text-white font-bold shadow-xs'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  Shelters ({shelters.length})
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Situation Details Modal */}
      {selectedSituationId && (
        <SituationDetailsModal
          situationId={selectedSituationId}
          onClose={() => setSelectedSituationId(null)}
          onSituationUpdated={fetchMapData}
        />
      )}

      {/* Report Details Modal */}
      {selectedReportId && (
        <ReportDetailsModal
          reportId={selectedReportId}
          onClose={() => setSelectedReportId(null)}
          onReportUpdated={fetchMapData}
        />
      )}
    </div>
  );
};

export default OfficerMapView;
