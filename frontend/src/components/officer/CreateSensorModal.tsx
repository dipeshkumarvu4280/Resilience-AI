import React, { useState } from 'react';
import { X, Radio, Activity, Gauge, Link2, AlertCircle } from 'lucide-react';
import { createSensor } from '../../services/api';
import type { SensorType, SensorCreatePayload, Sensor, SensorLocation, SensorCoverage } from '../../types';
import { SensorLocationCoveragePicker } from './SensorLocationCoveragePicker';

interface CreateSensorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSensorCreated: (sensor: Sensor) => void;
  defaultSituationId?: string;
}

interface SensorTypeOption {
  value: SensorType;
  label: string;
  defaultUnit: string;
  defaultThreshold: number;
  placeholder: string;
  description: string;
}

const SENSOR_TYPE_OPTIONS: SensorTypeOption[] = [
  {
    value: 'WATER_LEVEL',
    label: 'Water Level',
    defaultUnit: 'meters',
    defaultThreshold: 2.5,
    placeholder: 'e.g. Krishna Barrage Flood Gauge #3',
    description: 'Measures river, reservoir, or canal water height in meters',
  },
  {
    value: 'RAINFALL',
    label: 'Rainfall',
    defaultUnit: 'mm/hour',
    defaultThreshold: 50.0,
    placeholder: 'e.g. Auto Nagar Meteorological Pluviometer',
    description: 'Measures precipitation rate in mm/hour',
  },
  {
    value: 'TEMPERATURE',
    label: 'Temperature',
    defaultUnit: '°C',
    defaultThreshold: 45.0,
    placeholder: 'e.g. Industrial Sector Ambient Thermal Sensor',
    description: 'Measures ambient thermal level in °C',
  },
  {
    value: 'SMOKE_AIR_QUALITY',
    label: 'Smoke / Air Quality',
    defaultUnit: 'AQI',
    defaultThreshold: 300.0,
    placeholder: 'e.g. Downtown Smoke & Particulate Monitor',
    description: 'Measures smoke density and air quality index',
  },
  {
    value: 'AQI',
    label: 'AQI',
    defaultUnit: 'AQI',
    defaultThreshold: 250.0,
    placeholder: 'e.g. Central Vijayawada AQI Station #1',
    description: 'Measures Air Quality Index telemetry',
  },
];

