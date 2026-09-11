import React, { useState, useEffect, useRef, useCallback } from 'react';
import { loadGoogleMaps, hasGoogleMapsApiKey } from '../../utils/googleMapsLoader';
import { getActiveHotspots } from '../../services/api';
import type { PublicEmergencyHotspot, SeverityLevel } from '../../types';
import { Map as MapIcon, Radio, Layers, Globe } from 'lucide-react';

const PREVIEW_LIGHT_STYLES: google.maps.MapTypeStyle[] = [
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#cce5ff' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#f8fafc' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#ffffff' }] },
  { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#e2e8f0' }] },
  { featureType: 'poi', elementType: 'geometry', stylers: [{ color: '#f1f5f9' }] },
  { featureType: 'administrative', elementType: 'labels.text.fill', stylers: [{ color: '#475569' }] },
];

export const LiveMapPreview: React.FC<{ className?: string }> = ({ className = '' }) => {
  const [hotspots, setHotspots] = useState<PublicEmergencyHotspot[]>([]);
  const [mapType, setMapType] = useState<'roadmap' | 'satellite'>('roadmap');
  const [loading, setLoading] = useState<boolean>(true);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const googleInstanceRef = useRef<typeof google | null>(null);
  const markersRef = useRef<{ [key: string]: google.maps.Marker }>({});
  const circlesRef = useRef<{ [key: string]: google.maps.Circle }>({});
  const activeInfoWindowRef = useRef<google.maps.InfoWindow | null>(null);

  const fetchHotspots = useCallback(async () => {
    try {
      const data = await getActiveHotspots();
      setHotspots(data.hotspots || []);
    } catch (err) {
      console.warn('Public live map preview could not load active hotspots:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHotspots();
    const interval = setInterval(fetchHotspots, 20000);
    return () => clearInterval(interval);
  }, [fetchHotspots]);

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

  // Helper to create anonymous hotspot pin
  const createHotspotMarkerSvg = (severity: SeverityLevel, count: number) => {
    let color = '#dc2626';
    if (severity === 'CRITICAL') color = '#dc2626';
    else if (severity === 'HIGH') color = '#ea580c';
    else if (severity === 'MEDIUM') color = '#d97706';
    else if (severity === 'LOW') color = '#2563eb';

    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="38" height="38" viewBox="0 0 38 38">
        <defs>
          <filter id="shadow-hs" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000000" flood-opacity="0.35"/>
          </filter>
        </defs>
        <circle cx="19" cy="19" r="17" fill="${color}" fill-opacity="0.22" stroke="${color}" stroke-width="1.5" stroke-dasharray="3 2"/>
        <circle cx="19" cy="19" r="13" fill="${color}" stroke="#ffffff" stroke-width="2.5" filter="url(#shadow-hs)"/>
        <text x="19" y="23" font-size="11" font-weight="900" font-family="system-ui, -apple-system, sans-serif" fill="#ffffff" text-anchor="middle">${count > 1 ? count : '!'}</text>
      </svg>
    `;
    return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
  };

  const initialCameraFittedRef = useRef<boolean>(false);
  const userHasInteractedRef = useRef<boolean>(false);

  // Initialize Map
  useEffect(() => {
    let isMounted = true;
    const initMap = async () => {
      if (!mapContainerRef.current) return;
      if (googleMapRef.current) return;
      if (!hasGoogleMapsApiKey()) return;

      try {
        const googleObj = await loadGoogleMaps();
        if (!isMounted || !mapContainerRef.current) return;

        googleInstanceRef.current = googleObj;

        const map = new googleObj.maps.Map(mapContainerRef.current, {
          center: { lat: 16.2954, lng: 80.6482 },
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

        // Track user interaction so automatic camera resets never override human choices
        map.addListener('dragstart', () => {
          userHasInteractedRef.current = true;
        });
        map.addListener('zoom_changed', () => {
          // If map has already completed initial fit, any subsequent zoom change is user-initiated
          if (initialCameraFittedRef.current) {
            userHasInteractedRef.current = true;
          }
        });

        googleMapRef.current = map;
      } catch (err) {
        console.warn('Could not initialize Google Map for preview:', err);
      }
    };

    initMap();
    return () => {
      isMounted = false;
    };
  }, []);

  // Synchronize Hotspot Markers & Circles (Data Refresh decoupled from Camera)
  useEffect(() => {
    const map = googleMapRef.current;
    const googleObj = googleInstanceRef.current;
    if (!map || !googleObj) return;

    // 1. Clear previous markers
    Object.values(markersRef.current).forEach((m) => m.setMap(null));
    markersRef.current = {};

    // 2. Clear previous circles
    Object.values(circlesRef.current).forEach((c) => c.setMap(null));
    circlesRef.current = {};

    if (activeInfoWindowRef.current) {
      activeInfoWindowRef.current.close();
    }

    if (hotspots.length === 0) return;

    const bounds = new googleObj.maps.LatLngBounds();
    let validCount = 0;

    hotspots.forEach((hs) => {
      const lat = hs.latitude;
      const lng = hs.longitude;
      if (typeof lat !== 'number' || typeof lng !== 'number' || isNaN(lat) || isNaN(lng)) return;

      bounds.extend({ lat, lng });
      validCount++;

      let sevColor = '#dc2626';
      if (hs.severity_level === 'CRITICAL') sevColor = '#dc2626';
      else if (hs.severity_level === 'HIGH') sevColor = '#ea580c';
      else if (hs.severity_level === 'MEDIUM') sevColor = '#d97706';
      else if (hs.severity_level === 'LOW') sevColor = '#2563eb';

      // Draw soft radius circle
      const radiusMeters = (hs.impact_radius_km || 1.2) * 1000;
      const circle = new googleObj.maps.Circle({
        map,
        center: { lat, lng },
        radius: radiusMeters,
        fillColor: sevColor,
        fillOpacity: 0.15,
        strokeColor: sevColor,
        strokeOpacity: 0.7,
        strokeWeight: 1.5,
      });
      circlesRef.current[hs.hotspot_id] = circle;

      // Draw anonymous marker
      const marker = new googleObj.maps.Marker({
        map,
        position: { lat, lng },
        title: `Active Emergency Hotspot - ${hs.general_area_name || 'Operational Sector'}`,
        icon: {
          url: createHotspotMarkerSvg(hs.severity_level, hs.active_incident_count),
          scaledSize: new googleObj.maps.Size(36, 36),
          anchor: new googleObj.maps.Point(18, 18),
        },
        zIndex: 50,
      });

      // Anonymous, Public-Safe Popup
      const infoContent = document.createElement('div');
      infoContent.className = 'p-3 font-sans max-w-xs';
      infoContent.innerHTML = `
        <div style="font-family: system-ui, -apple-system, sans-serif;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px;">
            <span style="font-size: 11px; font-weight: 800; color: #0f172a; font-family: monospace;">HOTSPOT ACTIVE</span>
            <span style="font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 9999px; background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5;">
              ${hs.severity_level}
            </span>
          </div>
          <h4 style="font-size: 12px; font-weight: 700; color: #0f172a; margin: 0 0 4px 0;">${hs.general_area_name || 'Operational Response Sector'}</h4>
          <p style="font-size: 11px; color: #475569; margin: 0 0 6px 0; line-height: 1.4;">
            Active emergency incidents: <strong>${hs.active_incident_count}</strong>. Response and logistics are actively coordinated through authorized dispatch teams.
          </p>
          <div style="font-size: 10px; color: #64748b; font-style: italic;">
            Public safe view • Operational details restricted
          </div>
        </div>
      `;

      const infoWindow = new googleObj.maps.InfoWindow({
        content: infoContent,
      });

      marker.addListener('click', () => {
        if (activeInfoWindowRef.current) activeInfoWindowRef.current.close();
        infoWindow.open(map, marker);
        activeInfoWindowRef.current = infoWindow;
      });

      markersRef.current[hs.hotspot_id] = marker;
    });

    // ONLY establish camera on initial genuine data setup; do NOT reset camera on subsequent data polling cycles
    if (validCount > 0 && map && !initialCameraFittedRef.current && !userHasInteractedRef.current) {
      map.fitBounds(bounds);
      if (map.getZoom() && map.getZoom()! > 14) {
        map.setZoom(14);
      }
      initialCameraFittedRef.current = true;
    }
  }, [hotspots]);

  return (
    <div
      className={`relative w-full rounded-2xl border border-slate-200/90 bg-white shadow-xl shadow-slate-200/50 overflow-hidden flex flex-col justify-between ${className}`}
    >
      {/* Top Header Bar */}
      <div className="px-4 py-3 bg-slate-50/90 border-b border-slate-200/80 flex items-center justify-between z-20">
        <div className="font-sans text-xs font-bold text-slate-800 tracking-wider flex items-center gap-2">
          <MapIcon className="w-4 h-4 text-red-600" />
          <span className="font-mono text-[11px] font-extrabold uppercase text-slate-900">
            PUBLIC SITUATIONAL MAP
          </span>
          <span className="text-slate-300 hidden sm:inline">—</span>
          <span className="text-slate-500 font-mono text-[10px] hidden sm:inline">
            GOOGLE MAPS PLATFORM
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Subtle Map Type Toggle */}
          <div className="flex items-center rounded-lg border border-slate-200 bg-white p-0.5 text-[10px] font-semibold">
            <button
              type="button"
              onClick={() => handleToggleMapType('roadmap')}
              className={`flex items-center gap-1 px-2 py-0.5 rounded transition-all ${
                mapType === 'roadmap'
                  ? 'bg-slate-900 text-white font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Layers className="w-3 h-3" />
              <span>Map</span>
            </button>
            <button
              type="button"
              onClick={() => handleToggleMapType('satellite')}
              className={`flex items-center gap-1 px-2 py-0.5 rounded transition-all ${
                mapType === 'satellite'
                  ? 'bg-blue-600 text-white font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Globe className="w-3 h-3" />
              <span>Satellite</span>
            </button>
          </div>

          <div
            className={`flex items-center gap-1.5 font-mono text-[11px] font-bold px-2.5 py-0.5 rounded-md border ${
              hotspots.length > 0
                ? 'text-red-700 bg-red-50 border-red-200'
                : 'text-emerald-700 bg-emerald-50 border-emerald-200'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                hotspots.length > 0 ? 'bg-red-500 animate-pulse' : 'bg-emerald-500'
              }`}
            />
            <span>
              {hotspots.length} ACTIVE HOTSPOT{hotspots.length === 1 ? '' : 'S'}
            </span>
          </div>
        </div>
      </div>

      {/* Map Area */}
      <div className="relative flex-1 min-h-[340px] sm:min-h-[390px] flex items-center justify-center overflow-hidden bg-slate-50">
        <div ref={mapContainerRef} className="absolute inset-0 w-full h-full" />

        {/* Honest Overlay When 0 Active Hotspots */}
        {!loading && hotspots.length === 0 && (
          <div className="absolute bottom-4 left-4 right-4 sm:left-auto sm:right-4 z-10 flex items-center gap-3 p-3.5 bg-white/95 backdrop-blur-md rounded-xl border border-slate-200 shadow-lg max-w-sm">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 flex-shrink-0">
              <Radio className="w-4 h-4" />
            </div>
            <div>
              <div className="font-mono text-[11px] font-bold uppercase text-slate-900">
                0 Active Emergency Hotspots
              </div>
              <p className="text-[11px] font-sans text-slate-600 leading-tight mt-0.5">
                No active emergency hotspots currently reported. Live citizen emergencies will appear automatically.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default LiveMapPreview;
