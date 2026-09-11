import React, { useState, useEffect } from 'react';
import { X, Edit3, Gauge, Link2, AlertCircle, Save, Activity } from 'lucide-react';
import { updateSensor } from '../../services/api';
import type { Sensor, SensorUpdatePayload, SensorLocation, SensorCoverage, SensorType } from '../../types';
import { SensorLocationCoveragePicker } from './SensorLocationCoveragePicker';

interface EditSensorModalProps {
  isOpen: boolean;
  sensor: Sensor | null;
  onClose: () => void;
  onSensorUpdated: (sensor: Sensor) => void;
}

interface SensorTypeOption {
  value: SensorType;
  label: string;
  defaultUnit: string;
  defaultThreshold: number;
}

const SENSOR_TYPE_OPTIONS: SensorTypeOption[] = [
  { value: 'WATER_LEVEL', label: 'Water Level', defaultUnit: 'meters', defaultThreshold: 2.5 },
  { value: 'RAINFALL', label: 'Rainfall', defaultUnit: 'mm/hour', defaultThreshold: 50.0 },
  { value: 'TEMPERATURE', label: 'Temperature', defaultUnit: '°C', defaultThreshold: 45.0 },
  { value: 'SMOKE_AIR_QUALITY', label: 'Smoke / Air Quality', defaultUnit: 'AQI', defaultThreshold: 300.0 },
  { value: 'AQI', label: 'AQI', defaultUnit: 'AQI', defaultThreshold: 250.0 },
];

