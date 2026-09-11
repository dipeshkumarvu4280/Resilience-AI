import React, { useState, useEffect, useRef } from 'react';
import {
  X,
  MapPin,
  Clock,
  User,
  Phone,
  ShieldCheck,
  AlertTriangle,
  FileText,
  Send,
  CheckCircle,
  RefreshCw,
  Activity,
  Boxes,
  ChevronDown,
  ChevronUp,
  Info,
  ShieldAlert,
  Eye,
  Sparkles,
  Layers,
  Globe,
  Camera,
  Check,
  HelpCircle,
} from 'lucide-react';
import type {
  OfficerReportDetailResponse,
  ReportPriority,
  ReportStatus,
} from '../../types';
import {
  getOfficerReportById,
  acknowledgeOfficerReport,
  updateOfficerReportPriority,
  updateOfficerReportStatus,
  addOfficerNote,
  analyzeOfficerVisualEvidence,
  extractOfficerTextEvidence,
} from '../../services/api';
import NeedsAndAllocationsPanel from './NeedsAndAllocationsPanel';
import { IncidentEvolutionTimeline } from '../common/IncidentEvolutionTimeline';
import { SubmitFieldVerificationModal } from '../volunteer/SubmitFieldVerificationModal';
import { loadGoogleMaps, hasGoogleMapsApiKey } from '../../utils/googleMapsLoader';

