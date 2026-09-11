import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  Camera,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  MapPin,
  Clock,
  ShieldCheck,
  X,
  FlipHorizontal,
  Loader2,
} from 'lucide-react';
import type { LiveEvidencePayload } from '../../types';
import {
  type CameraFacingMode,
  getAvailableVideoInputs,
  checkHasMultipleCameras,
  getStreamForFacingMode,
  isStreamHealthy,
  isVideoElementReady,
  stopMediaStream,
} from '../../utils/camera';

interface LiveCameraCaptureProps {
  onEvidenceCaptured: (evidence: LiveEvidencePayload | null) => void;
  reportLatitude?: number;
  reportLongitude?: number;
}

export const LiveCameraCapture: React.FC<LiveCameraCaptureProps> = ({
  onEvidenceCaptured,
}) => {
  const [cameraOpen, setCameraOpen] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [isSwitching, setIsSwitching] = useState(false);
  const [facingMode, setFacingMode] = useState<CameraFacingMode>('environment');
  const [actualFacingMode, setActualFacingMode] = useState<CameraFacingMode>('environment');
  const [hasMultipleCameras, setHasMultipleCameras] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);

  // Evidence state
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [captureTime, setCaptureTime] = useState<Date | null>(null);
  const [evidenceLocation, setEvidenceLocation] = useState<{
    latitude: number;
    longitude: number;
    accuracy: number;
  } | null>(null);
  const [gpsStatus, setGpsStatus] = useState<'locating' | 'ready' | 'unavailable'>('unavailable');
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [streamWarning, setStreamWarning] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const currentDeviceIdRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string>(`SES-${Math.random().toString(36).substring(2, 10).toUpperCase()}`);

  // Query devices safely and update camera count
  const refreshDeviceEnumeration = useCallback(async () => {
    try {
      const devices = await getAvailableVideoInputs();
      setHasMultipleCameras(checkHasMultipleCameras(devices));
    } catch {
      setHasMultipleCameras(false);
    }
  }, []);

  // Initial check on mount
  useEffect(() => {
    refreshDeviceEnumeration();
  }, [refreshDeviceEnumeration]);

  // Stop camera stream safely and clear references
  const stopStream = useCallback(() => {
    if (streamRef.current) {
      stopMediaStream(streamRef.current);
      streamRef.current = null;
    }
    if (videoRef.current) {
      try {
        videoRef.current.srcObject = null;
      } catch (err) {
        console.warn('[CAMERA] Error clearing video srcObject:', err);
      }
    }
    setStream(null);
  }, []);

  // Cleanup tracks on unmount
  useEffect(() => {
    return () => {
      stopStream();
    };
  }, [stopStream]);

  // Attach active stream to video element when video mounts or stream changes
  useEffect(() => {
    if (cameraOpen && stream && videoRef.current) {
      const videoEl = videoRef.current;
      videoEl.srcObject = stream;

      const playPromise = videoEl.play();
      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            setStreamWarning(null);
          })
          .catch((err) => {
            console.warn('[CAMERA] video.play() notice:', err);
            // Handle mobile browser autoplay restriction without crashing
            if (err?.name !== 'AbortError') {
              setStreamWarning('Tap viewfinder if video preview does not play automatically.');
            }
          });
      }
    }
  }, [cameraOpen, stream]);

  // Request GPS coordinates simultaneously with camera capture session safely
  const acquireGpsLocation = useCallback(() => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setGpsStatus('unavailable');
      return;
    }

    setGpsStatus('locating');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setEvidenceLocation({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: Math.round(pos.coords.accuracy),
        });
        setGpsStatus('ready');
      },
      (err) => {
        console.warn('Live evidence GPS acquisition notice:', err?.message || 'Unavailable');
        setGpsStatus('unavailable');
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  }, []);

  // Start device camera only on explicit user click (prefer rear camera by default)
  const startCamera = async () => {
    setCameraError(null);
    setStreamWarning(null);
    setCapturing(true);

    // Acquire GPS concurrently (GPS remains independent)
    acquireGpsLocation();

    try {
      // 1. Acquire stream using resilient multi-tier acquisition
      const result = await getStreamForFacingMode('environment');

      streamRef.current = result.stream;
      currentDeviceIdRef.current = result.deviceId || null;
      setFacingMode('environment');
      setActualFacingMode(result.actualFacingMode);
      setStream(result.stream);
      setCameraOpen(true);

      // 2. Post-permission authoritative device enumeration
      await refreshDeviceEnumeration();
    } catch (err: any) {
      console.warn('[CAMERA] Camera access error:', err);
      const isDenied =
        err?.name === 'NotAllowedError' ||
        err?.name === 'PermissionDeniedError' ||
        err?.name === 'SecurityError';
      const errMsg = isDenied
        ? 'Camera permission was denied. You can still submit your emergency report without photo evidence.'
        : `Camera unavailable on this device/browser: ${err?.message || 'Device camera could not be accessed.'}`;
      setCameraError(errMsg);
      setCameraOpen(false);
      setStream(null);

      // Report UNAVAILABLE status to parent without blocking emergency report submission
      onEvidenceCaptured({
        status: 'UNAVAILABLE',
        error_reason: errMsg,
        capture_session_id: sessionIdRef.current,
        latitude: evidenceLocation?.latitude,
        longitude: evidenceLocation?.longitude,
        accuracy_meters: evidenceLocation?.accuracy,
      });
    } finally {
      setCapturing(false);
    }
  };

  // Toggle front / back camera if device has multiple cameras
  const switchCameraFacing = async () => {
    if (isSwitching) return;
    setIsSwitching(true);
    setStreamWarning(null);

    const targetMode: CameraFacingMode = facingMode === 'environment' ? 'user' : 'environment';

    // 1. Stop existing stream completely
    stopStream();

    try {
      // 2. Request new stream with target facing mode
      const result = await getStreamForFacingMode(targetMode, {
        preferredDeviceId: currentDeviceIdRef.current,
      });

      // 3. Attach new stream and update states on success
      streamRef.current = result.stream;
      currentDeviceIdRef.current = result.deviceId || null;
      setFacingMode(targetMode);
      setActualFacingMode(result.actualFacingMode);
      setStream(result.stream);
      setCameraOpen(true);

      // Re-enumerate to ensure fresh device state
      await refreshDeviceEnumeration();
    } catch (err: any) {
      console.warn('[CAMERA] Camera switch error:', err);
      setStreamWarning(`Could not switch camera: ${err?.message || 'Camera mode unavailable'}. Please retry.`);
      // Clean up to prevent dead stream viewfinder
      setCameraOpen(false);
      setStream(null);
    } finally {
      setIsSwitching(false);
    }
  };

  // Capture snapshot frame from live video with stream health & readiness validation
  const takeSnapshot = () => {
    setStreamWarning(null);

    // 1. Verify stream health
    if (!isStreamHealthy(streamRef.current)) {
      setStreamWarning('Camera stream is not ready. Please retry.');
      return;
    }

    const video = videoRef.current;
    // 2. Verify video element readiness to prevent blank/zero-dimension frames
    const readiness = isVideoElementReady(video);
    if (!readiness.ready || !video) {
      setStreamWarning(readiness.reason || 'Camera stream is not ready. Please retry.');
      return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    const ctx = canvas.getContext('2d');

    if (!ctx) {
      setStreamWarning('Could not initialize image capture canvas. Please retry.');
      return;
    }

    // Draw real video frame to canvas
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const dataUri = canvas.toDataURL('image/jpeg', 0.85);

    // Stop live stream immediately upon capture to release camera resource
    const now = new Date();
    setCapturedImage(dataUri);
    setCaptureTime(now);
    setCameraOpen(false);
    stopStream();

    const userAgentStr = typeof navigator !== 'undefined' ? navigator.userAgent : 'Browser Client';
    const effectiveFacing = actualFacingMode || facingMode;

    // Notify parent of verified live evidence
    onEvidenceCaptured({
      image_base64: dataUri,
      capture_session_id: sessionIdRef.current,
      client_capture_timestamp: now.toISOString(),
      latitude: evidenceLocation?.latitude,
      longitude: evidenceLocation?.longitude,
      accuracy_meters: evidenceLocation?.accuracy,
      device_info: `${userAgentStr} [${effectiveFacing}]`,
      status: 'VALIDATED',
    });
  };

  // Retake photo
  const handleRetake = () => {
    setCapturedImage(null);
    setCaptureTime(null);
    setStreamWarning(null);
    onEvidenceCaptured(null);
    startCamera();
  };

  // Remove evidence
  const handleRemove = () => {
    setCapturedImage(null);
    setCaptureTime(null);
    setEvidenceLocation(null);
    setCameraOpen(false);
    setStreamWarning(null);
    stopStream();
    onEvidenceCaptured(null);
  };

  return (
    <div className="space-y-3">
      {/* 1. Captured Photo Preview State */}
      {capturedImage && (
        <div className="p-4 rounded-xl border border-emerald-200 bg-emerald-50/50 shadow-xs space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-emerald-100">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span className="text-xs font-bold text-emerald-950 uppercase tracking-wider font-mono">
                LIVE CAMERA EVIDENCE ATTACHED
              </span>
            </div>
            <button
              type="button"
              onClick={handleRemove}
              className="text-xs text-slate-400 hover:text-red-600 font-semibold p-1 transition-colors"
              title="Remove evidence"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-4">
            <div className="relative rounded-lg overflow-hidden border border-emerald-200 w-full sm:w-48 h-36 bg-black flex-shrink-0">
              <img
                src={capturedImage}
                alt="Captured Emergency Evidence"
                className="w-full h-full object-cover"
              />
              <span className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-black/70 text-emerald-400 text-[10px] font-mono font-bold">
                LIVE CAPTURE
              </span>
            </div>

            <div className="flex-1 space-y-2 text-xs text-slate-700 w-full">
              <div className="flex items-center gap-2">
                <Clock className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                <span className="font-mono text-[11px]">
                  Captured at: <strong>{captureTime?.toLocaleTimeString()}</strong> ({captureTime?.toLocaleDateString()})
                </span>
              </div>

              <div className="flex items-start gap-2">
                <MapPin className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0 mt-0.5" />
                <div className="font-mono text-[11px]">
                  {evidenceLocation ? (
                    <div>
                      <span>Coordinates: <strong>{evidenceLocation.latitude.toFixed(5)}, {evidenceLocation.longitude.toFixed(5)}</strong></span>
                      <div className="text-[10px] text-emerald-700 font-semibold">
                        GPS Accuracy: ±{evidenceLocation.accuracy}m
                      </div>
                    </div>
                  ) : (
                    <span className="text-slate-500 italic">GPS tagging unavailable at capture time</span>
                  )}
                </div>
              </div>

              <div className="pt-1 flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleRetake}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-300 hover:bg-slate-50 text-xs font-bold text-slate-700 shadow-2xs transition-all"
                >
                  <RefreshCw className="w-3.5 h-3.5 text-slate-500" />
                  <span>Retake Photo</span>
                </button>
                <span className="text-[11px] text-emerald-700 font-semibold flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Ready for Submission</span>
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 2. Active Viewfinder Live Camera State */}
      {cameraOpen && (
        <div className="p-3 sm:p-4 rounded-xl border border-slate-300 bg-slate-900 text-white shadow-lg space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-red-400">
                LIVE CAMERA VIEWFINDER
              </span>
              {/* Facing mode badge */}
              <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] font-mono text-slate-300 border border-slate-700 uppercase">
                {actualFacingMode === 'environment' ? 'BACK CAMERA' : 'FRONT CAMERA'}
              </span>
            </div>

            {/* GPS Tag Badge */}
            <div className="flex items-center gap-1.5">
              {gpsStatus === 'ready' && evidenceLocation && (
                <span className="px-2 py-0.5 rounded-md bg-emerald-950/80 border border-emerald-500/50 text-[10px] font-mono text-emerald-300 flex items-center gap-1">
                  <MapPin className="w-3 h-3 text-emerald-400" />
                  <span>GPS Tag Ready (±{evidenceLocation.accuracy}m)</span>
                </span>
              )}
              {gpsStatus === 'locating' && (
                <span className="px-2 py-0.5 rounded-md bg-amber-950/80 border border-amber-500/50 text-[10px] font-mono text-amber-300 flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin text-amber-400" />
                  <span>Acquiring GPS...</span>
                </span>
              )}
              {gpsStatus === 'unavailable' && (
                <span className="px-2 py-0.5 rounded-md bg-slate-800 border border-slate-700 text-[10px] font-mono text-slate-400">
                  GPS Unavailable
                </span>
              )}
            </div>
          </div>

          {/* Non-blocking Stream Notice / Warning */}
          {streamWarning && (
            <div className="p-2 rounded-lg bg-amber-900/60 border border-amber-500/50 text-amber-200 text-xs flex items-center gap-2">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
              <span>{streamWarning}</span>
            </div>
          )}

          {/* Viewfinder Canvas */}
          <div className="relative rounded-xl overflow-hidden bg-black aspect-video sm:max-h-80 w-full flex items-center justify-center border border-slate-700">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full h-full object-cover block"
            />
            {/* Viewfinder Target Overlay */}
            <div className="absolute inset-4 border border-white/20 rounded-lg pointer-events-none flex items-center justify-center">
              <div className="w-8 h-8 border-t border-l border-white/40 absolute top-2 left-2" />
              <div className="w-8 h-8 border-t border-r border-white/40 absolute top-2 right-2" />
              <div className="w-8 h-8 border-b border-l border-white/40 absolute bottom-2 left-2" />
              <div className="w-8 h-8 border-b border-r border-white/40 absolute bottom-2 right-2" />
            </div>
          </div>

          {/* Camera Action Buttons */}
          <div className="flex flex-wrap items-center justify-between gap-2.5 pt-1">
            <button
              type="button"
              onClick={() => {
                setCameraOpen(false);
                setStreamWarning(null);
                stopStream();
              }}
              className="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 transition-colors min-h-[44px] cursor-pointer"
            >
              Cancel
            </button>

            <button
              type="button"
              onClick={takeSnapshot}
              disabled={isSwitching}
              className="inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-xl bg-red-600 hover:bg-red-500 text-white text-xs sm:text-sm font-bold shadow-md transition-all active:scale-95 cursor-pointer disabled:opacity-50 min-h-[44px] touch-manipulation flex-1 sm:flex-none"
            >
              <Camera className="w-4 h-4" />
              <span>Capture Live Photo</span>
            </button>

            {hasMultipleCameras ? (
              <button
                type="button"
                onClick={switchCameraFacing}
                disabled={isSwitching}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition-colors disabled:opacity-50 min-h-[44px] cursor-pointer"
                title="Switch Camera (Front / Back)"
              >
                {isSwitching ? (
                  <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
                ) : (
                  <FlipHorizontal className="w-4 h-4" />
                )}
                <span className="hidden sm:inline">Switch Camera</span>
              </button>
            ) : (
              <div className="w-4" />
            )}
          </div>
        </div>
      )}

      {/* 3. Idle / Initial State */}
      {!cameraOpen && !capturedImage && (
        <div className="p-4 rounded-xl border border-dashed border-slate-300 bg-slate-50/80 text-center space-y-3">
          <div className="flex flex-col items-center justify-center space-y-2">
            <div className="w-10 h-10 rounded-full bg-red-50 border border-red-200 text-[#dc2626] flex items-center justify-center">
              <Camera className="w-5 h-5" />
            </div>
            <div>
              <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider font-mono">
                CAPTURE LIVE CAMERA EVIDENCE
              </h4>
              <p className="text-[11px] text-slate-500 max-w-md mx-auto mt-0.5">
                Take a fresh live photo from your device camera to provide visual proof and geolocation verification to the Emergency Operations Center.
              </p>
            </div>
          </div>

          {cameraError && (
            <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs text-left flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-bold">Notice: </span>
                <span>{cameraError}</span>
              </div>
            </div>
          )}

          {streamWarning && (
            <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs text-left flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <span className="font-bold">Notice: </span>
                <span>{streamWarning}</span>
              </div>
            </div>
          )}

          <div className="pt-1">
            <button
              type="button"
              onClick={startCamera}
              disabled={capturing}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-sans font-bold shadow-sm transition-all active:scale-95 cursor-pointer disabled:opacity-50"
            >
              {capturing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-red-500" />
                  <span>Accessing Device Camera...</span>
                </>
              ) : (
                <>
                  <Camera className="w-4 h-4 text-red-400" />
                  <span>Open Camera to Capture</span>
                </>
              )}
            </button>
          </div>

          <p className="text-[10px] text-slate-400 font-mono">
            Direct browser camera capture • No gallery file uploads permitted • Non-blocking if camera is unavailable
          </p>
        </div>
      )}
    </div>
  );
};
