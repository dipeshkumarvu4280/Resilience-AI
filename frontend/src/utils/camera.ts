/**
 * Camera Hardening Utilities
 * Provides resilient media stream acquisition, mobile front/back camera detection,
 * post-permission device enumeration, stream health validation, and safe resource cleanup.
 */

export type CameraFacingMode = 'environment' | 'user';

export interface CameraStreamResult {
  stream: MediaStream;
  actualFacingMode: CameraFacingMode;
  deviceId?: string;
  isFallback: boolean;
}

export interface VideoReadinessResult {
  ready: boolean;
  reason?: string;
}

/**
 * Safely enumerate available video input devices.
 * Returns an empty array if navigator/mediaDevices is unavailable or permissions not yet granted.
 */
export async function getAvailableVideoInputs(): Promise<MediaDeviceInfo[]> {
  if (
    typeof window === 'undefined' ||
    typeof navigator === 'undefined' ||
    !navigator.mediaDevices?.enumerateDevices
  ) {
    return [];
  }

  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((d) => d.kind === 'videoinput');
  } catch (err) {
    console.warn('[CAMERA] Device enumeration error:', err);
    return [];
  }
}

/**
 * Determine if device has multiple video inputs based on authoritative list
 */
export function checkHasMultipleCameras(devices: MediaDeviceInfo[]): boolean {
  return devices.length > 1;
}

/**
 * Select the best matching deviceId for the requested facing mode from enumerated devices.
 * Uses getCapabilities() where supported, followed by label heuristics and device rotation.
 */
export function selectDeviceIdForFacingMode(
  desiredMode: CameraFacingMode,
  devices: MediaDeviceInfo[],
  currentDeviceId?: string | null
): string | null {
  if (!devices || devices.length === 0) {
    return null;
  }

  if (devices.length === 1) {
    return devices[0].deviceId;
  }

  // 1. Inspect device capabilities if available in modern browsers
  for (const device of devices) {
    if (typeof (device as any).getCapabilities === 'function') {
      try {
        const capabilities = (device as any).getCapabilities();
        if (
          Array.isArray(capabilities?.facingMode) &&
          capabilities.facingMode.includes(desiredMode)
        ) {
          return device.deviceId;
        }
      } catch {
        // Ignore capability query error
      }
    }
  }

  // 2. Heuristic matching on device label (language/vendor agnostic keywords)
  const isBackKeyword = /back|rear|environment|outward|world|main/i;
  const isFrontKeyword = /front|user|selfie|inward|facetime|forward/i;

  const targetRegex = desiredMode === 'environment' ? isBackKeyword : isFrontKeyword;
  const labelMatched = devices.find((d) => d.label && targetRegex.test(d.label));
  if (labelMatched && labelMatched.deviceId) {
    return labelMatched.deviceId;
  }

  // 3. If switching and current device is known, select the other device
  if (currentDeviceId) {
    const otherDevice = devices.find((d) => d.deviceId && d.deviceId !== currentDeviceId);
    if (otherDevice) {
      return otherDevice.deviceId;
    }
  }

  // 4. Default index heuristics for common mobile devices:
  // On many Android phones with multiple cameras, back is index 0 or 1.
  if (desiredMode === 'environment') {
    return devices[0].deviceId || null;
  } else {
    return devices[devices.length - 1].deviceId || devices[0].deviceId || null;
  }
}

/**
 * Resilient multi-tier stream acquisition:
 * Tier 1: Request facingMode with ideal constraints
 * Tier 2: Enumerate devices, pick candidate deviceId, request with deviceId constraint
 * Tier 3: Generic video: true compatibility fallback
 */
