import React, { useState, useEffect, useRef } from 'react';
import { MapPin, Navigation, Compass } from 'lucide-react';
import { loadGoogleMaps, hasGoogleMapsApiKey } from '../../utils/googleMapsLoader';
import type { SensorLocation, SensorCoverage } from '../../types';

interface SensorLocationCoveragePickerProps {
  location: SensorLocation;
  coverage: SensorCoverage;
  locationName: string;
  onLocationChange: (location: SensorLocation) => void;
  onCoverageChange: (coverage: SensorCoverage) => void;
  onLocationNameChange: (name: string) => void;
  disabled?: boolean;
}

const PREVIEW_LIGHT_STYLES: google.maps.MapTypeStyle[] = [
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#cce5ff' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#f8fafc' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#ffffff' }] },
  { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#e2e8f0' }] },
  { featureType: 'poi', elementType: 'geometry', stylers: [{ color: '#f1f5f9' }] },
  { featureType: 'administrative', elementType: 'labels.text.fill', stylers: [{ color: '#475569' }] },
];

export const SensorLocationCoveragePicker: React.FC<SensorLocationCoveragePickerProps> = ({
  location,
  coverage,
  locationName,
  onLocationChange,
  onCoverageChange,
  onLocationNameChange,
  disabled = false,
}) => {
  const [mapType, setMapType] = useState<'roadmap' | 'satellite'>('roadmap');
  const [showAdvancedAddress, setShowAdvancedAddress] = useState<boolean>(false);

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const googleObjRef = useRef<typeof google | null>(null);
  const markerRef = useRef<google.maps.Marker | null>(null);
  const circleRef = useRef<google.maps.Circle | null>(null);

  // Unit and display value management
  const [radiusValue, setRadiusValue] = useState<number | ''>(
    coverage.display_value !== undefined && coverage.display_value !== null
      ? coverage.display_value
      : coverage.radius_meters >= 1000
      ? coverage.radius_meters / 1000
      : coverage.radius_meters || 2
  );
  const [radiusUnit, setRadiusUnit] = useState<'km' | 'm'>(
    (coverage.display_unit?.toLowerCase() === 'm' || coverage.display_unit?.toLowerCase() === 'meters') ? 'm' : 'km'
  );

  // Helper to generate SVG Sensor Marker
  const createSensorPinSvg = () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44">
        <defs>
          <filter id="shadow-sns" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#000000" flood-opacity="0.4"/>
          </filter>
        </defs>
        <circle cx="22" cy="22" r="20" fill="#dc2626" fill-opacity="0.25" stroke="#dc2626" stroke-width="2" stroke-dasharray="3 2"/>
        <circle cx="22" cy="22" r="14" fill="#dc2626" stroke="#ffffff" stroke-width="3" filter="url(#shadow-sns)"/>
        <circle cx="22" cy="22" r="5" fill="#ffffff"/>
      </svg>
    `;
    return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
  };

  // Sync radius changes back to parent
  const handleRadiusChange = (newVal: number | '', newUnit: 'km' | 'm') => {
    setRadiusValue(newVal);
    setRadiusUnit(newUnit);
    if (typeof newVal === 'number' && !isNaN(newVal) && newVal > 0) {
      const radiusMeters = newUnit === 'km' ? newVal * 1000 : newVal;
      onCoverageChange({
        radius_meters: radiusMeters,
        display_value: newVal,
        display_unit: newUnit,
      });
    }
  };

  // Update map coordinates on manual input
  const handleCoordinateChange = (latVal: number | '', lngVal: number | '') => {
    const newLat = latVal === '' ? location.latitude : Number(latVal);
    const newLng = lngVal === '' ? location.longitude : Number(lngVal);

    onLocationChange({
      ...location,
      latitude: newLat,
      longitude: newLng,
    });

    if (googleMapRef.current && markerRef.current && circleRef.current && !isNaN(newLat) && !isNaN(newLng)) {
      const newPos = { lat: newLat, lng: newLng };
      markerRef.current.setPosition(newPos);
      circleRef.current.setCenter(newPos);
      googleMapRef.current.panTo(newPos);
    }
  };

  // Initialize Interactive Map
  useEffect(() => {
    let isMounted = true;

    const initMap = async () => {
      if (!mapContainerRef.current) return;
      if (googleMapRef.current) return;
      if (!hasGoogleMapsApiKey()) return;

      try {
        const googleObj = await loadGoogleMaps();
        if (!isMounted || !mapContainerRef.current) return;

        googleObjRef.current = googleObj;

        const initialLat = location.latitude || 16.5062;
        const initialLng = location.longitude || 80.6480;
        const initialRadiusMeters = coverage.radius_meters || 2000;

        const map = new googleObj.maps.Map(mapContainerRef.current, {
          center: { lat: initialLat, lng: initialLng },
          zoom: initialRadiusMeters > 5000 ? 11 : 13,
          mapTypeId: mapType,
          disableDefaultUI: true,
          zoomControl: true,
          gestureHandling: 'greedy',
          scrollwheel: true,
          clickableIcons: false,
          styles: mapType === 'roadmap' ? PREVIEW_LIGHT_STYLES : [],
        });

        googleMapRef.current = map;

        // Create Coverage Radius Circle
        const circle = new googleObj.maps.Circle({
          map,
          center: { lat: initialLat, lng: initialLng },
          radius: initialRadiusMeters,
          fillColor: '#dc2626',
          fillOpacity: 0.18,
          strokeColor: '#dc2626',
          strokeOpacity: 0.85,
          strokeWeight: 2,
        });
        circleRef.current = circle;

        // Create Draggable Sensor Marker
        const marker = new googleObj.maps.Marker({
          map,
          position: { lat: initialLat, lng: initialLng },
          draggable: !disabled,
          title: 'Sensor Station Physical Location',
          icon: {
            url: createSensorPinSvg(),
            scaledSize: new googleObj.maps.Size(40, 40),
            anchor: new googleObj.maps.Point(20, 20),
          },
          zIndex: 100,
        });
        markerRef.current = marker;

        // Click map -> move marker & circle
        map.addListener('click', (e: google.maps.MapMouseEvent) => {
          if (disabled || !e.latLng) return;
          const clickedLat = e.latLng.lat();
          const clickedLng = e.latLng.lng();

          marker.setPosition({ lat: clickedLat, lng: clickedLng });
          circle.setCenter({ lat: clickedLat, lng: clickedLng });

          onLocationChange({
            ...location,
            latitude: clickedLat,
            longitude: clickedLng,
          });
        });

        // Drag marker -> update coordinates & move circle
        marker.addListener('drag', (e: google.maps.MapMouseEvent) => {
          if (!e.latLng) return;
          const dragLat = e.latLng.lat();
          const dragLng = e.latLng.lng();
          circle.setCenter({ lat: dragLat, lng: dragLng });
        });

        marker.addListener('dragend', (e: google.maps.MapMouseEvent) => {
          if (!e.latLng) return;
          const endLat = e.latLng.lat();
          const endLng = e.latLng.lng();

          onLocationChange({
            ...location,
            latitude: endLat,
            longitude: endLng,
          });
        });

      } catch (err) {
        console.warn('Google Maps failed to initialize in SensorLocationCoveragePicker:', err);
      }
    };

    initMap();

    return () => {
      isMounted = false;
    };
  }, []);

  // Sync radius circle size when coverage changes
  useEffect(() => {
    if (circleRef.current) {
      const radiusM = coverage.radius_meters || 2000;
      circleRef.current.setRadius(radiusM);

      if (googleMapRef.current && location.latitude && location.longitude) {
        // Adjust zoom slightly if circle grows significantly
        const currentZoom = googleMapRef.current.getZoom() || 13;
        if (radiusM > 10000 && currentZoom > 11) {
          googleMapRef.current.setZoom(11);
        } else if (radiusM <= 1000 && currentZoom < 14) {
          googleMapRef.current.setZoom(14);
        }
      }
    }
  }, [coverage.radius_meters]);

  // Sync marker position when location changes externally
  useEffect(() => {
    if (markerRef.current && circleRef.current && location.latitude && location.longitude) {
      const pos = { lat: location.latitude, lng: location.longitude };
      markerRef.current.setPosition(pos);
      circleRef.current.setCenter(pos);
    }
  }, [location.latitude, location.longitude]);

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

  const calculatedRadiusKm = ((coverage.radius_meters || 2000) / 1000).toFixed(2);

  return (
    <div className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/50 p-4.5">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-red-100 text-red-600 flex items-center justify-center font-bold">
            <Navigation className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-xs font-black uppercase tracking-wider text-slate-900">
              Sensor Physical Location & Coverage Range
            </h4>
            <p className="text-[10px] text-slate-500">
              Configure authoritative geographic coordinates and environmental observation radius.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 self-end sm:self-auto">
          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-red-100 text-red-800 border border-red-200">
            Radius: {calculatedRadiusKm} km ({coverage.radius_meters || 2000} m)
          </span>
        </div>
      </div>

      {/* Interactive Map Container */}
      <div className="relative w-full h-64 rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden">
        <div ref={mapContainerRef} className="w-full h-full" />

        {/* Map Type & Controls Overlay */}
        <div className="absolute top-2.5 right-2.5 z-10 flex items-center gap-1.5 bg-white/90 backdrop-blur-md px-2 py-1 rounded-lg border border-slate-200 shadow-xs text-[10px] font-bold">
          <button
            type="button"
            onClick={() => handleToggleMapType('roadmap')}
            className={`px-2 py-0.5 rounded ${mapType === 'roadmap' ? 'bg-slate-900 text-white' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Map
          </button>
          <button
            type="button"
            onClick={() => handleToggleMapType('satellite')}
            className={`px-2 py-0.5 rounded ${mapType === 'satellite' ? 'bg-blue-600 text-white' : 'text-slate-600 hover:text-slate-900'}`}
          >
            Satellite
          </button>
        </div>

        {/* Map Interactive Hint Overlay */}
        <div className="absolute bottom-2.5 left-2.5 z-10 flex items-center gap-2 bg-slate-900/80 backdrop-blur-md px-3 py-1.5 rounded-lg text-white text-[10px] font-medium shadow-md">
          <MapPin className="w-3.5 h-3.5 text-red-400 shrink-0" />
          <span>Click map or drag pin to position sensor. Red circle shows observation radius.</span>
        </div>
      </div>

      {/* Primary Coordinates & Range Inputs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
        {/* Latitude */}
        <div>
          <label className="block text-[11px] font-bold text-slate-700 mb-1">
            Latitude (-90° to 90°) *
          </label>
          <input
            type="number"
            step="0.000001"
            min="-90"
            max="90"
            required
            disabled={disabled}
            value={location.latitude}
            onChange={(e) => handleCoordinateChange(e.target.value === '' ? '' : parseFloat(e.target.value), location.longitude)}
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono text-slate-900 bg-white focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
            placeholder="16.5062"
          />
        </div>

        {/* Longitude */}
        <div>
          <label className="block text-[11px] font-bold text-slate-700 mb-1">
            Longitude (-180° to 180°) *
          </label>
          <input
            type="number"
            step="0.000001"
            min="-180"
            max="180"
            required
            disabled={disabled}
            value={location.longitude}
            onChange={(e) => handleCoordinateChange(location.latitude, e.target.value === '' ? '' : parseFloat(e.target.value))}
            className="w-full rounded-xl border border-slate-200 px-3 py-2 text-xs font-mono text-slate-900 bg-white focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
            placeholder="80.6480"
          />
        </div>

        {/* Coverage Range & Unit Selector */}
        <div>
          <label className="block text-[11px] font-bold text-slate-700 mb-1">
            Coverage Range / Radius *
          </label>
          <div className="flex rounded-xl border border-slate-200 bg-white overflow-hidden focus-within:ring-1 focus-within:ring-red-500 focus-within:border-red-500">
            <input
              type="number"
              step={radiusUnit === 'km' ? '0.1' : '50'}
              min="0.1"
              required
              disabled={disabled}
              value={radiusValue}
              onChange={(e) => handleRadiusChange(e.target.value === '' ? '' : parseFloat(e.target.value), radiusUnit)}
              className="w-full px-3 py-2 text-xs font-bold font-mono text-slate-900 focus:outline-hidden"
              placeholder="2.0"
            />
            <div className="flex border-l border-slate-200 bg-slate-50 p-0.5">
              <button
                type="button"
                onClick={() => handleRadiusChange(radiusValue, 'km')}
                className={`px-2.5 py-1 text-[10px] font-bold rounded-lg transition ${radiusUnit === 'km' ? 'bg-red-600 text-white' : 'text-slate-600 hover:text-slate-900'}`}
              >
                KM
              </button>
              <button
                type="button"
                onClick={() => handleRadiusChange(radiusValue, 'm')}
                className={`px-2.5 py-1 text-[10px] font-bold rounded-lg transition ${radiusUnit === 'm' ? 'bg-red-600 text-white' : 'text-slate-600 hover:text-slate-900'}`}
              >
                M
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Location / Operational Name */}
      <div>
        <label className="block text-[11px] font-bold text-slate-700 mb-1">
          Address / Location Station Name *
        </label>
        <div className="relative">
          <MapPin className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
          <input
            type="text"
            required
            disabled={disabled}
            value={locationName}
            onChange={(e) => {
              onLocationNameChange(e.target.value);
              onLocationChange({ ...location, address: e.target.value });
            }}
            placeholder="e.g. Barrage Sector 4, Krishna River Embankment"
            className="w-full rounded-xl border border-slate-200 pl-9 pr-3.5 py-2 text-xs text-slate-900 bg-white focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
          />
        </div>
      </div>

      {/* Collapsible Detailed Address Metadata */}
      <div>
        <button
          type="button"
          onClick={() => setShowAdvancedAddress(!showAdvancedAddress)}
          className="text-[11px] font-bold text-red-600 hover:text-red-700 flex items-center gap-1 transition"
        >
          <Compass className="w-3.5 h-3.5" />
          <span>{showAdvancedAddress ? 'Hide Structured Address Fields' : '+ Configure Detailed Regional & Postal Address (Optional)'}</span>
        </button>

        {showAdvancedAddress && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 pt-3 border-t border-slate-200 mt-2">
            <div>
              <label className="block text-[10px] font-bold text-slate-600 mb-1">Street Address</label>
              <input
                type="text"
                disabled={disabled}
                value={location.street_address || ''}
                onChange={(e) => onLocationChange({ ...location, street_address: e.target.value })}
                placeholder="e.g. NH-65 River Bypass"
                className="w-full rounded-xl border border-slate-200 px-3 py-1.5 text-xs text-slate-800 bg-white"
              />
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-600 mb-1">Optional Landmark</label>
              <input
                type="text"
                disabled={disabled}
                value={location.landmark || ''}
                onChange={(e) => onLocationChange({ ...location, landmark: e.target.value })}
                placeholder="e.g. Near Sluice Gate #12"
                className="w-full rounded-xl border border-slate-200 px-3 py-1.5 text-xs text-slate-800 bg-white"
              />
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-600 mb-1">Operational Zone</label>
              <input
                type="text"
                disabled={disabled}
                value={location.zone || ''}
                onChange={(e) => onLocationChange({ ...location, zone: e.target.value })}
                placeholder="e.g. Krishna Central Zone"
                className="w-full rounded-xl border border-slate-200 px-3 py-1.5 text-xs text-slate-800 bg-white"
              />
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-600 mb-1">District</label>
              <input
                type="text"
                disabled={disabled}
                value={location.district || ''}
                onChange={(e) => onLocationChange({ ...location, district: e.target.value })}
                placeholder="e.g. NTR District"
                className="w-full rounded-xl border border-slate-200 px-3 py-1.5 text-xs text-slate-800 bg-white"
              />
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-600 mb-1">City</label>
              <input
                type="text"
                disabled={disabled}
                value={location.city || ''}
                onChange={(e) => onLocationChange({ ...location, city: e.target.value })}
                placeholder="e.g. Vijayawada"
                className="w-full rounded-xl border border-slate-200 px-3 py-1.5 text-xs text-slate-800 bg-white"
              />
            </div>

            <div>
              <label className="block text-[10px] font-bold text-slate-600 mb-1">State & Country</label>
              <div className="grid grid-cols-2 gap-1.5">
                <input
                  type="text"
                  disabled={disabled}
                  value={location.state || ''}
                  onChange={(e) => onLocationChange({ ...location, state: e.target.value })}
                  placeholder="State (AP)"
                  className="w-full rounded-xl border border-slate-200 px-2 py-1.5 text-xs text-slate-800 bg-white"
                />
                <input
                  type="text"
                  disabled={disabled}
                  value={location.country || 'India'}
                  onChange={(e) => onLocationChange({ ...location, country: e.target.value })}
                  placeholder="Country"
                  className="w-full rounded-xl border border-slate-200 px-2 py-1.5 text-xs text-slate-800 bg-white"
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SensorLocationCoveragePicker;