export const EditSensorModal: React.FC<EditSensorModalProps> = ({
  isOpen,
  sensor,
  onClose,
  onSensorUpdated,
}) => {
  const [name, setName] = useState('');
  const [sensorType, setSensorType] = useState<SensorType>('SMOKE_AIR_QUALITY');
  const [locationName, setLocationName] = useState('');
  const [location, setLocation] = useState<SensorLocation>({
    latitude: 16.5062,
    longitude: 80.6480,
    address: '',
    street_address: '',
    landmark: '',
    zone: '',
    district: '',
    city: '',
    state: '',
    country: 'India',
  });
  const [coverage, setCoverage] = useState<SensorCoverage>({
    radius_meters: 2000,
    display_value: 2.0,
    display_unit: 'km',
  });
  const [unit, setUnit] = useState('AQI');
  const [threshold, setThreshold] = useState<number | ''>(300.0);
  const [linkedSituationId, setLinkedSituationId] = useState('');
  const [description, setDescription] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (sensor) {
      setName(sensor.name || '');
      setSensorType(sensor.sensor_type || 'SMOKE_AIR_QUALITY');
      setLocationName(sensor.location_name || '');

      const loc = sensor.location || {
        latitude: sensor.latitude,
        longitude: sensor.longitude,
        address: sensor.location_name,
        street_address: '',
        landmark: '',
        zone: '',
        district: '',
        city: '',
        state: '',
        country: 'India',
      };
      setLocation({
        ...loc,
        latitude: sensor.latitude ?? loc.latitude,
        longitude: sensor.longitude ?? loc.longitude,
      });

      const cov = sensor.coverage || {
        radius_meters: 2000,
        display_value: 2.0,
        display_unit: 'km',
      };
      setCoverage(cov);

      setUnit(sensor.unit || 'units');
      setThreshold(sensor.threshold ?? 0);
      setLinkedSituationId(sensor.linked_situation_id || '');
      setDescription(sensor.description || '');
      setError(null);
    }
  }, [sensor]);

  const scrollBodyRef = React.useRef<HTMLDivElement>(null);

  // Scroll top reset, escape key, and backdrop lock
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      if (scrollBodyRef.current) {
        scrollBodyRef.current.scrollTop = 0;
      }
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          onClose();
        }
      };
      window.addEventListener('keydown', handleKeyDown);
      return () => {
        document.body.style.overflow = '';
        window.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [isOpen, onClose]);

  if (!isOpen || !sensor) return null;

  const handleTypeChange = (newType: SensorType) => {
    setSensorType(newType);
    const opt = SENSOR_TYPE_OPTIONS.find((o) => o.value === newType);
    if (opt && !unit) {
      setUnit(opt.defaultUnit);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError('Sensor Identifier / Station Name is required.');
      return;
    }
    if (!sensorType) {
      setError('Type of Sensor is required.');
      return;
    }
    if (!locationName.trim()) {
      setError('Operational location or station address is required.');
      return;
    }
    if (
      typeof location.latitude !== 'number' ||
      typeof location.longitude !== 'number' ||
      isNaN(location.latitude) ||
      isNaN(location.longitude)
    ) {
      setError('Valid numeric latitude and longitude coordinates are required.');
      return;
    }
    if (location.latitude < -90 || location.latitude > 90 || location.longitude < -180 || location.longitude > 180) {
      setError('Latitude must be between -90 and 90, and Longitude must be between -180 and 180.');
      return;
    }
    if (!coverage.radius_meters || coverage.radius_meters <= 0 || isNaN(coverage.radius_meters)) {
      setError('Valid coverage range / radius greater than 0 is required.');
      return;
    }
    if (threshold === '' || isNaN(Number(threshold))) {
      setError('A valid numerical critical threshold is required.');
      return;
    }

    setLoading(true);
    try {
      const payload: SensorUpdatePayload = {
        name: name.trim(),
        sensor_type: sensorType,
        location_name: locationName.trim(),
        latitude: location.latitude,
        longitude: location.longitude,
        location: {
          ...location,
          address: locationName.trim(),
        },
        coverage: coverage,
        coverage_radius_value: coverage.display_value || (coverage.radius_meters >= 1000 ? coverage.radius_meters / 1000 : coverage.radius_meters),
        coverage_radius_unit: coverage.display_unit || (coverage.radius_meters >= 1000 ? 'km' : 'm'),
        unit: unit.trim() || undefined,
        threshold: Number(threshold),
        linked_situation_id: linkedSituationId.trim() || undefined,
        description: description.trim() || undefined,
      };

      const updated = await updateSensor(sensor.sensor_id, payload);
      onSensorUpdated(updated);
      onClose();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update sensor configuration.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-2 sm:p-4 md:p-6"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-sensor-modal-title"
    >
      <div className="relative w-full max-w-3xl rounded-2xl bg-white shadow-2xl border border-slate-200 flex flex-col max-h-[calc(100dvh-1rem)] sm:max-h-[calc(100dvh-2rem)] overflow-hidden">
        {/* Fixed Header (shrink-0) */}
        <div className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-slate-100 bg-slate-50/90 shrink-0 z-10 min-w-0">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-xl bg-amber-100 text-amber-700 flex items-center justify-center font-bold shrink-0">
              <Edit3 className="w-4 h-4 sm:w-5 sm:h-5" />
            </div>
            <div className="min-w-0">
              <h3 id="edit-sensor-modal-title" className="text-sm sm:text-base font-bold text-slate-900 truncate">Edit Sensor Location & Range</h3>
              <p className="text-xs text-slate-500 font-mono truncate">
                {sensor.sensor_id} • Status: {sensor.status}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded-lg p-1.5 sm:p-2 text-slate-400 hover:bg-slate-200/60 hover:text-slate-700 transition cursor-pointer flex-shrink-0"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Container with scrollable body + pinned footer */}
        <form onSubmit={handleSubmit} className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {/* Scrollable Body */}
          <div ref={scrollBodyRef} className="flex-1 overflow-y-auto p-3 sm:p-6 space-y-4 sm:space-y-5 touch-scroll">
            {/* Error Alert */}
            {error && (
              <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs flex items-center gap-2.5">
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* 1. Sensor Name */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Sensor Name / Station Identifier <span className="text-red-600">*</span>
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs text-slate-900 focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
              />
            </div>

            {/* 2. Type of Sensor */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Type of Sensor <span className="text-red-600">*</span>
              </label>
              <div className="relative">
                <select
                  required
                  value={sensorType}
                  onChange={(e) => handleTypeChange(e.target.value as SensorType)}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs text-slate-900 bg-white appearance-none focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500 font-medium cursor-pointer"
                >
                  {SENSOR_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3 text-slate-500">
                  <Activity className="w-4 h-4" />
                </div>
              </div>
            </div>

            {/* 3 & 4. Location & Coverage Range */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Sensor Physical Location & Coverage Range <span className="text-red-600">*</span>
                </label>
                <span className="text-[10px] text-slate-500">Interactive Map Pin & Dynamic Radius</span>
              </div>
              <SensorLocationCoveragePicker
                location={location}
                coverage={coverage}
                locationName={locationName}
                onLocationChange={setLocation}
                onCoverageChange={setCoverage}
                onLocationNameChange={setLocationName}
              />
            </div>

            {/* 5. Threshold Configuration */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Critical Alert Threshold <span className="text-red-600">*</span>
                </label>
                <div className="relative">
                  <Gauge className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                  <input
                    type="number"
                    step="0.1"
                    required
                    value={threshold}
                    onChange={(e) => setThreshold(e.target.value === '' ? '' : parseFloat(e.target.value))}
                    className="w-full rounded-xl border border-slate-200 pl-9 pr-3.5 py-2 text-xs font-bold text-slate-900 focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
                  />
                </div>
                <p className="text-[10px] text-slate-500 mt-1">Readings exceeding this value generate a threshold breach alert.</p>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Measurement Unit</label>
                <input
                  type="text"
                  value={unit}
                  onChange={(e) => setUnit(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2 text-xs text-slate-900 focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
                />
              </div>
            </div>

            {/* 6. Linked Situation & Description */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Linked Situation ID (Optional)
                </label>
                <div className="relative">
                  <Link2 className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    value={linkedSituationId}
                    onChange={(e) => setLinkedSituationId(e.target.value)}
                    placeholder="e.g. SIT-VIJ-1650-8064"
                    className="w-full rounded-xl border border-slate-200 pl-9 pr-3.5 py-2 text-xs text-slate-900 focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Operational Notes / Description (Optional)
                </label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Sensor deployment notes, hardware specs..."
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2 text-xs text-slate-900 focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
                />
              </div>
            </div>
          </div>

          {/* Fixed/Sticky Footer Actions (shrink-0) */}
          <div className="shrink-0 px-6 py-4 border-t border-slate-100 bg-slate-50/95 flex items-center justify-end gap-3 z-10">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100 transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold shadow-sm transition flex items-center gap-2 disabled:opacity-50 cursor-pointer"
            >
              <Save className="w-4 h-4" />
              {loading ? 'Saving Changes...' : 'Save Sensor Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EditSensorModal;