export async function getStreamForFacingMode(
  desiredMode: CameraFacingMode,
  options?: {
    preferredDeviceId?: string | null;
  }
): Promise<CameraStreamResult> {
  if (
    typeof navigator === 'undefined' ||
    !navigator.mediaDevices ||
    !navigator.mediaDevices.getUserMedia
  ) {
    throw new Error('Camera access is not supported by your browser or environment.');
  }

  // Tier 1: Try ideal facingMode and high-resolution standard constraints
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: desiredMode },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    });

    const activeTrack = stream.getVideoTracks()[0];
    const trackSettings = activeTrack?.getSettings?.();
    const resolvedMode = (trackSettings?.facingMode as CameraFacingMode) || desiredMode;
    const resolvedDeviceId = trackSettings?.deviceId || options?.preferredDeviceId || undefined;

    return {
      stream,
      actualFacingMode: resolvedMode,
      deviceId: resolvedDeviceId,
      isFallback: false,
    };
  } catch (tier1Error: any) {
    console.warn('[CAMERA] Tier 1 ideal facingMode request failed:', tier1Error);

    // If permission was explicitly denied, throw immediately
    if (
      tier1Error?.name === 'NotAllowedError' ||
      tier1Error?.name === 'PermissionDeniedError' ||
      tier1Error?.name === 'SecurityError'
    ) {
      throw tier1Error;
    }

    // Tier 2: Attempt deviceId-based selection from enumerated devices
    try {
      const devices = await getAvailableVideoInputs();
      const candidateDeviceId = selectDeviceIdForFacingMode(
        desiredMode,
        devices,
        options?.preferredDeviceId
      );

      if (candidateDeviceId) {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: {
              deviceId: { exact: candidateDeviceId },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
            audio: false,
          });

          const activeTrack = stream.getVideoTracks()[0];
          const trackSettings = activeTrack?.getSettings?.();
          const resolvedMode = (trackSettings?.facingMode as CameraFacingMode) || desiredMode;

          return {
            stream,
            actualFacingMode: resolvedMode,
            deviceId: candidateDeviceId,
            isFallback: false,
          };
        } catch (exactErr) {
          console.warn('[CAMERA] Exact deviceId constraint failed, retrying without exact:', exactErr);
          const stream = await navigator.mediaDevices.getUserMedia({
            video: {
              deviceId: candidateDeviceId,
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
            audio: false,
          });

          const activeTrack = stream.getVideoTracks()[0];
          const trackSettings = activeTrack?.getSettings?.();
          const resolvedMode = (trackSettings?.facingMode as CameraFacingMode) || desiredMode;

          return {
            stream,
            actualFacingMode: resolvedMode,
            deviceId: candidateDeviceId,
            isFallback: false,
          };
        }
      }
    } catch (tier2Error: any) {
      console.warn('[CAMERA] Tier 2 device selection failed:', tier2Error);
      if (
        tier2Error?.name === 'NotAllowedError' ||
        tier2Error?.name === 'PermissionDeniedError' ||
        tier2Error?.name === 'SecurityError'
      ) {
        throw tier2Error;
      }
    }

    // Tier 3: Final generic video compatibility fallback
    console.warn('[CAMERA] Falling back to generic video: true');
    const stream = await navigator.mediaDevices.getUserMedia({
      video: true,
      audio: false,
    });

    const activeTrack = stream.getVideoTracks()[0];
    const trackSettings = activeTrack?.getSettings?.();
    const resolvedMode = (trackSettings?.facingMode as CameraFacingMode) || desiredMode;

    return {
      stream,
      actualFacingMode: resolvedMode,
      deviceId: trackSettings?.deviceId,
      isFallback: true,
    };
  }
}

/**
 * Validate that the media stream is active and has at least one live video track.
 */
export function isStreamHealthy(stream: MediaStream | null): boolean {
  if (!stream) return false;
  if (!stream.active) return false;
  const tracks = stream.getVideoTracks();
  if (tracks.length === 0) return false;
  return tracks.some((t) => t.readyState === 'live' && t.enabled);
}

/**
 * Validate video element readiness prior to snapshot capture to prevent blank or zero-dimension frames.
 */
export function isVideoElementReady(video: HTMLVideoElement | null): VideoReadinessResult {
  if (!video) {
    return { ready: false, reason: 'Camera video element is not mounted.' };
  }

  // readyState >= 2 (HAVE_CURRENT_DATA) indicates video frame data is ready to be drawn
  if (typeof video.readyState === 'number' && video.readyState < 2) {
    return {
      ready: false,
      reason: 'Camera video is still buffering. Please wait a moment and tap Capture again.',
    };
  }

  if (video.videoWidth === 0 || video.videoHeight === 0) {
    return {
      ready: false,
      reason: 'Camera video dimensions not ready. Please wait a moment and tap Capture again.',
    };
  }

  return { ready: true };
}

/**
 * Safely stop all tracks on a MediaStream.
 */
export function stopMediaStream(stream: MediaStream | null): void {
  if (!stream) return;
  try {
    stream.getTracks().forEach((track) => {
      try {
        track.stop();
      } catch (err) {
        console.warn('[CAMERA] Error stopping track:', err);
      }
    });
  } catch (err) {
    console.warn('[CAMERA] Error stopping stream tracks:', err);
  }
}
