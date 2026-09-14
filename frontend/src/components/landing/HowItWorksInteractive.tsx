import React, { useState } from 'react';
import {
  Camera,
  MapPin,
  Clock,
  Sparkles,
  ShieldCheck,
  Radio,
  Cpu,
  UserCheck,
  Truck,
  Boxes,
  RefreshCw,
  FlaskConical,
  CheckCircle2,
  AlertTriangle,
  Send,
  MessageSquare,
  Navigation,
  ChevronRight,
  Shield,
  ArrowRight,
  Info,
  Sliders,
  FileCheck,
  Activity,
  HeartPulse,
  Home,
  Users,
  Building2,
  Lock,
  TrendingUp,
  CloudSun,
} from 'lucide-react';
import { useLanguage } from '../../context/LanguageContext';

interface Stage {
  id: string;
  stepNum: string;
  title: string;
  shortDesc: string;
  tag: string;
  tagColor: string;
  category: 'ingestion' | 'intelligence' | 'coordination' | 'execution' | 'governance';
  content: React.ReactNode;
}

export const HowItWorksInteractive: React.FC = () => {
  const { t } = useLanguage();
  const [activeStageId, setActiveStageId] = useState<string>('01');
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [replanningSimState, setReplanningSimState] = useState<'initial' | 'blocked' | 'revised'>('initial');

  const categories = [
    { id: 'all', label: t('how.journeyTitle', 'Complete 15-Stage Journey') },
    { id: 'ingestion', label: t('how.catIngestion', '1. Citizen Intake & Guidance') },
    { id: 'intelligence', label: t('how.catIntelligence', '2. AI & Officer Verification') },
    { id: 'coordination', label: t('how.catCoordination', '3. 9-Agent Coordination') },
    { id: 'execution', label: t('how.catExecution', '4. Human Approval & Field Action') },
    { id: 'governance', label: t('how.catGovernance', '5. Replanning, Simulation & Audit') },
  ];

  const agentNodes = [
    { num: '01', name: t('how.agent.a1Name', 'Priority Agent'), question: t('how.agent.a1Q', 'How serious is it?'), role: t('how.agent.a1Role', 'Deterministic Severity & Triage'), icon: AlertTriangle, color: 'text-red-600 bg-red-50 border-red-200', hoverClass: 'hover:border-red-400 hover:shadow-lg hover:shadow-red-500/10' },
    { num: '02', name: t('how.agent.a2Name', 'Needs Agent'), question: t('how.agent.a2Q', 'What is required?'), role: t('how.agent.a2Role', 'Demand & Supply Assessment'), icon: Boxes, color: 'text-amber-600 bg-amber-50 border-amber-200', hoverClass: 'hover:border-amber-400 hover:shadow-lg hover:shadow-amber-500/10' },
    { num: '03', name: t('how.agent.a3Name', 'Resource Coordination'), question: t('how.agent.a3Q', 'Where can it come from?'), role: t('how.agent.a3Role', 'Inventory & Depot Matching'), icon: Truck, color: 'text-emerald-600 bg-emerald-50 border-emerald-200', hoverClass: 'hover:border-emerald-400 hover:shadow-lg hover:shadow-emerald-500/10' },
    { num: '04', name: t('how.agent.a4Name', 'Conflict Resolution'), question: t('how.agent.a4Q', 'Is there a conflict?'), role: t('how.agent.a4Role', 'Constraint & Route Validation'), icon: Shield, color: 'text-indigo-600 bg-indigo-50 border-indigo-200', hoverClass: 'hover:border-indigo-400 hover:shadow-lg hover:shadow-indigo-500/10' },
    { num: '05', name: t('how.agent.a5Name', 'Shelter Agent'), question: t('how.agent.a5Q', 'Where can people evacuate?'), role: t('how.agent.a5Role', 'Capacity & Proximity Allocation'), icon: Home, color: 'text-teal-600 bg-teal-50 border-teal-200', hoverClass: 'hover:border-teal-400 hover:shadow-lg hover:shadow-teal-500/10' },
    { num: '06', name: t('how.agent.a6Name', 'Healthcare Agent'), question: t('how.agent.a6Q', 'Where can patients be treated?'), role: t('how.agent.a6Role', 'Hospital & Bed Routing'), icon: HeartPulse, color: 'text-rose-600 bg-rose-50 border-rose-200', hoverClass: 'hover:border-rose-400 hover:shadow-lg hover:shadow-rose-500/10' },
    { num: '07', name: t('how.agent.a7Name', 'Volunteer Agent'), question: t('how.agent.a7Q', 'Who is available?'), role: t('how.agent.a7Role', 'Skills & Proximity Assignment'), icon: Users, color: 'text-blue-600 bg-blue-50 border-blue-200', hoverClass: 'hover:border-blue-400 hover:shadow-lg hover:shadow-blue-500/10' },
    { num: '08', name: t('how.agent.a8Name', 'Routes & Transport'), question: t('how.agent.a8Q', 'How do we get there?'), role: t('how.agent.a8Role', 'Google Routes Road Geometry'), icon: Navigation, color: 'text-cyan-600 bg-cyan-50 border-cyan-200', hoverClass: 'hover:border-cyan-400 hover:shadow-lg hover:shadow-cyan-500/10' },
    { num: '09', name: t('how.agent.a9Name', 'Dynamic Replanning'), question: t('how.agent.a9Q', 'What changes when conditions change?'), role: t('how.agent.a9Role', 'Impact Analysis & Allocation Diff'), icon: RefreshCw, color: 'text-purple-600 bg-purple-50 border-purple-200', hoverClass: 'hover:border-purple-400 hover:shadow-lg hover:shadow-purple-500/10' },
  ];

  const stages: Stage[] = [
    // STAGE 01: CITIZEN REPORT
    {
      id: '01',
      stepNum: '01',
      title: t('how.s1.title', 'Report an Emergency'),
      shortDesc: t('how.s1.shortDesc', 'Instant, account-free citizen reporting with structured observation inputs.'),
      tag: t('how.s1.tag', 'CITIZEN INTAKE'),
      tagColor: 'bg-red-50 text-[#dc2626] border-red-200',
      category: 'ingestion',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s1.desc', 'Citizens can immediately report an emergency without creating an official account. The portal ingests structured observations to initiate first-responder triage.')}
          </p>

          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-xs">
            <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500 mb-2.5">
              {t('how.s1.inputsTitle', 'Structured Report Inputs')}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">🚨</span>
                <div>
                  <span className="font-bold text-slate-800">{t('how.s1.inputEmergencyType', 'Emergency Type')}</span>
                  <span className="block text-[11px] text-slate-500">{t('how.s1.inputEmergencyTypeDesc', 'Flood, Fire, Medical, Structural, Accident')}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-amber-400 hover:shadow-md hover:shadow-amber-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">⚠️</span>
                <div>
                  <span className="font-bold text-slate-800">{t('how.s1.inputIntensity', 'Problem Intensity')}</span>
                  <span className="block text-[11px] text-slate-500">{t('how.s1.inputIntensityDesc', 'Initial citizen signal (Advisory)')}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">📝</span>
                <div>
                  <span className="font-bold text-slate-800">{t('how.s1.inputDesc', 'Description')}</span>
                  <span className="block text-[11px] text-slate-500">{t('how.s1.inputDescDesc', 'Real-time observed situation details')}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-purple-400 hover:shadow-md hover:shadow-purple-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">📷</span>
                <div>
                  <span className="font-bold text-slate-800">{t('how.s1.inputCamera', 'Camera Evidence')}</span>
                  <span className="block text-[11px] text-slate-500">{t('how.s1.inputCameraDesc', 'Live capture / photo upload')}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">📍</span>
                <div>
                  <span className="font-bold text-slate-800">{t('how.s1.inputGps', 'Current GPS Location')}</span>
                  <span className="block text-[11px] text-slate-500">{t('how.s1.inputGpsDesc', 'Device coordinates with accuracy radius')}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">👤</span>
                <div>
                  <span className="font-bold text-slate-800">{t('how.s1.inputContact', 'Name + Mobile')}</span>
                  <span className="block text-[11px] text-slate-500">{t('how.s1.inputContactDesc', 'Contact details for field coordination')}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-start gap-2 p-3.5 rounded-xl bg-amber-50/80 border border-amber-200 text-amber-900 text-xs shadow-xs">
            <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <span>
              <strong>{t('how.s1.crucialPrinciple', 'Crucial Principle:')}</strong> {t('how.s1.crucialPrincipleText', 'Citizen-reported intensity provides an initial signal for assessment, not the final authoritative severity.')}
            </span>
          </div>
        </div>
      ),
    },

    // STAGE 02: GEOTAGGED CAMERA EVIDENCE
    {
      id: '02',
      stepNum: '02',
      title: t('how.s2.title', 'Capture Real-World Evidence'),
      shortDesc: t('how.s2.shortDesc', 'Geotagged visual evidence provides ground truth with timestamp and coordinates.'),
      tag: t('how.s2.tag', 'EVIDENCE CONTEXT'),
      tagColor: 'bg-blue-50 text-blue-700 border-blue-200',
      category: 'ingestion',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s2.desc', 'Visual evidence provides essential ground truth for emergency responders. Resilience securely binds every photo to physical device coordinates and verifiable timestamp metadata.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-center mb-3">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-slate-400 hover:shadow-md hover:shadow-slate-200/60 hover:-translate-y-0.5 transition-all duration-200">
                <Camera className="w-5 h-5 mx-auto mb-1 text-slate-700" />
                <div className="font-mono text-xs font-bold text-slate-800">{t('how.s2.cameraTitle', 'Camera Photo')}</div>
                <div className="text-[10px] text-slate-500">{t('how.s2.cameraDesc', 'Visual Evidence File')}</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <MapPin className="w-5 h-5 mx-auto mb-1 text-[#dc2626]" />
                <div className="font-mono text-xs font-bold text-slate-800">{t('how.s2.gpsTitle', 'GPS Location')}</div>
                <div className="text-[10px] text-slate-500">{t('how.s2.gpsDesc', 'Device Coordinates')}</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <Clock className="w-5 h-5 mx-auto mb-1 text-blue-600" />
                <div className="font-mono text-xs font-bold text-slate-800">{t('how.s2.timeTitle', 'Timestamp & Hash')}</div>
                <div className="text-[10px] text-slate-500">{t('how.s2.timeDesc', 'Provenance Context')}</div>
              </div>
            </div>

            <div className="text-center py-2.5 px-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-mono font-bold flex items-center justify-center gap-2 shadow-xs">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>{t('how.s2.verifiedBadge', 'Verified Evidence Context')}</span>
            </div>
          </div>

          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
            <strong>{t('how.s2.advisoryNote', 'Advisory Note:')}</strong> {t('how.s2.advisoryNoteText', 'Evidence context helps responders assess consistency and trust without claiming metadata alone guarantees authenticity.')}
          </div>
        </div>
      ),
    },

    // STAGE 03: GEMINI VISION ANALYSIS
    {
      id: '03',
      stepNum: '03',
      title: t('how.s3.title', 'AI Understands the Evidence'),
      shortDesc: t('how.s3.shortDesc', 'Gemini Vision extracts structured observations from photo evidence for officer review.'),
      tag: t('how.s3.tag', 'GEMINI VISION (PRIMARY)'),
      tagColor: 'bg-purple-50 text-purple-700 border-purple-200',
      category: 'intelligence',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s3.desc', 'Gemini Vision analyzes uploaded visual evidence to extract structured hazard observations. If Gemini is temporarily unreachable, the provider router automatically uses OpenAI Vision as an upstream fallback.')}
          </p>

          <div className="p-4 rounded-xl bg-purple-50/50 border border-purple-200 hover:border-purple-300 hover:shadow-md hover:shadow-purple-500/5 transition-all duration-200 shadow-xs">
            <div className="flex items-center justify-between pb-2 mb-3 border-b border-purple-200/60">
              <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-purple-900">
                <Sparkles className="w-4 h-4 text-purple-600" />
                <span>{t('how.s3.analysisTitle', 'AI VISUAL EVIDENCE ANALYSIS')}</span>
              </div>
              <span className="font-mono text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-purple-100 text-purple-800 border border-purple-200">
                {t('how.s3.analysisBadge', 'GEMINI VISION PRIMARY • OPENAI FALLBACK')}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 font-mono text-xs text-slate-700">
              <div className="p-2.5 rounded-lg bg-white border border-purple-100 hover:border-purple-300 hover:shadow-xs transition-all flex justify-between">
                <span>{t('how.s3.hazardLabel', 'Hazard Indicators:')}</span>
                <strong className="text-purple-700">{t('how.s3.hazardVal', 'Flooding / Debris')}</strong>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-purple-100 hover:border-purple-300 hover:shadow-xs transition-all flex justify-between">
                <span>{t('how.s3.accessLabel', 'Access Obstruction:')}</span>
                <strong className="text-amber-700">{t('how.s3.accessVal', 'Road Submerged')}</strong>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-purple-100 hover:border-purple-300 hover:shadow-xs transition-all flex justify-between">
                <span>{t('how.s3.vulnerableLabel', 'Vulnerable Persons:')}</span>
                <strong className="text-slate-700">{t('how.s3.vulnerableVal', 'Elderly Reported')}</strong>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-purple-100 hover:border-purple-300 hover:shadow-xs transition-all flex justify-between">
                <span>{t('how.s3.confidenceLabel', 'Analysis Confidence:')}</span>
                <strong className="text-emerald-700">{t('how.s3.confidenceVal', 'Advisory High')}</strong>
              </div>
            </div>

            <div className="mt-3 pt-2.5 border-t border-purple-200/60 flex items-center justify-between text-xs">
              <span className="text-slate-600 font-medium">{t('how.s3.consistencyLabel', 'Text–Image Consistency:')}</span>
              <span className="font-mono font-bold text-emerald-700 bg-emerald-100/70 border border-emerald-300 px-2 py-0.5 rounded shadow-2xs">
                {t('how.s3.consistencyVal', 'SUPPORTED (Observation Consistent)')}
              </span>
            </div>
          </div>

          <div className="text-xs text-slate-500 bg-slate-50 p-3 rounded-xl border border-slate-200">
            <strong>{t('how.s3.boundaryLabel', 'Advisory Boundary:')}</strong> {t('how.s3.boundaryText', 'AI provides evidence observations; emergency officers make the final operational judgement.')}
          </div>
        </div>
      ),
    },

    // STAGE 04: IMMEDIATE SAFETY GUIDANCE
    {
      id: '04',
      stepNum: '04',
      title: t('how.s4.title', 'Get Immediate Safety Guidance'),
      shortDesc: t('how.s4.shortDesc', 'Instant tailored guidance, real Google Places discovery, and true Google Road routes.'),
      tag: t('how.s4.tag', 'SAFETY & REAL ROUTING'),
      tagColor: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      category: 'ingestion',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s4.desc', 'Immediately upon submitting a report, the Safety Guidance Agent provides context-specific life-safety instructions and discovers real nearby destinations using the live Google Places API.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            <div className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-500">
              {t('how.s4.pipelineTitle', 'Safety Guidance & Navigation Pipeline')}
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-2 text-xs font-mono">
              <div className="flex-1 w-full p-2.5 rounded-lg bg-slate-50 border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/10 hover:-translate-y-0.5 transition-all duration-200 text-center">
                <MapPin className="w-4 h-4 mx-auto text-red-600 mb-0.5" />
                <span className="font-bold">{t('how.s4.citizenLoc', 'Citizen Location')}</span>
                <span className="block text-[10px] text-slate-400">{t('how.s4.citizenLocDesc', 'Incident Origin')}</span>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 rotate-90 sm:rotate-0" />
              <div className="flex-1 w-full p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/10 hover:-translate-y-0.5 transition-all duration-200 text-emerald-900 text-center">
                <Building2 className="w-4 h-4 mx-auto text-emerald-600 mb-0.5" />
                <span className="font-bold">{t('how.s4.places', 'Google Places')}</span>
                <span className="block text-[10px] text-emerald-700">{t('how.s4.placesDesc', 'Real Nearby Shelter/Hospital')}</span>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 rotate-90 sm:rotate-0" />
              <div className="flex-1 w-full p-2.5 rounded-lg bg-blue-50 border border-blue-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/10 hover:-translate-y-0.5 transition-all duration-200 text-blue-900 text-center">
                <Navigation className="w-4 h-4 mx-auto text-blue-600 mb-0.5" />
                <span className="font-bold">{t('how.s4.routes', 'Google Routes')}</span>
                <span className="block text-[10px] text-blue-700">{t('how.s4.routesDesc', 'Real Road Geometry & ETA')}</span>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-300 transition-colors text-xs font-sans text-slate-700 space-y-1">
              <div className="font-bold text-slate-900 flex items-center gap-1.5">
                <Navigation className="w-3.5 h-3.5 text-blue-600" />
                <span>{t('how.s4.routesBoxTitle', 'Google Routes Calculates Real Road-Network Routes')}</span>
              </div>
              <p className="text-[11px] text-slate-600">
                {t('how.s4.routesBoxDesc', 'Google Routes computes actual road turns, distance, travel time, and surfaces official advisories or closed-road warnings.')}
              </p>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 05: STAY INFORMED
    {
      id: '05',
      stepNum: '05',
      title: t('how.s5.title', 'Stay Informed via Push & WhatsApp'),
      shortDesc: t('how.s5.shortDesc', 'Transparent updates via opt-in Browser Web Push and WhatsApp report tracking.'),
      tag: t('how.s5.tag', 'NOTIFICATIONS'),
      tagColor: 'bg-cyan-50 text-cyan-700 border-cyan-200',
      category: 'ingestion',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s5.desc', 'Citizens receive transparent updates on their report’s review, team assignment, and resolution.')}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Web Push */}
            <div className="p-4 rounded-xl bg-white border border-slate-200 hover:border-red-400 hover:shadow-xl hover:shadow-red-500/10 hover:-translate-y-1 shadow-xs transition-all duration-200">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-lg bg-red-50 border border-red-200 flex items-center justify-center text-[#dc2626]">
                  <Send className="w-4 h-4" />
                </div>
                <div>
                  <div className="font-bold text-xs text-slate-900">{t('how.s5.pushTitle', 'Browser Web Push')}</div>
                  <div className="text-[10px] text-slate-500 font-mono">{t('how.s5.pushTag', 'Explicit Citizen Opt-In')}</div>
                </div>
              </div>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                {t('how.s5.pushDesc', 'Permission granted → Push Subscription registered → Instant emergency alert broadcast to affected area browsers.')}
              </p>
            </div>

            {/* WhatsApp Updates */}
            <div className="p-4 rounded-xl bg-white border border-slate-200 hover:border-emerald-400 hover:shadow-xl hover:shadow-emerald-500/10 hover:-translate-y-1 shadow-xs transition-all duration-200">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600">
                  <MessageSquare className="w-4 h-4" />
                </div>
                <div>
                  <div className="font-bold text-xs text-slate-900">{t('how.s5.waTitle', 'WhatsApp Status Tracking')}</div>
                  <div className="text-[10px] text-slate-500 font-mono">{t('how.s5.waTag', 'Secondary Tracking Channel')}</div>
                </div>
              </div>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                {t('how.s5.waDesc', 'Report ID → Status Updates (Reviewed → Team Assigned → Resolved).')} <em>{t('how.s5.waNote', 'Note: WhatsApp is an update channel, not an intake channel.')}</em>
              </p>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 06: OFFICER VERIFICATION
    {
      id: '06',
      stepNum: '06',
      title: t('how.s6.title', 'Verify the Situation'),
      shortDesc: t('how.s6.shortDesc', 'Multi-source corroboration combining citizen reports, IoT sensors, and field teams.'),
      tag: t('how.s6.tag', 'OFFICER VERIFICATION'),
      tagColor: 'bg-red-50 text-red-700 border-red-200',
      category: 'intelligence',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s6.desc', 'In the Emergency Operations Center (EOC), official incident command officers evaluate the complete operational picture corroborated from multiple physical and digital sources.')}
          </p>

          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-xs">
            <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500 mb-2">
              {t('how.s6.engineTitle', 'Multi-Source Corroboration Engine')}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs font-mono mb-3">
              <div className="p-2.5 rounded-lg bg-white border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="block text-sm mb-0.5">👤</span>
                <span className="font-bold text-slate-800">{t('how.s6.reportTitle', 'Citizen Report')}</span>
                <span className="block text-[10px] text-slate-500">{t('how.s6.reportDesc', 'Initial observation')}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-slate-200 hover:border-purple-400 hover:shadow-md hover:shadow-purple-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="block text-sm mb-0.5">📷</span>
                <span className="font-bold text-slate-800">{t('how.s6.evidenceTitle', 'Visual Evidence')}</span>
                <span className="block text-[10px] text-slate-500">{t('how.s6.evidenceDesc', 'Gemini observations')}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-slate-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="block text-sm mb-0.5">📡</span>
                <span className="font-bold text-slate-800">{t('how.s6.sensorsTitle', 'IoT Sensors')}</span>
                <span className="block text-[10px] text-slate-500">{t('how.s6.sensorsDesc', 'Real-time signals')}</span>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-slate-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="block text-sm mb-0.5">👷</span>
                <span className="font-bold text-slate-800">{t('how.s6.groundTitle', 'Ground Teams')}</span>
                <span className="block text-[10px] text-slate-500">{t('how.s6.groundDesc', 'Field verification')}</span>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-white border border-red-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/10 transition-all duration-200 text-center font-mono text-xs font-bold text-red-700 flex items-center justify-center gap-2">
              <UserCheck className="w-4 h-4 text-red-600" />
              <span>{t('how.s6.officerVerify', 'The officer verifies the situation before operational coordination.')}</span>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 07: SITUATION INTELLIGENCE
    {
      id: '07',
      stepNum: '07',
      title: t('how.s7.title', 'Understand the Situation'),
      shortDesc: t('how.s7.shortDesc', 'Mathematical priority scoring and deterministic severity mapping without hallucinations.'),
      tag: t('how.s7.tag', 'TRIAGE & SEVERITY'),
      tagColor: 'bg-amber-50 text-amber-700 border-amber-200',
      category: 'intelligence',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s7.desc', 'The system combines verified evidence into an operational picture: incident type, impact radius, deterministic severity, priority scoring, confidence, and supporting evidence.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-2.5">
            <div className="flex items-center justify-between text-xs font-mono p-2 rounded-lg bg-slate-50 border border-slate-100 hover:border-red-300 transition-colors">
              <span className="text-slate-600">{t('how.s7.severityLabel', 'Severity Assessment:')}</span>
              <span className="font-bold text-red-700 bg-red-50 border border-red-200 px-2.5 py-0.5 rounded shadow-2xs">
                {t('how.s7.severityVal', 'DETERMINISTIC & AUDITABLE')}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs font-mono p-2 rounded-lg bg-slate-50 border border-slate-100 hover:border-purple-300 transition-colors">
              <span className="text-slate-600">{t('how.s7.roleLabel', 'AI Extraction Role:')}</span>
              <span className="font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2.5 py-0.5 rounded shadow-2xs">
                {t('how.s7.roleVal', 'ADVISORY (NON-MUTATING)')}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs font-mono p-2 rounded-lg bg-slate-50 border border-slate-100 hover:border-slate-300 transition-colors">
              <span className="text-slate-600">{t('how.s7.authLabel', 'Decision Authority:')}</span>
              <span className="font-bold text-slate-900 bg-slate-100 border border-slate-200 px-2.5 py-0.5 rounded shadow-2xs">
                {t('how.s7.authVal', 'COMMANDING OFFICER')}
              </span>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 08: MULTI-AGENT COORDINATION
    {
      id: '08',
      stepNum: '08',
      title: t('how.s8.title', 'Specialized AI Agents Coordinate the Response'),
      shortDesc: t('how.s8.shortDesc', 'Dependency-aware orchestrator coordinating 9 specialized deterministic agents.'),
      tag: t('how.s8.tag', '9-AGENT ORCHESTRATOR'),
      tagColor: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      category: 'coordination',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s8.desc', 'A central orchestrator sequences 9 specialized deterministic AI agents through a dependency-aware workflow. Each agent solves one discrete domain problem without hallucination.')}
          </p>

          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-xs space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-slate-800">
                <Cpu className="w-4 h-4 text-indigo-600" />
                <span>{t('how.agent.orchTitle', 'CENTRAL MULTI-AGENT ORCHESTRATOR')}</span>
              </div>
              <span className="text-[10px] font-mono font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded">
                {t('how.agent.orchActive', '9 ACTIVE NODES')}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              {agentNodes.map((agent) => {
                const IconComponent = agent.icon;
                return (
                  <div
                    key={agent.num}
                    className={`group p-3 rounded-xl bg-white border border-slate-200 hover:-translate-y-0.5 transition-all duration-200 flex flex-col justify-between cursor-default ${agent.hoverClass}`}
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className={`w-7 h-7 rounded-lg flex items-center justify-center border text-xs transition-transform group-hover:scale-105 ${agent.color}`}>
                        <IconComponent className="w-4 h-4" />
                      </span>
                      <div className="font-mono text-xs font-bold text-slate-900">{agent.num} {agent.name}</div>
                    </div>
                    <div className="text-[11px] text-slate-500 italic mb-1.5">&ldquo;{agent.question}&rdquo;</div>
                    <div className="text-[10px] font-mono text-slate-700 font-semibold">{agent.role}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 09: HUMAN-IN-THE-LOOP PLAN REVIEW
    {
      id: '09',
      stepNum: '09',
      title: t('how.s9.title', 'AI Recommends. Human Decides.'),
      shortDesc: t('how.s9.shortDesc', 'Explainable response plans submitted for officer review with Approve, Modify, or Reject controls.'),
      tag: t('how.s9.tag', 'HUMAN-IN-THE-LOOP'),
      tagColor: 'bg-red-50 text-[#dc2626] border-red-200',
      category: 'coordination',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s9.desc', 'AI coordinates and proposes a structured response plan. The Emergency Officer retains complete authority to inspect resource allocations, adjust quantities, change assignments, or reject recommendations.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="font-mono text-xs font-bold text-slate-900">
                {t('how.s9.reviewTitle', 'ILLUSTRATIVE PLAN REVIEW: EMERGENCY WATER SUPPLY')}
              </div>
              <span className="text-[10px] font-mono font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded shadow-2xs">
                {t('how.s9.pendingBadge', 'PENDING APPROVAL')}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 hover:border-amber-300 hover:shadow-xs transition-all duration-200">
                <span className="font-mono text-[10px] font-bold text-slate-400 uppercase">{t('how.s9.needsLabel', 'Needs Assessment (What is required?)')}</span>
                <div className="font-bold text-slate-900 text-sm mt-1">{t('how.s9.needsVal', '100 Liters Clean Water')}</div>
                <div className="text-[11px] text-slate-500">{t('how.s9.needsSub', 'Estimated for 50 evacuated persons')}</div>
              </div>

              <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 hover:border-emerald-300 hover:shadow-xs transition-all duration-200">
                <span className="font-mono text-[10px] font-bold text-slate-400 uppercase">{t('how.s9.allocLabel', 'AI Recommended Allocation (How to fulfill?)')}</span>
                <div className="text-slate-800 text-xs font-mono mt-1 space-y-0.5">
                  <div>{t('how.s9.allocItem1', '• Warehouse A → 70 L (Distance: 2.1 km)')}</div>
                  <div>{t('how.s9.allocItem2', '• Warehouse B → 30 L (Distance: 4.8 km)')}</div>
                </div>
              </div>
            </div>

            {/* Officer Decision Controls with Hover feedback */}
            <div className="flex items-center gap-2 pt-2">
              <div className="flex-1 py-2.5 px-3 rounded-lg bg-emerald-50 border border-emerald-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/10 text-emerald-800 text-center font-mono text-xs font-bold flex items-center justify-center gap-1.5 transition-all duration-200 cursor-pointer">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>{t('how.s9.btnApprove', 'APPROVE PLAN')}</span>
              </div>
              <div className="flex-1 py-2.5 px-3 rounded-lg bg-amber-50 border border-amber-200 hover:border-amber-400 hover:shadow-md hover:shadow-amber-500/10 text-amber-800 text-center font-mono text-xs font-bold flex items-center justify-center gap-1.5 transition-all duration-200 cursor-pointer">
                <Sliders className="w-3.5 h-3.5 text-amber-600" />
                <span>{t('how.s9.btnModify', 'MODIFY QUANTITIES')}</span>
              </div>
              <div className="flex-1 py-2.5 px-3 rounded-lg bg-red-50 border border-red-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/10 text-red-800 text-center font-mono text-xs font-bold flex items-center justify-center gap-1.5 transition-all duration-200 cursor-pointer">
                <AlertTriangle className="w-3.5 h-3.5 text-red-600" />
                <span>{t('how.s9.btnReject', 'REJECT')}</span>
              </div>
            </div>
          </div>

          <div className="text-xs text-slate-500 bg-slate-50 p-3 rounded-xl border border-slate-200">
            <strong>{t('how.s9.keyDistinction', 'Key Distinction:')}</strong> {t('how.s9.keyDistinctionText', 'Need Assessment ("What is required?") is decoupled from Coordination ("How can we fulfill it?").')}
          </div>
        </div>
      ),
    },

    // STAGE 10: RESOURCE & VOLUNTEER EXECUTION
    {
      id: '10',
      stepNum: '10',
      title: t('how.s10.title', 'Turn the Plan into Action'),
      shortDesc: t('how.s10.shortDesc', 'Approved tasks dispatched to resource teams and volunteers with explicit acceptance workflows.'),
      tag: t('how.s10.tag', 'EXECUTION'),
      tagColor: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      category: 'execution',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s10.desc', 'Upon human approval, the plan generates discrete actionable tasks. Field responders and volunteers explicitly review and accept assignments prior to execution.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500">
              {t('how.s10.lifecycleTitle', 'Task Lifecycle & State Machine')}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-mono">
              <span className="px-2.5 py-1 rounded bg-slate-100 border border-slate-200 font-bold">{t('how.s10.stCreated', '1. CREATED')}</span>
              <ChevronRight className="w-4 h-4 text-slate-400" />
              <span className="px-2.5 py-1 rounded bg-blue-50 border border-blue-200 text-blue-800 font-bold">{t('how.s10.stAssigned', '2. ASSIGNED')}</span>
              <ChevronRight className="w-4 h-4 text-slate-400" />
              <span className="px-2.5 py-1 rounded bg-amber-50 border border-amber-200 text-amber-800 font-bold">{t('how.s10.stAccepted', '3. ACCEPTED')}</span>
              <ChevronRight className="w-4 h-4 text-slate-400" />
              <span className="px-2.5 py-1 rounded bg-purple-50 border border-purple-200 text-purple-800 font-bold">{t('how.s10.stInProgress', '4. IN PROGRESS')}</span>
              <ChevronRight className="w-4 h-4 text-slate-400" />
              <span className="px-2.5 py-1 rounded bg-emerald-50 border border-emerald-200 text-emerald-800 font-bold">{t('how.s10.stCompleted', '5. COMPLETED')}</span>
            </div>

            {/* Inventory Model */}
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono space-y-1">
              <div className="font-bold text-slate-900">{t('how.s10.invModelTitle', 'Inventory Ledger Model (Plan creation does NOT consume inventory):')}</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center pt-1.5">
                <div className="p-2 rounded bg-white border border-slate-200 hover:border-slate-300 transition-colors">
                  <span className="block text-[10px] text-slate-400">{t('how.s10.total', 'TOTAL')}</span>
                  <strong className="text-slate-800">{t('how.s10.totalVal', '100 L')}</strong>
                </div>
                <div className="p-2 rounded bg-white border border-slate-200 hover:border-amber-400 hover:shadow-xs transition-all">
                  <span className="block text-[10px] text-amber-600">{t('how.s10.reserved', 'RESERVED')}</span>
                  <strong className="text-amber-700">{t('how.s10.reservedVal', '40 L')}</strong>
                </div>
                <div className="p-2 rounded bg-white border border-slate-200 hover:border-emerald-400 hover:shadow-xs transition-all">
                  <span className="block text-[10px] text-emerald-600">{t('how.s10.available', 'AVAILABLE')}</span>
                  <strong className="text-emerald-700">{t('how.s10.availableVal', '60 L')}</strong>
                </div>
                <div className="p-2 rounded bg-white border border-slate-200 hover:border-blue-400 hover:shadow-xs transition-all">
                  <span className="block text-[10px] text-blue-600">{t('how.s10.consumed', 'CONSUMED')}</span>
                  <strong className="text-blue-700">{t('how.s10.consumedVal', '40 L (Upon Task Done)')}</strong>
                </div>
              </div>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 11: LIVE MONITORING
    {
      id: '11',
      stepNum: '11',
      title: t('how.s11.title', 'Monitor What Changes'),
      shortDesc: t('how.s11.shortDesc', 'Live monitoring of genuine sensor events, field updates, and response changes.'),
      tag: t('how.s11.tag', 'LIVE MONITORING'),
      tagColor: 'bg-blue-50 text-blue-700 border-blue-200',
      category: 'execution',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s11.desc', 'The situation never stays static. The system continuously tracks genuine operational changes including sensor alerts, volunteer progress, and road condition updates.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-center">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-blue-400 hover:shadow-xl hover:shadow-blue-500/10 hover:-translate-y-1 transition-all duration-200">
                <Radio className="w-5 h-5 mx-auto mb-1 text-blue-600" />
                <div className="font-mono text-xs font-bold text-slate-800">{t('how.s11.sensorTitle', 'Sensor Signals')}</div>
                <div className="text-[10px] text-slate-500">{t('how.s11.sensorDesc', 'Real-time water & flood alerts')}</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-emerald-400 hover:shadow-xl hover:shadow-emerald-500/10 hover:-translate-y-1 transition-all duration-200">
                <Users className="w-5 h-5 mx-auto mb-1 text-emerald-600" />
                <div className="font-mono text-xs font-bold text-slate-800">{t('how.s11.fieldTitle', 'Field Updates')}</div>
                <div className="text-[10px] text-slate-500">{t('how.s11.fieldDesc', 'Ground responder status')}</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-purple-400 hover:shadow-xl hover:shadow-purple-500/10 hover:-translate-y-1 transition-all duration-200">
                <Activity className="w-5 h-5 mx-auto mb-1 text-purple-600" />
                <div className="font-mono text-xs font-bold text-slate-800">{t('how.s11.eventsTitle', 'Response Events')}</div>
                <div className="text-[10px] text-slate-500">{t('how.s11.eventsDesc', 'Supply deliveries & intake')}</div>
              </div>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 12: PREDICTIVE ANALYSIS
    {
      id: '12',
      stepNum: '12',
      title: t('how.s12.title', 'Predictive Analysis'),
      shortDesc: t('how.s12.shortDesc', 'Analyze recent incident, sensor, and weather trends to estimate short-term escalation risk.'),
      tag: t('how.s12.tag', 'ADVISORY FORECAST'),
      tagColor: 'bg-blue-50 text-blue-700 border-blue-200',
      category: 'execution',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s12.desc', 'Analyze recent incident, sensor, and environmental trends to estimate how emergency conditions may evolve over the next 15, 30, and 60 minutes.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-slate-900">
                <TrendingUp className="w-4 h-4 text-blue-600" />
                <span>{t('how.s12.headerTitle', 'PREDICTIVE INTELLIGENCE & SHORT-TERM RISK ESTIMATION')}</span>
              </div>
              <span className="font-mono text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded shadow-2xs">
                {t('how.s12.headerBadge', 'ADVISORY ONLY • NON-MUTATING')}
              </span>
            </div>

            {/* Core Analytical Inputs & Capabilities */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs font-sans">
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-blue-300 hover:shadow-xs transition-all duration-200">
                <div className="flex items-center gap-1.5 font-bold text-slate-900 mb-1">
                  <Radio className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                  <span>{t('how.s12.c1Title', 'Sensor Telemetry & Incident History')}</span>
                </div>
                <p className="text-[11px] text-slate-600 leading-relaxed">
                  {t('how.s12.c1Desc', 'Evaluates genuine time-series sensor observations and recent report frequency to detect rising, stable, or receding trends.')}
                </p>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-blue-300 hover:shadow-xs transition-all duration-200">
                <div className="flex items-center gap-1.5 font-bold text-slate-900 mb-1">
                  <CloudSun className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                  <span>{t('how.s12.c2Title', 'Live Environmental & Weather Context')}</span>
                </div>
                <p className="text-[11px] text-slate-600 leading-relaxed">
                  {t('how.s12.c2Desc', 'Correlates local precipitation observations, wind velocity, and soil saturation as external risk factors.')}
                </p>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-blue-300 hover:shadow-xs transition-all duration-200">
                <div className="flex items-center gap-1.5 font-bold text-slate-900 mb-1">
                  <Clock className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                  <span>{t('how.s12.c3Title', '15 / 30 / 60-Minute Horizon Forecasts')}</span>
                </div>
                <p className="text-[11px] text-slate-600 leading-relaxed">
                  {t('how.s12.c3Desc', 'Computes multi-horizon escalation estimates and surfaces explainable contributing factor weights.')}
                </p>
              </div>

              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-blue-300 hover:shadow-xs transition-all duration-200">
                <div className="flex items-center gap-1.5 font-bold text-slate-900 mb-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                  <span>{t('how.s12.c4Title', 'Confidence & Data-Sufficiency Guardrails')}</span>
                </div>
                <p className="text-[11px] text-slate-600 leading-relaxed">
                  {t('how.s12.c4Desc', 'Explicitly indicates data completeness; falls back to UNCERTAIN when sensor or weather evidence is insufficient.')}
                </p>
              </div>
            </div>

            {/* Workflow Progression: Live Monitoring -> Predictive -> Impact -> Dynamic Replanning */}
            <div className="p-3 rounded-lg bg-blue-50/70 border border-blue-200 space-y-1.5">
              <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-blue-900">
                {t('how.s12.wfTitle', 'Decision Support Workflow Progression')}
              </div>
              <div className="flex flex-col sm:flex-row items-center gap-1.5 text-[11px] font-mono text-slate-800">
                <span className="p-1.5 rounded bg-white border border-blue-200 text-center w-full sm:w-auto font-semibold">
                  {t('how.s12.wf1', '1. Predictive Analysis detects potential change')}
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-blue-600 shrink-0 rotate-90 sm:rotate-0" />
                <span className="p-1.5 rounded bg-white border border-blue-200 text-center w-full sm:w-auto font-semibold">
                  {t('how.s12.wf2', '2. Impact Analysis evaluates operational risk')}
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-blue-600 shrink-0 rotate-90 sm:rotate-0" />
                <span className="p-1.5 rounded bg-white border border-blue-200 text-center w-full sm:w-auto font-semibold">
                  {t('how.s12.wf3', '3. Dynamic Replanning prepares revised plan')}
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-blue-600 shrink-0 rotate-90 sm:rotate-0" />
                <span className="p-1.5 rounded bg-white border border-red-200 text-red-800 text-center w-full sm:w-auto font-bold">
                  {t('how.s12.wf4', '4. Officer reviews & approves')}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-start gap-2 p-3.5 rounded-xl bg-amber-50/80 border border-amber-200 text-amber-900 text-xs shadow-xs">
            <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <span>
              <strong>{t('how.s12.guardrailLabel', 'Decision Support Guardrail:')}</strong> {t('how.s12.guardrailText', 'Predictive analysis provides advisory risk estimates and never automatically overwrites authoritative incident severity, dispatches resources, triggers public alerts, or autonomously executes a replan. The Emergency Officer remains the authoritative decision-maker.')}
            </span>
          </div>
        </div>
      ),
    },

    // STAGE 13: DYNAMIC REPLANNING
    {
      id: '13',
      stepNum: '13',
      title: t('how.s13.title', 'Adapt When Conditions Change'),
      shortDesc: t('how.s13.shortDesc', 'Automated impact analysis and allocation diffs when roads or warehouses become blocked.'),
      tag: t('how.s13.tag', 'DYNAMIC REPLANNING'),
      tagColor: 'bg-purple-50 text-purple-700 border-purple-200',
      category: 'governance',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s13.desc', 'When ground teams or sensors detect that a warehouse route is flooded, Resilience performs automated impact analysis and computes a revised allocation diff without changing the underlying need.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            {/* Interactive simulation toggle */}
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="font-mono text-xs font-bold text-slate-900">
                {t('how.s13.scenarioTitle', 'SCENARIO: WAREHOUSE ACCESS OBSTRUCTION')}
              </div>
              <div className="flex items-center gap-1 font-mono text-[10px]">
                <button
                  onClick={() => setReplanningSimState('initial')}
                  className={`px-2.5 py-1 rounded transition-all duration-200 cursor-pointer ${replanningSimState === 'initial' ? 'bg-slate-900 text-white font-bold shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                >
                  {t('how.s13.tabOriginal', 'Original')}
                </button>
                <button
                  onClick={() => setReplanningSimState('blocked')}
                  className={`px-2.5 py-1 rounded transition-all duration-200 cursor-pointer ${replanningSimState === 'blocked' ? 'bg-red-600 text-white font-bold shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                >
                  {t('how.s13.tabBlocked', 'Road Blocked')}
                </button>
                <button
                  onClick={() => setReplanningSimState('revised')}
                  className={`px-2.5 py-1 rounded transition-all duration-200 cursor-pointer ${replanningSimState === 'revised' ? 'bg-purple-600 text-white font-bold shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                >
                  {t('how.s13.tabRevised', 'Revised Plan Diff')}
                </button>
              </div>
            </div>

            {replanningSimState === 'initial' && (
              <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono space-y-1">
                <div className="text-slate-500 font-bold">{t('how.s13.origPlanTitle', 'Active Plan (100 L Water Need):')}</div>
                <div className="text-slate-800">{t('how.s13.origItem1', '• Warehouse A: 70 L (Dispatched)')}</div>
                <div className="text-slate-800">{t('how.s13.origItem2', '• Warehouse B: 30 L (Dispatched)')}</div>
              </div>
            )}

            {replanningSimState === 'blocked' && (
              <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-xs font-mono space-y-1 text-red-900 shadow-xs">
                <div className="font-bold flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-red-600" />
                  <span>{t('how.s13.alertTitle', 'ALERT: Warehouse A access road flooded and inaccessible!')}</span>
                </div>
                <div className="text-xs text-red-700">{t('how.s13.alertDesc', 'Impact Analysis Triggered: 70 L allocation invalidated.')}</div>
              </div>
            )}

            {replanningSimState === 'revised' && (
              <div className="p-3.5 rounded-lg bg-purple-50 border border-purple-200 text-xs font-mono space-y-2 shadow-xs">
                <div className="font-bold text-purple-900">{t('how.s13.revisedTitle', 'Revised Replanning Diff (Need remains 100 L):')}</div>
                <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
                  <div className="p-2 rounded bg-red-100 text-red-800 border border-red-200">
                    <span className="block font-bold">{t('how.s13.diffRemoved', 'REMOVED')}</span>
                    <span>{t('how.s13.diffWhA', 'Warehouse A (70 L)')}</span>
                  </div>
                  <div className="p-2 rounded bg-slate-100 text-slate-800 border border-slate-200">
                    <span className="block font-bold">{t('how.s13.diffUnchanged', 'UNCHANGED')}</span>
                    <span>{t('how.s13.diffWhB', 'Warehouse B (30 L)')}</span>
                  </div>
                  <div className="p-2 rounded bg-emerald-100 text-emerald-800 border border-emerald-200">
                    <span className="block font-bold">{t('how.s13.diffAdded', 'ADDED')}</span>
                    <span>{t('how.s13.diffWhC', 'Warehouse C (70 L)')}</span>
                  </div>
                </div>
                <div className="text-[10px] text-purple-800 text-center font-bold">
                  {t('how.s13.revisedStatus', 'Status: PENDING EMERGENCY OFFICER REVIEW (Never silently auto-applied)')}
                </div>
              </div>
            )}
          </div>
        </div>
      ),
    },

    // STAGE 14: WHAT-IF SIMULATION
    {
      id: '14',
      stepNum: '14',
      title: t('how.s14.title', 'Plan for What Could Happen (What-If)'),
      shortDesc: t('how.s14.shortDesc', 'Sandbox simulation engine for capacity stress-testing without touching live operational state.'),
      tag: t('how.s14.tag', 'WHAT-IF SIMULATION'),
      tagColor: 'bg-teal-50 text-teal-700 border-teal-200',
      category: 'governance',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s14.desc', 'Commanders can test prospective scenarios in a strictly isolated sandbox before making field decisions.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 hover:border-teal-300 hover:shadow-md hover:shadow-teal-500/5 transition-all duration-200 shadow-xs space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-slate-900">
                <FlaskConical className="w-4 h-4 text-teal-600" />
                <span>{t('how.s14.simTitle', 'WHAT-IF SCENARIO SIMULATOR')}</span>
              </div>
              <span className="font-mono text-[10px] font-bold bg-teal-100 text-teal-800 border border-teal-300 px-2 py-0.5 rounded shadow-2xs">
                {t('how.s14.simBadge', 'SIMULATION — NOT ACTIVE RESPONSE')}
              </span>
            </div>

            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono text-slate-700 space-y-1">
              <div className="font-bold text-slate-900">{t('how.s14.scenarioDesc', 'Scenario: "What if Primary Shelter S1 becomes unavailable?"')}</div>
              <p className="text-[11px] text-slate-500">
                {t('how.s14.scenarioSub', 'Simulation calculates backup shelter capacities and route adjustments without modifying live inventory or database records.')}
              </p>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 15: RESOLUTION & AUDIT TRAIL
    {
      id: '15',
      stepNum: '15',
      title: t('how.s15.title', 'Resolve & Learn'),
      shortDesc: t('how.s15.shortDesc', 'End-to-end immutability with verified closure metrics and post-incident analytics.'),
      tag: t('how.s15.tag', 'GOVERNANCE & AUDIT'),
      tagColor: 'bg-slate-100 text-slate-800 border-slate-300',
      category: 'governance',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            {t('how.s15.desc', 'Every citizen report, officer decision, AI recommendation, resource dispatch, and volunteer action is recorded in an immutable audit trail for post-incident analysis and governance.')}
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-center text-xs font-mono">
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <FileCheck className="w-4 h-4 mx-auto mb-1 text-emerald-600" />
                <span className="font-bold text-slate-800">{t('how.s15.fieldComplete', 'Field Complete')}</span>
                <span className="block text-[10px] text-slate-500">{t('how.s15.fieldCompleteDesc', 'All tasks verified')}</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <Boxes className="w-4 h-4 mx-auto mb-1 text-blue-600" />
                <span className="font-bold text-slate-800">{t('how.s15.ledgerClosed', 'Ledger Closed')}</span>
                <span className="block text-[10px] text-slate-500">{t('how.s15.ledgerClosedDesc', 'Actuals matched')}</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-purple-400 hover:shadow-md hover:shadow-purple-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <Lock className="w-4 h-4 mx-auto mb-1 text-purple-600" />
                <span className="font-bold text-slate-800">{t('how.s15.auditTrail', 'Audit Trail')}</span>
                <span className="block text-[10px] text-slate-500">{t('how.s15.auditTrailDesc', 'Immutable history')}</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-400 hover:shadow-md hover:shadow-slate-300/40 hover:-translate-y-0.5 transition-all duration-200">
                <Activity className="w-4 h-4 mx-auto mb-1 text-slate-700" />
                <span className="font-bold text-slate-800">{t('how.s15.eocAnalytics', 'EOC Analytics')}</span>
                <span className="block text-[10px] text-slate-500">{t('how.s15.eocAnalyticsDesc', 'After-action review')}</span>
              </div>
            </div>

            <div className="text-center py-2.5 px-3 rounded-lg bg-slate-50 border border-slate-200 font-mono text-xs text-slate-700">
              {t('how.s15.banner', 'AUDIT CERTIFIED • ZERO UNEXPLAINED ACTIONS • 100% TRACEABLE')}
            </div>
          </div>
        </div>
      ),
    },
  ];

  const filteredStages = activeCategory === 'all' 
    ? stages 
    : stages.filter(s => s.category === activeCategory);

  const activeStage = stages.find(s => s.id === activeStageId) || stages[0];

  return (
    <section id="how-it-works" className="scroll-mt-20 mb-20">
      {/* Section Header */}
      <div className="text-left mb-8 sm:mb-10">
        <div className="inline-flex items-center gap-2 font-mono text-[11px] uppercase text-[#dc2626] font-bold tracking-wider mb-2">
          <Radio className="w-3.5 h-3.5" />
          <span>{t('how.tag', 'END-TO-END EMERGENCY RESPONSE ARCHITECTURE')}</span>
        </div>
        <h2 className="text-2xl sm:text-4xl font-black uppercase font-sans tracking-tight text-slate-900 leading-tight">
          {t('how.title', 'How Resilience Works')}
        </h2>
        <p className="text-sm sm:text-base text-slate-600 mt-2 max-w-2xl leading-relaxed font-sans">
          {t('how.subtitle', 'From the first citizen report to coordinated emergency response. Resilience connects citizen observations, geotagged evidence, AI-assisted situation understanding, real-world resources, field teams, and human decision-makers into one auditable response workflow.')}
        </p>
      </div>

      {/* Human-in-the-loop Banner Principle */}
      <div className="mb-8 p-4 sm:p-5 rounded-2xl bg-white border border-slate-300 shadow-sm hover:border-slate-400 hover:shadow-xl hover:shadow-slate-200/60 hover:-translate-y-0.5 transition-all duration-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-red-50 border border-red-200 flex items-center justify-center text-[#dc2626] shrink-0">
            <UserCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="font-mono text-xs font-bold text-slate-900 uppercase tracking-wide">
              {t('status.hitl', 'Core Product Principle: AI is Not the Final Authority')}
            </div>
            <div className="text-xs text-slate-700 mt-0.5">
              {t('usp.c4Desc', 'AI analyzes and recommends. Human emergency officers verify and approve. Field teams execute. The system monitors and adapts.')}
            </div>
          </div>
        </div>

        <div className="font-mono text-[10px] text-slate-600 uppercase tracking-widest px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 shrink-0 font-bold">
          {t('footer.audited', 'HUMAN-IN-THE-LOOP ACTIVE')}
        </div>
      </div>

      {/* Category Filter Pills */}
      <div className="flex items-center gap-2 overflow-x-auto pb-3 mb-6 scrollbar-none">
        {categories.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setActiveCategory(cat.id)}
            className={`whitespace-nowrap px-3.5 py-1.5 rounded-xl font-sans text-xs font-bold transition-all duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${
              activeCategory === cat.id
                ? 'bg-slate-900 text-white shadow-xs'
                : 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 hover:text-slate-900 hover:border-slate-400 hover:shadow-xs'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Two-Column Master Interactive Stage Viewer */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* LEFT: Stage Stepper List (Desktop & Mobile) */}
        <div className="lg:col-span-5 space-y-2.5 max-h-[640px] overflow-y-auto pr-1">
          {filteredStages.map((stage) => {
            const isSelected = stage.id === activeStageId;
            return (
              <button
                key={stage.id}
                onClick={() => setActiveStageId(stage.id)}
                className={`w-full text-left p-3.5 rounded-xl border transition-all duration-200 cursor-pointer flex items-center justify-between gap-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400 ${
                  isSelected
                    ? 'bg-white border-[#dc2626] shadow-lg shadow-red-500/10 -translate-y-0.5 ring-1 ring-red-500/20'
                    : 'bg-white border-slate-300 hover:border-red-300 hover:shadow-md hover:shadow-red-500/5 hover:-translate-y-0.5'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`w-7 h-7 rounded-lg flex items-center justify-center font-mono text-xs font-bold shrink-0 transition-transform ${
                      isSelected
                        ? 'bg-[#dc2626] text-white shadow-xs scale-105'
                        : 'bg-slate-100 text-slate-700 border border-slate-300'
                    }`}
                  >
                    {stage.stepNum}
                  </span>
                  <div>
                    <div className={`font-bold text-xs sm:text-sm font-sans transition-colors ${isSelected ? 'text-slate-900' : 'text-slate-800'}`}>
                      {stage.title}
                    </div>
                    <div className="text-[11px] text-slate-600 font-sans line-clamp-1">
                      {stage.shortDesc}
                    </div>
                  </div>
                </div>

                <ChevronRight
                  className={`w-4 h-4 shrink-0 transition-transform ${
                    isSelected ? 'text-[#dc2626] translate-x-0.5' : 'text-slate-400'
                  }`}
                />
              </button>
            );
          })}
        </div>

        {/* RIGHT: Active Stage Deep-Dive Card */}
        <div className="lg:col-span-7">
          <div className="p-6 sm:p-8 rounded-2xl bg-white border border-slate-300 shadow-md hover:border-slate-400 hover:shadow-xl hover:shadow-slate-200/50 transition-all duration-200">
            {/* Header of Active Stage */}
            <div className="flex flex-wrap items-center justify-between gap-2 pb-4 mb-5 border-b border-slate-100">
              <div className="flex items-center gap-2.5">
                <span className="w-8 h-8 rounded-xl bg-[#dc2626] text-white flex items-center justify-center font-mono text-sm font-bold shadow-xs">
                  {activeStage.stepNum}
                </span>
                <div>
                  <div className="font-mono text-[10px] uppercase font-bold text-slate-400">
                    {t('how.nav.stageOf', 'STAGE {num} OF 15').replace('{num}', activeStage.stepNum)}
                  </div>
                  <h3 className="text-lg sm:text-xl font-black font-sans text-slate-900 uppercase">
                    {activeStage.title}
                  </h3>
                </div>
              </div>

              <span className={`font-mono text-[10px] font-bold uppercase px-2.5 py-1 rounded-md border ${activeStage.tagColor}`}>
                {activeStage.tag}
              </span>
            </div>

            {/* Dynamic Stage Body */}
            {activeStage.content}

            {/* Navigation Buttons Between Stages */}
            <div className="flex items-center justify-between pt-6 mt-6 border-t border-slate-100">
              <button
                disabled={activeStageId === '01'}
                onClick={() => {
                  const currentIdx = stages.findIndex((s) => s.id === activeStageId);
                  if (currentIdx > 0) setActiveStageId(stages[currentIdx - 1].id);
                }}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-sans font-semibold text-slate-600 hover:text-slate-900 border border-transparent hover:border-slate-200 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              >
                <span>{t('how.nav.prev', '← Previous Stage')}</span>
              </button>

              <div className="text-[11px] font-mono text-slate-400">
                {t('how.nav.stepOf', 'Step {step} / 15').replace('{step}', String(parseInt(activeStage.stepNum, 10)))}
              </div>

              <button
                disabled={activeStageId === '15'}
                onClick={() => {
                  const currentIdx = stages.findIndex((s) => s.id === activeStageId);
                  if (currentIdx < stages.length - 1) setActiveStageId(stages[currentIdx + 1].id);
                }}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-[#dc2626] text-white text-xs font-sans font-bold shadow-xs hover:shadow-md hover:shadow-red-500/20 disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
              >
                <span>{t('how.nav.next', 'Next Stage')}</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