const REPORT_LIGHT_STYLES: google.maps.MapTypeStyle[] = [
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#cce5ff' }] },
  { featureType: 'landscape', elementType: 'geometry', stylers: [{ color: '#f8fafc' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#ffffff' }] },
  { featureType: 'road.arterial', elementType: 'geometry', stylers: [{ color: '#e2e8f0' }] },
  { featureType: 'poi', elementType: 'geometry', stylers: [{ color: '#f1f5f9' }] },
  { featureType: 'administrative', elementType: 'labels.text.fill', stylers: [{ color: '#475569' }] },
];

interface ReportDetailsModalProps {
  reportId: string;
  onClose: () => void;
  onReportUpdated?: () => void;
}

export const ReportDetailsModal: React.FC<ReportDetailsModalProps> = ({
  reportId,
  onClose,
  onReportUpdated,
}) => {
  const [report, setReport] = useState<OfficerReportDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'incident' | 'resources' | 'evolution'>('incident');
  const [showVerificationModal, setShowVerificationModal] = useState(false);

  // Actions state
  const [actionLoading, setActionLoading] = useState(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Notes state
  const [newNote, setNewNote] = useState('');
  const [submittingNote, setSubmittingNote] = useState(false);

  // Status transition reason
  const [statusReason, setStatusReason] = useState('');

  // Map state & reference (Google Maps Platform)
  const [mapType, setMapType] = useState<'roadmap' | 'satellite'>('roadmap');
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const googleMapRef = useRef<google.maps.Map | null>(null);
  const googleObjRef = useRef<typeof google | null>(null);
  const markerRef = useRef<google.maps.Marker | null>(null);
  const activeInfoWindowRef = useRef<google.maps.InfoWindow | null>(null);

  // Image lightbox
  const [activeMediaUrl, setActiveMediaUrl] = useState<string | null>(null);

  // Evidence verification explainability accordion state
  const [showWhyVerification, setShowWhyVerification] = useState(false);
  const [showWhyCorroboration, setShowWhyCorroboration] = useState(false);
  const [showVisualModal, setShowVisualModal] = useState(false);
  const [analyzingVisual, setAnalyzingVisual] = useState(false);
  const [analyzingText, setAnalyzingText] = useState(false);

  const handleRunTextExtraction = async () => {
    if (!report || analyzingText) return;
    setAnalyzingText(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await extractOfficerTextEvidence(report.report_id);
      setReport(updated);
      if (updated.llm_extraction?.status === 'SUCCESS') {
        const prov = updated.llm_extraction.provider || 'AI';
        const fallbackNote = updated.llm_extraction.fallback_used ? ' (via OpenAI Fallback)' : '';
        setActionSuccess(`AI text evidence extracted successfully by ${prov}${fallbackNote}.`);
      } else {
        setActionError(updated.llm_extraction?.error_message || 'AI text extraction temporarily unavailable.');
      }
      onReportUpdated?.();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Text evidence extraction failed.');
    } finally {
      setAnalyzingText(false);
    }
  };

  const handleRunVisualAnalysis = async () => {
    if (!report || analyzingVisual) return;
    setAnalyzingVisual(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await analyzeOfficerVisualEvidence(report.report_id);
      setReport(updated);
      if (updated.visual_evidence?.status === 'SUCCESS') {
        setActionSuccess('AI multimodal visual analysis completed.');
      } else if (updated.visual_evidence?.status === 'TEMPORARILY_UNAVAILABLE') {
        setActionError('Visual analysis service is temporarily unavailable. Your camera evidence has been safely preserved. Please try again shortly.');
      }
      onReportUpdated?.();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Visual evidence analysis failed.');
    } finally {
      setAnalyzingVisual(false);
    }
  };

  const fetchDetails = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getOfficerReportById(reportId);
      setReport(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load report details.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDetails();
  }, [reportId]);

  const handleToggleMapType = (type: 'roadmap' | 'satellite') => {
    setMapType(type);
    if (googleMapRef.current) {
      googleMapRef.current.setMapTypeId(type);
      if (type === 'roadmap') {
        googleMapRef.current.setOptions({ styles: REPORT_LIGHT_STYLES });
      } else {
        googleMapRef.current.setOptions({ styles: [] });
      }
    }
  };

  // Google Maps setup for authoritative incident location
  useEffect(() => {
    let isMounted = true;
    if (!report || !mapContainerRef.current) return;

    const lat = report.location?.latitude;
    const lng = report.location?.longitude;

    const isValidCoord =
      typeof lat === 'number' &&
      typeof lng === 'number' &&
      !isNaN(lat) &&
      !isNaN(lng) &&
      lat >= -90 &&
      lat <= 90 &&
      lng >= -180 &&
      lng <= 180 &&
      !(lat === 0 && lng === 0);

    if (!isValidCoord || !hasGoogleMapsApiKey()) return;

    const initMap = async () => {
      try {
        const googleObj = await loadGoogleMaps();
        if (!isMounted || !mapContainerRef.current) return;

        googleObjRef.current = googleObj;

        // If map is already initialized, just update marker and panTo without resetting
        if (googleMapRef.current) {
          googleMapRef.current.panTo({ lat, lng });
          if (markerRef.current) {
            markerRef.current.setPosition({ lat, lng });
          }
          return;
        }

        const map = new googleObj.maps.Map(mapContainerRef.current, {
          center: { lat, lng },
          zoom: 15,
          minZoom: 4,
          maxZoom: 19,
          mapTypeId: mapType,
          disableDefaultUI: true,
          zoomControl: true,
          gestureHandling: 'greedy',
          scrollwheel: true,
          isFractionalZoomEnabled: true,
          clickableIcons: false,
          styles: mapType === 'roadmap' ? REPORT_LIGHT_STYLES : [],
        });

        const svgPin = `
          <svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44">
            <defs>
              <filter id="shadow-rep" x="-20%" y="-20%" width="140%" height="140%">
                <feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#000000" flood-opacity="0.4"/>
              </filter>
            </defs>
            <circle cx="22" cy="22" r="20" fill="#dc2626" fill-opacity="0.25" stroke="#dc2626" stroke-width="2" stroke-dasharray="3 2"/>
            <circle cx="22" cy="22" r="14" fill="#dc2626" stroke="#ffffff" stroke-width="3" filter="url(#shadow-rep)"/>
            <circle cx="22" cy="22" r="5" fill="#ffffff"/>
          </svg>
        `;

        const marker = new googleObj.maps.Marker({
          map,
          position: { lat, lng },
          title: `Authoritative Incident Location: ${report.emergency_type} (${report.report_id})`,
          icon: {
            url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svgPin),
            scaledSize: new googleObj.maps.Size(40, 40),
            anchor: new googleObj.maps.Point(20, 20),
          },
          zIndex: 100,
        });

        const infoContent = document.createElement('div');
        infoContent.className = 'p-3 font-sans max-w-xs';
        infoContent.innerHTML = `
          <div style="font-family: system-ui, -apple-system, sans-serif;">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 4px;">
              <span style="font-size: 11px; font-weight: 800; color: #dc2626; font-family: monospace;">${report.emergency_type}</span>
              <span style="font-size: 10px; font-weight: 700; color: #64748b;">${report.report_id}</span>
            </div>
            <div style="font-size: 11px; color: #0f172a; margin-top: 2px;">
              ${report.location.street_address || report.location.address || 'Authoritative GPS coordinates verified'}
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

        googleMapRef.current = map;
        markerRef.current = marker;
      } catch (err) {
        console.warn('Could not initialize Google Map in ReportDetailsModal:', err);
      }
    };

    initMap();

    return () => {
      isMounted = false;
    };
  }, [report?.location?.latitude, report?.location?.longitude]);

  const handleAcknowledge = async () => {
    if (!report) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await acknowledgeOfficerReport(report.report_id);
      setReport(updated);
      setActionSuccess('Report acknowledged successfully.');
      onReportUpdated?.();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Acknowledgement failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handlePriorityChange = async (newPriority: ReportPriority) => {
    if (!report || report.priority === newPriority) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await updateOfficerReportPriority(report.report_id, newPriority);
      setReport(updated);
      setActionSuccess(`Priority updated to ${newPriority}.`);
      onReportUpdated?.();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Priority update failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleStatusTransition = async (statusToSet: ReportStatus) => {
    if (!report) return;
    setActionLoading(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const updated = await updateOfficerReportStatus(
        report.report_id,
        statusToSet,
        statusReason.trim() || undefined
      );
      setReport(updated);
      setActionSuccess(`Status transitioned to ${statusToSet}.`);
      setStatusReason('');
      onReportUpdated?.();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Status transition failed.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!report || !newNote.trim()) return;
    setSubmittingNote(true);
    setActionError(null);
    try {
      const updated = await addOfficerNote(report.report_id, newNote.trim());
      setReport(updated);
      setNewNote('');
      setActionSuccess('Operational note recorded.');
      onReportUpdated?.();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Could not save note.');
    } finally {
      setSubmittingNote(false);
    }
  };

  const getPriorityBadgeClass = (priority?: string) => {
    switch (priority) {
      case 'CRITICAL':
        return 'bg-red-100 text-red-800 border-red-300 font-bold';
      case 'HIGH':
        return 'bg-orange-100 text-orange-800 border-orange-300 font-bold';
      case 'MEDIUM':
        return 'bg-amber-100 text-amber-800 border-amber-300 font-medium';
      case 'LOW':
        return 'bg-blue-100 text-blue-800 border-blue-300 font-medium';
      default:
        return 'bg-slate-100 text-slate-600 border-slate-300 font-medium';
    }
  };

  const getCitizenImpactBadgeClass = (impact?: string) => {
    switch (impact) {
      case 'CRITICAL':
        return 'bg-red-50 text-red-700 border-red-200 font-bold';
      case 'HIGH':
        return 'bg-orange-50 text-orange-700 border-orange-200 font-bold';
      case 'MEDIUM':
        return 'bg-amber-50 text-amber-700 border-amber-200 font-semibold';
      case 'LOW':
        return 'bg-blue-50 text-blue-700 border-blue-200 font-semibold';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200 font-medium';
    }
  };

  const getConfidenceBadgeClass = (confidence?: string) => {
    switch (confidence) {
      case 'HIGH':
        return 'bg-emerald-50 text-emerald-800 border-emerald-300 font-bold';
      case 'MEDIUM':
        return 'bg-amber-50 text-amber-800 border-amber-300 font-bold';
      case 'LOW':
        return 'bg-purple-50 text-purple-800 border-purple-300 font-bold';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-300 font-medium';
    }
  };

  const getVerificationStatusBadgeClass = (status?: string) => {
    switch (status) {
      case 'PARTIALLY_VERIFIED':
        return 'bg-emerald-50 text-emerald-800 border-emerald-300 font-bold';
      case 'UNVERIFIED':
        return 'bg-slate-100 text-slate-700 border-slate-300 font-semibold';
      case 'CORROBORATED':
      case 'FIELD_VERIFIED':
        return 'bg-blue-50 text-blue-800 border-blue-300 font-bold';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200 font-medium';
    }
  };

  const getCorroborationBadgeClass = (status?: string) => {
    switch (status) {
      case 'CORROBORATED':
        return 'bg-emerald-50 text-emerald-800 border-emerald-300 font-bold';
      case 'PARTIALLY_CORROBORATED':
        return 'bg-blue-50 text-blue-800 border-blue-300 font-bold';
      case 'CONFLICTED':
        return 'bg-red-50 text-red-800 border-red-300 font-bold';
      case 'NO_CORROBORATION':
      default:
        return 'bg-slate-100 text-slate-700 border-slate-300 font-semibold';
    }
  };

  const getConsistencyBadgeClass = (consistency?: string) => {
    switch (consistency) {
      case 'SUPPORTED':
        return 'bg-emerald-50 text-emerald-800 border-emerald-300 font-bold';
      case 'PARTIALLY_SUPPORTED':
        return 'bg-blue-50 text-blue-800 border-blue-300 font-bold';
      case 'NOT_SUPPORTED':
        return 'bg-amber-50 text-amber-800 border-amber-300 font-bold';
      case 'INCONCLUSIVE':
        return 'bg-purple-50 text-purple-800 border-purple-300 font-bold';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200 font-medium';
    }
  };

  const getClaimStatusBadgeClass = (status?: string) => {
    switch (status) {
      case 'SUPPORTED':
        return 'bg-emerald-100 text-emerald-800 border-emerald-300 font-bold';
      case 'NOT_OBSERVABLE':
        return 'bg-slate-100 text-slate-700 border-slate-300 font-semibold';
      case 'CONTRADICTED':
        return 'bg-red-100 text-red-800 border-red-300 font-bold';
      case 'UNCERTAIN':
        return 'bg-amber-100 text-amber-800 border-amber-300 font-semibold';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };



  const getStatusBadgeClass = (status?: string) => {
    switch (status) {
      case 'RECEIVED':
        return 'bg-red-50 text-red-700 border-red-200 animate-pulse';
      case 'ACKNOWLEDGED':
        return 'bg-amber-50 text-amber-800 border-amber-200';
      case 'UNDER_ASSESSMENT':
        return 'bg-blue-50 text-blue-800 border-blue-200';
      case 'ACTION_REQUIRED':
        return 'bg-purple-50 text-purple-800 border-purple-200';
      case 'RESOLVED':
        return 'bg-emerald-50 text-emerald-800 border-emerald-200';
      default:
        return 'bg-slate-100 text-slate-700 border-slate-200';
    }
  };

  const formatEmergencyTitle = (type?: string | null) => {
    if (!type || type === 'Other' || type === 'OTHER' || type === 'UNKNOWN' || type === 'Unspecified') {
      return 'Emergency Incident';
    }
    const cleanType = type.trim();
    if (cleanType.toLowerCase().endsWith('emergency')) {
      return cleanType;
    }
    return `${cleanType} Emergency`;
  };

  const hasHazardDiscrepancy = Boolean(
    report &&
    report.llm_extraction?.hazard?.value &&
    report.emergency_type &&
    report.llm_extraction.status === 'SUCCESS' &&
    report.llm_extraction.hazard.confidence >= 0.70 &&
    !report.emergency_type.toLowerCase().includes(report.llm_extraction.hazard.value.toLowerCase()) &&
    !report.llm_extraction.hazard.value.toLowerCase().includes(report.emergency_type.toLowerCase())
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 md:p-6 bg-slate-900/60 backdrop-blur-xs overflow-y-auto">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl w-full max-w-5xl max-h-[calc(100dvh-1rem)] sm:max-h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Modal Header */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-slate-200 bg-slate-50/80 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className={`w-8 h-8 sm:w-9 sm:h-9 rounded-xl border flex items-center justify-center font-bold flex-shrink-0 ${
              report?.emergency_type === 'Flood'
                ? 'bg-blue-50 border-blue-200 text-blue-600'
                : report?.emergency_type === 'Fire'
                ? 'bg-red-50 border-red-200 text-red-600'
                : 'bg-amber-50 border-amber-200 text-amber-600'
            }`}>
              <AlertTriangle className="w-4 h-4 sm:w-5 sm:h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                <span className="text-sm sm:text-base font-bold text-slate-900 truncate">
                  {formatEmergencyTitle(report?.emergency_type)}
                </span>
                {report && (
                  <span className="font-mono text-[11px] sm:text-xs font-semibold px-2 py-0.5 rounded bg-slate-200 text-slate-800">
                    {report.report_id}
                  </span>
                )}
                {hasHazardDiscrepancy && report?.llm_extraction?.hazard && (
                  <span className="inline-flex items-center gap-1 text-[10px] sm:text-[11px] font-bold px-2 py-0.5 rounded-full bg-purple-100 text-purple-800 border border-purple-200 animate-pulse">
                    <Sparkles className="w-3 h-3 text-purple-600" />
                    AI: {report.llm_extraction.hazard.value} ({Math.round(report.llm_extraction.hazard.confidence * 100)}%)
                  </span>
                )}
              </div>
              <p className="text-[11px] sm:text-xs text-slate-500 truncate hidden xs:block">
                Authorized Watch Officer Incident Inspection & Assessment Console
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1 sm:gap-2 flex-shrink-0">
            <button
              onClick={fetchDetails}
              disabled={loading}
              className="p-1.5 sm:p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-200/60 transition-colors"
              title="Refresh Report"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-red-600' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 sm:p-2 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Content */}
        <div className="flex-1 overflow-y-auto p-3 sm:p-6 space-y-4 sm:space-y-6 touch-scroll">
          {loading && !report && (
            <div className="py-20 text-center space-y-3">
              <RefreshCw className="w-8 h-8 text-red-600 animate-spin mx-auto" />
              <p className="text-sm font-semibold text-slate-600">Retrieving authoritative emergency record...</p>
            </div>
          )}

          {error && (
            <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
              {error}
            </div>
          )}

          {report && (
            <>
              {/* Alert Feedback Banners */}
              {actionSuccess && (
                <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-emerald-600" />
                    {actionSuccess}
                  </span>
                  <button onClick={() => setActionSuccess(null)} className="text-emerald-700 hover:text-emerald-900">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {actionError && (
                <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-semibold flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-600" />
                    {actionError}
                  </span>
                  <button onClick={() => setActionError(null)} className="text-red-700 hover:text-red-900">
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {/* Tab Navigation */}
              <div className="flex border-b border-slate-200 gap-3 sm:gap-6 overflow-x-auto no-scrollbar touch-scroll whitespace-nowrap">
                <button
                  type="button"
                  onClick={() => setActiveTab('incident')}
                  className={`pb-2.5 sm:pb-3 text-xs font-bold flex items-center gap-1.5 sm:gap-2 border-b-2 transition-all cursor-pointer whitespace-nowrap ${
                    activeTab === 'incident'
                      ? 'border-red-600 text-red-600'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <Activity className="w-4 h-4" />
                  <span>Incident Overview & Assessment</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('resources')}
                  className={`pb-2.5 sm:pb-3 text-xs font-bold flex items-center gap-1.5 sm:gap-2 border-b-2 transition-all cursor-pointer whitespace-nowrap ${
                    activeTab === 'resources'
                      ? 'border-red-600 text-red-600'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <Boxes className="w-4 h-4" />
                  <span>Resource Coordination & Allocations</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('evolution')}
                  className={`pb-2.5 sm:pb-3 text-xs font-bold flex items-center gap-1.5 sm:gap-2 border-b-2 transition-all cursor-pointer whitespace-nowrap ${
                    activeTab === 'evolution'
                      ? 'border-red-600 text-red-600'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  <Clock className="w-4 h-4" />
                  <span>Incident Evolution Timeline</span>
                </button>
              </div>

              {activeTab === 'incident' ? (
                <>
                  {/* Top Operational Action Ribbon */}
                  <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex flex-wrap items-center gap-3">
                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">CITIZEN IMPACT</div>
                    <span className={`inline-block mt-0.5 px-2.5 py-1 rounded-lg border text-xs ${getCitizenImpactBadgeClass(report.citizen_impact_level)}`}>
                      {report.citizen_impact_level || 'NOT_SURE'}
                    </span>
                  </div>

                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">EVIDENCE CONFIDENCE</div>
                    <span className={`inline-block mt-0.5 px-2.5 py-1 rounded-lg border text-xs font-bold ${getConfidenceBadgeClass(report.evidence_verification?.confidence_band || 'LOW')}`}>
                      {report.evidence_verification?.confidence_band || 'LOW'}
                    </span>
                  </div>

                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">VERIFICATION STATUS</div>
                    <span className={`inline-block mt-0.5 px-2.5 py-1 rounded-lg border text-xs font-bold ${getVerificationStatusBadgeClass(report.evidence_verification?.verification_status || 'UNVERIFIED')}`}>
                      {report.evidence_verification?.verification_status || 'UNVERIFIED'}
                    </span>
                  </div>

                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">LIFECYCLE STATUS</div>
                    <span className={`inline-block mt-0.5 px-3 py-1 rounded-lg border text-xs font-bold ${getStatusBadgeClass(report.status)}`}>
                      {report.status}
                    </span>
                  </div>

                  <div>
                    <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">OFFICER PRIORITY</div>
                    <span className={`inline-block mt-0.5 px-3 py-1 rounded-lg border text-xs ${getPriorityBadgeClass(report.priority)}`}>
                      {report.priority || 'UNASSESSED'}
                    </span>
                  </div>

                  {report.acknowledged_at && (
                    <div>
                      <div className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">ACKNOWLEDGED BY</div>
                      <div className="text-xs font-semibold text-slate-700 mt-0.5">
                        {report.acknowledged_by || 'Authenticated Operator'}
                      </div>
                    </div>
                  )}
                </div>

                {/* Status Progression Controls */}
                <div className="flex flex-wrap items-center gap-2">
                  {report.status === 'RECEIVED' && (
                    <button
                      onClick={handleAcknowledge}
                      disabled={actionLoading}
                      className="px-4 py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold shadow-xs transition-all flex items-center gap-1.5"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      <span>ACKNOWLEDGE REPORT</span>
                    </button>
                  )}

                  {report.status === 'ACKNOWLEDGED' && (
                    <button
                      onClick={() => handleStatusTransition('UNDER_ASSESSMENT')}
                      disabled={actionLoading}
                      className="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-xs transition-all flex items-center gap-1.5"
                    >
                      <Activity className="w-4 h-4" />
                      <span>Start Assessment</span>
                    </button>
                  )}

                  {report.status === 'UNDER_ASSESSMENT' && (
                    <button
                      onClick={() => handleStatusTransition('ACTION_REQUIRED')}
                      disabled={actionLoading}
                      className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold shadow-xs transition-all flex items-center gap-1.5"
                    >
                      <AlertTriangle className="w-4 h-4" />
                      <span>Mark Action Required</span>
                    </button>
                  )}

                  {report.status === 'ACTION_REQUIRED' && (
                    <button
                      onClick={() => handleStatusTransition('RESOLVED')}
                      disabled={actionLoading}
                      className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold shadow-xs transition-all flex items-center gap-1.5"
                    >
                      <CheckCircle className="w-4 h-4" />
                      <span>Resolve Incident</span>
                    </button>
                  )}

                  {/* Priority Switcher Dropdown */}
                  <div className="flex items-center gap-1.5 bg-white border border-slate-200 rounded-xl px-2.5 py-1.5 shadow-2xs">
                    <span className="text-[11px] font-bold text-slate-500">Set Priority:</span>
                    <select
                      value={report.priority || 'UNASSESSED'}
                      onChange={(e) => handlePriorityChange(e.target.value as ReportPriority)}
                      disabled={actionLoading}
                      className="text-xs font-bold text-slate-800 bg-transparent border-none focus:ring-0 cursor-pointer outline-none"
                    >
                      <option value="UNASSESSED">UNASSESSED</option>
                      <option value="LOW">LOW</option>
                      <option value="MEDIUM">MEDIUM</option>
                      <option value="HIGH">HIGH</option>
                      <option value="CRITICAL">CRITICAL</option>
                    </select>
                  </div>

                  {/* Ground Verification Button */}
                  <button
                    type="button"
                    onClick={() => setShowVerificationModal(true)}
                    className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold shadow-xs transition-all flex items-center gap-1.5"
                  >
                    <Eye className="w-4 h-4" />
                    <span>Ground Verification</span>
                  </button>
                </div>
              </div>

              {/* 2-Column Main Workspace */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Left Column: Citizen Report Details, Location & Media (7 cols) */}
                <div className="lg:col-span-7 space-y-6">
                  {/* Citizen Description Card */}
                  <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs space-y-4">
                    <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-red-600" />
                        <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                          EMERGENCY INCIDENT DETAILS
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-400 flex items-center gap-1 font-mono">
                        <Clock className="w-3 h-3 text-slate-400" />
                        Submitted {new Date(report.created_at).toLocaleString()}
                      </span>
                    </div>

                    <div>
                      <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">DESCRIPTION</h4>
                      <p className="text-sm text-slate-800 leading-relaxed bg-slate-50/70 p-3.5 rounded-xl border border-slate-100">
                        {report.description}
                      </p>
                    </div>

                    {/* Citizen Info Grid */}
                    <div className="grid grid-cols-2 gap-3 pt-2">
                      <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                          <User className="w-3 h-3" /> CITIZEN NAME
                        </div>
                        <div className="text-xs font-bold text-slate-900 mt-1">
                          {report.citizen_name}
                        </div>
                      </div>

                      <div className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                        <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                          <Phone className="w-3 h-3" /> CONTACT PHONE
                        </div>
                        <div className="text-xs font-bold text-slate-900 mt-1 flex items-center justify-between">
                          <span>{report.citizen_phone}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                            report.phone_verified
                              ? 'bg-emerald-100 text-emerald-800'
                              : 'bg-slate-200 text-slate-600'
                          }`}>
                            {report.phone_verified ? 'Verified' : 'Unverified'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Canonical Location & Interactive Google Maps Card */}
                  <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs space-y-4">
                    <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
                      <div className="flex items-center gap-2">
                        <MapPin className="w-4 h-4 text-red-600" />
                        <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                          AUTHORITATIVE INCIDENT LOCATION
                        </span>
                      </div>
                      <span className="text-[11px] font-mono text-slate-500">
                        {report.location.latitude?.toFixed(5)}, {report.location.longitude?.toFixed(5)}
                      </span>
                    </div>

                    {/* Location Breakdown */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
                      <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-100 col-span-2 sm:col-span-3">
                        <span className="text-[10px] text-slate-400 font-bold uppercase block">Resolved Address</span>
                        <span className="font-semibold text-slate-800">
                          {report.location.street_address || report.location.address || 'Address unavailable'}
                        </span>
                      </div>

                      {report.location.landmark && (
                        <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-100">
                          <span className="text-[10px] text-slate-400 font-bold uppercase block">Landmark</span>
                          <span className="font-medium text-slate-700">{report.location.landmark}</span>
                        </div>
                      )}

                      {(report.location.zone_or_district || report.location.manual_zone) && (
                        <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-100">
                          <span className="text-[10px] text-slate-400 font-bold uppercase block">Zone / District</span>
                          <span className="font-medium text-slate-700">{report.location.zone_or_district || report.location.manual_zone}</span>
                        </div>
                      )}

                      {(report.location.city || report.location.state) && (
                        <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-100">
                          <span className="text-[10px] text-slate-400 font-bold uppercase block">City & State</span>
                          <span className="font-medium text-slate-700">{[report.location.city, report.location.state].filter(Boolean).join(', ')}</span>
                        </div>
                      )}
                    </div>

                    {/* Google Maps Embed with Roadmap / Satellite Selector */}
                    <div className="rounded-xl overflow-hidden border border-slate-200 h-64 bg-slate-100 relative">
                      <div ref={mapContainerRef} className="w-full h-full z-0" />

                      {/* Map Type & Controls Overlay */}
                      <div className="absolute top-2.5 right-2.5 z-10 flex items-center gap-1.5 bg-white/90 backdrop-blur-md px-2 py-1 rounded-lg border border-slate-200 shadow-xs text-[10px] font-bold">
                        <button
                          type="button"
                          onClick={() => handleToggleMapType('roadmap')}
                          className={`flex items-center gap-1 px-2.5 py-0.5 rounded transition-all ${
                            mapType === 'roadmap'
                              ? 'bg-slate-900 text-white font-bold'
                              : 'text-slate-600 hover:text-slate-900'
                          }`}
                        >
                          <Layers className="w-3 h-3" />
                          <span>Roadmap</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleToggleMapType('satellite')}
                          className={`flex items-center gap-1 px-2.5 py-0.5 rounded transition-all ${
                            mapType === 'satellite'
                              ? 'bg-blue-600 text-white font-bold'
                              : 'text-slate-600 hover:text-slate-900'
                          }`}
                        >
                          <Globe className="w-3 h-3" />
                          <span>Satellite</span>
                        </button>
                      </div>

                      {/* Authoritative GPS Coordinates Overlay */}
                      <div className="absolute bottom-2.5 left-2.5 z-10 flex items-center gap-1.5 bg-slate-900/80 backdrop-blur-md px-2.5 py-1 rounded-lg text-white text-[10px] font-mono shadow-md">
                        <MapPin className="w-3 h-3 text-red-400" />
                        <span>{report.location.latitude?.toFixed(6)}, {report.location.longitude?.toFixed(6)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Evidence Trust & Verification Section */}
                  <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs space-y-4">
                    <div className="flex flex-wrap items-center justify-between pb-2.5 border-b border-slate-100 gap-2">
                      <div className="flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4 text-red-600" />
                        <span className="text-xs font-bold text-slate-900 uppercase tracking-wider font-mono">
                          EVIDENCE TRUST & VERIFICATION
                        </span>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] px-2 py-0.5 rounded-md font-mono font-bold border ${getConfidenceBadgeClass(report.evidence_verification?.confidence_band || 'LOW')}`}>
                          CONFIDENCE: {report.evidence_verification?.confidence_band || 'LOW'}
                        </span>
                        <span className={`text-[10px] px-2 py-0.5 rounded-md font-mono font-bold border ${getVerificationStatusBadgeClass(report.evidence_verification?.verification_status || 'UNVERIFIED')}`}>
                          {report.evidence_verification?.verification_status || 'UNVERIFIED'}
                        </span>
                      </div>
                    </div>

                    {/* Verification Signals Summary Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                      <div className="p-2 rounded-xl bg-slate-50 border border-slate-100">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">LOCATION MATCH</span>
                        <span className={`font-bold text-[11px] ${
                          report.evidence_verification?.location_match_state === 'MATCH'
                            ? 'text-emerald-700'
                            : report.evidence_verification?.location_match_state === 'NEAR_MATCH'
                            ? 'text-blue-700'
                            : report.evidence_verification?.location_match_state === 'MISMATCH'
                            ? 'text-red-700'
                            : 'text-slate-500'
                        }`}>
                          {report.evidence_verification?.location_match_state || (report.evidence?.distance_from_report_meters !== undefined ? 'MATCH' : 'UNAVAILABLE')}
                          {report.evidence?.distance_from_report_meters !== undefined && report.evidence?.distance_from_report_meters !== null && (
                            <span className="text-[10px] font-normal text-slate-500 block">
                              ({report.evidence.distance_from_report_meters}m)
                            </span>
                          )}
                        </span>
                      </div>

                      <div className="p-2 rounded-xl bg-slate-50 border border-slate-100">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">FRESHNESS</span>
                        <span className={`font-bold text-[11px] ${
                          report.evidence_verification?.evidence_freshness === 'FRESH'
                            ? 'text-emerald-700'
                            : report.evidence_verification?.evidence_freshness === 'AGING'
                            ? 'text-amber-700'
                            : report.evidence_verification?.evidence_freshness === 'STALE'
                            ? 'text-red-700'
                            : 'text-slate-500'
                        }`}>
                          {report.evidence_verification?.evidence_freshness || (report.evidence?.client_capture_timestamp ? 'FRESH' : 'UNAVAILABLE')}
                        </span>
                      </div>

                      <div className="p-2 rounded-xl bg-slate-50 border border-slate-100">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">COMPLETENESS</span>
                        <span className="font-bold text-[11px] text-slate-800">
                          {report.evidence_verification?.report_completeness || 'COMPLETE'}
                        </span>
                      </div>

                      <div className="p-2 rounded-xl bg-slate-50 border border-slate-100">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">CONTENT HASH</span>
                        <span className={`font-bold text-[11px] ${
                          report.evidence?.is_duplicate ? 'text-red-700' : report.evidence?.content_hash ? 'text-emerald-700' : 'text-slate-500'
                        }`}>
                          {report.evidence?.is_duplicate ? 'DUPLICATE' : report.evidence?.content_hash ? 'VERIFIED' : 'NONE'}
                        </span>
                      </div>
                    </div>

                    {/* Live Evidence Media & Geo Details */}
                    {report.evidence && report.evidence.file_url ? (
                      <div className="space-y-3">
                        <div className="flex flex-col sm:flex-row gap-4">
                          {/* Image preview */}
                          <div
                            onClick={() => report.evidence?.file_url && setActiveMediaUrl(report.evidence.file_url)}
                            className="relative group rounded-xl overflow-hidden border border-slate-200 w-full sm:w-56 h-40 bg-black cursor-pointer flex-shrink-0"
                          >
                            <img
                              src={report.evidence.file_url}
                              alt="Captured Live Evidence"
                              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                            />
                            <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white text-xs font-semibold transition-opacity">
                              Click to Enlarge
                            </div>
                            <span className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-black/75 text-emerald-400 text-[10px] font-mono font-bold">
                              LIVE CAPTURE
                            </span>
                          </div>

                          {/* Evidence Metadata */}
                          <div className="flex-1 space-y-2 text-xs font-mono text-slate-700">
                            <div className="grid grid-cols-2 gap-2 text-[11px]">
                              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100">
                                <span className="text-[10px] text-slate-400 uppercase block font-bold">EVIDENCE ID</span>
                                <span className="font-bold text-slate-900">{report.evidence.evidence_id}</span>
                              </div>
                              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100">
                                <span className="text-[10px] text-slate-400 uppercase block font-bold">SOURCE</span>
                                <span className="font-bold text-slate-900">{report.evidence.source}</span>
                              </div>
                            </div>

                            {report.evidence.latitude && report.evidence.longitude && (
                              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-[11px] space-y-0.5">
                                <div className="text-[10px] text-slate-400 uppercase font-bold">CAPTURE GEOLOCATION</div>
                                <div>
                                  {report.evidence.latitude.toFixed(5)}, {report.evidence.longitude.toFixed(5)}
                                  {report.evidence.accuracy_meters && (
                                    <span className="text-slate-500 font-normal"> (±{report.evidence.accuracy_meters}m)</span>
                                  )}
                                </div>
                                {report.evidence.distance_from_report_meters !== undefined && report.evidence.distance_from_report_meters !== null && (
                                  <div className="text-[10px] text-slate-600 font-semibold pt-0.5">
                                    Distance from Report Location: <strong className={report.evidence.distance_from_report_meters <= 1000 ? 'text-emerald-700' : 'text-red-700'}>{report.evidence.distance_from_report_meters} meters</strong>
                                  </div>
                                )}
                              </div>
                            )}

                            {report.evidence.content_hash && (
                              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100 text-[10px] font-mono truncate">
                                <span className="text-slate-400 font-bold uppercase block">SHA-256 CONTENT HASH</span>
                                <span className="text-slate-600 select-all">{report.evidence.content_hash}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ) : report.evidence && report.evidence.validation_status === 'UNAVAILABLE' ? (
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs font-mono text-slate-600 space-y-1">
                        <div className="font-bold text-slate-800 flex items-center gap-1.5">
                          <AlertTriangle className="w-3.5 h-3.5 text-slate-500" />
                          <span>Camera Evidence Status: UNAVAILABLE</span>
                        </div>
                        <p className="text-[11px] text-slate-500">
                          {report.evidence.error_reason || 'Citizen device camera was unavailable or permission was not granted at report time.'}
                        </p>
                      </div>
                    ) : (
                      <div className="p-4 text-center rounded-xl bg-slate-50 border border-dashed border-slate-200 text-slate-400 text-xs font-semibold font-mono">
                        NO LIVE CAMERA EVIDENCE ATTACHED (Standard Citizen Intake)
                      </div>
                    )}

                    {/* Attached Media Photos (if any) */}
                    {report.media && report.media.length > 0 && (
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-2.5">
                        <div className="text-[11px] font-bold font-mono text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                          <Camera className="w-3.5 h-3.5 text-blue-600" />
                          <span>ATTACHED CITIZEN MEDIA ({report.media.length})</span>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                          {report.media.map((m, idx) => {
                            const isImg = m.media_type?.startsWith('image/') || m.filename?.match(/\.(jpg|jpeg|png|webp)$/i);
                            return (
                              <div
                                key={idx}
                                onClick={() => m.file_url && setActiveMediaUrl(m.file_url)}
                                className="relative group rounded-xl overflow-hidden border border-slate-200 h-28 bg-black cursor-pointer"
                              >
                                {isImg ? (
                                  <img
                                    src={m.file_url}
                                    alt={m.filename || 'Attached Media'}
                                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                                  />
                                ) : (
                                  <div className="w-full h-full flex flex-col items-center justify-center text-slate-400 text-[10px] p-2 text-center">
                                    <span className="font-mono font-bold text-slate-200">{m.filename}</span>
                                    <span className="text-slate-500 mt-1">{m.media_type}</span>
                                  </div>
                                )}
                                <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white text-[11px] font-semibold transition-opacity">
                                  Click to Enlarge
                                </div>
                                <span className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded bg-black/75 text-blue-300 text-[9px] font-mono font-bold">
                                  ATTACHMENT
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Warnings Section (if any exist) */}
                    {report.evidence_verification?.warnings && report.evidence_verification.warnings.length > 0 && (
                      <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs space-y-1">
                        <div className="font-bold flex items-center gap-1.5 text-amber-800">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                          <span>Verification Warnings</span>
                        </div>
                        <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                          {report.evidence_verification.warnings.map((w, idx) => (
                            <li key={idx}>{w}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Explainability Accordion: "Why this verification status?" */}
                    <div className="pt-2 border-t border-slate-100">
                      <button
                        type="button"
                        onClick={() => setShowWhyVerification(!showWhyVerification)}
                        className="w-full flex items-center justify-between p-2 rounded-xl bg-slate-50 hover:bg-slate-100 text-xs font-bold text-slate-700 transition-colors"
                      >
                        <span className="flex items-center gap-1.5">
                          <Info className="w-4 h-4 text-slate-500" />
                          <span>Why this verification status?</span>
                        </span>
                        {showWhyVerification ? (
                          <ChevronUp className="w-4 h-4 text-slate-500" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-slate-500" />
                        )}
                      </button>

                      {showWhyVerification && (
                        <div className="mt-2.5 p-3.5 rounded-xl bg-slate-50/90 border border-slate-200 space-y-3 text-xs animate-in fade-in duration-150">
                          {/* Verified Factors */}
                          <div>
                            <span className="text-[10px] font-bold font-mono text-emerald-800 uppercase tracking-wider block mb-1">
                              VERIFIED FACTORS
                            </span>
                            {report.evidence_verification?.verified_factors && report.evidence_verification.verified_factors.length > 0 ? (
                              <ul className="space-y-1">
                                {report.evidence_verification.verified_factors.map((f, idx) => (
                                  <li key={idx} className="flex items-start gap-1.5 text-slate-700">
                                    <CheckCircle className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0 mt-0.5" />
                                    <span>{f}</span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="text-slate-400 italic text-[11px]">No verified evidence factors detected.</p>
                            )}
                          </div>

                          {/* Missing Factors */}
                          {report.evidence_verification?.missing_factors && report.evidence_verification.missing_factors.length > 0 && (
                            <div className="pt-2 border-t border-slate-200/60">
                              <span className="text-[10px] font-bold font-mono text-slate-500 uppercase tracking-wider block mb-1">
                                MISSING FACTORS / UNVERIFIED ATTRIBUTES
                              </span>
                              <ul className="space-y-1">
                                {report.evidence_verification.missing_factors.map((m, idx) => (
                                  <li key={idx} className="flex items-start gap-1.5 text-slate-600 text-[11px]">
                                    <span className="text-amber-500 font-bold">⚠</span>
                                    <span>{m}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Advisory Recommendation */}
                          <div className="pt-2 border-t border-slate-200/60">
                            <div className="flex items-start gap-1.5 text-slate-600 text-[11px]">
                              <ShieldAlert className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 mt-0.5" />
                              <span className="italic">
                                Human Officer Authority: Verification engine outputs are advisory. Watch Officers remain the sole authority for operational priority and resource dispatch.
                              </span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Hybrid AI Extracted Evidence Section (Google Gemini Advisory Layer) */}
                  {/* Hybrid AI Extracted Evidence Section (Multi-Provider: Gemini Primary + OpenAI Fallback) */}
                  {report.llm_extraction && (
                    <div className="p-5 rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/40 via-white to-purple-50/30 shadow-xs space-y-4">
                      <div className="flex flex-wrap items-center justify-between pb-2.5 border-b border-indigo-100/70 gap-2">
                        <div className="flex items-center gap-2">
                          <Sparkles className="w-4 h-4 text-indigo-600" />
                          <span className="text-xs font-bold text-slate-900 uppercase tracking-wider font-mono">
                            AI EXTRACTED EVIDENCE ({report.llm_extraction.provider || 'GEMINI'})
                          </span>
                          {report.llm_extraction.fallback_used && (
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-amber-100 text-amber-900 font-bold border border-amber-300">
                              FALLBACK ACTIVE (Gemini unavailable)
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-indigo-100 text-indigo-800 font-bold border border-indigo-200">
                            STATUS: {report.llm_extraction.status}
                          </span>
                          {report.llm_extraction.status === 'SUCCESS' && (
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 font-bold border border-emerald-200">
                              CONFIDENCE: {Math.round((report.llm_extraction.overall_confidence || 0.85) * 100)}%
                            </span>
                          )}
                        </div>
                      </div>

                      {report.llm_extraction.status === 'SUCCESS' ? (
                        <div className="space-y-3">
                          {/* Top Highlights Grid */}
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs font-mono">
                            {/* Hazard */}
                            <div className="p-2.5 rounded-xl bg-white border border-indigo-100 shadow-2xs">
                              <span className="text-[10px] text-indigo-500 uppercase font-bold block">INFERRED HAZARD</span>
                              <span className="font-bold text-slate-900 text-xs">
                                {report.llm_extraction.hazard?.value || 'UNSPECIFIED'}
                              </span>
                              {report.llm_extraction.hazard?.confidence !== undefined && (
                                <span className="text-[10px] text-slate-400 block">
                                  ({Math.round(report.llm_extraction.hazard.confidence * 100)}% match)
                                </span>
                              )}
                            </div>

                            {/* Estimated People */}
                            <div className="p-2.5 rounded-xl bg-white border border-indigo-100 shadow-2xs">
                              <span className="text-[10px] text-indigo-500 uppercase font-bold block">REPORTED AFFECTED</span>
                              <span className="font-bold text-slate-900 text-xs">
                                {report.llm_extraction.affected_population?.estimated_count !== null && report.llm_extraction.affected_population?.estimated_count !== undefined
                                  ? `${report.llm_extraction.affected_population.is_uncertain ? '~' : ''}${report.llm_extraction.affected_population.estimated_count} persons`
                                  : 'Not stated in text'}
                              </span>
                              {report.llm_extraction.affected_population?.uncertainty_phrase && (
                                <span className="text-[10px] text-amber-600 block">
                                  [{report.llm_extraction.affected_population.uncertainty_phrase}]
                                </span>
                              )}
                            </div>

                            {/* Vulnerable Groups */}
                            <div className="p-2.5 rounded-xl bg-white border border-indigo-100 shadow-2xs">
                              <span className="text-[10px] text-indigo-500 uppercase font-bold block">VULNERABLE GROUPS</span>
                              <span className="font-bold text-slate-900 text-xs">
                                {report.llm_extraction.vulnerable_groups && report.llm_extraction.vulnerable_groups.length > 0
                                  ? report.llm_extraction.vulnerable_groups.map(g => `${g.estimated_count ? g.estimated_count + ' ' : ''}${g.group_type}`).join(', ')
                                  : 'None explicitly stated'}
                              </span>
                            </div>
                          </div>

                          {/* Extracted Observations & Needs */}
                          {(report.llm_extraction.observations?.length > 0 || report.llm_extraction.reported_needs?.length > 0) && (
                            <div className="p-3 rounded-xl bg-white border border-indigo-100/80 space-y-2 text-xs">
                              {report.llm_extraction.observations?.length > 0 && (
                                <div>
                                  <span className="text-[10px] font-bold font-mono text-indigo-700 uppercase tracking-wider block mb-1">
                                    EXTRACTED OBSERVATIONS
                                  </span>
                                  <div className="flex flex-wrap gap-1.5">
                                    {report.llm_extraction.observations.map((obs, idx) => (
                                      <span key={idx} className="px-2 py-0.5 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-900 font-mono text-[11px]">
                                        {obs.type}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {report.llm_extraction.reported_needs?.length > 0 && (
                                <div className="pt-2 border-t border-slate-100">
                                  <span className="text-[10px] font-bold font-mono text-purple-700 uppercase tracking-wider block mb-1">
                                    CITIZEN REPORTED NEEDS (ADVISORY)
                                  </span>
                                  <div className="flex flex-wrap gap-1.5">
                                    {report.llm_extraction.reported_needs.map((nd, idx) => (
                                      <span key={idx} className="px-2 py-0.5 rounded-lg bg-purple-50 border border-purple-100 text-purple-900 font-mono text-[11px]">
                                        {nd.need_type} {nd.suggested_quantity ? `(${nd.suggested_quantity} ${nd.unit || ''})` : ''} [{nd.urgency}]
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {report.llm_extraction.mentioned_landmarks?.length > 0 && (
                                <div className="pt-1.5 text-[11px] text-slate-600">
                                  <span className="font-semibold text-slate-700">Mentioned Landmarks: </span>
                                  {report.llm_extraction.mentioned_landmarks.join(', ')}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Advisory Provenance & Disclaimer */}
                          <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200/70 text-[11px] text-slate-500 flex items-start gap-2">
                            <Info className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0 mt-0.5" />
                            <span>
                              <strong>Advisory Provenance:</strong> Provider: {report.llm_extraction.provider || 'GEMINI'}{report.llm_extraction.fallback_used ? ` (Fallback from ${report.llm_extraction.primary_provider || 'GEMINI'})` : ''} | Model: {report.llm_extraction.model} (Prompt v{report.llm_extraction.prompt_version}). AI extraction is advisory natural language interpretation. Operational priority, resource allocation, and dispatches remain governed by deterministic rules and Officer approval.
                            </span>
                          </div>
                        </div>
                      ) : (
                        <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-3">
                          <div className="flex items-start gap-2">
                            <Info className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
                            <div>
                              <span className="font-semibold text-slate-800">AI text extraction state: {report.llm_extraction.status}</span>
                              <p className="text-[11px] text-slate-500 mt-0.5">{report.llm_extraction.error_message || 'AI extraction is currently unavailable. Standard deterministic processing continues.'}</p>
                            </div>
                          </div>
                          <button
                            onClick={handleRunTextExtraction}
                            disabled={analyzingText}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors shadow-2xs cursor-pointer"
                          >
                            <Sparkles className="w-3.5 h-3.5" />
                            {analyzingText ? 'Analyzing via OpenAI Fallback...' : 'Re-extract Text Evidence (Failover Enabled)'}
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* AI Multimodal Visual Evidence Section (Multi-Provider: Gemini Primary + OpenAI Fallback) */}
                  <div className="p-5 rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50/40 via-white to-cyan-50/30 shadow-xs space-y-4 font-sans">
                    <div className="flex flex-wrap items-center justify-between pb-2.5 border-b border-blue-100 gap-2">
                      <div className="flex items-center gap-2">
                        <Camera className="w-4 h-4 text-blue-600" />
                        <span className="text-xs font-bold text-slate-900 uppercase tracking-wider font-mono">
                          AI VISUAL EVIDENCE {report.visual_evidence?.provider ? `(${report.visual_evidence.provider})` : '(GEMINI PRIMARY)'}
                        </span>
                        {report.visual_evidence?.fallback_triggered && (
                          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-bold border border-amber-300">
                            FAILOVER ACTIVE
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-bold border border-slate-200">
                          ADVISORY ONLY
                        </span>
                        {report.visual_evidence?.status === 'SUCCESS' && (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 font-bold border border-emerald-200">
                            AI CONFIDENCE: {Math.round((report.visual_evidence.overall_confidence || 0.85) * 100)}%
                          </span>
                        )}
                      </div>
                    </div>

                    {report.visual_evidence && report.visual_evidence.status === 'SUCCESS' ? (
                      <div className="space-y-3">
                        {/* Highlights Grid */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                          <div className="p-2.5 rounded-xl bg-white border border-blue-100 shadow-2xs">
                            <span className="text-[10px] text-blue-500 uppercase font-bold block">SOURCE / PROVIDER</span>
                            <span className="font-bold text-slate-900 text-xs">
                              {report.visual_evidence.source_type === 'PHOTO_ATTACHMENT' ? 'Photo Attachment' : 'Live Camera'} • {report.visual_evidence.provider || 'GEMINI'}
                            </span>
                          </div>
                          <div className="p-2.5 rounded-xl bg-white border border-blue-100 shadow-2xs">
                            <span className="text-[10px] text-blue-500 uppercase font-bold block">VISUAL ASSESSMENT</span>
                            <span className="font-bold text-slate-900 text-xs">{report.visual_evidence.hazard_type}</span>
                          </div>
                          <div className="p-2.5 rounded-xl bg-white border border-blue-100 shadow-2xs">
                            <span className="text-[10px] text-blue-500 uppercase font-bold block">TEXT ↔ IMAGE</span>
                            <span className={`inline-block mt-0.5 px-2 py-0.5 rounded text-[11px] border ${getConsistencyBadgeClass(report.visual_evidence.text_image_consistency)}`}>
                              {report.visual_evidence.text_image_consistency}
                            </span>
                          </div>
                          <div className="p-2.5 rounded-xl bg-white border border-blue-100 shadow-2xs">
                            <span className="text-[10px] text-blue-500 uppercase font-bold block">AI CONFIDENCE</span>
                            <span className="font-bold text-slate-900 text-xs">{Math.round(report.visual_evidence.overall_confidence * 100)}%</span>
                          </div>
                        </div>

                        {report.visual_evidence.hazard_description && (
                          <p className="text-xs text-slate-700 bg-white/90 p-3 rounded-xl border border-blue-100 leading-relaxed">
                            {report.visual_evidence.hazard_description}
                          </p>
                        )}

                        {/* Visible Impacts Preview */}
                        {report.visual_evidence.visible_impacts && report.visual_evidence.visible_impacts.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 items-center">
                            <span className="text-[10px] font-bold font-mono text-blue-800 uppercase mr-1">Visible Impacts:</span>
                            {report.visual_evidence.visible_impacts.map((imp, idx) => (
                              <span key={idx} className="px-2 py-0.5 rounded-lg bg-blue-50 border border-blue-200 text-blue-900 font-mono text-[11px]">
                                {imp}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Action Buttons */}
                        <div className="flex items-center justify-between pt-1">
                          <button
                            type="button"
                            onClick={() => setShowVisualModal(true)}
                            className="px-3.5 py-1.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold shadow-xs transition-all flex items-center gap-1.5"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            <span>View Analysis</span>
                          </button>

                          <button
                            type="button"
                            onClick={handleRunVisualAnalysis}
                            disabled={analyzingVisual}
                            className="px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold border border-slate-200 transition-all flex items-center gap-1.5"
                          >
                            <RefreshCw className={`w-3.5 h-3.5 ${analyzingVisual ? 'animate-spin text-blue-600' : ''}`} />
                            <span>{analyzingVisual ? 'Analyzing...' : 'Re-run Vision Analysis'}</span>
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div className="space-y-1">
                          <p className="font-medium text-slate-700">
                            {report.visual_evidence?.status === 'TEMPORARILY_UNAVAILABLE'
                              ? 'Visual analysis service is temporarily unavailable. Your camera evidence has been safely preserved. Please try again shortly.'
                              : report.visual_evidence?.status === 'UNAVAILABLE'
                              ? (report.visual_evidence.error_message || report.visual_evidence.error_reason || 'AI visual analysis temporarily unavailable.')
                              : (report.evidence?.file_url || (report.media && report.media.some((m: any) => m.file_url || m.url)))
                              ? (report.evidence?.file_url
                                  ? 'Live camera photo attached. Multimodal visual analysis ready.'
                                  : 'Photo attachment uploaded. Multimodal visual analysis ready.')
                              : 'No live camera evidence or photo attachment found on this report.'}
                          </p>
                          {report.visual_evidence?.status === 'TEMPORARILY_UNAVAILABLE' && (
                            <p className="text-[11px] text-amber-700 font-mono">
                              Status: TEMPORARILY_UNAVAILABLE (High demand / temporary provider spike). Camera evidence preserved.
                            </p>
                          )}
                        </div>
                        {(report.evidence?.file_url || (report.media && report.media.some((m: any) => m.file_url || m.url))) && (
                          <button
                            type="button"
                            onClick={handleRunVisualAnalysis}
                            disabled={analyzingVisual}
                            className="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold shadow-xs transition-all flex items-center justify-center gap-1.5 shrink-0"
                          >
                            <Sparkles className={`w-3.5 h-3.5 ${analyzingVisual ? 'animate-spin' : ''}`} />
                            <span>
                              {analyzingVisual
                                ? 'Analyzing visual evidence...'
                                : report.visual_evidence?.status === 'TEMPORARILY_UNAVAILABLE' || report.visual_evidence?.status === 'UNAVAILABLE'
                                ? 'Retry Visual Analysis'
                                : 'Analyze Visual Evidence'}
                            </span>
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Multi-Source Corroboration & Conflict Detection Section */}
                  <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs space-y-4">
                    <div className="flex flex-wrap items-center justify-between pb-2.5 border-b border-slate-100 gap-2">
                      <div className="flex items-center gap-2">
                        <Boxes className="w-4 h-4 text-red-600" />
                        <span className="text-xs font-bold text-slate-900 uppercase tracking-wider font-mono">
                          MULTI-SOURCE CORROBORATION
                        </span>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <span className={`text-[10px] px-2 py-0.5 rounded-md font-mono font-bold border ${getCorroborationBadgeClass(report.corroboration?.corroboration_status || 'NO_CORROBORATION')}`}>
                          STATUS: {report.corroboration?.corroboration_status || 'NO_CORROBORATION'}
                        </span>
                      </div>
                    </div>

                    {/* Conflict Banner if Conflicted */}
                    {report.corroboration?.corroboration_status === 'CONFLICTED' && (
                      <div className="p-4 rounded-xl bg-red-50/90 border border-red-200 text-red-900 text-xs space-y-2.5 animate-in fade-in">
                        <div className="flex items-center gap-2 font-bold text-red-800 text-xs tracking-wide">
                          <AlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0" />
                          <span>CONFLICT DETECTED — HUMAN REVIEW REQUIRED</span>
                        </div>
                        
                        {report.corroboration.conflict_details?.map((c, idx) => (
                          <div key={idx} className="p-2.5 rounded-lg bg-white/80 border border-red-200 space-y-1">
                            <div className="flex items-center justify-between text-[11px] font-bold text-red-900">
                              <span>{c.summary}</span>
                              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-red-100 text-red-800">
                                {c.category}
                              </span>
                            </div>
                            <p className="text-[11px] text-red-800">{c.reason}</p>
                            <div className="text-[10px] font-semibold text-slate-700 pt-1 border-t border-red-100">
                              <strong>Recommended Action:</strong> {c.recommended_action}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Source Summary Stats */}
                    <div className="grid grid-cols-3 gap-2 text-xs font-mono">
                      <div className="p-2 rounded-xl bg-emerald-50 border border-emerald-100 text-center">
                        <span className="text-[10px] text-emerald-600 uppercase font-bold block">SUPPORTING</span>
                        <span className="font-bold text-sm text-emerald-800">
                          {report.corroboration?.supporting_source_count ?? 0}
                        </span>
                      </div>

                      <div className="p-2 rounded-xl bg-red-50 border border-red-100 text-center">
                        <span className="text-[10px] text-red-600 uppercase font-bold block">CONFLICTING</span>
                        <span className="font-bold text-sm text-red-800">
                          {report.corroboration?.conflicting_source_count ?? 0}
                        </span>
                      </div>

                      <div className="p-2 rounded-xl bg-slate-50 border border-slate-100 text-center">
                        <span className="text-[10px] text-slate-400 uppercase font-bold block">NEUTRAL</span>
                        <span className="font-bold text-sm text-slate-700">
                          {report.corroboration?.neutral_source_count ?? 0}
                        </span>
                      </div>
                    </div>

                    {/* Detailed Sources List */}
                    <div className="space-y-2">
                      {/* Supporting Sources */}
                      {report.corroboration?.supporting_sources && report.corroboration.supporting_sources.length > 0 && (
                        <div className="space-y-1.5">
                          <span className="text-[10px] font-bold font-mono text-emerald-800 uppercase tracking-wider block">
                            ✓ SUPPORTING SOURCES
                          </span>
                          {report.corroboration.supporting_sources.map((s, idx) => (
                            <div key={idx} className="p-2.5 rounded-xl bg-emerald-50/50 border border-emerald-100 text-xs flex items-start justify-between gap-2">
                              <div className="space-y-0.5">
                                <div className="font-bold text-emerald-950 flex items-center gap-1.5">
                                  <CheckCircle className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                                  <span>{s.source_name || s.source_id}</span>
                                  <span className="text-[10px] font-mono font-normal text-emerald-700 px-1.5 py-0.5 rounded bg-emerald-100">
                                    {s.source_type}
                                  </span>
                                </div>
                                <p className="text-[11px] text-slate-700">{s.summary}</p>
                              </div>
                              {s.distance_meters !== undefined && s.distance_meters !== null && (
                                <span className="text-[10px] font-mono text-slate-500 flex-shrink-0">
                                  {s.distance_meters}m
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Conflicting Sources */}
                      {report.corroboration?.conflicting_sources && report.corroboration.conflicting_sources.length > 0 && (
                        <div className="space-y-1.5">
                          <span className="text-[10px] font-bold font-mono text-red-800 uppercase tracking-wider block">
                            ⚠ CONFLICTING SOURCES
                          </span>
                          {report.corroboration.conflicting_sources.map((s, idx) => (
                            <div key={idx} className="p-2.5 rounded-xl bg-red-50/50 border border-red-100 text-xs flex items-start justify-between gap-2">
                              <div className="space-y-0.5">
                                <div className="font-bold text-red-950 flex items-center gap-1.5">
                                  <AlertTriangle className="w-3.5 h-3.5 text-red-600 flex-shrink-0" />
                                  <span>{s.source_name || s.source_id}</span>
                                  <span className="text-[10px] font-mono font-normal text-red-700 px-1.5 py-0.5 rounded bg-red-100">
                                    {s.source_type}
                                  </span>
                                </div>
                                <p className="text-[11px] text-slate-700">{s.summary}</p>
                              </div>
                              {s.distance_meters !== undefined && s.distance_meters !== null && (
                                <span className="text-[10px] font-mono text-slate-500 flex-shrink-0">
                                  {s.distance_meters}m
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Neutral Sources */}
                      {report.corroboration?.neutral_sources && report.corroboration.neutral_sources.length > 0 && (
                        <div className="space-y-1.5">
                          <span className="text-[10px] font-bold font-mono text-slate-500 uppercase tracking-wider block">
                            • NEUTRAL / NON-CORROBORATING SOURCES
                          </span>
                          {report.corroboration.neutral_sources.map((s, idx) => (
                            <div key={idx} className="p-2 rounded-xl bg-slate-50 border border-slate-100 text-xs flex items-start justify-between gap-2">
                              <div className="space-y-0.5">
                                <div className="font-semibold text-slate-700 flex items-center gap-1.5">
                                  <span className="text-slate-400">•</span>
                                  <span>{s.source_name || s.source_id}</span>
                                  <span className="text-[10px] font-mono font-normal text-slate-500 px-1.5 py-0.5 rounded bg-slate-200">
                                    {s.source_type}
                                  </span>
                                </div>
                                <p className="text-[10px] text-slate-500">{s.summary}</p>
                              </div>
                              {s.distance_meters !== undefined && s.distance_meters !== null && (
                                <span className="text-[10px] font-mono text-slate-400 flex-shrink-0">
                                  {s.distance_meters}m
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* "Why this result?" Explainability Accordion */}
                    <div className="pt-2 border-t border-slate-100">
                      <button
                        type="button"
                        onClick={() => setShowWhyCorroboration(!showWhyCorroboration)}
                        className="w-full flex items-center justify-between p-2 rounded-xl bg-slate-50 hover:bg-slate-100 text-xs font-bold text-slate-700 transition-colors"
                      >
                        <span className="flex items-center gap-1.5">
                          <Info className="w-4 h-4 text-slate-500" />
                          <span>Why this result? (Corroboration Analysis)</span>
                        </span>
                        {showWhyCorroboration ? (
                          <ChevronUp className="w-4 h-4 text-slate-500" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-slate-500" />
                        )}
                      </button>

                      {showWhyCorroboration && (
                        <div className="mt-2.5 p-3.5 rounded-xl bg-slate-50/90 border border-slate-200 space-y-3 text-xs animate-in fade-in duration-150">
                          <div>
                            <span className="text-[10px] font-bold font-mono text-slate-500 uppercase tracking-wider block mb-1">
                              EXPLANATION
                            </span>
                            <p className="text-slate-800 leading-relaxed font-sans">
                              {report.corroboration?.explanation || 'Single-source report: No independent corroborating sources detected within operational thresholds.'}
                            </p>
                          </div>

                          {report.corroboration?.corroboration_factors && report.corroboration.corroboration_factors.length > 0 && (
                            <div>
                              <span className="text-[10px] font-bold font-mono text-emerald-800 uppercase tracking-wider block mb-1">
                                CORROBORATING FACTORS
                              </span>
                              <ul className="space-y-1">
                                {report.corroboration.corroboration_factors.map((f, idx) => (
                                  <li key={idx} className="flex items-start gap-1.5 text-emerald-900 text-[11px]">
                                    <span className="text-emerald-600 font-bold">✓</span>
                                    <span>{f}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {report.corroboration?.conflict_factors && report.corroboration.conflict_factors.length > 0 && (
                            <div>
                              <span className="text-[10px] font-bold font-mono text-red-800 uppercase tracking-wider block mb-1">
                                CONFLICT FACTORS
                              </span>
                              <ul className="space-y-1">
                                {report.corroboration.conflict_factors.map((f, idx) => (
                                  <li key={idx} className="flex items-start gap-1.5 text-red-900 text-[11px]">
                                    <span className="text-red-600 font-bold">⚠</span>
                                    <span>{f}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Advisory HITL Boundary Notice */}
                          <div className="pt-2 border-t border-slate-200/60">
                            <div className="flex items-start gap-1.5 text-slate-600 text-[11px]">
                              <ShieldAlert className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 mt-0.5" />
                              <span className="italic">
                                Human-in-the-Loop Advisory: Corroboration and conflict engines never autonomously reject reports, mutate officer priority, or dispatch response plans.
                              </span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Right Column: Officer Notes & Operational Timeline (5 cols) */}
                <div className="lg:col-span-5 space-y-6">
                  {/* Evidence-Aware Priority Recommendation Card */}
                  <div className="p-5 rounded-2xl border border-red-200 bg-gradient-to-br from-red-50/40 via-white to-amber-50/30 shadow-xs space-y-3 font-sans">
                    <div className="flex items-center justify-between pb-2 border-b border-red-100">
                      <div className="flex items-center gap-2">
                        <ShieldAlert className="w-4 h-4 text-red-600" />
                        <span className="text-xs font-bold text-slate-900 uppercase tracking-wider font-mono">
                          PRIORITY RECOMMENDATION
                        </span>
                      </div>
                      {report.priority_recommendation && (
                        <span className={`text-xs px-2.5 py-0.5 rounded-lg border font-bold ${getPriorityBadgeClass(report.priority_recommendation.recommended_priority)}`}>
                          {report.priority_recommendation.recommended_priority} ({report.priority_recommendation.score}/10)
                        </span>
                      )}
                    </div>

                    {report.priority_recommendation ? (
                      <div className="space-y-2.5 text-xs">
                        {/* Evidence Factors Checklist */}
                        <div className="space-y-1">
                          <span className="text-[10px] font-bold font-mono text-slate-400 uppercase tracking-wider block">
                            EVIDENCE FACTORS
                          </span>
                          <ul className="space-y-1">
                            {report.priority_recommendation.evidence_factors.map((f, idx) => (
                              <li key={idx} className="flex items-start gap-1.5 text-slate-700 text-[11px]">
                                <Check className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0 mt-0.5" />
                                <span>{f}</span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        {/* Preserved Unverified Claims (Highest-Impact Safety Rule) */}
                        {report.priority_recommendation.unverified_claims && report.priority_recommendation.unverified_claims.length > 0 && (
                          <div className="pt-2 border-t border-slate-100 space-y-1">
                            <span className="text-[10px] font-bold font-mono text-amber-700 uppercase tracking-wider block">
                              PRESERVED UNVERIFIED CLAIMS (SAFETY RULE)
                            </span>
                            <ul className="space-y-1">
                              {report.priority_recommendation.unverified_claims.map((u, idx) => (
                                <li key={idx} className="flex items-start gap-1.5 text-amber-900 text-[11px]">
                                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600 flex-shrink-0 mt-0.5" />
                                  <span>{u}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Uncertainties */}
                        {report.priority_recommendation.uncertainties && report.priority_recommendation.uncertainties.length > 0 && (
                          <div className="pt-2 border-t border-slate-100 space-y-1">
                            <span className="text-[10px] font-bold font-mono text-purple-700 uppercase tracking-wider block">
                              UNCERTAINTIES
                            </span>
                            <ul className="space-y-1">
                              {report.priority_recommendation.uncertainties.map((unc, idx) => (
                                <li key={idx} className="flex items-start gap-1.5 text-purple-900 text-[11px]">
                                  <HelpCircle className="w-3.5 h-3.5 text-purple-600 flex-shrink-0 mt-0.5" />
                                  <span>{unc}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Quick-Apply Recommendation Button */}
                        {report.priority !== report.priority_recommendation.recommended_priority && report.priority_recommendation.recommended_priority !== 'UNASSESSED' && (
                          <div className="pt-2">
                            <button
                              type="button"
                              onClick={() => handlePriorityChange(report.priority_recommendation?.recommended_priority as ReportPriority)}
                              disabled={actionLoading}
                              className="w-full py-1.5 px-3 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-bold shadow-xs transition-all flex items-center justify-center gap-1.5 cursor-pointer"
                            >
                              <span>Accept Recommendation ({report.priority_recommendation.recommended_priority})</span>
                            </button>
                          </div>
                        )}

                        <p className="text-[10px] text-slate-500 italic pt-1 border-t border-slate-100">
                          Officer Authority: Priority recommendations are advisory. Watch Officers retain full operational authority to override or set priority levels.
                        </p>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 italic">No priority recommendation computed.</p>
                    )}
                  </div>

                  {/* Officer Operational Notes */}
                  <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs space-y-4">
                    <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-red-600" />
                        <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                          OFFICER NOTES
                        </span>
                      </div>
                      <span className="text-[11px] font-semibold text-slate-400">
                        {report.notes?.length || 0} Note(s)
                      </span>
                    </div>

                    {/* Add Note Form */}
                    <form onSubmit={handleAddNote} className="space-y-2.5">
                      <textarea
                        rows={3}
                        value={newNote}
                        onChange={(e) => setNewNote(e.target.value)}
                        placeholder="Add operational notes, dispatch instructions, or field verification status..."
                        className="w-full p-3 rounded-xl border border-slate-200 text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500"
                      />
                      <div className="flex justify-end">
                        <button
                          type="submit"
                          disabled={submittingNote || !newNote.trim()}
                          className="px-3.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 transition-all"
                        >
                          <Send className="w-3.5 h-3.5" />
                          <span>{submittingNote ? 'Saving...' : 'Add Note'}</span>
                        </button>
                      </div>
                    </form>

                    {/* Existing Notes Feed */}
                    <div className="space-y-2.5 max-h-56 overflow-y-auto pr-1">
                      {report.notes && report.notes.length > 0 ? (
                        report.notes.map((n) => (
                          <div
                            key={n.note_id}
                            className="p-3 rounded-xl bg-slate-50 border border-slate-100 text-xs space-y-1"
                          >
                            <div className="flex items-center justify-between text-[10px] text-slate-400">
                              <span className="font-bold text-slate-700">
                                {n.author_name} ({n.author_role})
                              </span>
                              <span className="font-mono">
                                {new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                            <p className="text-slate-800">{n.note}</p>
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-slate-400 text-center py-3 italic">
                          No officer notes recorded yet.
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Operational Timeline & Audit Trail */}
                  <div className="p-5 rounded-2xl border border-slate-200 bg-white shadow-xs space-y-4">
                    <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
                      <div className="flex items-center gap-2">
                        <Activity className="w-4 h-4 text-red-600" />
                        <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                          OPERATIONAL AUDIT TIMELINE
                        </span>
                      </div>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-bold">
                        IMMUTABLE LOG
                      </span>
                    </div>

                    {/* Timeline Event Feed */}
                    <div className="space-y-3 max-h-72 overflow-y-auto pr-1">
                      {report.timeline && report.timeline.length > 0 ? (
                        [...report.timeline]
                          .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
                          .map((evt) => (
                          <div
                            key={evt.event_id}
                            className="flex items-start gap-2.5 text-xs pb-2 border-b border-slate-100 last:border-0"
                          >
                            <div className="w-2 h-2 rounded-full bg-red-600 mt-1.5 flex-shrink-0" />
                            <div className="flex-1">
                              <div className="flex items-center justify-between text-[10px] text-slate-400">
                                <span className="font-bold text-slate-700">
                                  {evt.event_type.replace('_', ' ')}
                                </span>
                                <span className="font-mono">
                                  {new Date(evt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                </span>
                              </div>
                              <p className="text-slate-700 mt-0.5 leading-relaxed">{evt.details}</p>
                              <div className="text-[10px] text-slate-500 mt-0.5">
                                <span>Actor: </span>
                                <span className="font-semibold text-slate-700">
                                  {evt.actor_name || 'Authenticated operator'}
                                </span>
                                {evt.actor_role && (
                                  <span className="text-slate-400"> ({evt.actor_role})</span>
                                )}
                              </div>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-slate-400 text-center py-4 italic">
                          No audit timeline events yet.
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : activeTab === 'resources' ? (
            <NeedsAndAllocationsPanel
              reportId={report.report_id}
              onRefreshReport={() => {
                fetchDetails();
                onReportUpdated?.();
              }}
            />
          ) : (
            <IncidentEvolutionTimeline
              targetId={report.report_id}
              targetType="CITIZEN_REPORT"
            />
          )}
        </>
      )}
        </div>
      </div>

      {/* Live Field Verification Modal */}
      {showVerificationModal && report && (
        <SubmitFieldVerificationModal
          isOpen={showVerificationModal}
          onClose={() => setShowVerificationModal(false)}
          targetId={report.report_id}
          targetType="CITIZEN_REPORT"
          targetTitle={`${report.emergency_type} Emergency`}
          targetCoords={report.location ? { latitude: report.location.latitude, longitude: report.location.longitude } : null}
          onSuccess={() => {
            fetchDetails();
            onReportUpdated?.();
          }}
        />
      )}

      {/* Expanded AI Visual Evidence Analysis Modal */}
      {showVisualModal && report?.visual_evidence && (
        <div className="fixed inset-0 z-60 flex items-center justify-center p-3 sm:p-4 md:p-6 bg-slate-900/70 backdrop-blur-xs overflow-y-auto">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Camera className="w-5 h-5 text-blue-600" />
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-slate-900 font-mono">
                      AI MULTIMODAL VISUAL EVIDENCE ANALYSIS
                    </h3>
                    {report.visual_evidence.fallback_triggered && (
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 font-bold border border-amber-300">
                        OPENAI FAILOVER
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 font-mono">
                    Provider: {report.visual_evidence.provider || 'GEMINI'} • Model: {report.visual_evidence.model} • Prompt v{report.visual_evidence.prompt_version} • {new Date(report.visual_evidence.analyzed_at).toLocaleString()}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowVisualModal(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-5 text-xs font-sans">
              {/* Summary Badges */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono">
                <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-[10px] text-slate-400 font-bold uppercase block">STATUS</span>
                  <span className="font-bold text-slate-900">{report.visual_evidence.status}</span>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-[10px] text-slate-400 font-bold uppercase block">HAZARD TYPE</span>
                  <span className="font-bold text-blue-700">{report.visual_evidence.hazard_type}</span>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-[10px] text-slate-400 font-bold uppercase block">CONSISTENCY</span>
                  <span className={`font-bold ${
                    report.visual_evidence.text_image_consistency === 'SUPPORTED' ? 'text-emerald-700' :
                    report.visual_evidence.text_image_consistency === 'PARTIALLY_SUPPORTED' ? 'text-blue-700' :
                    report.visual_evidence.text_image_consistency === 'NOT_SUPPORTED' ? 'text-amber-700' : 'text-purple-700'
                  }`}>
                    {report.visual_evidence.text_image_consistency}
                  </span>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200">
                  <span className="text-[10px] text-slate-400 font-bold uppercase block">CONFIDENCE</span>
                  <span className="font-bold text-slate-900">{Math.round(report.visual_evidence.overall_confidence * 100)}%</span>
                </div>
              </div>

              {/* Observed Visual Findings */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2.5">
                <h4 className="text-xs font-bold font-mono text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                  <Eye className="w-4 h-4 text-blue-600" />
                  <span>OBSERVED (VISUAL FINDINGS)</span>
                </h4>
                <p className="text-slate-700 leading-relaxed bg-white p-3 rounded-lg border border-slate-200">
                  {report.visual_evidence.hazard_description || 'Visual findings recorded.'}
                </p>

                {report.visual_evidence.visible_impacts && report.visual_evidence.visible_impacts.length > 0 && (
                  <div>
                    <span className="text-[10px] font-bold font-mono text-slate-400 uppercase block mb-1">Impacts Observed</span>
                    <div className="flex flex-wrap gap-1.5">
                      {report.visual_evidence.visible_impacts.map((imp, idx) => (
                        <span key={idx} className="px-2.5 py-1 rounded-lg bg-blue-50 border border-blue-200 text-blue-900 font-mono text-[11px]">
                          {imp}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Infrastructure Conditions */}
                {report.visual_evidence.infrastructure_conditions && report.visual_evidence.infrastructure_conditions.length > 0 && (
                  <div className="pt-2 border-t border-slate-200 space-y-1.5">
                    <span className="text-[10px] font-bold font-mono text-slate-400 uppercase block">Infrastructure & Access Conditions</span>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {report.visual_evidence.infrastructure_conditions.map((inf, idx) => (
                        <div key={idx} className="p-2.5 rounded-lg bg-white border border-slate-200 text-[11px] space-y-1">
                          <div className="flex items-center justify-between font-mono font-bold">
                            <span className="text-slate-900">{inf.infrastructure_type}</span>
                            <span className={inf.is_access_blocked ? 'text-red-600' : 'text-slate-600'}>
                              {inf.condition} {inf.is_access_blocked ? '(BLOCKED)' : ''}
                            </span>
                          </div>
                          <p className="text-slate-600">{inf.visual_description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Vulnerable Person Indicators */}
                {report.visual_evidence.vulnerable_person_indicators && report.visual_evidence.vulnerable_person_indicators.length > 0 && (
                  <div className="pt-2 border-t border-slate-200 space-y-1.5">
                    <span className="text-[10px] font-bold font-mono text-purple-700 uppercase block">Vulnerable Person Indicators</span>
                    <ul className="space-y-1">
                      {report.visual_evidence.vulnerable_person_indicators.map((v, idx) => (
                        <li key={idx} className="p-2 rounded-lg bg-purple-50 border border-purple-100 text-[11px] text-purple-950 font-mono">
                          <strong>{v.indicator_type}:</strong> {v.visual_description} {v.observable_count ? `(${v.observable_count} visible)` : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Supported Claims & Potential Inconsistencies */}
              {report.visual_evidence.claim_evaluations && report.visual_evidence.claim_evaluations.length > 0 && (
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2.5">
                  <h4 className="text-xs font-bold font-mono text-slate-900 uppercase tracking-wider">
                    CLAIM-BY-CLAIM EVALUATION
                  </h4>
                  <div className="space-y-2">
                    {report.visual_evidence.claim_evaluations.map((c, idx) => (
                      <div key={idx} className="p-3 rounded-lg bg-white border border-slate-200 space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-slate-800 text-xs">
                            "{c.claim_text}"
                          </span>
                          <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${getClaimStatusBadgeClass(c.status)}`}>
                            {c.status}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-600">
                          {c.visual_observation}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Uncertainty & Limitations */}
              {report.visual_evidence.uncertainties && report.visual_evidence.uncertainties.length > 0 && (
                <div className="p-4 rounded-xl bg-purple-50 border border-purple-200 space-y-2">
                  <h4 className="text-xs font-bold font-mono text-purple-900 uppercase tracking-wider flex items-center gap-1.5">
                    <HelpCircle className="w-4 h-4 text-purple-600" />
                    <span>UNCERTAINTIES & UNRESOLVED FACTORS</span>
                  </h4>
                  <ul className="space-y-1 text-[11px] text-purple-950">
                    {report.visual_evidence.uncertainties.map((unc, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-purple-600 font-bold">•</span>
                        <span>{unc}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Audit Provenance & Disclaimer */}
              <div className="p-3.5 rounded-xl bg-slate-100 border border-slate-200 font-mono text-[10px] text-slate-500 space-y-1">
                <div className="flex items-center justify-between text-slate-700">
                  <span>ANALYSIS ID: {report.visual_evidence.analysis_id}</span>
                  <span>EVIDENCE ID: {report.visual_evidence.evidence_id || report.evidence?.evidence_id || 'N/A'}</span>
                </div>
                {report.evidence?.content_hash && (
                  <div className="truncate">
                    <span>SHA-256: {report.evidence.content_hash}</span>
                  </div>
                )}
                <p className="text-[10px] text-slate-400 font-sans italic pt-1">
                  Safety Boundary: Multimodal vision is an advisory perception layer. Final priority recommendations are computed deterministically by the PriorityAgent and finalized by authorized officers.
                </p>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex justify-end">
              <button
                type="button"
                onClick={() => setShowVisualModal(false)}
                className="px-4 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-semibold cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Lightbox for Image Preview */}
      {activeMediaUrl && (
        <div
          onClick={() => setActiveMediaUrl(null)}
          className="fixed inset-0 z-60 bg-black/80 flex items-center justify-center p-4 cursor-pointer"
        >
          <div className="relative max-w-4xl max-h-[90vh]">
            <img src={activeMediaUrl} alt="Enlarged inspection" className="max-w-full max-h-[85vh] rounded-xl shadow-2xl" />
            <button
              onClick={() => setActiveMediaUrl(null)}
              className="absolute top-3 right-3 p-2 rounded-full bg-black/60 text-white hover:bg-black"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ReportDetailsModal;

