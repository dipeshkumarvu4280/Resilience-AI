import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { TacticalBackground } from '../../components/layout/TacticalBackground';
import { EmergencyEmblem } from '../../components/common/EmergencyEmblem';
import { LiveCameraCapture } from '../../components/citizen/LiveCameraCapture';
import { ErrorBoundary } from '../../components/common/ErrorBoundary';
import { LanguageSelector } from '../../components/common/LanguageSelector';
import { useLanguage } from '../../context/LanguageContext';
import { loadGoogleMaps, hasGoogleMapsApiKey } from '../../utils/googleMapsLoader';
import {
  Flame,
  Waves,
  HeartPulse,
  Car,
  Wind,
  Mountain,
  Building2,
  UserX,
  AlertTriangle,
  MapPin,
  Navigation,
  ShieldCheck,
  Copy,
  Check,
  ArrowLeft,
  Siren,
  Phone,
  User,
  X,
  Loader2,
  ExternalLink,
  HelpCircle,
  AlertCircle,
  Edit3,
  Save,
  CheckCircle2,
  Bell,
  BellRing,
  BellOff,
} from 'lucide-react';
import type {
  EmergencyType,
  CitizenImpactLevel,
  LiveEvidencePayload,
  EmergencyReportResponse,
} from '../../types';
import {
  createEmergencyReport,
  getEmergencyReport,
  updateCitizenReport,
  reverseGeocodeLocation,
} from '../../services/api';
import {
  registerServiceWorkerAndSubscribe,
  getComprehensivePushState,
  sendTestPushNotification,
} from '../../utils/webPush';
import type { WebPushState } from '../../types';

