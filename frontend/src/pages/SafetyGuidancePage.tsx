import React, { useEffect, useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Shield,
  AlertTriangle,
  Navigation,
  RefreshCw,
  Bell,
  CheckCircle2,
  AlertCircle,
  Clock,
  ArrowLeft,
  HeartPulse,
  Flame,
  Siren,
  MapPin,
  Home,
  Phone,
  Star,
  Compass,
  Check,
  ExternalLink,
} from 'lucide-react';
import {
  getSafetyGuidanceByToken,
  refreshSafetyGuidanceForReport,
  getSafetyGuidanceHistory,
} from '../services/api';
import type { CitizenSafetyGuidance, VerifiedDestination, WebPushState } from '../types';
import {
  registerServiceWorkerAndSubscribe,
  getComprehensivePushState,
  sendTestPushNotification,
  isWebPushSupported,
} from '../utils/webPush';
import { loadGoogleMaps } from '../utils/googleMapsLoader';

declare global {
  interface Window {
    google: any;
  }
}

export const SafetyGuidancePage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const [guidance, setGuidance] = useState<CitizenSafetyGuidance | null>(null);
  const [selectedAlternative, setSelectedAlternative] = useState<VerifiedDestination | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [completedActions, setCompletedActions] = useState<Set<number>>(new Set());
  const [mapType, setMapType] = useState<'roadmap' | 'satellite'>('roadmap');

  // 7-State Web Push machine
  const [pushState, setPushState] = useState<WebPushState>('PERMISSION_NOT_REQUESTED');
  const [pushSubscribing, setPushSubscribing] = useState<boolean>(false);
  const [testPushSending, setTestPushSending] = useState<boolean>(false);
  const [testPushMessage, setTestPushMessage] = useState<string | null>(null);

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const polylineRef = useRef<any>(null);
  const circlesRef = useRef<any[]>([]);

  const [showHistory, setShowHistory] = useState<boolean>(false);
  const [historyList, setHistoryList] = useState<any[]>([]);
  const [mapsLoaded, setMapsLoaded] = useState<boolean>(false);

  useEffect(() => {
    loadGoogleMaps()
      .then(() => setMapsLoaded(true))
      .catch((err) => {
        console.warn('Google Maps JS API load notice:', err);
      });
  }, []);

  useEffect(() => {
    if (token) {
      fetchGuidance(token);
    } else {
      setError('Invalid or missing safety guidance token.');
      setLoading(false);
    }
    const checkState = async () => {
      const s = await getComprehensivePushState();
      setPushState(s);
    };
    checkState();
  }, [token]);

  const fetchGuidance = async (authToken: string) => {
    try {
      setLoading(true);
      setError(null);
      const res = await getSafetyGuidanceByToken(authToken);
      if (res.success && res.guidance) {
        setGuidance(res.guidance);
        setSelectedAlternative(null);
      } else {
        setError(res.message || 'Safety guidance record not found.');
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Failed to load safety guidance.');
    } finally {
      setLoading(false);
    }
  };

  const handleFetchHistory = async () => {
    if (!token) return;
    try {
      const hist = await getSafetyGuidanceHistory(token);
      if (hist && hist.versions) {
        setHistoryList(hist.versions);
        setShowHistory(true);
      }
    } catch (err) {
      console.warn('Could not fetch history:', err);
    }
  };

  const handleRefresh = async () => {
    if (!guidance?.report_id) return;
    try {
      setRefreshing(true);
      const res = await refreshSafetyGuidanceForReport(guidance.report_id);
      if (res.success && res.guidance) {
        setGuidance(res.guidance);
        setSelectedAlternative(null);
      }
    } catch (err: any) {
      console.error('Refresh error:', err);
    } finally {
      setRefreshing(false);
    }
  };

  const toggleActionItem = (idx: number) => {
    setCompletedActions((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const getGoogleMapsDirectionsUrl = (dest: VerifiedDestination) => {
    const originLat = guidance?.route?.origin_latitude;
    const originLng = guidance?.route?.origin_longitude;
    const originParam = originLat !== undefined && originLng !== undefined ? `${originLat},${originLng}` : '';
    const destParam = `${dest.latitude},${dest.longitude}`;
    const placeIdParam = dest.place_id ? `&destination_place_id=${encodeURIComponent(dest.place_id)}` : '';
    return `https://www.google.com/maps/dir/?api=1&origin=${originParam}&destination=${destParam}${placeIdParam}&travelmode=driving`;
  };

  const handleEnablePush = async () => {
    setPushSubscribing(true);
    setPushState('SUBSCRIPTION_PENDING');
    const res = await registerServiceWorkerAndSubscribe(guidance?.report_id);
    setPushSubscribing(false);
    if (res.success) {
      setPushState('ACTIVE');
      try {
        await sendTestPushNotification(guidance?.report_id);
      } catch (e) {
        console.info('[WebPush] Initial guidance push notice:', e);
      }
    } else {
      const s = await getComprehensivePushState();
      setPushState(s);
    }
  };

  const handleSendTestPush = async () => {
    setTestPushSending(true);
    setTestPushMessage(null);
    try {
      const res = await sendTestPushNotification(guidance?.report_id);
      setTestPushMessage(res.message);
    } catch (err: any) {
      setTestPushMessage('Failed to send test alert.');
    } finally {
      setTestPushSending(false);
    }
  };

  const getDestinationCategoryConfig = (type?: string) => {
    const t = (type || '').toUpperCase();
    if (t.includes('HEALTH') || t.includes('HOSPITAL') || t.includes('MEDICAL')) {
      return {
        label: 'Healthcare / Hospital',
        icon: HeartPulse,
        iconBg: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        badge: 'bg-emerald-50 text-emerald-800 border-emerald-200',
        mapIconColor: '#059669',
      };
    }
    if (t.includes('POLICE') || t.includes('SECURITY') || t.includes('LAW')) {
      return {
        label: 'Police / Law Enforcement',
        icon: Siren,
        iconBg: 'bg-blue-50 text-blue-700 border-blue-200',
        badge: 'bg-blue-50 text-blue-800 border-blue-200',
        mapIconColor: '#2563EB',
      };
    }
    if (t.includes('FIRE')) {
      return {
        label: 'Fire Station / Rescue',
        icon: Flame,
        iconBg: 'bg-orange-50 text-orange-700 border-orange-200',
        badge: 'bg-orange-50 text-orange-800 border-orange-200',
        mapIconColor: '#EA580C',
      };
    }
    if (t.includes('BUS') || t.includes('TRANSIT') || t.includes('TRANSPORT')) {
      return {
        label: 'Transit / Bus Station',
        icon: Navigation,
        iconBg: 'bg-indigo-50 text-indigo-700 border-indigo-200',
        badge: 'bg-indigo-50 text-indigo-800 border-indigo-200',
        mapIconColor: '#4F46E5',
      };
    }
    if (t.includes('ASSEMBLY')) {
      return {
        label: 'Safe Assembly Area',
        icon: MapPin,
        iconBg: 'bg-purple-50 text-purple-700 border-purple-200',
        badge: 'bg-purple-50 text-purple-800 border-purple-200',
        mapIconColor: '#9333EA',
      };
    }
    return {
      label: 'Emergency Shelter',
      icon: Home,
      iconBg: 'bg-amber-50 text-amber-700 border-amber-200',
      badge: 'bg-amber-50 text-amber-800 border-amber-200',
      mapIconColor: '#D97706',
    };
  };

  // Active Destination (Primary or selected alternative)
  const activeDest: VerifiedDestination | null = selectedAlternative || guidance?.recommended_destination || null;

  // Google Maps Initialization & Dynamic Polyline Rendering
  useEffect(() => {
    if (!guidance || !mapContainerRef.current) return;

    const google = window.google;
    if (!google?.maps) return;

    const route = guidance.route;
    const dest = activeDest;

    const defaultCenter = route
      ? { lat: (route.origin_latitude + route.destination_latitude) / 2, lng: (route.origin_longitude + route.destination_longitude) / 2 }
      : dest
      ? { lat: dest.latitude, lng: dest.longitude }
      : { lat: 16.5062, lng: 80.648 };

    if (!mapInstanceRef.current) {
      mapInstanceRef.current = new google.maps.Map(mapContainerRef.current, {
        center: defaultCenter,
        zoom: 14,
        mapTypeId: mapType,
        disableDefaultUI: false,
        zoomControl: true,
        mapTypeControl: false,
        streetViewControl: false,
        fullscreenControl: true,
      });
    } else {
      mapInstanceRef.current.setMapTypeId(mapType);
    }

    const map = mapInstanceRef.current;

    // Clear previous markers & polylines
    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];
    circlesRef.current.forEach((c) => c.setMap(null));
    circlesRef.current = [];
    if (polylineRef.current) {
      polylineRef.current.setMap(null);
      polylineRef.current = null;
    }

    const bounds = new google.maps.LatLngBounds();

    // 1. Citizen Origin Marker
    if (route) {
      const originPos = { lat: route.origin_latitude, lng: route.origin_longitude };
      const originMarker = new google.maps.Marker({
        position: originPos,
        map,
        title: 'Your Location (Report Origin)',
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 9,
          fillColor: '#DC2626',
          fillOpacity: 1,
          strokeColor: '#FFFFFF',
          strokeWeight: 2,
        },
      });
      markersRef.current.push(originMarker);
      bounds.extend(originPos);
    }

    // 2. Destination Marker
    if (dest) {
      const destPos = { lat: dest.latitude, lng: dest.longitude };
      const destConfig = getDestinationCategoryConfig(dest.destination_type);
      const destMarker = new google.maps.Marker({
        position: destPos,
        map,
        title: `${dest.destination_name} (${destConfig.label})`,
        icon: {
          path: google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
          scale: 8,
          fillColor: destConfig.mapIconColor,
          fillOpacity: 1,
          strokeColor: '#FFFFFF',
          strokeWeight: 2,
        },
      });
      markersRef.current.push(destMarker);
      bounds.extend(destPos);
    }

    // 3. Render Route Polyline ONLY if genuine points available and route is routable
    if (
      route &&
      route.route_status !== 'ROUTE_UNAVAILABLE' &&
      route.route_status !== 'ROUTE_PROVIDER_ERROR'
    ) {
      let pathCoordinates: { lat: number; lng: number }[] = [];
      if (route.encoded_polyline && (google.maps.geometry as any)?.encoding) {
        try {
          const decoded = (google.maps.geometry as any).encoding.decodePath(route.encoded_polyline);
          pathCoordinates = decoded.map((p: any) => ({ lat: p.lat(), lng: p.lng() }));
        } catch (e) {
          console.warn('Failed to decode encoded_polyline client-side:', e);
        }
      }
      if (pathCoordinates.length < 2 && route.polyline_points && route.polyline_points.length >= 2) {
        pathCoordinates = route.polyline_points.map(([lat, lng]) => ({ lat, lng }));
      }

      if (pathCoordinates.length >= 2) {
        pathCoordinates.forEach((p) => bounds.extend(p));

        const strokeColor =
          route.route_status === 'ROUTE_UNSAFE'
            ? '#DC2626'
            : route.route_status === 'RESTRICTED'
            ? '#D97706'
            : '#2563EB';

        polylineRef.current = new google.maps.Polyline({
          path: pathCoordinates,
          geodesic: true,
          strokeColor,
          strokeOpacity: 0.9,
          strokeWeight: 5,
          map,
        });
      }
    }

    // 4. Render Hazard Avoidance Zones
    if (guidance.avoid_locations) {
      guidance.avoid_locations.forEach((haz) => {
        const center = { lat: haz.latitude, lng: haz.longitude };
        const circle = new google.maps.Circle({
          strokeColor: '#DC2626',
          strokeOpacity: 0.8,
          strokeWeight: 2,
          fillColor: '#EF4444',
          fillOpacity: 0.2,
          map,
          center,
          radius: (haz.radius_km || 1.0) * 1000,
        });
        circlesRef.current.push(circle);
      });
    }

    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { top: 40, bottom: 40, left: 40, right: 40 });
    }
  }, [guidance, activeDest, mapType, mapsLoaded]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col items-center justify-center p-6 font-sans">
        <div className="flex flex-col items-center gap-4 bg-white border border-slate-200 p-8 rounded-2xl shadow-sm max-w-md w-full text-center">
          <RefreshCw className="w-10 h-10 text-red-600 animate-spin" />
          <h2 className="text-xl font-bold tracking-tight text-slate-900">Synthesizing Safety Guidance</h2>
          <p className="text-sm text-slate-600">
            Connecting real-time GIS layers, emergency shelter capacity, and local hazard corridors...
          </p>
        </div>
      </div>
    );
  }

  if (error || !guidance) {
    return (
      <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col items-center justify-center p-6 font-sans">
        <div className="bg-white border border-red-200 p-8 rounded-2xl shadow-sm max-w-md w-full text-center">
          <AlertTriangle className="w-12 h-12 text-red-600 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-slate-900 mb-2">Safety Advisory Notice</h2>
          <p className="text-sm text-slate-600 mb-6">{error || 'No safety guidance available for this incident.'}</p>
          <Link
            to="/citizen/report"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-red-600 hover:bg-red-700 text-white font-bold text-xs uppercase tracking-wider transition-all shadow-sm"
          >
            <ArrowLeft className="w-4 h-4" /> Return to Emergency Portal
          </Link>
        </div>
      </div>
    );
  }

  const getRiskBadgeColor = (risk: string) => {
    switch (risk?.toUpperCase()) {
      case 'CRITICAL':
        return 'bg-red-50 text-red-700 border-red-200';
      case 'HIGH':
        return 'bg-amber-50 text-amber-700 border-amber-200';
      case 'MEDIUM':
        return 'bg-yellow-50 text-yellow-800 border-yellow-200';
      default:
        return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-16 font-sans">
      {/* Top Header Banner */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200 px-3 sm:px-6 lg:px-8 py-2.5 sm:py-3.5 shadow-xs">
        <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex items-center gap-2.5 sm:gap-3">
            <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-red-600 flex items-center justify-center shadow-xs text-white flex-shrink-0">
              <Shield className="w-4 h-4 sm:w-5 sm:h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-1.5 sm:gap-2">
                <span className="text-[10px] sm:text-xs font-mono font-bold uppercase tracking-wider text-red-600">RESILIENCE AI</span>
                <span className="text-xs text-slate-400">•</span>
                <span className="text-[10px] sm:text-xs font-mono text-slate-600">Report #{guidance.report_id}</span>
              </div>
              <h1 className="text-xs sm:text-base font-bold text-slate-900 tracking-tight">Citizen Safety Guidance</h1>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
            <Link
              to={`/citizen/report?id=${guidance.report_id}`}
              className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-white hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-700 transition-all shadow-xs min-h-[36px]"
              title="Return to Report Receipt & Modification"
            >
              <ArrowLeft className="w-3.5 h-3.5 text-slate-500" />
              <span className="hidden xs:inline">Report Details</span>
            </Link>

            {isWebPushSupported() && (
              <button
                onClick={handleEnablePush}
                disabled={pushSubscribing || pushState === 'ACTIVE'}
                className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all shadow-xs cursor-pointer min-h-[36px] touch-manipulation ${
                  pushState === 'ACTIVE'
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-300 hover:bg-emerald-100'
                    : 'bg-red-600 text-white border-red-700 hover:bg-red-700'
                }`}
                title="Browser Web Push Notification Controls"
              >
                <Bell className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{pushSubscribing ? 'Connecting...' : pushState === 'ACTIVE' ? 'Push Active' : 'Enable Push'}</span>
              </button>
            )}

            <button
              onClick={handleFetchHistory}
              className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-white hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-700 transition-all shadow-xs cursor-pointer min-h-[36px] touch-manipulation"
              title="View immutable version history"
            >
              <Clock className="w-3.5 h-3.5 text-slate-500" />
              <span className="hidden sm:inline">History (v{guidance?.version || 1})</span>
            </button>

            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg bg-white hover:bg-slate-100 border border-slate-300 text-xs font-semibold text-slate-700 transition-all shadow-xs cursor-pointer min-h-[36px] touch-manipulation"
              title="Refresh safety guidance with latest real-time GIS and road network data"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-red-600' : 'text-slate-500'}`} />
              <span className="hidden sm:inline">{refreshing ? 'Refreshing...' : 'Refresh'}</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="max-w-7xl mx-auto px-4 lg:px-8 pt-6 space-y-6">
        {/* Dynamic Change Reason Alert (Phase 2) */}
        {guidance.change_reason && (
          <div className="p-4 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 shadow-sm flex items-start gap-3.5 animate-in slide-in-from-top-2">
            <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1 text-xs space-y-1">
              <div className="font-bold text-amber-900 uppercase tracking-wider flex items-center gap-2 font-mono text-[11px]">
                <span>Dynamic Guidance Update (Version {guidance.version})</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] bg-amber-200/60 border border-amber-300 text-amber-900 font-mono">
                  LIVE RE-EVALUATION
                </span>
              </div>
              <p className="text-amber-800 leading-relaxed font-sans">{guidance.change_reason}</p>
            </div>
          </div>
        )}

        {/* Stale Guidance Notice if expired */}
        {guidance.is_stale && (
          <div className="p-4 rounded-2xl bg-red-50 border border-red-200 text-red-900 shadow-sm flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <Clock className="w-5 h-5 text-red-600 flex-shrink-0" />
              <div className="text-xs">
                <div className="font-bold text-red-900">Guidance Advisory Expired</div>
                <p className="text-red-700">This navigation advisory was calculated over 4 hours ago and may no longer reflect live conditions.</p>
              </div>
            </div>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="px-3.5 py-1.5 rounded-lg bg-red-600 hover:bg-red-700 text-white font-bold text-xs shadow-sm flex-shrink-0 cursor-pointer"
            >
              Recalculate Now
            </button>
          </div>
        )}

        {/* Status Bar / Emergency Classification Banner */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-red-50 flex items-center justify-center border border-red-100">
              <AlertCircle className="w-6 h-6 text-red-600" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg font-bold text-slate-900 tracking-tight">{guidance.emergency_type} Advisory</span>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getRiskBadgeColor(guidance.risk_level)}`}>
                  {guidance.risk_level} RISK
                </span>
                <span className="px-2 py-0.5 rounded-full text-xs font-mono font-bold bg-slate-100 text-slate-700 border border-slate-300">
                  v{guidance.version}
                </span>
              </div>
              <p className="text-xs text-slate-500 flex items-center gap-2">
                <Clock className="w-3.5 h-3.5 text-slate-400" />
                <span>Generated {new Date(guidance.generated_at).toLocaleTimeString()}</span>
                <span>•</span>
                <span>Confidence: {(guidance.confidence * 100).toFixed(0)}%</span>
              </p>
            </div>
          </div>

          {/* Web Push Alerts Opt-in Component */}
          {isWebPushSupported() && pushState === 'PERMISSION_DENIED' && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs font-semibold">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
              <span>Alerts Blocked in Browser Settings</span>
            </div>
          )}

          {isWebPushSupported() && pushState !== 'ACTIVE' && pushState !== 'PERMISSION_DENIED' && (
            <button
              onClick={handleEnablePush}
              disabled={pushSubscribing}
              className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all shadow-sm cursor-pointer disabled:opacity-50"
            >
              <Bell className="w-4 h-4 text-white" />
              <span>{pushSubscribing ? 'Enabling Live Alerts...' : 'Enable Emergency Push Alerts'}</span>
            </button>
          )}

          {pushState === 'ACTIVE' && (
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>Push Alerts Active</span>
              </div>
              <button
                onClick={handleSendTestPush}
                disabled={testPushSending}
                className="px-2.5 py-1.5 rounded-lg bg-white hover:bg-slate-100 border border-slate-300 text-xs text-slate-700 font-mono font-semibold transition-all shadow-sm cursor-pointer"
                title="Verify delivery of genuine push alert without affecting operational logs"
              >
                {testPushSending ? 'Testing...' : 'Send Test Alert'}
              </button>
              {testPushMessage && (
                <span className="text-[11px] font-mono text-emerald-700 hidden sm:inline font-semibold">
                  {testPushMessage}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Version History Modal */}
        {showHistory && (
          <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in-50">
            <div className="bg-white border border-slate-200 rounded-2xl max-w-xl w-full p-6 shadow-xl space-y-4 max-h-[85vh] overflow-y-auto">
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <div className="flex items-center gap-2">
                  <Clock className="w-5 h-5 text-red-600" />
                  <h3 className="text-base font-bold text-slate-900">Guidance Version History Audit Trail</h3>
                </div>
                <button
                  onClick={() => setShowHistory(false)}
                  className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
                >
                  ✕
                </button>
              </div>

              <div className="space-y-3">
                {historyList.map((v, i) => (
                  <div
                    key={v.guidance_id || i}
                    className={`p-3.5 rounded-xl border ${
                      v.version === guidance.version
                        ? 'bg-red-50/50 border-red-200 text-slate-900'
                        : 'bg-slate-50 border-slate-200 text-slate-700'
                    } text-xs space-y-1.5`}
                  >
                    <div className="flex items-center justify-between font-mono font-bold">
                      <span className="flex items-center gap-2">
                        <span>Version {v.version}</span>
                        {v.version === guidance.version && (
                          <span className="px-1.5 py-0.5 rounded bg-red-100 text-red-800 text-[10px]">CURRENT</span>
                        )}
                      </span>
                      <span className="text-slate-500 font-normal">{new Date(v.generated_at).toLocaleTimeString()}</span>
                    </div>
                    {v.change_reason && (
                      <p className="text-slate-700 font-sans"><strong className="text-amber-800">Trigger:</strong> {v.change_reason}</p>
                    )}
                    <div className="flex items-center gap-3 text-[11px] text-slate-500 font-mono">
                      <span>Status: {v.status}</span>
                      <span>•</span>
                      <span>Approval: {v.approval_state}</span>
                      {v.destination_name && (
                        <>
                          <span>•</span>
                          <span>Dest: {v.destination_name}</span>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Two Column Layout: Left (Actions & Destination), Right (Map & Route) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Immediate Actions, Precautions & Destinations (6 Cols) */}
          <div className="lg:col-span-6 space-y-6">
            {/* Immediate Action Checklist */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-red-50 border border-red-100 flex items-center justify-center">
                    <AlertTriangle className="w-4 h-4 text-red-600" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-slate-900">Immediate Action Items</h2>
                    <span className="text-[11px] text-slate-500">Urgent steps for on-site safety</span>
                  </div>
                </div>
                <span className="text-xs font-mono font-semibold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-full">
                  {completedActions.size}/{guidance.immediate_actions.length} Done
                </span>
              </div>

              <div className="space-y-2.5">
                {guidance.immediate_actions.map((act, idx) => {
                  const isDone = completedActions.has(idx);
                  return (
                    <div
                      key={idx}
                      onClick={() => toggleActionItem(idx)}
                      className={`flex items-start gap-3.5 p-3.5 rounded-xl border transition-all cursor-pointer ${
                        isDone
                          ? 'bg-emerald-50/40 border-emerald-200 text-slate-500 line-through'
                          : 'bg-slate-50 border-slate-200 hover:border-slate-300 text-slate-800'
                      }`}
                    >
                      <div className="mt-0.5">
                        <div
                          className={`w-5 h-5 rounded-md flex items-center justify-center border transition-all ${
                            isDone
                              ? 'bg-emerald-600 border-emerald-600 text-white'
                              : 'border-slate-300 bg-white'
                          }`}
                        >
                          {isDone ? <Check className="w-3.5 h-3.5 text-white" /> : <span className="text-[10px] font-mono font-bold text-slate-500">{idx + 1}</span>}
                        </div>
                      </div>
                      <p className="text-sm leading-snug select-none font-medium">{act}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Contextual Precautions & Safety Advisories */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
              <div className="flex items-center gap-2.5 border-b border-slate-100 pb-3">
                <div className="w-8 h-8 rounded-lg bg-amber-50 border border-amber-100 flex items-center justify-center">
                  <Shield className="w-4 h-4 text-amber-600" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-900">Safety Precautions</h2>
                  <span className="text-[11px] text-slate-500">Hazard avoidance and protective measures</span>
                </div>
              </div>

              <div className="space-y-2.5">
                {guidance.precautions.map((prec, idx) => (
                  <div key={idx} className="flex items-start gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200">
                    <span className="text-amber-600 text-base leading-none mt-0.5">•</span>
                    <p className="text-xs text-slate-700 leading-relaxed font-normal">{prec}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Recommended Destination Card */}
            {(() => {
              const dest = activeDest;
              const isPrimary = !selectedAlternative || (guidance.recommended_destination && dest?.destination_id === guidance.recommended_destination.destination_id);
              const destConfig = getDestinationCategoryConfig(dest?.destination_type);
              const DestIcon = destConfig.icon;
              return (
                <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                    <div className="flex items-center gap-2.5">
                      <div className={`w-9 h-9 rounded-xl ${destConfig.iconBg} flex items-center justify-center border`}>
                        <DestIcon className="w-5 h-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 className="text-base font-bold text-slate-900">
                            {isPrimary ? 'Recommended Destination' : 'Selected Destination'}
                          </h2>
                          {isPrimary && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-red-100 text-red-800 border border-red-200">
                              PRIMARY
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] text-slate-500">{destConfig.label}</span>
                      </div>
                    </div>
                    {dest && (
                      <span className={`px-2.5 py-1 rounded-lg text-xs font-semibold border ${destConfig.badge}`}>
                        {dest.destination_type}
                      </span>
                    )}
                  </div>

                  {dest ? (
                    <div className="space-y-3.5">
                      <div>
                        <div className="flex items-start justify-between gap-2">
                          <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                            <span>{dest.destination_name}</span>
                          </h3>
                          {dest.rating && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-xs font-mono font-bold shrink-0">
                              <Star className="w-3 h-3 fill-amber-500 text-amber-500" />
                              <span>{dest.rating.toFixed(1)}</span>
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-600 mt-1 flex items-center gap-1.5">
                          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                          <span>{dest.address_or_landmark}</span>
                        </p>
                        {dest.contact_phone && (
                          <p className="text-xs text-red-600 mt-1 flex items-center gap-1.5 font-mono font-semibold">
                            <Phone className="w-3.5 h-3.5 text-red-500 shrink-0" />
                            <span>Emergency Contact: {dest.contact_phone}</span>
                          </p>
                        )}
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
                        <div className="bg-slate-50 border border-slate-200 p-2.5 rounded-xl">
                          <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider block mb-0.5">Road Distance</span>
                          <span className="text-xs font-bold text-slate-900">{dest.distance_km} km</span>
                        </div>

                        <div className="bg-slate-50 border border-slate-200 p-2.5 rounded-xl">
                          <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider block mb-0.5">Est. Drive</span>
                          <span className="text-xs font-bold text-slate-900">
                            {dest.estimated_drive_minutes ? `~${Math.round(dest.estimated_drive_minutes)} min` : 'Direct Route'}
                          </span>
                        </div>

                        <div className="bg-slate-50 border border-slate-200 p-2.5 rounded-xl">
                          <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider block mb-0.5">Status</span>
                          <span className={`text-xs font-bold ${dest.open_now === true ? 'text-emerald-700' : dest.open_now === false ? 'text-rose-700' : 'text-slate-800'}`}>
                            {dest.open_now === true ? 'OPEN NOW' : dest.open_now === false ? 'CLOSED' : 'OPERATIONAL'}
                          </span>
                        </div>

                        <div className="bg-slate-50 border border-slate-200 p-2.5 rounded-xl">
                          <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-wider block mb-0.5">Source</span>
                          <span className="text-[10px] font-mono text-slate-600 truncate block">
                            {dest.provider || 'Live Places'}
                          </span>
                        </div>
                      </div>

                      {dest.suitability_reason && (
                        <p className="text-xs text-slate-700 bg-slate-50 p-3 rounded-xl border border-slate-200 leading-relaxed">
                          <strong className="text-slate-900">Selection Rationale: </strong>
                          {dest.suitability_reason}
                        </p>
                      )}

                      <div className="flex flex-wrap items-center gap-2 pt-2">
                        <button
                          onClick={() => {
                            setSelectedAlternative(null);
                            mapContainerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                          }}
                          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all shadow-sm cursor-pointer"
                        >
                          <Navigation className="w-3.5 h-3.5" />
                          <span>View Route</span>
                        </button>

                        <a
                          href={getGoogleMapsDirectionsUrl(dest)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white hover:bg-slate-100 text-slate-800 border border-slate-300 text-xs font-bold transition-all shadow-sm cursor-pointer"
                        >
                          <ExternalLink className="w-3.5 h-3.5 text-slate-500" />
                          <span>Navigate with Google Maps ↗</span>
                        </a>
                      </div>

                      {!isPrimary && (
                        <button
                          onClick={() => setSelectedAlternative(null)}
                          className="w-full py-2.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold transition-all flex items-center justify-center gap-1.5 cursor-pointer border border-slate-300 mt-2"
                        >
                          <Compass className="w-3.5 h-3.5 text-slate-600" />
                          <span>Reset to Primary Recommended Destination</span>
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="p-4 rounded-xl bg-slate-50 border border-amber-200 text-center space-y-2">
                      <AlertCircle className="w-8 h-8 text-amber-600 mx-auto" />
                      <h3 className="text-sm font-semibold text-slate-900">No Verified Destination Available</h3>
                      <p className="text-xs text-slate-600 max-w-sm mx-auto leading-relaxed">
                        {guidance.destination_reason || 'No confirmed emergency facility is currently available in this sector. Remain sheltered in place and await responder directives.'}
                      </p>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Other Nearby Options (Alternatives) */}
            {guidance.nearby_alternatives && guidance.nearby_alternatives.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center">
                      <Compass className="w-4 h-4 text-blue-600" />
                    </div>
                    <div>
                      <h2 className="text-base font-bold text-slate-900">Other Relevant Nearby Facilities</h2>
                      <span className="text-[11px] text-slate-500">Alternative operational destinations ranked by road travel time</span>
                    </div>
                  </div>
                  <span className="text-xs font-mono font-semibold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-full">
                    {guidance.nearby_alternatives.length} Nearby
                  </span>
                </div>

                <div className="space-y-3">
                  {guidance.nearby_alternatives.map((alt, idx) => {
                    const altConfig = getDestinationCategoryConfig(alt.destination_type);
                    const AltIcon = altConfig.icon;
                    const isSelected = selectedAlternative?.destination_id === alt.destination_id;
                    return (
                      <div
                        key={alt.destination_id || idx}
                        className={`p-4 rounded-xl border transition-all ${
                          isSelected
                            ? 'bg-blue-50/60 border-blue-300 ring-2 ring-blue-400/30'
                            : 'bg-slate-50 border-slate-200 hover:border-slate-300'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="flex items-start gap-2.5">
                            <div className={`w-8 h-8 rounded-lg ${altConfig.iconBg} flex items-center justify-center border shrink-0 mt-0.5`}>
                              <AltIcon className="w-4 h-4" />
                            </div>
                            <div>
                              <h4 className="text-xs font-bold text-slate-900 leading-snug">{alt.destination_name}</h4>
                              <p className="text-[11px] text-slate-500 mt-0.5">{alt.address_or_landmark}</p>
                            </div>
                          </div>

                          <div className="flex items-center gap-1.5 shrink-0">
                            {alt.rating && (
                              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-amber-50 border border-amber-200 text-amber-800 text-[10px] font-mono font-bold">
                                <Star className="w-2.5 h-2.5 fill-amber-500 text-amber-500" />
                                {alt.rating.toFixed(1)}
                              </span>
                            )}
                            <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${altConfig.badge}`}>
                              {alt.destination_type}
                            </span>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200 text-[11px]">
                          <div className="flex items-center gap-3 text-slate-600 font-mono">
                            <span><strong className="text-slate-900">{alt.distance_km} km</strong> road</span>
                            <span>•</span>
                            <span>ETA: <strong className="text-slate-900">~{Math.round(alt.estimated_drive_minutes || 0)} min</strong></span>
                            {alt.open_now !== undefined && (
                              <>
                                <span>•</span>
                                <span className={alt.open_now ? 'text-emerald-700 font-bold' : 'text-rose-700 font-bold'}>
                                  {alt.open_now ? 'OPEN' : 'CLOSED'}
                                </span>
                              </>
                            )}
                          </div>

                          <div className="flex items-center gap-2 shrink-0">
                            <button
                              onClick={() => {
                                setSelectedAlternative(alt);
                                mapContainerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                              }}
                              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer shadow-sm flex items-center gap-1 ${
                                isSelected
                                  ? 'bg-blue-600 text-white'
                                  : 'bg-white hover:bg-slate-100 text-slate-800 border border-slate-300'
                              }`}
                            >
                              <Navigation className="w-3 h-3" />
                              <span>{isSelected ? 'Viewing Route' : 'View Route'}</span>
                            </button>

                            <a
                              href={getGoogleMapsDirectionsUrl(alt)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="px-3 py-1.5 rounded-lg text-xs font-bold bg-white hover:bg-slate-100 text-slate-800 border border-slate-300 transition-all shadow-sm flex items-center gap-1 cursor-pointer"
                            >
                              <ExternalLink className="w-3 h-3 text-slate-500" />
                              <span className="hidden sm:inline">Google Maps ↗</span>
                            </a>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Interactive Map & Live Corridor Routing (6 Cols) */}
          <div className="lg:col-span-6 space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm flex flex-col h-[520px] lg:h-[680px]">
              {/* Map Header & Controls */}
              <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-white">
                <div className="flex items-center gap-2">
                  <Navigation className="w-4 h-4 text-red-600" />
                  <span className="text-xs font-bold text-slate-900 uppercase tracking-wider font-mono">Real Road Route Map</span>
                </div>

                <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-lg border border-slate-200 text-xs">
                  <button
                    onClick={() => setMapType('roadmap')}
                    className={`px-2.5 py-1 rounded-md transition-all font-semibold cursor-pointer ${
                      mapType === 'roadmap' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    Roadmap
                  </button>
                  <button
                    onClick={() => setMapType('satellite')}
                    className={`px-2.5 py-1 rounded-md transition-all font-semibold cursor-pointer ${
                      mapType === 'satellite' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    Satellite
                  </button>
                </div>
              </div>

              {/* Map Canvas Container */}
              <div className="relative flex-1 w-full h-full bg-slate-100">
                <div ref={mapContainerRef} className="w-full h-full" />

                {/* Route Status Overlay */}
                {guidance.route && guidance.route.route_status === 'RESTRICTED' ? (
                  <div className="absolute top-3 left-3 bg-white/95 backdrop-blur-md border border-amber-300 p-3 rounded-xl shadow-md text-xs space-y-1.5 max-w-sm">
                    <div className="flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
                      <span className="font-bold text-slate-900 font-sans">
                        {guidance.route.distance_km} km (~{Math.round(guidance.route.estimated_duration_minutes)} min drive)
                      </span>
                    </div>
                    <div className="flex items-start gap-1.5 text-amber-800 font-medium">
                      <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-amber-600 mt-0.5" />
                      <span className="text-[11px] leading-tight">
                        Google route found — access restriction warning (restricted usage or private roads). Proceed with caution.
                      </span>
                    </div>
                  </div>
                ) : guidance.route && (guidance.route.route_status === 'CALCULATED' || guidance.route.route_status === 'ROUTE_UNSAFE') ? (
                  <div className="absolute top-3 left-3 bg-white/95 backdrop-blur-md border border-slate-200 p-3 rounded-xl shadow-md text-xs space-y-1">
                    <div className="flex items-center gap-2">
                      <span className={`w-2.5 h-2.5 rounded-full ${guidance.route.route_status === 'ROUTE_UNSAFE' ? 'bg-red-600' : 'bg-emerald-600'}`} />
                      <span className="font-bold text-slate-900 font-sans">
                        {guidance.route.distance_km} km ({guidance.route.estimated_duration_minutes} min drive)
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500 block font-mono">{guidance.route.provider}</span>
                  </div>
                ) : guidance.route && guidance.route.route_status === 'ROUTE_PROVIDER_ERROR' ? (
                  <div className="absolute top-3 left-3 bg-white/95 backdrop-blur-md border border-amber-300 p-3 rounded-xl shadow-md text-xs space-y-1 max-w-xs">
                    <div className="flex items-center gap-1.5 text-amber-800 font-bold">
                      <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600" />
                      <span>Route Provider Temporarily Unavailable</span>
                    </div>
                    <span className="text-[11px] text-slate-600 block">
                      Google Routes API limit reached (HTTP 429). Destination is verified, but live route corridor cannot be computed right now.
                    </span>
                  </div>
                ) : (
                  <div className="absolute top-3 left-3 bg-white/95 backdrop-blur-md border border-amber-300 p-3 rounded-xl shadow-md text-xs space-y-1 max-w-xs">
                    <div className="flex items-center gap-1.5 text-amber-800 font-bold">
                      <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600" />
                      <span>No Driving Route Available</span>
                    </div>
                    <span className="text-[11px] text-slate-600 block">
                      Google Routes found no accessible driving corridor to destination. Follow on-site emergency directives.
                    </span>
                  </div>
                )}
              </div>

              {/* Route Warnings & Hazards Footer */}
              {guidance.route_warnings && guidance.route_warnings.length > 0 && (
                <div className="p-3.5 bg-red-50 border-t border-red-200 text-xs space-y-1">
                  {guidance.route_warnings.map((w, idx) => (
                    <p key={idx} className="text-red-800 flex items-start gap-1.5 leading-snug font-medium">
                      <AlertTriangle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
                      <span>{w}</span>
                    </p>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
