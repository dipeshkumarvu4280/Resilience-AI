import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { EmergencyEmblem } from '../components/common/EmergencyEmblem';
import { TacticalBackground } from '../components/layout/TacticalBackground';
import { LiveMapPreview } from '../components/common/LiveMapPreview';
import { HumanInTheLoopPipeline } from '../components/common/HumanInTheLoopPipeline';
import { SystemStatusPanel } from '../components/common/SystemStatusPanel';
import {
  Shield,
  Boxes,
  Users,
  Lock,
  ArrowRight,
  AlertTriangle,
  Radio,
  Siren,
  ExternalLink,
  Check,
  Activity,
  Menu,
  X,
} from 'lucide-react';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const [showPhase1Modal, setShowPhase1Modal] = useState(false);
  const [activeNav, setActiveNav] = useState<'home' | 'about' | 'how-it-works' | 'contact'>('home');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const roleCards = [
    {
      id: 'officer',
      title: 'EMERGENCY OFFICER',
      badge: 'COMMAND',
      desc: 'Incident command & operations management.',
      capabilities: [
        'Situation Assessment',
        'Response Coordination',
        'Field Operations',
      ],
      route: '/login/officer',
      icon: Shield,
      accentColor: 'red',
      iconContainer: 'bg-red-50 text-[#dc2626] border-red-200',
      badgeClass: 'bg-red-50 text-red-700 border-red-200',
      checkColor: 'text-red-600',
      hoverBorder: 'hover:border-red-300',
      ctaText: 'Login to Command Center',
      ctaClass: 'bg-slate-900 hover:bg-[#dc2626] text-white',
    },
    {
      id: 'resource-manager',
      title: 'RESOURCE MANAGER',
      badge: 'LOGISTICS',
      desc: 'Resource allocation and supply chain coordination.',
      capabilities: [
        'Inventory Management',
        'Vehicle & Equipment',
        'Dispatch Operations',
      ],
      route: '/login/resource-manager',
      icon: Boxes,
      accentColor: 'green',
      iconContainer: 'bg-emerald-50 text-emerald-600 border-emerald-200',
      badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      checkColor: 'text-emerald-600',
      hoverBorder: 'hover:border-emerald-300',
      ctaText: 'Login to Resource Operations',
      ctaClass: 'bg-slate-900 hover:bg-emerald-700 text-white',
    },
    {
      id: 'volunteer',
      title: 'VOLUNTEER',
      badge: 'COMMUNITY',
      desc: 'Be the change. Help your community.',
      capabilities: [
        'Skills & Availability',
        'Community Support',
        'Response Participation',
      ],
      route: '/login/volunteer',
      registerRoute: '/register/volunteer',
      icon: Users,
      accentColor: 'blue',
      iconContainer: 'bg-blue-50 text-blue-600 border-blue-200',
      badgeClass: 'bg-blue-50 text-blue-700 border-blue-200',
      checkColor: 'text-blue-600',
      hoverBorder: 'hover:border-blue-300',
      ctaText: 'Login to Volunteer Portal',
      ctaClass: 'bg-slate-900 hover:bg-blue-700 text-white',
    },
    {
      id: 'admin',
      title: 'ADMIN',
      badge: 'SYSTEM',
      desc: 'Platform management and security control.',
      capabilities: [
        'User Management',
        'System Configuration',
        'Audit & Compliance',
      ],
      route: '/login/admin',
      icon: Lock,
      accentColor: 'purple',
      iconContainer: 'bg-purple-50 text-purple-600 border-purple-200',
      badgeClass: 'bg-purple-50 text-purple-700 border-purple-200',
      checkColor: 'text-purple-600',
      hoverBorder: 'hover:border-purple-300',
      ctaText: 'Login to System Admin',
      ctaClass: 'bg-slate-900 hover:bg-purple-700 text-white',
    },
  ];

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    el?.scrollIntoView({ behavior: 'smooth' });
    setMobileMenuOpen(false);
  };

  return (
    <div className="relative min-h-screen text-slate-900 selection:bg-red-100 selection:text-red-900 overflow-x-hidden">
      <TacticalBackground />

      {/* ========================================================
          1. HEADER — CLEAN WHITE/LIGHT HEADER
          ======================================================== */}
      <header className="sticky top-0 z-40 w-full px-3 sm:px-8 py-2.5 sm:py-3.5 border-b border-slate-200/80 bg-white/95 backdrop-blur-md flex items-center justify-between shadow-xs">
        {/* Left: RESILIENCE Logo */}
        <div className="flex items-center gap-2">
          <EmergencyEmblem size="sm" theme="light" />
        </div>

        {/* Center: Desktop Nav */}
        <nav className="hidden md:flex items-center gap-8 text-xs font-sans font-semibold text-slate-600">
          <button
            onClick={() => {
              setActiveNav('home');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
            className={`transition-colors pb-1 cursor-pointer ${
              activeNav === 'home'
                ? 'text-slate-900 border-b-2 border-[#dc2626]'
                : 'hover:text-slate-900'
            }`}
          >
            Home
          </button>
          <button
            onClick={() => {
              setActiveNav('about');
              scrollToSection('paradigm');
            }}
            className={`transition-colors pb-1 cursor-pointer ${
              activeNav === 'about'
                ? 'text-slate-900 border-b-2 border-[#dc2626]'
                : 'hover:text-slate-900'
            }`}
          >
            About
          </button>
          <button
            onClick={() => {
              setActiveNav('how-it-works');
              scrollToSection('paradigm');
            }}
            className={`transition-colors pb-1 cursor-pointer ${
              activeNav === 'how-it-works'
                ? 'text-slate-900 border-b-2 border-[#dc2626]'
                : 'hover:text-slate-900'
            }`}
          >
            How It Works
          </button>
          <button
            onClick={() => {
              setActiveNav('contact');
              scrollToSection('operations');
            }}
            className={`transition-colors pb-1 cursor-pointer ${
              activeNav === 'contact'
                ? 'text-slate-900 border-b-2 border-[#dc2626]'
                : 'hover:text-slate-900'
            }`}
          >
            Contact
          </button>
        </nav>

        {/* Right: Actions + Mobile Menu Toggle */}
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            onClick={() => scrollToSection('operations')}
            className="hidden sm:inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white hover:bg-slate-50 text-slate-800 border border-slate-300 font-sans text-xs font-semibold transition-all shadow-xs cursor-pointer"
          >
            <span>Enter Operations</span>
            <ExternalLink className="w-3 h-3 text-slate-500" />
          </button>

          <button
            onClick={() => navigate('/report-emergency')}
            className="inline-flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs font-bold transition-all shadow-xs hover:shadow-md hover:-translate-y-0.5 min-h-[40px] cursor-pointer touch-manipulation"
          >
            <Siren className="w-3.5 h-3.5" />
            <span className="whitespace-nowrap">Report Emergency</span>
          </button>

          {/* Mobile Hamburger Button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 rounded-xl text-slate-700 hover:text-slate-900 hover:bg-slate-100 border border-slate-200 transition-colors cursor-pointer min-h-[40px] min-w-[40px] flex items-center justify-center touch-manipulation"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </header>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 md:hidden flex flex-col bg-white animate-in slide-in-from-top duration-200">
          <div className="flex items-center justify-between p-4 border-b border-slate-200">
            <EmergencyEmblem size="sm" theme="light" />
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="p-2 rounded-xl text-slate-500 hover:bg-slate-100 cursor-pointer min-h-[44px] min-w-[44px] flex items-center justify-center"
              aria-label="Close menu"
            >
              <X className="w-6 h-6" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            <nav className="space-y-3 text-base font-bold text-slate-800 font-sans">
              <button
                onClick={() => {
                  setActiveNav('home');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                  setMobileMenuOpen(false);
                }}
                className="w-full text-left py-2.5 px-3 rounded-xl hover:bg-slate-50 flex items-center justify-between"
              >
                <span>Home</span>
                <ArrowRight className="w-4 h-4 text-slate-400" />
              </button>
              <button
                onClick={() => scrollToSection('paradigm')}
                className="w-full text-left py-2.5 px-3 rounded-xl hover:bg-slate-50 flex items-center justify-between"
              >
                <span>About Platform</span>
                <ArrowRight className="w-4 h-4 text-slate-400" />
              </button>
              <button
                onClick={() => scrollToSection('paradigm')}
                className="w-full text-left py-2.5 px-3 rounded-xl hover:bg-slate-50 flex items-center justify-between"
              >
                <span>How It Works</span>
                <ArrowRight className="w-4 h-4 text-slate-400" />
              </button>
              <button
                onClick={() => scrollToSection('operations')}
                className="w-full text-left py-2.5 px-3 rounded-xl hover:bg-slate-50 flex items-center justify-between"
              >
                <span>Operational Portals</span>
                <ArrowRight className="w-4 h-4 text-slate-400" />
              </button>
            </nav>

            <div className="pt-4 border-t border-slate-200 space-y-3">
              <div className="text-xs font-mono font-bold uppercase tracking-wider text-slate-400">
                Direct Operational Portals
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs font-bold">
                <button
                  onClick={() => { setMobileMenuOpen(false); navigate('/login/officer'); }}
                  className="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-center"
                >
                  Officer Command
                </button>
                <button
                  onClick={() => { setMobileMenuOpen(false); navigate('/login/resource-manager'); }}
                  className="p-3 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 text-center"
                >
                  Resource Manager
                </button>
                <button
                  onClick={() => { setMobileMenuOpen(false); navigate('/login/volunteer'); }}
                  className="p-3 rounded-xl bg-blue-50 text-blue-800 border border-blue-200 text-center"
                >
                  Volunteer Portal
                </button>
                <button
                  onClick={() => { setMobileMenuOpen(false); navigate('/login/admin'); }}
                  className="p-3 rounded-xl bg-purple-50 text-purple-800 border border-purple-200 text-center"
                >
                  System Admin
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================
          2. HERO SECTION — TWO COLUMN COMPOSITION
          ======================================================== */}
      <main className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 sm:pt-12 pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center mb-12 sm:mb-16">
          
          {/* LEFT SIDE: HERO CONTENT */}
          <div className="lg:col-span-6 text-left space-y-5 sm:space-y-6">
            {/* Small Green Status Badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 font-mono text-[10px] sm:text-[11px] font-bold tracking-wider shadow-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>AI-POWERED EMERGENCY COORDINATION</span>
            </div>

            {/* Large Headline */}
            <h1 className="text-3xl xs:text-4xl sm:text-5xl lg:text-[56px] font-black tracking-tight uppercase font-sans text-slate-900 leading-[1.08] sm:leading-[1.06]">
              STRONGER<br />
              COMMUNITIES.<br />
              <span className="text-[#dc2626]">
                FASTER RESPONSE.
              </span><br />
              SAFER TOMORROW.
            </h1>

            {/* Hero Description */}
            <p className="text-xs sm:text-base text-slate-600 max-w-lg leading-relaxed font-sans font-normal">
              An AI-powered emergency coordination platform that transforms community reports
              and real-time situation data into explainable, human-approved response plans.
            </p>

            {/* Hero Buttons */}
            <div className="pt-2">
              <div className="flex flex-wrap items-center gap-3">
                {/* Primary CTA */}
                <button
                  onClick={() => navigate('/report-emergency')}
                  className="inline-flex items-center justify-center gap-2 px-5 sm:px-6 py-3 sm:py-3.5 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs sm:text-sm font-bold tracking-wide shadow-xs hover:shadow-lg transition-all hover:-translate-y-0.5 min-h-[44px] touch-manipulation cursor-pointer"
                >
                  <Siren className="w-4 h-4" />
                  <span>REPORT EMERGENCY</span>
                </button>

                {/* Secondary CTA */}
                <button
                  onClick={() => scrollToSection('operations')}
                  className="inline-flex items-center justify-center gap-2 px-4 sm:px-5 py-3 sm:py-3.5 rounded-xl bg-white hover:bg-slate-50 text-slate-800 font-sans text-xs sm:text-sm font-bold tracking-wide border border-slate-300 shadow-xs transition-all hover:-translate-y-0.5 min-h-[44px] touch-manipulation cursor-pointer"
                >
                  <span>ENTER OPERATIONS</span>
                  <ArrowRight className="w-4 h-4 text-slate-500" />
                </button>
              </div>

              {/* Sub-label under emergency CTA */}
              <div className="text-[11px] text-slate-400 font-medium mt-2 pl-1">
                (Live • No Account Required)
              </div>
            </div>
          </div>

          {/* RIGHT SIDE: LIVE SITUATIONAL MAP PANEL */}
          <div className="lg:col-span-6 w-full">
            <LiveMapPreview />
          </div>
        </div>

        {/* ========================================================
            3. FOUR OPERATION CARDS (IMMEDIATELY BELOW HERO/MAP)
            ======================================================== */}
        <section id="operations" className="mb-16">
          <div className="text-left mb-6">
            <div className="font-mono text-[11px] uppercase text-[#dc2626] font-bold tracking-wider mb-1">
              AUTHORIZED ACCESS PORTALS
            </div>
            <h2 className="text-2xl sm:text-3xl font-black uppercase font-sans tracking-tight text-slate-900">
              Operational Command Centers
            </h2>
            <p className="text-xs sm:text-sm text-slate-600 mt-1 max-w-xl">
              Select your role console to authenticate with verified role credentials and manage emergency response pipelines.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
            {roleCards.map((card) => {
              const RoleIcon = card.icon;
              return (
                <div
                  key={card.id}
                  className={`group relative flex flex-col justify-between p-6 rounded-2xl bg-white border border-slate-200/90 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all duration-200 ${card.hoverBorder}`}
                >
                  <div>
                    {/* Top: Icon container + Badge */}
                    <div className="flex items-center justify-between mb-4">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${card.iconContainer} transition-transform group-hover:scale-105`}>
                        <RoleIcon className="w-5 h-5" />
                      </div>
                      <span className={`font-mono text-[10px] uppercase font-bold tracking-wider px-2.5 py-0.5 rounded-md border ${card.badgeClass}`}>
                        {card.badge}
                      </span>
                    </div>

                    {/* Card Title & Description */}
                    <h3 className="text-base font-bold font-sans tracking-tight text-slate-900 uppercase mb-1.5">
                      {card.title}
                    </h3>
                    <p className="text-xs text-slate-600 leading-relaxed mb-4">
                      {card.desc}
                    </p>

                    {/* Capabilities Checklist */}
                    <div className="pt-3 border-t border-slate-100 mb-6 space-y-2">
                      <div className="text-[10px] font-mono uppercase text-slate-400 font-bold tracking-wider mb-1">
                        Capabilities:
                      </div>
                      {card.capabilities.map((cap) => (
                        <div key={cap} className="flex items-center gap-2 text-xs text-slate-700 font-medium">
                          <Check className={`w-3.5 h-3.5 flex-shrink-0 ${card.checkColor}`} strokeWidth={2.5} />
                          <span>{cap}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Card Bottom CTA */}
                  <div className="space-y-2 pt-2">
                    <button
                      onClick={() => navigate(card.route)}
                      className={`w-full inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl font-sans text-xs font-bold transition-all shadow-sm ${card.ctaClass}`}
                    >
                      <span>{card.ctaText}</span>
                      <ArrowRight className="w-3.5 h-3.5 opacity-80" />
                    </button>

                    {card.registerRoute && (
                      <button
                        onClick={() => navigate(card.registerRoute)}
                        className="w-full inline-flex items-center justify-center py-2 px-3 rounded-xl bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 font-sans text-xs font-semibold transition-all"
                      >
                        Register as Volunteer
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* ========================================================
            4. WORKFLOW & PARADIGM SECTION
            ======================================================== */}
        <section id="paradigm" className="mb-16 p-6 sm:p-8 rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-4 border-b border-slate-100 mb-6 gap-2">
            <div>
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-emerald-600" />
                <h3 className="font-sans text-sm sm:text-base font-extrabold tracking-wider uppercase text-slate-900">
                  Resilience Response Paradigm
                </h3>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Full-lifecycle emergency coordination: from community alerts to dynamic re-planning.
              </p>
            </div>
            <div className="font-mono text-[10px] text-slate-600 font-semibold px-3 py-1 rounded-md bg-slate-100 border border-slate-200">
              COMMUNITY ➔ AI ➔ HUMAN DECISION ➔ RE-PLANNING
            </div>
          </div>

          <HumanInTheLoopPipeline variant="workflow" />
        </section>

        {/* ========================================================
            5. SYSTEM STATUS & TELEMETRY
            ======================================================== */}
        <section className="mb-12">
          <div className="font-mono text-[11px] uppercase text-slate-500 font-bold tracking-wider mb-2">
            PLATFORM HEALTH & TELEMETRY
          </div>
          <SystemStatusPanel />
        </section>

        {/* ========================================================
            6. BOTTOM STATUS STRIP (MATCH REFERENCE)
            ======================================================== */}
        <div className="p-4 sm:p-5 rounded-2xl bg-white border border-slate-200/90 shadow-sm flex flex-col md:flex-row items-center justify-between gap-4">
          {/* Left: System Status */}
          <div className="flex items-center gap-3 font-sans text-xs">
            <div className="flex items-center gap-2 font-bold text-emerald-700 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200 font-mono text-[11px]">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>SYSTEM OPERATIONAL</span>
            </div>
            <div className="hidden sm:flex items-center gap-2 text-slate-500 text-xs">
              <span className="font-medium">Secure</span>
              <span>•</span>
              <span className="font-medium">Scalable</span>
              <span>•</span>
              <span className="font-medium">Community First</span>
            </div>
          </div>

          {/* Right: Heartbeat Quote */}
          <div className="flex items-center gap-2.5 text-slate-600 text-xs sm:text-sm italic font-sans text-center md:text-right">
            <Activity className="w-4 h-4 text-red-500 flex-shrink-0 animate-pulse" />
            <span>&ldquo;Resilience is not just a platform, it&apos;s a community.&rdquo;</span>
          </div>
        </div>
      </main>

      {/* Phase 1 Reporting Planned Modal */}
      {showPhase1Modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="max-w-md w-full p-6 sm:p-8 rounded-2xl border border-slate-200 bg-white text-center shadow-2xl">
            <div className="w-12 h-12 rounded-full bg-red-50 border border-red-200 flex items-center justify-center mx-auto mb-4 text-[#dc2626]">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <div className="font-mono text-xs text-[#dc2626] uppercase font-bold tracking-widest mb-1">
              Phase 1 Milestone Notice
            </div>
            <h3 className="text-lg font-bold text-slate-900 mb-2">
              Citizen Emergency Reporting
            </h3>
            <p className="text-xs text-slate-600 leading-relaxed mb-6">
              Citizen multi-channel reporting (Web, Offline PWA, Voice & WhatsApp mesh) is scheduled for 
              <strong className="text-slate-900"> Phase 1</strong>. Phase 0 establishes the security, RBAC, and operational command foundation.
            </p>
            <div className="flex justify-center">
              <button
                onClick={() => setShowPhase1Modal(false)}
                className="px-6 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-sans text-xs font-bold transition-all shadow-sm"
              >
                Acknowledge & Return
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="relative z-10 border-t border-slate-200 bg-slate-50 py-8 text-center text-xs font-mono text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            RESILIENCE © 2026 • AI-Powered Emergency Response Platform
          </div>
          <div className="flex items-center gap-4 text-[11px]">
            <span>ENTERPRISE COMMAND PLATFORM</span>
            <span>•</span>
            <span className="text-slate-800 font-semibold">ZERO DUMMY DATA CERTIFIED</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