const MAP_LIGHT_STYLES: google.maps.MapTypeStyle[] = [
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#cce5ff' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#f8fafc' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#ffffff' }] },
  { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#e2e8f0' }] },
  { featureType: 'poi', elementType: 'geometry', stylers: [{ color: '#f1f5f9' }] },
  { featureType: 'administrative', elementType: 'labels.text.fill', stylers: [{ color: '#475569' }] },
];

export const ReportEmergencyPage: React.FC = () => {
  console.log('[REPORT-EMERGENCY] route mounted');
  const navigate = useNavigate();
  const { language, t } = useLanguage();
  const [searchParams] = useSearchParams();
  const viewReportId = searchParams.get('id');

  // Form State
  const [emergencyType, setEmergencyType] = useState<EmergencyType>('Medical Emergency');
  const [userManuallySelectedType, setUserManuallySelectedType] = useState(false);
  const [autoDetectedTypeNotice, setAutoDetectedTypeNotice] = useState<string | null>(null);
  const [citizenImpactLevel, setCitizenImpactLevel] = useState<CitizenImpactLevel | null>(null);
  const [description, setDescription] = useState('');
  const [latitude, setLatitude] = useState<string>('');
  const [longitude, setLongitude] = useState<string>('');
  const [address, setAddress] = useState('');
  const [manualZone, setManualZone] = useState('');
  const [locating, setLocating] = useState(false);
  const [locationStatus, setLocationStatus] = useState<string | null>(null);

  // Google Maps State & Refs
  const [mapType, setMapType] = useState<'roadmap' | 'satellite'>('roadmap');
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const googleInstanceRef = useRef<typeof google | null>(null);
  const markerRef = useRef<google.maps.Marker | null>(null);


  const inferEmergencyTypeFromText = (text: string): EmergencyType | null => {
    const lower = text.toLowerCase();
    
    // Flood / Waterlogging indicators (English, Hindi, transliterated)
    if (
      lower.includes('paani') || lower.includes('pani') || lower.includes('nadi') ||
      lower.includes('flood') || lower.includes('waterlog') || lower.includes('water rising') ||
      lower.includes('submerged') || lower.includes('drowning') || lower.includes('jal-bharaav') ||
      lower.includes('water entered') || lower.includes('river water') || lower.includes('overflow')
    ) {
      return 'Flood';
    }

    // Fire indicators
    if (
      lower.includes('fire') || lower.includes('aag') || lower.includes('smoke') ||
      lower.includes('dhuan') || lower.includes('flames') || lower.includes('blaze') ||
      lower.includes('cylinder blast') || lower.includes('burning')
    ) {
      return 'Fire';
    }

    // Cyclone / Storm indicators
    if (
      lower.includes('cyclone') || lower.includes('toofan') || lower.includes('storm') ||
      lower.includes('high wind') || lower.includes('heavy rain and wind') || lower.includes('tornado')
    ) {
      return 'Cyclone / Storm';
    }

    // Landslide indicators
    if (
      lower.includes('landslide') || lower.includes('pahad') || lower.includes('boulder') ||
      lower.includes('mudslide') || lower.includes('debris flow') || lower.includes('rockfall')
    ) {
      return 'Landslide';
    }

    // Building Collapse indicators
    if (
      lower.includes('building collapse') || lower.includes('wall collapse') ||
      lower.includes('chhat gir') || lower.includes('structural collapse') || lower.includes('malba')
    ) {
      return 'Building Collapse';
    }

    // Road Accident indicators
    if (
      lower.includes('accident') || lower.includes('crash') || lower.includes('collision') ||
      lower.includes('hit and run') || lower.includes('vehicle overturned')
    ) {
      return 'Road Accident';
    }

    // Medical Emergency indicators
    if (
      lower.includes('heart attack') || lower.includes('unconscious') || lower.includes('bleeding heavily') ||
      lower.includes('ambulance needed') || lower.includes('fracture') || lower.includes('pregnant emergency')
    ) {
      return 'Medical Emergency';
    }

    return null;
  };

  const handleDescriptionChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setDescription(val);

    if (!userManuallySelectedType && val.trim().length >= 4) {
      const detected = inferEmergencyTypeFromText(val);
      if (detected && detected !== emergencyType) {
        setEmergencyType(detected);
        setAutoDetectedTypeNotice(`Auto-selected "${detected}" based on your observation.`);
      }
    }
  };

  // Live Camera Evidence State
  const [evidencePayload, setEvidencePayload] = useState<LiveEvidencePayload | null>(null);

  // Citizen & Anti-bot State
  const [fullName, setFullName] = useState('');
  const [phone, setPhone] = useState('');
  const [botHoneypot, setBotHoneypot] = useState('');

  // Submission State
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedReport, setSubmittedReport] = useState<EmergencyReportResponse | null>(null);
  const [copiedId, setCopiedId] = useState(false);

  // Web Push Notification 7-State Machine
  const [comprehensivePushState, setComprehensivePushState] = useState<WebPushState>('PERMISSION_NOT_REQUESTED');
  const [pushSubscribing, setPushSubscribing] = useState(false);
  const [pushErrorNotice, setPushErrorNotice] = useState<string | null>(null);
  const [testPushSending, setTestPushSending] = useState(false);
  const [testPushMessage, setTestPushMessage] = useState<string | null>(null);

  useEffect(() => {
    const checkState = async () => {
      if (
        submittedReport?.report_id &&
        typeof Notification !== 'undefined' &&
        Notification.permission === 'granted'
      ) {
        await registerServiceWorkerAndSubscribe(
          submittedReport.report_id,
          submittedReport.safety_guidance_token
        ).catch(() => {});
      }
      const s = await getComprehensivePushState();
      setComprehensivePushState(s);
    };
    checkState();
  }, [submittedReport]);

  const handleOptInPush = async () => {
    setPushSubscribing(true);
    setPushErrorNotice(null);
    setComprehensivePushState('SUBSCRIPTION_PENDING');
    try {
      const res = await registerServiceWorkerAndSubscribe(
        submittedReport?.report_id,
        submittedReport?.safety_guidance_token
      );
      if (res.success) {
        setComprehensivePushState('ACTIVE');
      } else {
        const s = await getComprehensivePushState();
        setComprehensivePushState(s);
        setPushErrorNotice(res.error || 'Failed to enable emergency alerts.');
      }
    } catch (err: any) {
      const s = await getComprehensivePushState();
      setComprehensivePushState(s);
      setPushErrorNotice(err.message || 'Error subscribing to notifications.');
    } finally {
      setPushSubscribing(false);
    }
  };

  const handleSendTestPush = async () => {
    setTestPushSending(true);
    setTestPushMessage(null);
    try {
      if (
        submittedReport?.report_id &&
        typeof Notification !== 'undefined' &&
        Notification.permission === 'granted'
      ) {
        await registerServiceWorkerAndSubscribe(
          submittedReport.report_id,
          submittedReport.safety_guidance_token
        ).catch(() => {});
      }
      const res = await sendTestPushNotification(submittedReport?.report_id);
      setTestPushMessage(res.message);
    } catch (err: any) {
      setTestPushMessage('Failed to send test push.');
    } finally {
      setTestPushSending(false);
    }
  };

  // Report In-place Modification State
  const [isEditingReport, setIsEditingReport] = useState(false);
  const [editDescription, setEditDescription] = useState('');
  const [editImpactLevel, setEditImpactLevel] = useState<CitizenImpactLevel>('NOT_SURE');
  const [editFullName, setEditFullName] = useState('');
  const [editPhone, setEditPhone] = useState('');
  const [editAdditionalNotes, setEditAdditionalNotes] = useState('');
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editSuccessNotice, setEditSuccessNotice] = useState<string | null>(null);
  const [editErrorNotice, setEditErrorNotice] = useState<string | null>(null);

  // Sync edit form fields whenever active report changes
  useEffect(() => {
    if (submittedReport) {
      setEditDescription(submittedReport.description || '');
      setEditImpactLevel(submittedReport.citizen_impact_level || 'NOT_SURE');
      setEditFullName(submittedReport.citizen_name || '');
      setEditPhone(submittedReport.citizen_phone || '');
    }
  }, [submittedReport]);

  // If a report ID was passed in query or stored in sessionStorage, load its receipt safely
  useEffect(() => {
    const isExplicitNew = searchParams.get('new') === 'true';
    if (viewReportId) {
      getEmergencyReport(viewReportId)
        .then((data: EmergencyReportResponse) => {
          if (data && data.report_id) {
            setSubmittedReport(data);
            sessionStorage.setItem('resilience_active_citizen_report', JSON.stringify(data));
            setError(null);
          }
        })
        .catch((err: unknown) => {
          console.warn('Could not fetch report receipt:', err);
          // Only show error if no matching submitted report exists in memory or session
          const cached = sessionStorage.getItem('resilience_active_citizen_report');
          let hasLocalMatch = false;
          if (cached) {
            try {
              const parsed = JSON.parse(cached);
              if (parsed?.report_id === viewReportId) {
                setSubmittedReport(parsed);
                hasLocalMatch = true;
              }
            } catch (e) {
              console.warn('Cached report parse error:', e);
            }
          }
          if (!hasLocalMatch) {
            setError('Could not retrieve requested report receipt. You can create a new emergency report below.');
          }
        });
    } else if (!isExplicitNew) {
      const cached = sessionStorage.getItem('resilience_active_citizen_report');
      if (cached) {
        try {
          const parsed = JSON.parse(cached);
          if (parsed && parsed.report_id) {
            setSubmittedReport(parsed);
          }
        } catch (e) {
          console.warn('Failed to parse cached active citizen report:', e);
        }
      }
    }
  }, [viewReportId, searchParams]);

  const emergencyTypesList: { type: EmergencyType; label: string; icon: any }[] = [
    { type: 'Medical Emergency', label: 'Medical Emergency', icon: HeartPulse },
    { type: 'Fire', label: 'Fire Outbreak', icon: Flame },
    { type: 'Flood', label: 'Flood / Waterlogging', icon: Waves },
    { type: 'Road Accident', label: 'Road Accident', icon: Car },
    { type: 'Cyclone / Storm', label: 'Cyclone / High Winds', icon: Wind },
    { type: 'Landslide', label: 'Landslide', icon: Mountain },
    { type: 'Building Collapse', label: 'Building Collapse', icon: Building2 },
    { type: 'Missing / Trapped Person', label: 'Trapped / Missing', icon: UserX },
    { type: 'Other', label: 'Other Emergency', icon: AlertTriangle },
  ];

  const impactLevelsList: {
    level: CitizenImpactLevel;
    label: string;
    description: string;
    color: string;
    badgeColor: string;
  }[] = [
    {
      level: 'LOW',
      label: 'Low',
      description: 'Minor damage or disruption. No immediate life threat or structural collapse.',
      color: 'border-blue-200 bg-blue-50/60 text-blue-900 hover:border-blue-400',
      badgeColor: 'bg-blue-100 text-blue-800 border-blue-200',
    },
    {
      level: 'MEDIUM',
      label: 'Medium',
      description: 'Moderate hazard with localized property damage. Standard emergency support needed.',
      color: 'border-amber-200 bg-amber-50/60 text-amber-900 hover:border-amber-400',
      badgeColor: 'bg-amber-100 text-amber-800 border-amber-200',
    },
    {
      level: 'HIGH',
      label: 'High',
      description: 'Severe threat to safety, spreading hazard, or major injuries. Urgent intervention required.',
      color: 'border-orange-200 bg-orange-50/60 text-orange-900 hover:border-orange-400',
      badgeColor: 'bg-orange-100 text-orange-800 border-orange-200',
    },
    {
      level: 'CRITICAL',
      label: 'Critical',
      description: 'Immediate life-threatening danger, catastrophic incident, or trapped individuals.',
      color: 'border-red-200 bg-red-50/60 text-red-900 hover:border-red-400',
      badgeColor: 'bg-red-100 text-red-800 border-red-200',
    },
    {
      level: 'NOT_SURE',
      label: "I'm not sure",
      description: 'Uncertain severity. Watch officer and AI intelligence will evaluate and triage.',
      color: 'border-slate-200 bg-slate-50/80 text-slate-800 hover:border-slate-400',
      badgeColor: 'bg-slate-100 text-slate-700 border-slate-200',
    },
  ];

  const createEmergencyPinSvg = () => {
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 40 40">
        <defs>
          <filter id="shadow-pin" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#000000" flood-opacity="0.35"/>
          </filter>
        </defs>
        <circle cx="20" cy="20" r="18" fill="#dc2626" fill-opacity="0.18" stroke="#dc2626" stroke-width="1.5" stroke-dasharray="3 2"/>
        <path d="M20 2 C13.37 2 8 7.37 8 14 C8 23 20 36 20 36 C20 36 32 23 32 14 C32 7.37 26.63 2 20 2 Z" fill="#dc2626" stroke="#ffffff" stroke-width="2" filter="url(#shadow-pin)"/>
        <circle cx="20" cy="14" r="5" fill="#ffffff"/>
        <circle cx="20" cy="14" r="2.5" fill="#dc2626"/>
      </svg>
    `;
    return 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg);
  };

  const handleToggleMapType = (type: 'roadmap' | 'satellite') => {
    setMapType(type);
    if (googleMapRef.current) {
      googleMapRef.current.setMapTypeId(type);
      if (type === 'roadmap') {
        googleMapRef.current.setOptions({ styles: MAP_LIGHT_STYLES });
      } else {
        googleMapRef.current.setOptions({ styles: [] });
      }
    }
  };

  // Google Map Initialization & Event Listeners
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

        const initialLat = parseFloat(latitude) || 16.2954;
        const initialLng = parseFloat(longitude) || 80.6482;
        const hasCoords = !isNaN(parseFloat(latitude)) && !isNaN(parseFloat(longitude));

        const map = new googleObj.maps.Map(mapContainerRef.current, {
          center: { lat: initialLat, lng: initialLng },
          zoom: hasCoords ? 15 : 12,
          minZoom: 4,
          maxZoom: 19,
          mapTypeId: mapType,
          disableDefaultUI: true,
          zoomControl: true,
          gestureHandling: 'cooperative',
          clickableIcons: false,
          styles: mapType === 'roadmap' ? MAP_LIGHT_STYLES : [],
        });

        // Add draggable marker
        const marker = new googleObj.maps.Marker({
          map: hasCoords ? map : null,
          position: { lat: initialLat, lng: initialLng },
          draggable: true,
          title: 'Emergency Epicenter',
          icon: {
            url: createEmergencyPinSvg(),
            scaledSize: new googleObj.maps.Size(36, 36),
            anchor: new googleObj.maps.Point(18, 34),
          },
        });

        // Dragend listener
        marker.addListener('dragend', async () => {
          const pos = marker.getPosition();
          if (pos) {
            const lat = pos.lat();
            const lon = pos.lng();
            setLatitude(lat.toFixed(6));
            setLongitude(lon.toFixed(6));
            setLocationStatus('Resolving address from map pin...');
            try {
              const geoRes = await reverseGeocodeLocation(lat, lon);
              if (geoRes && (geoRes.street_address || geoRes.address)) {
                const street = geoRes.street_address || geoRes.address || '';
                const zone = geoRes.zone_or_district || geoRes.city || geoRes.state || '';
                setAddress(street);
                if (zone) setManualZone(zone);
                setLocationStatus(`📍 ${street}${zone ? ` • Zone: ${zone}` : ''}`);
              } else {
                setLocationStatus(`📍 Pin Position: ${lat.toFixed(5)}, ${lon.toFixed(5)}`);
              }
            } catch {
              setLocationStatus(`📍 Pin Position: ${lat.toFixed(5)}, ${lon.toFixed(5)}`);
            }
          }
        });

        // Map Click listener to drop/move pin
        map.addListener('click', async (e: google.maps.MapMouseEvent) => {
          if (e.latLng) {
            const lat = e.latLng.lat();
            const lon = e.latLng.lng();
            marker.setPosition({ lat, lng: lon });
            marker.setMap(map);
            setLatitude(lat.toFixed(6));
            setLongitude(lon.toFixed(6));
            setLocationStatus('Resolving address from map pin...');
            try {
              const geoRes = await reverseGeocodeLocation(lat, lon);
              if (geoRes && (geoRes.street_address || geoRes.address)) {
                const street = geoRes.street_address || geoRes.address || '';
                const zone = geoRes.zone_or_district || geoRes.city || geoRes.state || '';
                setAddress(street);
                if (zone) setManualZone(zone);
                setLocationStatus(`📍 ${street}${zone ? ` • Zone: ${zone}` : ''}`);
              } else {
                setLocationStatus(`📍 Pin Position: ${lat.toFixed(5)}, ${lon.toFixed(5)}`);
              }
            } catch {
              setLocationStatus(`📍 Pin Position: ${lat.toFixed(5)}, ${lon.toFixed(5)}`);
            }
          }
        });

        googleMapRef.current = map;
        markerRef.current = marker;
      } catch (err) {
        console.warn('Could not initialize Google Map for citizen report:', err);
      }
    };

    initMap();
    return () => {
      isMounted = false;
    };
  }, []);

  // Geolocation & Reverse Geocoding Handler safely invoked only on user action
  const handleGetLocation = () => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setLocationStatus('Geolocation is not supported by your browser. Please enter coordinates or address manually.');
      return;
    }

    setLocating(true);
    setLocationStatus('Acquiring precise GPS coordinates...');

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const lat = position.coords.latitude;
        const lon = position.coords.longitude;
        const acc = Math.round(position.coords.accuracy);
        setLatitude(lat.toFixed(6));
        setLongitude(lon.toFixed(6));

        if (googleMapRef.current && markerRef.current) {
          googleMapRef.current.panTo({ lat, lng: lon });
          googleMapRef.current.setZoom(16);
          markerRef.current.setPosition({ lat, lng: lon });
          markerRef.current.setMap(googleMapRef.current);
        }

        setLocationStatus('Resolving address...');

        try {
          const geoRes = await reverseGeocodeLocation(lat, lon);
          if (geoRes && (geoRes.street_address || geoRes.address)) {
            const resolvedStreet = geoRes.street_address || geoRes.address || '';
            const resolvedZone = geoRes.zone_or_district || geoRes.city || geoRes.state || '';
            setAddress(resolvedStreet);
            if (resolvedZone) {
              setManualZone(resolvedZone);
            }
            setLocationStatus(`📍 ${resolvedStreet}${resolvedZone ? ` • Zone: ${resolvedZone}` : ''} (Accuracy: ±${acc}m)`);
          } else {
            setLocationStatus(`📍 GPS Captured: ${lat.toFixed(5)}, ${lon.toFixed(5)} (Accuracy: ±${acc}m)`);
          }
        } catch {
          setLocationStatus(`📍 GPS Captured: ${lat.toFixed(5)}, ${lon.toFixed(5)} (Accuracy: ±${acc}m)`);
        } finally {
          setLocating(false);
        }
      },
      (err) => {
        setLocating(false);
        if (err?.code === err?.PERMISSION_DENIED) {
          setLocationStatus('GPS permission was denied. You can manually enter your street address and coordinates below.');
        } else {
          setLocationStatus('Location unavailable. Please enter coordinates or street address manually.');
        }
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  };

  const handleManualResolveAddress = async () => {
    const latNum = parseFloat(latitude);
    const lonNum = parseFloat(longitude);
    if (isNaN(latNum) || isNaN(lonNum) || latNum < -90 || latNum > 90 || lonNum < -180 || lonNum > 180) {
      setError('Please provide valid coordinates (Latitude -90..90, Longitude -180..180) before resolving address.');
      return;
    }

    if (googleMapRef.current && markerRef.current) {
      googleMapRef.current.panTo({ lat: latNum, lng: lonNum });
      googleMapRef.current.setZoom(15);
      markerRef.current.setPosition({ lat: latNum, lng: lonNum });
      markerRef.current.setMap(googleMapRef.current);
    }

    setLocating(true);
    setLocationStatus('Resolving address...');
    try {
      const geoRes = await reverseGeocodeLocation(latNum, lonNum);
      if (geoRes && (geoRes.street_address || geoRes.address)) {
        const resolvedStreet = geoRes.street_address || geoRes.address || '';
        const resolvedZone = geoRes.zone_or_district || geoRes.city || geoRes.state || '';
        setAddress(resolvedStreet);
        if (resolvedZone) {
          setManualZone(resolvedZone);
        }
        setLocationStatus(`📍 ${resolvedStreet}${resolvedZone ? ` • Zone: ${resolvedZone}` : ''}`);
      } else {
        setLocationStatus('Address could not be resolved. Coordinates are still available.');
      }
    } catch {
      setLocationStatus('Address could not be resolved. Coordinates are still available.');
    } finally {
      setLocating(false);
    }
  };

  // Submit Report Handler
  const handleSubmitReport = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!fullName || fullName.trim().length < 2) {
      setError('Please provide your full name (at least 2 characters).');
      return;
    }

    if (!phone || phone.trim().length < 7) {
      setError('Please provide a valid reachable phone number (7-15 digits).');
      return;
    }

    if (!citizenImpactLevel) {
      setError('Please select an observed citizen impact level (or select "I\'m not sure").');
      return;
    }

    if (!description || description.trim().length < 10) {
      setError('Please provide a descriptive explanation of the incident (at least 10 characters).');
      return;
    }

    const latNum = parseFloat(latitude);
    const lonNum = parseFloat(longitude);

    if (isNaN(latNum) || isNaN(lonNum) || latNum < -90 || latNum > 90 || lonNum < -180 || lonNum > 180) {
      setError('Valid latitude (-90 to +90) and longitude (-180 to +180) are required. Use "Use My Location" or input coordinates.');
      return;
    }

    setSubmitting(true);

    try {
      const payload = {
        full_name: fullName.trim(),
        phone: phone.trim(),
        emergency_type: emergencyType,
        citizen_impact_level: citizenImpactLevel,
        description: description.trim(),
        preferred_language: language,
        location: {
          latitude: latNum,
          longitude: lonNum,
          address: address.trim() || undefined,
          manual_zone: manualZone.trim() || undefined,
        },
        bot_honeypot: botHoneypot || undefined,
        media: [],
        evidence: evidencePayload || undefined,
      };

      const response = await createEmergencyReport(payload);
      if (response && (response.report_id || response.id)) {
        const canonicalResponse = {
          ...response,
          report_id: response.report_id || response.id,
        };
        setError(null);
        setSubmittedReport(canonicalResponse);
        sessionStorage.setItem('resilience_active_citizen_report', JSON.stringify(canonicalResponse));

        // Deterministic push association if notification permission is already granted
        if (typeof Notification !== 'undefined' && Notification.permission === 'granted' && canonicalResponse.report_id) {
          try {
            console.log(`[WebPush] Auto-associating subscription with report_id=${canonicalResponse.report_id}`);
            await registerServiceWorkerAndSubscribe(
              canonicalResponse.report_id,
              canonicalResponse.safety_guidance_token
            );
          } catch (pushErr) {
            console.warn('[WebPush] Auto-association on submission notice:', pushErr);
          }
        }

        navigate(`/report-emergency?id=${canonicalResponse.report_id}`, { replace: true });
        if (typeof window !== 'undefined') {
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
      } else {
        throw new Error('Invalid response structure received from server.');
      }
    } catch (err: any) {
      console.error('[REPORT-SUBMIT-ERROR]', err);
      const backendError = err.response?.data?.detail;
      if (backendError) {
        setError(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
      } else if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        setError('Submission status could not be confirmed immediately due to network latency. Please check your active report status before resubmitting.');
      } else if (typeof navigator !== 'undefined' && !navigator.onLine) {
        setError('Network connection offline. Please check your internet connection before submitting.');
      } else {
        setError(err.message || 'Failed to submit emergency report. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdateReport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!submittedReport) return;
    setEditErrorNotice(null);
    setEditSuccessNotice(null);

    if (editDescription.trim().length < 10) {
      setEditErrorNotice('Description must be at least 10 characters.');
      return;
    }

    setEditSubmitting(true);
    try {
      const updatePayload = {
        citizen_token: submittedReport.safety_guidance_token || undefined,
        description: editDescription.trim(),
        citizen_impact_level: editImpactLevel,
        full_name: editFullName.trim() || undefined,
        phone: editPhone.trim() || undefined,
        additional_notes: editAdditionalNotes.trim() || undefined,
      };

      const updated = await updateCitizenReport(
        submittedReport.report_id,
        updatePayload,
        submittedReport.safety_guidance_token || undefined
      );

      setSubmittedReport(updated);
      sessionStorage.setItem('resilience_active_citizen_report', JSON.stringify(updated));
      setEditSuccessNotice('Emergency report updated successfully. Safety guidance was re-evaluated.');
      setEditAdditionalNotes('');
      setIsEditingReport(false);
      setTimeout(() => setEditSuccessNotice(null), 6000);
    } catch (err: any) {
      setEditErrorNotice(err.response?.data?.detail || 'Failed to update report details.');
    } finally {
      setEditSubmitting(false);
    }
  };

  const copyToClipboard = (text: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2500);
    }
  };

  return (
    <div className="relative min-h-screen text-slate-900 py-6 sm:py-10 px-4 sm:px-6 lg:px-8 bg-[#EEF2F6] selection:bg-red-100 selection:text-red-900">
      <TacticalBackground />
      {/* Top Brand Header */}
      <header className="relative z-10 max-w-4xl mx-auto w-full flex flex-wrap items-center justify-between gap-3 mb-6 pb-4 border-b border-slate-200/80">
        <div className="flex items-center gap-2.5 sm:gap-3">
          <EmergencyEmblem size="sm" />
          <div>
            <div className="font-mono text-[10px] sm:text-[11px] uppercase tracking-widest text-[#dc2626] font-bold">
              CITIZEN INTAKE PORTAL
            </div>
            <div className="font-black text-xs sm:text-sm text-slate-900 tracking-tight">
              RESILIENCE EMERGENCY RESPONSE NETWORK
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <LanguageSelector variant="compact" />
          <button
            onClick={() => navigate('/')}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white/80 hover:bg-slate-100 text-xs font-mono font-semibold text-slate-700 transition-all shadow-xs min-h-[36px] cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Exit to Home</span>
          </button>
        </div>
      </header>

      {/* Main Content Area Protected by ErrorBoundary */}
      <main className="relative z-10 max-w-3xl mx-auto w-full pb-12">
        <ErrorBoundary fallbackTitle="Emergency Report Form Could Not Be Loaded" fallbackMessage="An issue occurred while loading the emergency intake form. You can retry below or contact dispatch directly.">
        {submittedReport ? (
          /* ========================================================
             SUBMISSION RECEIPT & CONFIRMATION VIEW
             ======================================================== */
          <div className="p-6 sm:p-10 rounded-2xl bg-white border border-slate-200 shadow-xl shadow-slate-200/60 text-center animate-in fade-in duration-300">
            <div className="w-16 h-16 rounded-2xl bg-red-50 border-2 border-red-200 text-[#dc2626] flex items-center justify-center mx-auto mb-4 shadow-sm">
              <ShieldCheck className="w-9 h-9" />
            </div>

            <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-red-50 border border-red-200 text-[#dc2626] font-mono text-[11px] font-bold tracking-widest uppercase mb-2">
              <span className="w-2 h-2 rounded-full bg-[#dc2626] animate-ping" />
              STATUS: RECEIVED
            </div>

            <h1 className="text-2xl sm:text-3xl font-black font-sans tracking-tight text-slate-900 uppercase mb-2">
              Emergency Report Received
            </h1>

            <p className="text-xs sm:text-sm text-slate-600 max-w-lg mx-auto leading-relaxed mb-6">
              Your emergency report has been received by the Resilience emergency coordination network.
              Incident assessment is queued for immediate human-in-the-loop dispatch triage by an authorized watch officer.
            </p>

            {/* Prominent Report ID Card */}
            <div className="max-w-md mx-auto p-4 sm:p-5 rounded-xl bg-slate-50 border border-slate-200 mb-6 flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="text-left">
                <div className="font-mono text-[10px] uppercase text-slate-500 font-bold tracking-wider">
                  OFFICIAL REPORT IDENTIFIER
                </div>
                <div className="font-mono text-xl sm:text-2xl font-black text-slate-900 tracking-wider">
                  {submittedReport.report_id}
                </div>
              </div>

              <button
                onClick={() => copyToClipboard(submittedReport.report_id)}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-white hover:bg-slate-100 text-slate-800 border border-slate-300 text-xs font-mono font-semibold transition-all shadow-sm"
              >
                {copiedId ? (
                  <>
                    <Check className="w-4 h-4 text-emerald-600" />
                    <span className="text-emerald-700">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4 text-slate-500" />
                    <span>Copy Report ID</span>
                  </>
                )}
              </button>
            </div>

            {/* Summary Details Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-lg mx-auto mb-6 text-left text-xs font-mono">
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                <div className="text-[10px] text-slate-400 font-bold uppercase">EMERGENCY TYPE</div>
                <div className="font-bold text-slate-800 mt-0.5">{submittedReport.emergency_type}</div>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                <div className="text-[10px] text-slate-400 font-bold uppercase">DECLARED IMPACT</div>
                <div className="font-bold text-slate-900 mt-0.5 flex items-center gap-1">
                  <span className="inline-block w-2 h-2 rounded-full bg-red-600" />
                  <span>{submittedReport.citizen_impact_level || 'NOT_SURE'}</span>
                </div>
              </div>

              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                <div className="text-[10px] text-slate-400 font-bold uppercase">EVIDENCE STATUS</div>
                <div className="font-bold text-slate-800 mt-0.5 truncate">
                  {submittedReport.evidence ? (
                    <span className="text-emerald-700">✓ {submittedReport.evidence.validation_status}</span>
                  ) : (
                    <span className="text-slate-500">None Provided</span>
                  )}
                </div>
              </div>
            </div>

            {/* Confirmed Address Card */}
            <div className="max-w-lg mx-auto p-4 rounded-xl bg-slate-50 border border-slate-200 mb-6 text-left shadow-sm space-y-2">
              <div className="flex items-center justify-between">
                <div className="font-mono text-[10px] uppercase text-slate-500 font-bold tracking-wider">
                  CONFIRMED INCIDENT LOCATION
                </div>
                <a
                  href={`https://www.openstreetmap.org/?mlat=${submittedReport.location.latitude}&mlon=${submittedReport.location.longitude}#map=16/${submittedReport.location.latitude}/${submittedReport.location.longitude}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-mono font-semibold text-[#dc2626] hover:underline"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Open on Map</span>
                </a>
              </div>

              <div>
                <div className="text-[10px] font-mono text-slate-400 font-bold uppercase">Street Address / Landmark</div>
                <div className="flex items-start gap-1.5 text-sm font-sans font-bold text-slate-900 mt-0.5">
                  <MapPin className="w-4 h-4 text-[#dc2626] flex-shrink-0 mt-0.5" />
                  <span>{submittedReport.location.street_address || submittedReport.location.address || 'Address unavailable'}</span>
                </div>
              </div>

              <div className="text-xs font-mono text-slate-500 pl-5 pt-1 border-t border-slate-200/80">
                Coordinates: {submittedReport.location.latitude.toFixed(5)}, {submittedReport.location.longitude.toFixed(5)}
              </div>
            </div>

            {/* In-Place Report Modification Section */}
            {editSuccessNotice && (
              <div className="max-w-lg mx-auto p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 text-xs flex items-center gap-2 mb-4 animate-in fade-in">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
                <span>{editSuccessNotice}</span>
              </div>
            )}

            {!isEditingReport ? (
              <div className="max-w-lg mx-auto mb-6 flex justify-end">
                <button
                  onClick={() => setIsEditingReport(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-xs font-mono font-semibold text-slate-700 shadow-sm transition-all cursor-pointer"
                >
                  <Edit3 className="w-3.5 h-3.5 text-slate-500" />
                  <span>Modify Report Details</span>
                </button>
              </div>
            ) : (
              <form onSubmit={handleUpdateReport} className="max-w-lg mx-auto p-5 rounded-xl bg-slate-50 border border-slate-200 mb-6 text-left space-y-4 animate-in fade-in duration-200 shadow-sm">
                <div className="flex items-center justify-between border-b border-slate-200/80 pb-2">
                  <div className="font-mono text-xs font-bold text-slate-800 uppercase flex items-center gap-1.5">
                    <Edit3 className="w-3.5 h-3.5 text-red-600" />
                    <span>Update Report Details</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsEditingReport(false)}
                    className="text-xs text-slate-500 hover:text-slate-800 font-mono"
                  >
                    Cancel
                  </button>
                </div>

                {editErrorNotice && (
                  <div className="p-2.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 flex-shrink-0" />
                    <span>{editErrorNotice}</span>
                  </div>
                )}

                <div>
                  <label className="block text-[11px] font-mono font-bold text-slate-700 uppercase mb-1">
                    Incident Description (Min 10 characters)
                  </label>
                  <textarea
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    rows={3}
                    className="w-full text-xs font-sans p-2.5 rounded-lg border border-slate-300 bg-white focus:ring-2 focus:ring-red-500 focus:outline-none"
                    placeholder="Provide updated details on the situation..."
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-mono font-bold text-slate-700 uppercase mb-1">
                    Observed Citizen Impact
                  </label>
                  <div className="grid grid-cols-3 sm:grid-cols-5 gap-1.5">
                    {(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'NOT_SURE'] as CitizenImpactLevel[]).map((lvl) => (
                      <button
                        key={lvl}
                        type="button"
                        onClick={() => setEditImpactLevel(lvl)}
                        className={`py-1.5 px-2 rounded-lg text-[10px] font-mono font-bold border transition-all ${
                          editImpactLevel === lvl
                            ? 'bg-red-600 text-white border-red-600 shadow-sm'
                            : 'bg-white text-slate-700 border-slate-200 hover:border-slate-300'
                        }`}
                      >
                        {lvl}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  <div>
                    <label className="block text-[11px] font-mono font-bold text-slate-700 uppercase mb-1">
                      Contact Name
                    </label>
                    <input
                      type="text"
                      value={editFullName}
                      onChange={(e) => setEditFullName(e.target.value)}
                      className="w-full text-xs font-sans p-2 rounded-lg border border-slate-300 bg-white focus:ring-2 focus:ring-red-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-mono font-bold text-slate-700 uppercase mb-1">
                      Contact Phone
                    </label>
                    <input
                      type="tel"
                      value={editPhone}
                      onChange={(e) => setEditPhone(e.target.value)}
                      className="w-full text-xs font-sans p-2 rounded-lg border border-slate-300 bg-white focus:ring-2 focus:ring-red-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-mono font-bold text-slate-700 uppercase mb-1">
                    Additional Real-time Update / Note
                  </label>
                  <input
                    type="text"
                    value={editAdditionalNotes}
                    onChange={(e) => setEditAdditionalNotes(e.target.value)}
                    placeholder="e.g. Water level rising fast; 3 people on roof"
                    className="w-full text-xs font-sans p-2 rounded-lg border border-slate-300 bg-white focus:ring-2 focus:ring-red-500 focus:outline-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsEditingReport(false)}
                    className="px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-100 text-slate-700 text-xs font-mono font-semibold"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={editSubmitting}
                    className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-mono font-bold shadow-sm disabled:opacity-50"
                  >
                    {editSubmitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    <span>Save & Re-evaluate</span>
                  </button>
                </div>
              </form>
            )}

            {/* Prominent Live Safety Guidance Callout */}
            {submittedReport.safety_guidance_token ? (
              <div className="max-w-lg mx-auto p-5 rounded-2xl bg-gradient-to-br from-red-600 to-rose-700 text-white shadow-xl shadow-red-600/30 mb-8 text-left space-y-3 animate-in slide-in-from-bottom-2">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-white/20 text-white font-mono text-[10px] font-bold tracking-wider uppercase backdrop-blur-sm">
                    <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
                    LIVE ADVISORY GENERATED
                  </span>
                  <span className="text-[11px] font-mono opacity-80">AI Safety Guidance</span>
                </div>
                <div>
                  <h3 className="text-base font-bold text-white tracking-tight">
                    Instant Evacuation & Safety Route Ready
                  </h3>
                  <p className="text-xs text-red-100 mt-1 leading-relaxed">
                    AI safety intelligence has evaluated your emergency report and calculated a verified destination, safe navigation corridor, and immediate hazard precautions.
                  </p>
                </div>
                <div className="pt-1">
                  <button
                    onClick={() => navigate(`/safety-guidance/${submittedReport.safety_guidance_token}?lang=${encodeURIComponent(language || 'en')}`)}
                    className="w-full py-3 px-4 rounded-xl bg-white hover:bg-red-50 text-red-700 font-sans font-black text-xs uppercase tracking-wider shadow-lg flex items-center justify-center gap-2 transition-all active:scale-[0.98] cursor-pointer"
                  >
                    <span>VIEW LIVE SAFETY GUIDANCE & ROUTE</span>
                    <ExternalLink className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ) : (
              <div className="max-w-lg mx-auto p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 mb-6 text-left flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <div className="text-xs space-y-1">
                  <div className="font-bold">Live Safety Guidance Initializing...</div>
                  <p className="text-slate-600">
                    Your safety guidance is being calculated. You can access it anytime using your report reference.
                  </p>
                </div>
              </div>
            )}

            {/* Real Web Push Notification Card (8 Strict States) */}
            <div className="max-w-lg mx-auto mb-8 text-left">
              {comprehensivePushState === 'NOT_SUPPORTED' ? (
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-center gap-3 text-slate-500 text-xs">
                  <BellOff className="w-4 h-4 text-slate-400 flex-shrink-0" />
                  <span>Push notifications are not supported on this browser or device.</span>
                </div>
              ) : comprehensivePushState === 'INSECURE_CONTEXT' ? (
                <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-3 text-amber-900 text-xs">
                  <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="font-bold font-sans">Browser Notifications Require HTTPS</div>
                    <p className="text-amber-800 text-[11px] mt-0.5 leading-relaxed">
                      Browser notifications require HTTPS on this device. Emergency report submission and Safety Guidance remain fully functional.
                    </p>
                  </div>
                </div>
              ) : comprehensivePushState === 'PERMISSION_DENIED' ? (
                <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 flex items-start gap-3 text-amber-900 text-xs">
                  <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <div className="font-bold">Notifications Blocked in Browser Settings</div>
                    <p className="text-amber-800 text-[11px] mt-0.5">
                      Emergency push alerts cannot be delivered. To receive evacuation and road route updates, allow notifications in your browser's site settings.
                    </p>
                  </div>
                </div>
              ) : comprehensivePushState === 'ACTIVE' ? (
                <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-950 space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="space-y-0.5">
                      <div className="text-xs font-bold flex items-center gap-1.5 text-emerald-900">
                        <BellRing className="w-4 h-4 text-emerald-600 animate-pulse" />
                        <span>Emergency Alerts Active</span>
                      </div>
                      <p className="text-[11px] text-emerald-700">
                        This device is verified and registered to receive live evacuation, corridor, and road change alerts.
                      </p>
                    </div>
                    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-100 border border-emerald-300 text-emerald-800 text-[10px] font-mono font-bold uppercase tracking-wider flex-shrink-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                      Active
                    </span>
                  </div>

                  {/* Send Test Emergency Alert Button */}
                  <div className="pt-2 border-t border-emerald-200/80 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2">
                    <button
                      onClick={handleSendTestPush}
                      disabled={testPushSending}
                      className="px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-[11px] font-sans font-bold shadow-sm transition-all disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
                    >
                      <Bell className="w-3.5 h-3.5" />
                      <span>{testPushSending ? 'Sending Test...' : 'Send Test Emergency Alert'}</span>
                    </button>
                    {testPushMessage && (
                      <span className="text-[10px] font-mono text-emerald-800">
                        {testPushMessage}
                      </span>
                    )}
                  </div>
                </div>
              ) : comprehensivePushState === 'PERMISSION_GRANTED_NO_SUBSCRIPTION' || comprehensivePushState === 'SUBSCRIBED_NOT_PERSISTED' ? (
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between gap-3">
                  <div className="space-y-0.5">
                    <div className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                      <Bell className="w-4 h-4 text-red-600" />
                      <span>Connect Emergency Alerts</span>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Notification permission is granted. Complete registration to bind live alerts to report #{submittedReport.report_id}.
                    </p>
                  </div>
                  <button
                    onClick={handleOptInPush}
                    disabled={pushSubscribing}
                    className="px-3.5 py-1.5 rounded-lg bg-[#dc2626] hover:bg-[#b91c1c] text-white text-xs font-sans font-bold shadow-sm flex-shrink-0 disabled:opacity-50 cursor-pointer"
                  >
                    {pushSubscribing ? 'Connecting...' : 'Connect Alerts'}
                  </button>
                </div>
              ) : (
                /* PERMISSION_NOT_REQUESTED / SUBSCRIPTION_PENDING */
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <div className="space-y-0.5">
                    <div className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                      <Bell className="w-4 h-4 text-red-600" />
                      <span>🔔 Emergency Alerts & Evacuation Updates</span>
                    </div>
                    <p className="text-[11px] text-slate-600">
                      Get immediate alerts if evacuation orders, route corridors, or safety instructions change.
                    </p>
                    {pushErrorNotice && (
                      <p className="text-[11px] text-red-600 font-semibold pt-1">
                        {pushErrorNotice}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={handleOptInPush}
                    disabled={pushSubscribing}
                    className="w-full sm:w-auto px-4 py-2 rounded-lg bg-[#dc2626] hover:bg-[#b91c1c] text-white text-xs font-sans font-bold shadow-sm flex-shrink-0 disabled:opacity-50 cursor-pointer"
                  >
                    {pushSubscribing ? 'Enabling...' : 'Enable Alerts'}
                  </button>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={() => {
                  sessionStorage.removeItem('resilience_active_citizen_report');
                  navigate('/report-emergency?new=true', { replace: true });
                  setSubmittedReport(null);
                  setDescription('');
                  setLatitude('');
                  setLongitude('');
                  setAddress('');
                  setLocationStatus(null);
                  setEvidencePayload(null);
                  setFullName('');
                  setPhone('');
                  setBotHoneypot('');
                }}
                className="px-5 py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 font-sans text-xs font-bold transition-all"
              >
                Report Another Incident
              </button>

              <button
                onClick={() => navigate('/')}
                className="px-6 py-2.5 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs font-bold transition-all shadow-sm"
              >
                Return to Platform Landing
              </button>
            </div>
          </div>
        ) : (
          /* ========================================================
             REPORT EMERGENCY FORM
             ======================================================== */
          <div className="p-6 sm:p-10 rounded-2xl bg-white border border-slate-200 shadow-xl shadow-slate-200/60">
            {/* Header Title */}
            <div className="text-left mb-8 pb-6 border-b border-slate-100">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-50 border border-red-200 text-[#dc2626] font-mono text-[10px] font-bold uppercase tracking-wider mb-2">
                <Siren className="w-3.5 h-3.5" />
                <span>DIRECT CITIZEN INGESTION</span>
              </div>
              <h1 className="text-2xl sm:text-3xl font-black font-sans tracking-tight text-slate-900 uppercase">
                Report an Emergency
              </h1>
              <p className="text-xs sm:text-sm text-slate-600 mt-1 max-w-xl">
                Submit an immediate situational report to the emergency coordination network. Evidence-backed reports are prioritized for rapid dispatch triage.
              </p>
            </div>

            {/* Error Message */}
            {error && (
              <div className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 flex items-start gap-3 text-xs text-red-700">
                <AlertCircle className="w-5 h-5 text-[#dc2626] flex-shrink-0 mt-0.5" />
                <div className="flex-1 font-medium">{error}</div>
                <button onClick={() => setError(null)} className="text-red-400 hover:text-red-700">
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            <form onSubmit={handleSubmitReport} className="space-y-6">
              {/* 1. Emergency Type Selection */}
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-800 mb-2 font-bold">
                  1. Emergency Type *
                </label>
                {autoDetectedTypeNotice && (
                  <div className="mb-2 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-lg flex items-center justify-between animate-in fade-in">
                    <span>⚡ {autoDetectedTypeNotice}</span>
                    <button
                      type="button"
                      onClick={() => setAutoDetectedTypeNotice(null)}
                      className="text-emerald-500 hover:text-emerald-800 ml-2"
                    >
                      ×
                    </button>
                  </div>
                )}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                  {emergencyTypesList.map((item) => {
                    const Icon = item.icon;
                    const isSelected = emergencyType === item.type;
                    return (
                      <button
                        key={item.type}
                        type="button"
                        onClick={() => {
                          setEmergencyType(item.type);
                          setUserManuallySelectedType(true);
                          setAutoDetectedTypeNotice(null);
                        }}
                        className={`flex items-center gap-2.5 p-3 rounded-xl border text-left text-xs font-sans font-semibold transition-all shadow-sm ${
                          isSelected
                            ? 'border-[#dc2626] bg-red-50 text-slate-900 ring-1 ring-red-500/20'
                            : 'border-slate-200 bg-slate-50 text-slate-700 hover:border-slate-300 hover:bg-slate-100/70'
                        }`}
                      >
                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
                          isSelected ? 'bg-white text-[#dc2626] shadow-sm' : 'bg-slate-200/80 text-slate-600'
                        }`}>
                          <Icon className="w-4 h-4" />
                        </div>
                        <span className="truncate">{item.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* 2. Impact Level (Citizen Self-Assessment) */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-mono uppercase tracking-wider text-slate-800 font-bold">
                    2. Citizen-Assessed Impact Level *
                  </label>
                  <span className="text-[11px] text-slate-500 flex items-center gap-1 font-mono">
                    <HelpCircle className="w-3.5 h-3.5 text-slate-400" />
                    <span>Triage indicator for watch officers</span>
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 mb-2.5">
                  Select the urgency level based on your direct observation. The Emergency Officer will verify and assign final operational dispatch priority.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5">
                  {impactLevelsList.map((item) => {
                    const isSelected = citizenImpactLevel === item.level;
                    return (
                      <button
                        key={item.level}
                        type="button"
                        onClick={() => setCitizenImpactLevel(item.level)}
                        className={`flex flex-col justify-between p-3 rounded-xl border text-left transition-all shadow-2xs ${
                          isSelected
                            ? `${item.color} ring-2 ring-slate-900/20 shadow-sm`
                            : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100/70'
                        }`}
                      >
                        <div>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-bold font-sans">{item.label}</span>
                            {isSelected && <span className="w-2 h-2 rounded-full bg-slate-900" />}
                          </div>
                          <p className="text-[10px] text-slate-500 leading-tight">
                            {item.description}
                          </p>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* 3. Emergency Description */}
              <div>
                <div className="flex flex-wrap items-center justify-between gap-1.5 mb-1.5">
                  <label className="block text-xs font-mono uppercase tracking-wider text-slate-800 font-bold">
                    3. {t('report.description', 'Describe the Situation')} *
                  </label>
                  <span className="text-[10px] text-indigo-700 font-medium bg-indigo-50 border border-indigo-200 px-2 py-0.5 rounded-md flex items-center gap-1">
                    <span>🌐</span>
                    <span>{t('report.languageHint', 'Type in any Indian language. AI auto-detects & responds in same language.')}</span>
                  </span>
                </div>
                <textarea
                  rows={4}
                  required
                  value={description}
                  onChange={handleDescriptionChange}
                  placeholder={t('report.descriptionPlaceholder', 'What happened? How many people are affected? Is anyone trapped or injured? (You can type in Telugu, Hindi, Tamil, English, etc.)')}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#dc2626] focus:bg-white focus:ring-2 focus:ring-red-500/10 transition-all font-sans"
                />
              </div>

              {/* 4. Location Capture */}
              <div className="p-4 sm:p-5 rounded-xl bg-slate-50/80 border border-slate-200 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <label className="block text-xs font-mono uppercase tracking-wider text-slate-800 font-bold">
                      4. Incident Location *
                    </label>
                    <p className="text-[11px] text-slate-500">
                      Provide GPS coordinates, pinpoint on map, or specify address for accurate dispatch mapping.
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleGetLocation}
                      disabled={locating}
                      className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg bg-white hover:bg-slate-100 text-slate-800 border border-slate-300 text-xs font-sans font-bold shadow-sm transition-all cursor-pointer"
                    >
                      {locating ? (
                        <>
                          <Loader2 className="w-3.5 h-3.5 animate-spin text-[#dc2626]" />
                          <span>Locating...</span>
                        </>
                      ) : (
                        <>
                          <Navigation className="w-3.5 h-3.5 text-[#dc2626]" />
                          <span>Use My Current Location</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {/* Interactive Google Map Location Picker */}
                <div className="relative w-full rounded-xl overflow-hidden border border-slate-300/90 bg-white shadow-2xs">
                  <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 text-xs text-slate-700 font-sans font-semibold">
                      <MapPin className="w-3.5 h-3.5 text-[#dc2626]" />
                      <span className="text-[11px] font-mono uppercase font-bold text-slate-800">
                        Interactive Map Pinpoint
                      </span>
                    </div>
                    <div className="flex items-center rounded-lg border border-slate-300 bg-white p-0.5 text-[10px] font-semibold">
                      <button
                        type="button"
                        onClick={() => handleToggleMapType('roadmap')}
                        className={`px-2 py-0.5 rounded transition-all cursor-pointer ${
                          mapType === 'roadmap' ? 'bg-slate-900 text-white font-bold' : 'text-slate-600 hover:text-slate-900'
                        }`}
                      >
                        Map
                      </button>
                      <button
                        type="button"
                        onClick={() => handleToggleMapType('satellite')}
                        className={`px-2 py-0.5 rounded transition-all cursor-pointer ${
                          mapType === 'satellite' ? 'bg-blue-600 text-white font-bold' : 'text-slate-600 hover:text-slate-900'
                        }`}
                      >
                        Satellite
                      </button>
                    </div>
                  </div>

                  <div className="relative w-full h-[200px] sm:h-[240px] md:h-[260px] bg-slate-100">
                    <div ref={mapContainerRef} className="w-full h-full" />
                    <div className="absolute bottom-2 left-2 right-2 pointer-events-none">
                      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white/95 backdrop-blur-xs border border-slate-200 text-[10px] font-sans font-medium text-slate-700 shadow-xs">
                        <span>Tap map or drag pin to position emergency epicenter</span>
                      </div>
                    </div>
                  </div>
                </div>

                {locationStatus && (
                  <div className="p-2.5 rounded-lg bg-white border border-slate-200 text-xs font-mono text-slate-700 flex items-center gap-2">
                    <MapPin className="w-4 h-4 text-[#dc2626] flex-shrink-0" />
                    <span>{locationStatus}</span>
                  </div>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-mono text-slate-600 mb-1 font-semibold">
                      Latitude *
                    </label>
                    <input
                      type="number"
                      step="any"
                      required
                      value={latitude}
                      onChange={(e) => {
                        const val = e.target.value;
                        setLatitude(val);
                        const latNum = parseFloat(val);
                        const lonNum = parseFloat(longitude);
                        if (!isNaN(latNum) && !isNaN(lonNum) && googleMapRef.current && markerRef.current) {
                          markerRef.current.setPosition({ lat: latNum, lng: lonNum });
                          markerRef.current.setMap(googleMapRef.current);
                        }
                      }}
                      placeholder="e.g. 16.2415"
                      className="w-full px-3 py-2 rounded-lg bg-white border border-slate-200 text-xs text-slate-900 font-mono focus:outline-none focus:border-[#dc2626]"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[11px] font-mono text-slate-600 font-semibold">
                        Longitude *
                      </label>
                      {latitude && longitude && (
                        <button
                          type="button"
                          onClick={handleManualResolveAddress}
                          disabled={locating}
                          className="text-[10px] font-mono text-[#dc2626] hover:underline font-bold"
                        >
                          Resolve Address
                        </button>
                      )}
                    </div>
                    <input
                      type="number"
                      step="any"
                      required
                      value={longitude}
                      onChange={(e) => {
                        const val = e.target.value;
                        setLongitude(val);
                        const latNum = parseFloat(latitude);
                        const lonNum = parseFloat(val);
                        if (!isNaN(latNum) && !isNaN(lonNum) && googleMapRef.current && markerRef.current) {
                          markerRef.current.setPosition({ lat: latNum, lng: lonNum });
                          markerRef.current.setMap(googleMapRef.current);
                        }
                      }}
                      placeholder="e.g. 80.6433"
                      className="w-full px-3 py-2 rounded-lg bg-white border border-slate-200 text-xs text-slate-900 font-mono focus:outline-none focus:border-[#dc2626]"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-mono text-slate-600 mb-1 font-semibold">
                      Street Address / Landmark (Optional)
                    </label>
                    <input
                      type="text"
                      value={address}
                      onChange={(e) => setAddress(e.target.value)}
                      placeholder="e.g. Main Road Junction"
                      className="w-full px-3 py-2 rounded-lg bg-white border border-slate-200 text-xs text-slate-900 font-sans focus:outline-none focus:border-[#dc2626]"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-mono text-slate-600 mb-1 font-semibold">
                      Zone / District (Optional)
                    </label>
                    <input
                      type="text"
                      value={manualZone}
                      onChange={(e) => setManualZone(e.target.value)}
                      placeholder="e.g. Guntur District"
                      className="w-full px-3 py-2 rounded-lg bg-white border border-slate-200 text-xs text-slate-900 font-sans focus:outline-none focus:border-[#dc2626]"
                    />
                  </div>
                </div>
              </div>

              {/* 5. Live Browser Camera Evidence Capture (Optional) */}
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-800 mb-1.5 font-bold">
                  5. Live Photo Evidence (Optional)
                </label>
                <LiveCameraCapture
                  onEvidenceCaptured={(evidence) => setEvidencePayload(evidence)}
                  reportLatitude={parseFloat(latitude) || undefined}
                  reportLongitude={parseFloat(longitude) || undefined}
                />
              </div>

              {/* 6. Contact Information */}
              <div className="p-4 sm:p-5 rounded-xl bg-slate-50 border border-slate-200 space-y-4">
                <div className="flex items-center justify-between">
                  <label className="block text-xs font-mono uppercase tracking-wider text-slate-800 font-bold">
                    6. Contact Information *
                  </label>
                  <span className="text-[11px] text-slate-500 font-sans">
                    Required for dispatch contact & identity
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-mono text-slate-600 mb-1 font-semibold">
                      Full Name *
                    </label>
                    <div className="relative">
                      <User className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                      <input
                        type="text"
                        required
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        placeholder="e.g. Ramesh Varma"
                        className="w-full pl-9 pr-3 py-2 rounded-lg bg-white border border-slate-200 text-xs sm:text-sm text-slate-900 font-sans focus:outline-none focus:border-[#dc2626]"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-[11px] font-mono text-slate-600 mb-1 font-semibold">
                      Mobile Phone Number *
                    </label>
                    <div className="relative">
                      <Phone className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                      <input
                        type="tel"
                        required
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="e.g. 9876543210"
                        className="w-full pl-9 pr-3 py-2 rounded-lg bg-white border border-slate-200 text-xs sm:text-sm text-slate-900 font-mono focus:outline-none focus:border-[#dc2626]"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Hidden honeypot field for bot protection */}
              <input
                type="text"
                value={botHoneypot}
                onChange={(e) => setBotHoneypot(e.target.value)}
                style={{ display: 'none' }}
                tabIndex={-1}
                autoComplete="off"
              />

              {/* Submit Action */}
              <div className="pt-2">
                <button
                  type="submit"
                  disabled={submitting}
                  className="w-full py-3.5 px-6 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white text-sm font-sans font-bold shadow-md shadow-red-600/20 transition-all active:scale-[0.99] flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  {submitting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Transmitting Emergency Report...</span>
                    </>
                  ) : (
                    <>
                      <Siren className="w-4 h-4" />
                      <span>SUBMIT EMERGENCY REPORT</span>
                    </>
                  )}
                </button>
              </div>

              <div className="text-center">
                <p className="text-[11px] text-slate-400 font-mono">
                  RESILIENCE DISPATCH • HUMAN-IN-THE-LOOP VERIFICATION ENFORCED
                </p>
              </div>
            </form>
          </div>
        )}
        </ErrorBoundary>
      </main>
    </div>
  );
};