export const CreateSensorModal: React.FC<CreateSensorModalProps> = ({
  isOpen,
  onClose,
  onSensorCreated,
  defaultSituationId,
}) => {
  const [name, setName] = useState('');
  // No preselected default so the user consciously chooses the sensor type
  const [sensorType, setSensorType] = useState<SensorType | ''>('');
  const [locationName, setLocationName] = useState('');
  const [location, setLocation] = useState<SensorLocation>({
    latitude: 16.5062,
    longitude: 80.6480,
    address: '',
    street_address: '',
    landmark: '',
    zone: 'Krishna Central Zone',
    district: 'NTR District',
    city: 'Vijayawada',
    state: 'Andhra Pradesh',
    country: 'India',
  });
  const [coverage, setCoverage] = useState<SensorCoverage>({
    radius_meters: 2000,
    display_value: 2.0,
    display_unit: 'km',
  });

  const [unit, setUnit] = useState('');
  const [threshold, setThreshold] = useState<number | ''>('');
  const [linkedSituationId, setLinkedSituationId] = useState(defaultSituationId || '');
  const [description, setDescription] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scrollBodyRef = React.useRef<HTMLDivElement>(null);

  // Scroll top reset, escape key, and backdrop lock
  React.useEffect(() => {
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

  if (!isOpen) return null;

  const handleTypeChange = (selectedVal: string) => {
    if (!selectedVal) {
      setSensorType('');
      return;
    }
    const selectedType = selectedVal as SensorType;
    setSensorType(selectedType);
    const opt = SENSOR_TYPE_OPTIONS.find((o) => o.value === selectedType);
    if (opt) {
      setUnit(opt.defaultUnit);
      setThreshold(opt.defaultThreshold);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // 1. Sensor Name
    if (!name.trim()) {
      setError('Sensor Identifier / Station Name is required.');
      return;
    }

    // 2. Type of Sensor Validation
    if (!sensorType) {
      setError('Please select a valid "Type of Sensor" from the dropdown.');
      return;
    }

    // 3. Location Validation
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

    // 4. Coverage Range Validation
    if (!coverage.radius_meters || coverage.radius_meters <= 0 || isNaN(coverage.radius_meters)) {
      setError('Valid coverage range / radius greater than 0 is required.');
      return;
    }

    // 5. Threshold Validation
    if (threshold === '' || isNaN(Number(threshold))) {
      setError('A valid numerical critical threshold is required.');
      return;
    }

    setLoading(true);
    try {
      const payload: SensorCreatePayload = {
        name: name.trim(),
        sensor_type: sensorType as SensorType,
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

      const newSensor = await createSensor(payload);
      onSensorCreated(newSensor);
      onClose();
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to provision sensor. Please verify coordinate and threshold inputs.');
    } finally {
      setLoading(false);
    }
  };

  const selectedOption = SENSOR_TYPE_OPTIONS.find((o) => o.value === sensorType);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-2 sm:p-4 md:p-6"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-sensor-modal-title"
    >
      <div className="relative w-full max-w-3xl rounded-2xl bg-white shadow-2xl border border-slate-200 flex flex-col max-h-[calc(100dvh-1rem)] sm:max-h-[calc(100dvh-2rem)] overflow-hidden">
        {/* Fixed Header (shrink-0) */}
        <div className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-slate-100 bg-slate-50/90 shrink-0 z-10 min-w-0">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-xl bg-red-100 text-red-600 flex items-center justify-center font-bold shrink-0">
              <Radio className="w-4 h-4 sm:w-5 sm:h-5" />
            </div>
            <div className="min-w-0">
              <h3 id="create-sensor-modal-title" className="text-sm sm:text-base font-bold text-slate-900 truncate">Provision Operational IoT Sensor</h3>
              <p className="text-xs text-slate-500 truncate hidden xs:block">Configure simulated IoT telemetry source with coordinate-based coverage range.</p>
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

            {/* 1. SENSOR NAME */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Sensor Identifier / Station Name <span className="text-red-600">*</span>
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={selectedOption ? selectedOption.placeholder : 'e.g. Krishna Barrage Gate 10'}
                className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs text-slate-900 focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
              />
            </div>

            {/* 2. TYPE OF SENSOR */}
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1">
                Type of Sensor <span className="text-red-600">*</span>
              </label>
              <div className="relative">
                <select
                  required
                  value={sensorType}
                  onChange={(e) => handleTypeChange(e.target.value)}
                  className={`w-full rounded-xl border px-3.5 py-2.5 text-xs font-medium bg-white appearance-none focus:outline-hidden focus:ring-1 transition cursor-pointer ${
                    !sensorType
                      ? 'border-amber-300 text-slate-500 focus:border-amber-500 focus:ring-amber-500'
                      : 'border-slate-200 text-slate-900 focus:border-red-500 focus:ring-red-500'
                  }`}
                >
                  <option value="" disabled>
                    -- Select Sensor Type --
                  </option>
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
              {selectedOption && (
                <p className="text-[11px] text-slate-500 mt-1.5 flex items-center gap-1.5">
                  <span className="font-semibold text-slate-700">{selectedOption.label}:</span>
                  <span>{selectedOption.description}</span>
                  <span className="text-slate-400">• Standard Unit: {selectedOption.defaultUnit}</span>
                </p>
              )}
            </div>

            {/* 3 & 4. LOCATION & COVERAGE RANGE (Google Maps Picker) */}
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

            {/* 5. THRESHOLD CONFIGURATION */}
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
                    placeholder={selectedOption ? `e.g. ${selectedOption.defaultThreshold}` : 'Threshold value'}
                    className="w-full rounded-xl border border-slate-200 pl-9 pr-3.5 py-2 text-xs font-bold text-slate-900 focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
                  />
                </div>
                <p className="text-[10px] text-slate-500 mt-1">Readings exceeding this value generate an active threshold breach alert.</p>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">Measurement Unit</label>
                <input
                  type="text"
                  value={unit}
                  onChange={(e) => setUnit(e.target.value)}
                  placeholder={selectedOption ? selectedOption.defaultUnit : 'e.g. meters, mm/hour, AQI'}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2 text-xs text-slate-900 focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
                />
              </div>
            </div>

            {/* 6. STATUS / LINKED SITUATION & DESCRIPTION */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Explicitly Linked Situation ID (Optional)
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
                <p className="text-[10px] text-slate-500 mt-1">If empty, high-precision coverage radius matching will correlate active situations.</p>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Operational Notes / Description (Optional)
                </label>
                <textarea
                  rows={2}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Sensor deployment notes, hardware specs, calibration notes..."
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2 text-xs text-slate-900 focus:border-red-500 focus:outline-hidden focus:ring-1 focus:ring-red-500"
                />
              </div>
            </div>
          </div>

          {/* Fixed/Sticky Footer Actions (shrink-0) */}
          <div className="shrink-0 px-6 py-4 border-t border-slate-100 bg-slate-50/95 flex items-center justify-between z-10">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-blue-500" />
              <span className="text-[11px] font-semibold text-slate-600">
                Initial Status: <span className="font-mono text-blue-600">DRAFT</span>
              </span>
            </div>
            <div className="flex items-center gap-3">
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
                className="px-5 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold shadow-sm transition flex items-center gap-2 disabled:opacity-50 cursor-pointer"
              >
                {loading ? 'Provisioning...' : 'Create Sensor'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreateSensorModal;
