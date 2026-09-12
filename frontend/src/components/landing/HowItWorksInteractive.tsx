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
} from 'lucide-react';

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
  const [activeStageId, setActiveStageId] = useState<string>('01');
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [replanningSimState, setReplanningSimState] = useState<'initial' | 'blocked' | 'revised'>('initial');

  const categories = [
    { id: 'all', label: 'Complete 14-Stage Journey' },
    { id: 'ingestion', label: '1. Citizen Intake & Guidance' },
    { id: 'intelligence', label: '2. AI & Officer Verification' },
    { id: 'coordination', label: '3. 9-Agent Coordination' },
    { id: 'execution', label: '4. Human Approval & Field Action' },
    { id: 'governance', label: '5. Replanning, Simulation & Audit' },
  ];

  const agentNodes = [
    { num: '01', name: 'Priority Agent', question: 'How serious is it?', role: 'Deterministic Severity & Triage', icon: AlertTriangle, color: 'text-red-600 bg-red-50 border-red-200', hoverClass: 'hover:border-red-400 hover:shadow-lg hover:shadow-red-500/10' },
    { num: '02', name: 'Needs Agent', question: 'What is required?', role: 'Demand & Supply Assessment', icon: Boxes, color: 'text-amber-600 bg-amber-50 border-amber-200', hoverClass: 'hover:border-amber-400 hover:shadow-lg hover:shadow-amber-500/10' },
    { num: '03', name: 'Resource Coordination', question: 'Where can it come from?', role: 'Inventory & Depot Matching', icon: Truck, color: 'text-emerald-600 bg-emerald-50 border-emerald-200', hoverClass: 'hover:border-emerald-400 hover:shadow-lg hover:shadow-emerald-500/10' },
    { num: '04', name: 'Conflict Resolution', question: 'Is there a conflict?', role: 'Constraint & Route Validation', icon: Shield, color: 'text-indigo-600 bg-indigo-50 border-indigo-200', hoverClass: 'hover:border-indigo-400 hover:shadow-lg hover:shadow-indigo-500/10' },
    { num: '05', name: 'Shelter Agent', question: 'Where can people evacuate?', role: 'Capacity & Proximity Allocation', icon: Home, color: 'text-teal-600 bg-teal-50 border-teal-200', hoverClass: 'hover:border-teal-400 hover:shadow-lg hover:shadow-teal-500/10' },
    { num: '06', name: 'Healthcare Agent', question: 'Where can patients be treated?', role: 'Hospital & Bed Routing', icon: HeartPulse, color: 'text-rose-600 bg-rose-50 border-rose-200', hoverClass: 'hover:border-rose-400 hover:shadow-lg hover:shadow-rose-500/10' },
    { num: '07', name: 'Volunteer Agent', question: 'Who is available?', role: 'Skills & Proximity Assignment', icon: Users, color: 'text-blue-600 bg-blue-50 border-blue-200', hoverClass: 'hover:border-blue-400 hover:shadow-lg hover:shadow-blue-500/10' },
    { num: '08', name: 'Routes & Transport', question: 'How do we get there?', role: 'Google Routes Road Geometry', icon: Navigation, color: 'text-cyan-600 bg-cyan-50 border-cyan-200', hoverClass: 'hover:border-cyan-400 hover:shadow-lg hover:shadow-cyan-500/10' },
    { num: '09', name: 'Dynamic Replanning', question: 'What changes when conditions change?', role: 'Impact Analysis & Allocation Diff', icon: RefreshCw, color: 'text-purple-600 bg-purple-50 border-purple-200', hoverClass: 'hover:border-purple-400 hover:shadow-lg hover:shadow-purple-500/10' },
  ];

  const stages: Stage[] = [
    // STAGE 01: CITIZEN REPORT
    {
      id: '01',
      stepNum: '01',
      title: 'Report an Emergency',
      shortDesc: 'Instant, account-free citizen reporting with structured observation inputs.',
      tag: 'CITIZEN INTAKE',
      tagColor: 'bg-red-50 text-[#dc2626] border-red-200',
      category: 'ingestion',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Citizens can immediately report an emergency without creating an official account.
            The portal ingests structured observations to initiate first-responder triage.
          </p>

          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-xs">
            <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500 mb-2.5">
              Structured Report Inputs
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">🚨</span>
                <div>
                  <span className="font-bold text-slate-800">Emergency Type</span>
                  <span className="block text-[11px] text-slate-500">Flood, Fire, Medical, Structural, Accident</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-amber-400 hover:shadow-md hover:shadow-amber-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">⚠️</span>
                <div>
                  <span className="font-bold text-slate-800">Problem Intensity</span>
                  <span className="block text-[11px] text-slate-500">Initial citizen signal (Advisory)</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">📝</span>
                <div>
                  <span className="font-bold text-slate-800">Description</span>
                  <span className="block text-[11px] text-slate-500">Real-time observed situation details</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-purple-400 hover:shadow-md hover:shadow-purple-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">📷</span>
                <div>
                  <span className="font-bold text-slate-800">Camera Evidence</span>
                  <span className="block text-[11px] text-slate-500">Live capture / photo upload</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">📍</span>
                <div>
                  <span className="font-bold text-slate-800">Current GPS Location</span>
                  <span className="block text-[11px] text-slate-500">Device coordinates with accuracy radius</span>
                </div>
              </div>
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-white border border-slate-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="text-base">👤</span>
                <div>
                  <span className="font-bold text-slate-800">Name + Mobile</span>
                  <span className="block text-[11px] text-slate-500">Contact details for field coordination</span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-start gap-2 p-3.5 rounded-xl bg-amber-50/80 border border-amber-200 text-amber-900 text-xs shadow-xs">
            <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <span>
              <strong>Crucial Principle:</strong> Citizen-reported intensity provides an initial signal for assessment, not the final authoritative severity.
            </span>
          </div>
        </div>
      ),
    },

    // STAGE 02: GEOTAGGED CAMERA EVIDENCE
    {
      id: '02',
      stepNum: '02',
      title: 'Capture Real-World Evidence',
      shortDesc: 'Geotagged visual evidence provides ground truth with timestamp and coordinates.',
      tag: 'EVIDENCE CONTEXT',
      tagColor: 'bg-blue-50 text-blue-700 border-blue-200',
      category: 'ingestion',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Visual evidence provides essential ground truth for emergency responders. Resilience securely binds
            every photo to physical device coordinates and verifiable timestamp metadata.
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-center mb-3">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-slate-400 hover:shadow-md hover:shadow-slate-200/60 hover:-translate-y-0.5 transition-all duration-200">
                <Camera className="w-5 h-5 mx-auto mb-1 text-slate-700" />
                <div className="font-mono text-xs font-bold text-slate-800">Camera Photo</div>
                <div className="text-[10px] text-slate-500">Visual Evidence File</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <MapPin className="w-5 h-5 mx-auto mb-1 text-[#dc2626]" />
                <div className="font-mono text-xs font-bold text-slate-800">GPS Location</div>
                <div className="text-[10px] text-slate-500">Device Coordinates</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <Clock className="w-5 h-5 mx-auto mb-1 text-blue-600" />
                <div className="font-mono text-xs font-bold text-slate-800">Timestamp & Hash</div>
                <div className="text-[10px] text-slate-500">Provenance Context</div>
              </div>
            </div>

            <div className="text-center py-2.5 px-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-mono font-bold flex items-center justify-center gap-2 shadow-xs">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>Verified Evidence Context</span>
            </div>
          </div>

          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
            <strong>Advisory Note:</strong> Evidence context helps responders assess consistency and trust without claiming metadata alone guarantees authenticity.
          </div>
        </div>
      ),
    },

    // STAGE 03: GEMINI VISION ANALYSIS
    {
      id: '03',
      stepNum: '03',
      title: 'AI Understands the Evidence',
      shortDesc: 'Gemini Vision extracts structured observations from photo evidence for officer review.',
      tag: 'GEMINI VISION (PRIMARY)',
      tagColor: 'bg-purple-50 text-purple-700 border-purple-200',
      category: 'intelligence',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Gemini Vision analyzes uploaded visual evidence to extract structured hazard observations.
            If Gemini is temporarily unreachable, the provider router automatically uses OpenAI Vision as an upstream fallback.
          </p>

          <div className="p-4 rounded-xl bg-purple-50/50 border border-purple-200 hover:border-purple-300 hover:shadow-md hover:shadow-purple-500/5 transition-all duration-200 shadow-xs">
            <div className="flex items-center justify-between pb-2 mb-3 border-b border-purple-200/60">
              <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-purple-900">
                <Sparkles className="w-4 h-4 text-purple-600" />
                <span>AI VISUAL EVIDENCE ANALYSIS</span>
              </div>
              <span className="font-mono text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-purple-100 text-purple-800 border border-purple-200">
                GEMINI VISION PRIMARY • OPENAI FALLBACK
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 font-mono text-xs text-slate-700">
              <div className="p-2.5 rounded-lg bg-white border border-purple-100 hover:border-purple-300 hover:shadow-xs transition-all flex justify-between">
                <span>Hazard Indicators:</span>
                <strong className="text-purple-700">Flooding / Debris</strong>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-purple-100 hover:border-purple-300 hover:shadow-xs transition-all flex justify-between">
                <span>Access Obstruction:</span>
                <strong className="text-amber-700">Road Submerged</strong>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-purple-100 hover:border-purple-300 hover:shadow-xs transition-all flex justify-between">
                <span>Vulnerable Persons:</span>
                <strong className="text-slate-700">Elderly Reported</strong>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-purple-100 hover:border-purple-300 hover:shadow-xs transition-all flex justify-between">
                <span>Analysis Confidence:</span>
                <strong className="text-emerald-700">Advisory High</strong>
              </div>
            </div>

            <div className="mt-3 pt-2.5 border-t border-purple-200/60 flex items-center justify-between text-xs">
              <span className="text-slate-600 font-medium">Text–Image Consistency:</span>
              <span className="font-mono font-bold text-emerald-700 bg-emerald-100/70 border border-emerald-300 px-2 py-0.5 rounded shadow-2xs">
                SUPPORTED (Observation Consistent)
              </span>
            </div>
          </div>

          <div className="text-xs text-slate-500 bg-slate-50 p-3 rounded-xl border border-slate-200">
            <strong>Advisory Boundary:</strong> AI provides evidence observations; emergency officers make the final operational judgement.
          </div>
        </div>
      ),
    },

    // STAGE 04: IMMEDIATE SAFETY GUIDANCE
    {
      id: '04',
      stepNum: '04',
      title: 'Get Immediate Safety Guidance',
      shortDesc: 'Instant tailored guidance, real Google Places discovery, and true Google Road routes.',
      tag: 'SAFETY & REAL ROUTING',
      tagColor: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      category: 'ingestion',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Immediately upon submitting a report, the Safety Guidance Agent provides context-specific life-safety instructions
            and discovers real nearby destinations using the live <strong>Google Places API</strong>.
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            <div className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Safety Guidance & Navigation Pipeline
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-2 text-xs font-mono">
              <div className="flex-1 w-full p-2.5 rounded-lg bg-slate-50 border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/10 hover:-translate-y-0.5 transition-all duration-200 text-center">
                <MapPin className="w-4 h-4 mx-auto text-red-600 mb-0.5" />
                <span className="font-bold">Citizen Location</span>
                <span className="block text-[10px] text-slate-400">Incident Origin</span>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 rotate-90 sm:rotate-0" />
              <div className="flex-1 w-full p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/10 hover:-translate-y-0.5 transition-all duration-200 text-emerald-900 text-center">
                <Building2 className="w-4 h-4 mx-auto text-emerald-600 mb-0.5" />
                <span className="font-bold">Google Places</span>
                <span className="block text-[10px] text-emerald-700">Real Nearby Shelter/Hospital</span>
              </div>
              <ArrowRight className="w-4 h-4 text-slate-400 rotate-90 sm:rotate-0" />
              <div className="flex-1 w-full p-2.5 rounded-lg bg-blue-50 border border-blue-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/10 hover:-translate-y-0.5 transition-all duration-200 text-blue-900 text-center">
                <Navigation className="w-4 h-4 mx-auto text-blue-600 mb-0.5" />
                <span className="font-bold">Google Routes</span>
                <span className="block text-[10px] text-blue-700">Real Road Geometry & ETA</span>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-300 transition-colors text-xs font-sans text-slate-700 space-y-1">
              <div className="font-bold text-slate-900 flex items-center gap-1.5">
                <Navigation className="w-3.5 h-3.5 text-blue-600" />
                <span>Google Routes Calculates Real Road-Network Routes</span>
              </div>
              <p className="text-[11px] text-slate-600">
                Google Routes computes actual road turns, distance, travel time, and surfaces official advisories or closed-road warnings.
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
      title: 'Stay Informed via Push & WhatsApp',
      shortDesc: 'Transparent updates via opt-in Browser Web Push and WhatsApp report tracking.',
      tag: 'NOTIFICATIONS',
      tagColor: 'bg-cyan-50 text-cyan-700 border-cyan-200',
      category: 'ingestion',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Citizens receive transparent updates on their report&apos;s review, team assignment, and resolution.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Web Push */}
            <div className="p-4 rounded-xl bg-white border border-slate-200 hover:border-red-400 hover:shadow-xl hover:shadow-red-500/10 hover:-translate-y-1 shadow-xs transition-all duration-200">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-lg bg-red-50 border border-red-200 flex items-center justify-center text-[#dc2626]">
                  <Send className="w-4 h-4" />
                </div>
                <div>
                  <div className="font-bold text-xs text-slate-900">Browser Web Push</div>
                  <div className="text-[10px] text-slate-500 font-mono">Explicit Citizen Opt-In</div>
                </div>
              </div>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                Permission granted → Push Subscription registered → Instant emergency alert broadcast to affected area browsers.
              </p>
            </div>

            {/* WhatsApp Updates */}
            <div className="p-4 rounded-xl bg-white border border-slate-200 hover:border-emerald-400 hover:shadow-xl hover:shadow-emerald-500/10 hover:-translate-y-1 shadow-xs transition-all duration-200">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600">
                  <MessageSquare className="w-4 h-4" />
                </div>
                <div>
                  <div className="font-bold text-xs text-slate-900">WhatsApp Status Tracking</div>
                  <div className="text-[10px] text-slate-500 font-mono">Secondary Tracking Channel</div>
                </div>
              </div>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                Report ID → Status Updates (Reviewed → Team Assigned → Resolved). <em>Note: WhatsApp is an update channel, not an intake channel.</em>
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
      title: 'Verify the Situation',
      shortDesc: 'Multi-source corroboration combining citizen reports, IoT sensors, and field teams.',
      tag: 'OFFICER VERIFICATION',
      tagColor: 'bg-red-50 text-red-700 border-red-200',
      category: 'intelligence',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            In the Emergency Operations Center (EOC), official incident command officers evaluate the complete operational picture
            corroborated from multiple physical and digital sources.
          </p>

          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-xs">
            <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500 mb-2">
              Multi-Source Corroboration Engine
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs font-mono mb-3">
              <div className="p-2.5 rounded-lg bg-white border border-slate-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="block text-sm mb-0.5">👤</span>
                <span className="font-bold text-slate-800">Citizen Report</span>
                <span className="block text-[10px] text-slate-500">Initial observation</span>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-slate-200 hover:border-purple-400 hover:shadow-md hover:shadow-purple-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="block text-sm mb-0.5">📷</span>
                <span className="font-bold text-slate-800">Visual Evidence</span>
                <span className="block text-[10px] text-slate-500">Gemini observations</span>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-slate-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="block text-sm mb-0.5">📡</span>
                <span className="font-bold text-slate-800">IoT Sensors</span>
                <span className="block text-[10px] text-slate-500">Real-time signals</span>
              </div>
              <div className="p-2.5 rounded-lg bg-white border border-slate-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/5 hover:-translate-y-0.5 transition-all duration-200">
                <span className="block text-sm mb-0.5">👷</span>
                <span className="font-bold text-slate-800">Ground Teams</span>
                <span className="block text-[10px] text-slate-500">Field verification</span>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-white border border-red-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/10 transition-all duration-200 text-center font-mono text-xs font-bold text-red-700 flex items-center justify-center gap-2">
              <UserCheck className="w-4 h-4 text-red-600" />
              <span>The officer verifies the situation before operational coordination.</span>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 07: SITUATION INTELLIGENCE
    {
      id: '07',
      stepNum: '07',
      title: 'Understand the Situation',
      shortDesc: 'Mathematical priority scoring and deterministic severity mapping without hallucinations.',
      tag: 'TRIAGE & SEVERITY',
      tagColor: 'bg-amber-50 text-amber-700 border-amber-200',
      category: 'intelligence',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            The system combines verified evidence into an operational picture: incident type, impact radius,
            deterministic severity, priority scoring, confidence, and supporting evidence.
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-2.5">
            <div className="flex items-center justify-between text-xs font-mono p-2 rounded-lg bg-slate-50 border border-slate-100 hover:border-red-300 transition-colors">
              <span className="text-slate-600">Severity Assessment:</span>
              <span className="font-bold text-red-700 bg-red-50 border border-red-200 px-2.5 py-0.5 rounded shadow-2xs">
                DETERMINISTIC & AUDITABLE
              </span>
            </div>
            <div className="flex items-center justify-between text-xs font-mono p-2 rounded-lg bg-slate-50 border border-slate-100 hover:border-purple-300 transition-colors">
              <span className="text-slate-600">AI Extraction Role:</span>
              <span className="font-bold text-purple-700 bg-purple-50 border border-purple-200 px-2.5 py-0.5 rounded shadow-2xs">
                ADVISORY (NON-MUTATING)
              </span>
            </div>
            <div className="flex items-center justify-between text-xs font-mono p-2 rounded-lg bg-slate-50 border border-slate-100 hover:border-slate-300 transition-colors">
              <span className="text-slate-600">Decision Authority:</span>
              <span className="font-bold text-slate-900 bg-slate-100 border border-slate-200 px-2.5 py-0.5 rounded shadow-2xs">
                COMMANDING OFFICER
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
      title: 'Specialized AI Agents Coordinate the Response',
      shortDesc: 'Dependency-aware orchestrator coordinating 9 specialized deterministic agents.',
      tag: '9-AGENT ORCHESTRATOR',
      tagColor: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      category: 'coordination',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            A central orchestrator sequences 9 specialized deterministic AI agents through a dependency-aware workflow.
            Each agent solves one discrete domain problem without hallucination.
          </p>

          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 shadow-xs space-y-3">
            <div className="flex items-center justify-between border-b border-slate-200 pb-2">
              <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-slate-800">
                <Cpu className="w-4 h-4 text-indigo-600" />
                <span>CENTRAL MULTI-AGENT ORCHESTRATOR</span>
              </div>
              <span className="text-[10px] font-mono font-bold bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded">
                9 ACTIVE NODES
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
      title: 'AI Recommends. Human Decides.',
      shortDesc: 'Explainable response plans submitted for officer review with Approve, Modify, or Reject controls.',
      tag: 'HUMAN-IN-THE-LOOP',
      tagColor: 'bg-red-50 text-[#dc2626] border-red-200',
      category: 'coordination',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            AI coordinates and proposes a structured response plan. The Emergency Officer retains complete authority
            to inspect resource allocations, adjust quantities, change assignments, or reject recommendations.
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="font-mono text-xs font-bold text-slate-900">
                ILLUSTRATIVE PLAN REVIEW: EMERGENCY WATER SUPPLY
              </div>
              <span className="text-[10px] font-mono font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded shadow-2xs">
                PENDING APPROVAL
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 hover:border-amber-300 hover:shadow-xs transition-all duration-200">
                <span className="font-mono text-[10px] font-bold text-slate-400 uppercase">Needs Assessment (What is required?)</span>
                <div className="font-bold text-slate-900 text-sm mt-1">100 Liters Clean Water</div>
                <div className="text-[11px] text-slate-500">Estimated for 50 evacuated persons</div>
              </div>

              <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 hover:border-emerald-300 hover:shadow-xs transition-all duration-200">
                <span className="font-mono text-[10px] font-bold text-slate-400 uppercase">AI Recommended Allocation (How to fulfill?)</span>
                <div className="text-slate-800 text-xs font-mono mt-1 space-y-0.5">
                  <div>• Warehouse A → 70 L (Distance: 2.1 km)</div>
                  <div>• Warehouse B → 30 L (Distance: 4.8 km)</div>
                </div>
              </div>
            </div>

            {/* Officer Decision Controls with Hover feedback */}
            <div className="flex items-center gap-2 pt-2">
              <div className="flex-1 py-2.5 px-3 rounded-lg bg-emerald-50 border border-emerald-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/10 text-emerald-800 text-center font-mono text-xs font-bold flex items-center justify-center gap-1.5 transition-all duration-200 cursor-pointer">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                <span>APPROVE PLAN</span>
              </div>
              <div className="flex-1 py-2.5 px-3 rounded-lg bg-amber-50 border border-amber-200 hover:border-amber-400 hover:shadow-md hover:shadow-amber-500/10 text-amber-800 text-center font-mono text-xs font-bold flex items-center justify-center gap-1.5 transition-all duration-200 cursor-pointer">
                <Sliders className="w-3.5 h-3.5 text-amber-600" />
                <span>MODIFY QUANTITIES</span>
              </div>
              <div className="flex-1 py-2.5 px-3 rounded-lg bg-red-50 border border-red-200 hover:border-red-400 hover:shadow-md hover:shadow-red-500/10 text-red-800 text-center font-mono text-xs font-bold flex items-center justify-center gap-1.5 transition-all duration-200 cursor-pointer">
                <AlertTriangle className="w-3.5 h-3.5 text-red-600" />
                <span>REJECT</span>
              </div>
            </div>
          </div>

          <div className="text-xs text-slate-500 bg-slate-50 p-3 rounded-xl border border-slate-200">
            <strong>Key Distinction:</strong> <em>Need Assessment</em> (&ldquo;What is required?&rdquo;) is decoupled from <em>Coordination</em> (&ldquo;How can we fulfill it?&rdquo;).
          </div>
        </div>
      ),
    },

    // STAGE 10: RESOURCE & VOLUNTEER EXECUTION
    {
      id: '10',
      stepNum: '10',
      title: 'Turn the Plan into Action',
      shortDesc: 'Approved tasks dispatched to resource teams and volunteers with explicit acceptance workflows.',
      tag: 'EXECUTION',
      tagColor: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      category: 'execution',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Upon human approval, the plan generates discrete actionable tasks. Field responders and volunteers
            explicitly review and accept assignments prior to execution.
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-500">
              Task Lifecycle & State Machine
            </div>

            <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-mono">
              <span className="px-2.5 py-1 rounded bg-slate-100 border border-slate-200 font-bold">1. CREATED</span>
              <ChevronRight className="w-4 h-4 text-slate-400" />
              <span className="px-2.5 py-1 rounded bg-blue-50 border border-blue-200 text-blue-800 font-bold">2. ASSIGNED</span>
              <ChevronRight className="w-4 h-4 text-slate-400" />
              <span className="px-2.5 py-1 rounded bg-amber-50 border border-amber-200 text-amber-800 font-bold">3. ACCEPTED</span>
              <ChevronRight className="w-4 h-4 text-slate-400" />
              <span className="px-2.5 py-1 rounded bg-purple-50 border border-purple-200 text-purple-800 font-bold">4. IN PROGRESS</span>
              <ChevronRight className="w-4 h-4 text-slate-400" />
              <span className="px-2.5 py-1 rounded bg-emerald-50 border border-emerald-200 text-emerald-800 font-bold">5. COMPLETED</span>
            </div>

            {/* Inventory Model */}
            <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono space-y-1">
              <div className="font-bold text-slate-900">Inventory Ledger Model (Plan creation does NOT consume inventory):</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center pt-1.5">
                <div className="p-2 rounded bg-white border border-slate-200 hover:border-slate-300 transition-colors">
                  <span className="block text-[10px] text-slate-400">TOTAL</span>
                  <strong className="text-slate-800">100 L</strong>
                </div>
                <div className="p-2 rounded bg-white border border-slate-200 hover:border-amber-400 hover:shadow-xs transition-all">
                  <span className="block text-[10px] text-amber-600">RESERVED</span>
                  <strong className="text-amber-700">40 L</strong>
                </div>
                <div className="p-2 rounded bg-white border border-slate-200 hover:border-emerald-400 hover:shadow-xs transition-all">
                  <span className="block text-[10px] text-emerald-600">AVAILABLE</span>
                  <strong className="text-emerald-700">60 L</strong>
                </div>
                <div className="p-2 rounded bg-white border border-slate-200 hover:border-blue-400 hover:shadow-xs transition-all">
                  <span className="block text-[10px] text-blue-600">CONSUMED</span>
                  <strong className="text-blue-700">40 L (Upon Task Done)</strong>
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
      title: 'Monitor What Changes',
      shortDesc: 'Live monitoring of genuine sensor events, field updates, and response changes.',
      tag: 'LIVE MONITORING',
      tagColor: 'bg-blue-50 text-blue-700 border-blue-200',
      category: 'execution',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            The situation never stays static. The system continuously tracks genuine operational changes
            including sensor alerts, volunteer progress, and road condition updates.
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-center">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-blue-400 hover:shadow-xl hover:shadow-blue-500/10 hover:-translate-y-1 transition-all duration-200">
                <Radio className="w-5 h-5 mx-auto mb-1 text-blue-600" />
                <div className="font-mono text-xs font-bold text-slate-800">Sensor Signals</div>
                <div className="text-[10px] text-slate-500">Real-time water & flood alerts</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-emerald-400 hover:shadow-xl hover:shadow-emerald-500/10 hover:-translate-y-1 transition-all duration-200">
                <Users className="w-5 h-5 mx-auto mb-1 text-emerald-600" />
                <div className="font-mono text-xs font-bold text-slate-800">Field Updates</div>
                <div className="text-[10px] text-slate-500">Ground responder status</div>
              </div>
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 hover:border-purple-400 hover:shadow-xl hover:shadow-purple-500/10 hover:-translate-y-1 transition-all duration-200">
                <Activity className="w-5 h-5 mx-auto mb-1 text-purple-600" />
                <div className="font-mono text-xs font-bold text-slate-800">Response Events</div>
                <div className="text-[10px] text-slate-500">Supply deliveries & intake</div>
              </div>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 12: DYNAMIC REPLANNING
    {
      id: '12',
      stepNum: '12',
      title: 'Adapt When Conditions Change',
      shortDesc: 'Automated impact analysis and allocation diffs when roads or warehouses become blocked.',
      tag: 'DYNAMIC REPLANNING',
      tagColor: 'bg-purple-50 text-purple-700 border-purple-200',
      category: 'governance',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            When ground teams or sensors detect that a warehouse route is flooded, Resilience performs automated
            impact analysis and computes a revised allocation diff without changing the underlying need.
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            {/* Interactive simulation toggle */}
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="font-mono text-xs font-bold text-slate-900">
                SCENARIO: WAREHOUSE ACCESS OBSTRUCTION
              </div>
              <div className="flex items-center gap-1 font-mono text-[10px]">
                <button
                  onClick={() => setReplanningSimState('initial')}
                  className={`px-2.5 py-1 rounded transition-all duration-200 cursor-pointer ${replanningSimState === 'initial' ? 'bg-slate-900 text-white font-bold shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                >
                  Original
                </button>
                <button
                  onClick={() => setReplanningSimState('blocked')}
                  className={`px-2.5 py-1 rounded transition-all duration-200 cursor-pointer ${replanningSimState === 'blocked' ? 'bg-red-600 text-white font-bold shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                >
                  Road Blocked
                </button>
                <button
                  onClick={() => setReplanningSimState('revised')}
                  className={`px-2.5 py-1 rounded transition-all duration-200 cursor-pointer ${replanningSimState === 'revised' ? 'bg-purple-600 text-white font-bold shadow-xs' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}
                >
                  Revised Plan Diff
                </button>
              </div>
            </div>

            {replanningSimState === 'initial' && (
              <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono space-y-1">
                <div className="text-slate-500 font-bold">Active Plan (100 L Water Need):</div>
                <div className="text-slate-800">• Warehouse A: 70 L (Dispatched)</div>
                <div className="text-slate-800">• Warehouse B: 30 L (Dispatched)</div>
              </div>
            )}

            {replanningSimState === 'blocked' && (
              <div className="p-3.5 rounded-lg bg-red-50 border border-red-200 text-xs font-mono space-y-1 text-red-900 shadow-xs">
                <div className="font-bold flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-red-600" />
                  <span>ALERT: Warehouse A access road flooded and inaccessible!</span>
                </div>
                <div className="text-xs text-red-700">Impact Analysis Triggered: 70 L allocation invalidated.</div>
              </div>
            )}

            {replanningSimState === 'revised' && (
              <div className="p-3.5 rounded-lg bg-purple-50 border border-purple-200 text-xs font-mono space-y-2 shadow-xs">
                <div className="font-bold text-purple-900">Revised Replanning Diff (Need remains 100 L):</div>
                <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
                  <div className="p-2 rounded bg-red-100 text-red-800 border border-red-200">
                    <span className="block font-bold">REMOVED</span>
                    <span>Warehouse A (70 L)</span>
                  </div>
                  <div className="p-2 rounded bg-slate-100 text-slate-800 border border-slate-200">
                    <span className="block font-bold">UNCHANGED</span>
                    <span>Warehouse B (30 L)</span>
                  </div>
                  <div className="p-2 rounded bg-emerald-100 text-emerald-800 border border-emerald-200">
                    <span className="block font-bold">ADDED</span>
                    <span>Warehouse C (70 L)</span>
                  </div>
                </div>
                <div className="text-[10px] text-purple-800 text-center font-bold">
                  Status: PENDING EMERGENCY OFFICER REVIEW (Never silently auto-applied)
                </div>
              </div>
            )}
          </div>
        </div>
      ),
    },

    // STAGE 13: WHAT-IF SIMULATION
    {
      id: '13',
      stepNum: '13',
      title: 'Plan for What Could Happen (What-If)',
      shortDesc: 'Sandbox simulation engine for capacity stress-testing without touching live operational state.',
      tag: 'WHAT-IF SIMULATION',
      tagColor: 'bg-teal-50 text-teal-700 border-teal-200',
      category: 'governance',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Commanders can test prospective scenarios in a strictly isolated sandbox before making field decisions.
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 hover:border-teal-300 hover:shadow-md hover:shadow-teal-500/5 transition-all duration-200 shadow-xs space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-1.5 font-mono text-xs font-bold text-slate-900">
                <FlaskConical className="w-4 h-4 text-teal-600" />
                <span>WHAT-IF SCENARIO SIMULATOR</span>
              </div>
              <span className="font-mono text-[10px] font-bold bg-teal-100 text-teal-800 border border-teal-300 px-2 py-0.5 rounded shadow-2xs">
                SIMULATION — NOT ACTIVE RESPONSE
              </span>
            </div>

            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs font-mono text-slate-700 space-y-1">
              <div className="font-bold text-slate-900">Scenario: &ldquo;What if Primary Shelter S1 becomes unavailable?&rdquo;</div>
              <p className="text-[11px] text-slate-500">
                Simulation calculates backup shelter capacities and route adjustments without modifying live inventory or database records.
              </p>
            </div>
          </div>
        </div>
      ),
    },

    // STAGE 14: RESOLUTION & AUDIT TRAIL
    {
      id: '14',
      stepNum: '14',
      title: 'Resolve & Learn',
      shortDesc: 'End-to-end immutability with verified closure metrics and post-incident analytics.',
      tag: 'GOVERNANCE & AUDIT',
      tagColor: 'bg-slate-100 text-slate-800 border-slate-300',
      category: 'governance',
      content: (
        <div className="space-y-4">
          <p className="text-xs sm:text-sm text-slate-600 leading-relaxed">
            Every citizen report, officer decision, AI recommendation, resource dispatch, and volunteer action
            is recorded in an immutable audit trail for post-incident analysis and governance.
          </p>

          <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-center text-xs font-mono">
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-emerald-400 hover:shadow-md hover:shadow-emerald-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <FileCheck className="w-4 h-4 mx-auto mb-1 text-emerald-600" />
                <span className="font-bold text-slate-800">Field Complete</span>
                <span className="block text-[10px] text-slate-500">All tasks verified</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-blue-400 hover:shadow-md hover:shadow-blue-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <Boxes className="w-4 h-4 mx-auto mb-1 text-blue-600" />
                <span className="font-bold text-slate-800">Ledger Closed</span>
                <span className="block text-[10px] text-slate-500">Actuals matched</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-purple-400 hover:shadow-md hover:shadow-purple-500/10 hover:-translate-y-0.5 transition-all duration-200">
                <Lock className="w-4 h-4 mx-auto mb-1 text-purple-600" />
                <span className="font-bold text-slate-800">Audit Trail</span>
                <span className="block text-[10px] text-slate-500">Immutable history</span>
              </div>
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 hover:border-slate-400 hover:shadow-md hover:shadow-slate-300/40 hover:-translate-y-0.5 transition-all duration-200">
                <Activity className="w-4 h-4 mx-auto mb-1 text-slate-700" />
                <span className="font-bold text-slate-800">EOC Analytics</span>
                <span className="block text-[10px] text-slate-500">After-action review</span>
              </div>
            </div>

            <div className="text-center py-2.5 px-3 rounded-lg bg-slate-50 border border-slate-200 font-mono text-xs text-slate-700">
              AUDIT CERTIFIED • ZERO UNEXPLAINED ACTIONS • 100% TRACEABLE
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
          <span>END-TO-END EMERGENCY RESPONSE ARCHITECTURE</span>
        </div>
        <h2 className="text-2xl sm:text-4xl font-black uppercase font-sans tracking-tight text-slate-900 leading-tight">
          How Resilience Works
        </h2>
        <p className="text-sm sm:text-base text-slate-600 mt-2 max-w-2xl leading-relaxed font-sans">
          From the first citizen report to coordinated emergency response. Resilience connects citizen observations,
          geotagged evidence, AI-assisted situation understanding, real-world resources, field teams, and human
          decision-makers into one auditable response workflow.
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
              Core Product Principle: AI is Not the Final Authority
            </div>
            <div className="text-xs text-slate-700 mt-0.5">
              AI analyzes and recommends. Human emergency officers verify and approve. Field teams execute. The system monitors and adapts.
            </div>
          </div>
        </div>

        <div className="font-mono text-[10px] text-slate-600 uppercase tracking-widest px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-300 shrink-0 font-bold">
          HUMAN-IN-THE-LOOP ACTIVE
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
                    STAGE {activeStage.stepNum} OF 14
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
                <span>← Previous Stage</span>
              </button>

              <div className="text-[11px] font-mono text-slate-400">
                Step {parseInt(activeStage.stepNum, 10)} / 14
              </div>

              <button
                disabled={activeStageId === '14'}
                onClick={() => {
                  const currentIdx = stages.findIndex((s) => s.id === activeStageId);
                  if (currentIdx < stages.length - 1) setActiveStageId(stages[currentIdx + 1].id);
                }}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-[#dc2626] text-white text-xs font-sans font-bold shadow-xs hover:shadow-md hover:shadow-red-500/20 disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
              >
                <span>Next Stage</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
