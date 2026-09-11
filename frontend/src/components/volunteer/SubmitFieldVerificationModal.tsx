import React, { useState, useEffect } from 'react';
import {
  X,
  Camera,
  CheckCircle2,
  AlertTriangle,
  Send,
  RefreshCw,
  Eye,
  Navigation,
} from 'lucide-react';
import { submitFieldVerification } from '../../services/fieldOperationsApi';
import type {
  FieldVerificationStatus,
  FieldObservationCategory,
  FieldVerificationRecord,
} from '../../types';

interface SubmitFieldVerificationModalProps {
  isOpen: boolean;
  onClose: () => void;
  targetId: string;
  targetType: 'CITIZEN_REPORT' | 'SITUATION' | 'GENERAL_FIELD';
  targetTitle?: string;
  targetCoords?: { latitude: number; longitude: number } | null;
  onSuccess?: (record: FieldVerificationRecord) => void;
}

export const SubmitFieldVerificationModal: React.FC<SubmitFieldVerificationModalProps> = ({
  isOpen,
  onClose,
  targetId,
  targetType,
  targetTitle,
  targetCoords,
  onSuccess,
}) => {
  const [verificationStatus, setVerificationStatus] = useState<FieldVerificationStatus>('FIELD_VERIFIED');
  const [observationCategory, setObservationCategory] = useState<FieldObservationCategory>('INCIDENT_CONFIRMED');
  const [notes, setNotes] = useState<string>('');
  
  // Geolocation
  const [latitude, setLatitude] = useState<number | null>(null);
  const [longitude, setLongitude] = useState<number | null>(null);
  const [accuracyMeters, setAccuracyMeters] = useState<number | null>(null);
  const [locating, setLocating] = useState<boolean>(false);
  const [locError, setLocError] = useState<string | null>(null);

  // Photo
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [capturedAt, setCapturedAt] = useState<string | null>(null);

  // Submission state
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const acquireLocation = () => {
    if (!navigator.geolocation) {
      setLocError('Geolocation not supported by this browser.');
      return;
    }
    setLocating(true);
    setLocError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLatitude(pos.coords.latitude);
        setLongitude(pos.coords.longitude);
        setAccuracyMeters(pos.coords.accuracy);
        setLocating(false);
      },
      (err) => {
        // Fallback: if browser denies, allow officer to enter or use target coordinates as default reference
        if (targetCoords) {
          setLatitude(targetCoords.latitude);
          setLongitude(targetCoords.longitude);
          setAccuracyMeters(50.0);
        }
        setLocError(`GPS acquisition: ${err.message}. Using approximate fallback.`);
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
    );
  };

  useEffect(() => {
    if (isOpen) {
      acquireLocation();
      setSubmitError(null);
      setNotes('');
      setImageBase64(null);
      setCapturedAt(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handlePhotoCapture = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setImageBase64(reader.result as string);
        setCapturedAt(new Date().toISOString());
      };
      reader.readAsDataURL(file);
    }
  };

  const calculateDistance = () => {
    if (!latitude || !longitude || !targetCoords) return null;
    const R = 6371000;
    const dLat = ((targetCoords.latitude - latitude) * Math.PI) / 180;
    const dLon = ((targetCoords.longitude - longitude) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((latitude * Math.PI) / 180) *
        Math.cos((targetCoords.latitude * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return Math.round(R * c);
  };

  const distM = calculateDistance();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!latitude || !longitude) {
      setSubmitError('Officer GPS coordinates are required for live field verification.');
      return;
    }
    if (!notes.trim()) {
      setSubmitError('Verification notes are mandatory to capture ground conditions.');
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    try {
      const record = await submitFieldVerification({
        target_type: targetType,
        target_id: targetId,
        verification_status: verificationStatus,
        observation_category: observationCategory,
        latitude,
        longitude,
        accuracy_meters: accuracyMeters,
        notes: notes.trim(),
        image_base64: imageBase64,
        client_captured_at: capturedAt || new Date().toISOString(),
      });

      if (onSuccess) onSuccess(record);
      onClose();
    } catch (err: any) {
      setSubmitError(err?.response?.data?.detail || err.message || 'Failed to submit field verification.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-xl bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 bg-slate-850 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">
                Field Officer Live Verification
              </h3>
              <p className="text-xs text-slate-400">
                Target: <span className="font-mono text-emerald-400">{targetId}</span> {targetTitle ? `(${targetTitle})` : ''}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5 overflow-y-auto flex-1">
          {submitError && (
            <div className="flex items-center gap-2 p-3 text-xs bg-rose-500/10 border border-rose-500/30 text-rose-300 rounded-xl">
              <AlertTriangle className="w-4 h-4 flex-shrink-0 text-rose-400" />
              <span>{submitError}</span>
            </div>
          )}

          {/* GPS Coordinates Section */}
          <div className="p-3.5 bg-slate-950/50 border border-slate-800/80 rounded-xl space-y-2">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5 font-medium text-slate-200">
                <Navigation className="w-3.5 h-3.5 text-emerald-400" />
                <span>Responder Ground GPS</span>
              </div>
              <button
                type="button"
                onClick={acquireLocation}
                disabled={locating}
                className="flex items-center gap-1 text-[11px] text-emerald-400 hover:text-emerald-300 disabled:opacity-50"
              >
                <RefreshCw className={`w-3 h-3 ${locating ? 'animate-spin' : ''}`} />
                <span>{locating ? 'Acquiring...' : 'Re-acquire GPS'}</span>
              </button>
            </div>

            {latitude && longitude ? (
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-slate-300 pt-1">
                <div>
                  <span className="text-slate-500">LAT:</span> {latitude.toFixed(6)} | <span className="text-slate-500">LON:</span> {longitude.toFixed(6)}
                </div>
                {accuracyMeters && (
                  <div className="text-[11px] text-slate-400 font-sans">
                    Accuracy: ±{accuracyMeters.toFixed(0)}m
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-amber-400 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Acquiring ground telemetry...</span>
              </div>
            )}

            {distM !== null && (
              <div className="pt-1.5 border-t border-slate-800 flex items-center justify-between text-[11px]">
                <span className="text-slate-400">Distance from Target Coordinates:</span>
                <span className={`font-semibold ${distM <= 500 ? 'text-emerald-400' : distM <= 2000 ? 'text-amber-400' : 'text-rose-400'}`}>
                  {distM} meters {distM <= 500 ? '(MATCH ≤500m)' : distM <= 2000 ? '(NEAR MATCH ≤2km)' : '(MISMATCH >2km)'}
                </span>
              </div>
            )}

            {locError && (
              <p className="text-[11px] text-amber-400/90 pt-1">{locError}</p>
            )}
          </div>

          {/* Verification Status */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Verification Status
            </label>
            <select
              value={verificationStatus}
              onChange={(e) => setVerificationStatus(e.target.value as FieldVerificationStatus)}
              className="w-full px-3.5 py-2.5 bg-slate-950/80 border border-slate-800 rounded-xl text-xs text-white focus:outline-none focus:border-emerald-500 transition-colors"
            >
              <option value="FIELD_VERIFIED">FIELD VERIFIED (Direct Ground Confirmation)</option>
              <option value="PARTIALLY_VERIFIED">PARTIALLY VERIFIED (Incomplete / In Progress)</option>
              <option value="CONDITION_CHANGED">CONDITION CHANGED (Different from Report)</option>
              <option value="NOT_FOUND">NOT FOUND (Incident Not Located at Site)</option>
              <option value="UNABLE_TO_VERIFY">UNABLE TO VERIFY (Access Blocked / Hazardous)</option>
            </select>
          </div>

          {/* Observation Category */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Ground Observation Category
            </label>
            <select
              value={observationCategory}
              onChange={(e) => setObservationCategory(e.target.value as FieldObservationCategory)}
              className="w-full px-3.5 py-2.5 bg-slate-950/80 border border-slate-800 rounded-xl text-xs text-white focus:outline-none focus:border-emerald-500 transition-colors"
            >
              <option value="INCIDENT_CONFIRMED">Incident Confirmed</option>
              <option value="INCIDENT_NOT_FOUND">Incident Not Found / Resolved</option>
              <option value="SEVERITY_CHANGED">Severity Changed (Escalated / De-escalated)</option>
              <option value="WATER_LEVEL_CHANGED">Water Level Changed</option>
              <option value="FIRE_SPREADING">Fire Spreading</option>
              <option value="ROAD_BLOCKED">Road Blocked</option>
              <option value="ROAD_CLEAR">Road Clear</option>
              <option value="SHELTER_ACCESSIBLE">Shelter Accessible</option>
              <option value="SHELTER_INACCESSIBLE">Shelter Inaccessible</option>
              <option value="MEDICAL_NEED_OBSERVED">Medical Need Observed</option>
              <option value="RESOURCE_SHORTAGE_OBSERVED">Resource Shortage Observed</option>
              <option value="CONDITION_UNKNOWN">Condition Unknown</option>
            </select>
          </div>

          {/* Verification Notes */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Ground Observation Notes *
            </label>
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Describe actual ground conditions, depth of water, road clearance, active hazards, victims present..."
              className="w-full px-3.5 py-2.5 bg-slate-950/80 border border-slate-800 rounded-xl text-xs text-white placeholder-slate-600 focus:outline-none focus:border-emerald-500 transition-colors resize-none"
              required
            />
          </div>

          {/* Photo Evidence (Optional) */}
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
              Live Photo Evidence (Optional)
            </label>
            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 px-3.5 py-2 bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 rounded-xl text-xs text-slate-200 cursor-pointer transition-colors">
                <Camera className="w-4 h-4 text-emerald-400" />
                <span>{imageBase64 ? 'Replace Photo' : 'Capture Ground Photo'}</span>
                <input
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onChange={handlePhotoCapture}
                  className="hidden"
                />
              </label>

              {imageBase64 && (
                <span className="inline-flex items-center gap-1 text-xs text-emerald-400">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>Photo attached</span>
                </span>
              )}
            </div>
            {imageBase64 && (
              <div className="relative mt-2 w-32 h-20 rounded-lg overflow-hidden border border-slate-700">
                <img src={imageBase64} alt="Ground preview" className="w-full h-full object-cover" />
                <button
                  type="button"
                  onClick={() => setImageBase64(null)}
                  className="absolute top-1 right-1 p-0.5 bg-slate-900/80 text-rose-400 rounded-full hover:bg-rose-900"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}
          </div>

          {/* Advisory Notice */}
          <div className="p-3 bg-emerald-950/20 border border-emerald-900/30 rounded-xl text-[11px] text-slate-400">
            <span className="font-semibold text-emerald-400">Human-in-the-Loop Ground Intelligence:</span>{' '}
            Your live field verification provides authoritative ground evidence for Watch Officers and the Incident Evolution timeline.
          </div>

          {/* Action Buttons */}
          <div className="pt-3 border-t border-slate-800 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white rounded-xl hover:bg-slate-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !latitude || !longitude || !notes.trim()}
              className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-semibold rounded-xl shadow-lg shadow-emerald-900/20 transition-all disabled:opacity-50"
            >
              {submitting ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              <span>{submitting ? 'Submitting Verification...' : 'Submit Field Verification'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
