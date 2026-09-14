import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { EmergencyEmblem } from '../components/common/EmergencyEmblem';
import { TacticalBackground } from '../components/layout/TacticalBackground';
import { LiveMapPreview } from '../components/common/LiveMapPreview';
import { HowItWorksInteractive } from '../components/landing/HowItWorksInteractive';
import { LanguageSelector } from '../components/common/LanguageSelector';
import { useLanguage } from '../context/LanguageContext';
import {
  Shield,
  Boxes,
  Users,
  Lock,
  ArrowRight,
  Siren,
  ExternalLink,
  Check,
  Activity,
  Menu,
  X,
  Sparkles,
  MapPin,
  Cpu,
  UserCheck,
  FlaskConical,
  Bell,
  Navigation,
  PhoneCall,
  Phone,
} from 'lucide-react';

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [activeNav, setActiveNav] = useState<'home' | 'about' | 'how-it-works' | 'operations' | 'contact'>('home');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const roleCards = [
    {
      id: 'officer',
      titleKey: 'roles.officerTitle',
      defaultTitle: 'EMERGENCY OFFICER',
      badgeKey: 'roles.officerBadge',
      defaultBadge: 'INCIDENT COMMAND',
      descKey: 'roles.officerDesc',
      defaultDesc: 'Verify corroborated incidents, inspect AI-generated response plans, and authorize field actions.',
      capabilities: [
        { key: 'roles.officerC1', text: 'Multi-Source Corroboration' },
        { key: 'roles.officerC2', text: 'Human-in-the-Loop Plan Approval' },
        { key: 'roles.officerC3', text: 'Dynamic Replanning Triage' },
      ],
      route: '/login/officer',
      icon: Shield,
      accentColor: 'red',
      iconContainer: 'bg-red-50 text-[#dc2626] border-red-200 group-hover:bg-red-100/90 group-hover:border-red-400 group-hover:text-red-700',
      badgeClass: 'bg-red-50 text-red-700 border-red-200 group-hover:border-red-300 group-hover:bg-red-100/60',
      checkColor: 'text-red-600',
      hoverBorder: 'hover:border-red-500 hover:shadow-xl hover:shadow-red-500/10 focus-visible:border-red-500 focus-visible:ring-2 focus-visible:ring-red-500/20',
      ctaKey: 'roles.officerBtn',
      defaultCta: 'Login to Command Center',
      ctaClass: 'bg-slate-900 hover:bg-[#dc2626] text-white shadow-xs hover:shadow-md hover:shadow-red-500/20',
    },
    {
      id: 'resource-manager',
      titleKey: 'roles.rmTitle',
      defaultTitle: 'RESOURCE MANAGER',
      badgeKey: 'roles.rmBadge',
      defaultBadge: 'LOGISTICS & ASSETS',
      descKey: 'roles.rmDesc',
      defaultDesc: 'Track supply depots, verify real inventory balances, and dispatch supplies to approved emergency tasks.',
      capabilities: [
        { key: 'roles.rmC1', text: 'Real Inventory Ledger' },
        { key: 'roles.rmC2', text: 'Vehicle & Depot Tracking' },
        { key: 'roles.rmC3', text: 'Task Dispatch Operations' },
      ],
      route: '/login/resource-manager',
      icon: Boxes,
      accentColor: 'green',
      iconContainer: 'bg-emerald-50 text-emerald-600 border-emerald-200 group-hover:bg-emerald-100/90 group-hover:border-emerald-400 group-hover:text-emerald-700',
      badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200 group-hover:border-emerald-300 group-hover:bg-emerald-100/60',
      checkColor: 'text-emerald-600',
      hoverBorder: 'hover:border-emerald-500 hover:shadow-xl hover:shadow-emerald-500/10 focus-visible:border-emerald-500 focus-visible:ring-2 focus-visible:ring-emerald-500/20',
      ctaKey: 'roles.rmBtn',
      defaultCta: 'Login to Resource Operations',
      ctaClass: 'bg-slate-900 hover:bg-emerald-700 text-white shadow-xs hover:shadow-md hover:shadow-emerald-500/20',
    },
    {
      id: 'volunteer',
      titleKey: 'roles.volTitle',
      defaultTitle: 'VOLUNTEER RESPONDER',
      badgeKey: 'roles.volBadge',
      defaultBadge: 'COMMUNITY NETWORK',
      descKey: 'roles.volDesc',
      defaultDesc: 'Join local response teams, review proximity-based missions, and accept verified tasks in your zone.',
      capabilities: [
        { key: 'roles.volC1', text: 'Skill & Zone Registration' },
        { key: 'roles.volC2', text: 'Task Acceptance Workflow' },
        { key: 'roles.volC3', text: 'Field Execution & Updates' },
      ],
      route: '/login/volunteer',
      registerRoute: '/register/volunteer',
      icon: Users,
      accentColor: 'blue',
      iconContainer: 'bg-blue-50 text-blue-600 border-blue-200 group-hover:bg-blue-100/90 group-hover:border-blue-400 group-hover:text-blue-700',
      badgeClass: 'bg-blue-50 text-blue-700 border-blue-200 group-hover:border-blue-300 group-hover:bg-blue-100/60',
      checkColor: 'text-blue-600',
      hoverBorder: 'hover:border-blue-500 hover:shadow-xl hover:shadow-blue-500/10 focus-visible:border-blue-500 focus-visible:ring-2 focus-visible:ring-blue-500/20',
      ctaKey: 'roles.volBtn',
      defaultCta: 'Login to Volunteer Portal',
      registerKey: 'roles.volRegisterBtn',
      defaultRegister: 'Register as Volunteer',
      ctaClass: 'bg-slate-900 hover:bg-blue-700 text-white shadow-xs hover:shadow-md hover:shadow-blue-500/20',
    },
    {
      id: 'admin',
      titleKey: 'roles.adminTitle',
      defaultTitle: 'SYSTEM ADMIN',
      badgeKey: 'roles.adminBadge',
      defaultBadge: 'GOVERNANCE & AUDIT',
      descKey: 'roles.adminDesc',
      defaultDesc: 'Platform governance, role-based access control, security policies, and immutable audit inspection.',
      capabilities: [
        { key: 'roles.adminC1', text: 'RBAC & User Governance' },
        { key: 'roles.adminC2', text: 'Immutable Audit Trail Review' },
        { key: 'roles.adminC3', text: 'System Health & Config' },
      ],
      route: '/login/admin',
      icon: Lock,
      accentColor: 'purple',
      iconContainer: 'bg-purple-50 text-purple-600 border-purple-200 group-hover:bg-purple-100/90 group-hover:border-purple-400 group-hover:text-purple-700',
      badgeClass: 'bg-purple-50 text-purple-700 border-purple-200 group-hover:border-purple-300 group-hover:bg-purple-100/60',
      checkColor: 'text-purple-600',
      hoverBorder: 'hover:border-purple-500 hover:shadow-xl hover:shadow-purple-500/10 focus-visible:border-purple-500 focus-visible:ring-2 focus-visible:ring-purple-500/20',
      ctaKey: 'roles.adminBtn',
      defaultCta: 'Login to System Admin',
      ctaClass: 'bg-slate-900 hover:bg-purple-700 text-white shadow-xs hover:shadow-md hover:shadow-purple-500/20',
    },
  ];

  const coreUSPs = [
    {
      titleKey: 'usp.c1Title',
      defaultTitle: 'Multimodal Evidence & Gemini Vision',
      descKey: 'usp.c1Desc',
      defaultDesc: 'Citizens capture real-world photo evidence bound to GPS coordinates. Gemini Vision extracts structured hazard observations for advisory officer review.',
      icon: Sparkles,
      iconColor: 'text-purple-600 bg-purple-50 border-purple-200 group-hover:bg-purple-100 group-hover:border-purple-400',
      hoverBorder: 'hover:border-purple-400 hover:shadow-xl hover:shadow-purple-500/10',
    },
    {
      titleKey: 'usp.c2Title',
      defaultTitle: 'Real Google Places & Road Routing',
      descKey: 'usp.c2Desc',
      defaultDesc: 'Discovers verified physical hospitals and shelters via Google Places API and calculates true road-network routes with turn-by-turn geometry and ETA.',
      icon: Navigation,
      iconColor: 'text-blue-600 bg-blue-50 border-blue-200 group-hover:bg-blue-100 group-hover:border-blue-400',
      hoverBorder: 'hover:border-blue-400 hover:shadow-xl hover:shadow-blue-500/10',
    },
    {
      titleKey: 'usp.c3Title',
      defaultTitle: '9-Agent Dependency-Aware Orchestrator',
      descKey: 'usp.c3Desc',
      defaultDesc: 'Nine specialized deterministic agents coordinate priority, needs, resources, routes, shelters, healthcare, volunteers, and conflicts simultaneously.',
      icon: Cpu,
      iconColor: 'text-indigo-600 bg-indigo-50 border-indigo-200 group-hover:bg-indigo-100 group-hover:border-indigo-400',
      hoverBorder: 'hover:border-indigo-400 hover:shadow-xl hover:shadow-indigo-500/10',
    },
    {
      titleKey: 'usp.c4Title',
      defaultTitle: 'Human Authority & Explainable Plans',
      descKey: 'usp.c4Desc',
      defaultDesc: 'AI recommends; human officers decide. All response allocations require explicit officer approval or modification before field tasks are generated.',
      icon: UserCheck,
      iconColor: 'text-red-600 bg-red-50 border-red-200 group-hover:bg-red-100 group-hover:border-red-400',
      hoverBorder: 'hover:border-red-400 hover:shadow-xl hover:shadow-red-500/10',
    },
    {
      titleKey: 'usp.c5Title',
      defaultTitle: 'Dynamic Replanning & What-If Simulations',
      descKey: 'usp.c5Desc',
      defaultDesc: 'Automatically computes allocation diffs when roads or depots become blocked, and allows isolated what-if scenario testing without mutating live databases.',
      icon: FlaskConical,
      iconColor: 'text-teal-600 bg-teal-50 border-teal-200 group-hover:bg-teal-100 group-hover:border-teal-400',
      hoverBorder: 'hover:border-teal-400 hover:shadow-xl hover:shadow-teal-500/10',
    },
    {
      titleKey: 'usp.c6Title',
      defaultTitle: 'Multi-Channel Alerting & Tracking',
      descKey: 'usp.c6Desc',
      defaultDesc: 'Instant browser Web Push for affected community members and transparent status updates via WhatsApp by incident report ID.',
      icon: Bell,
      iconColor: 'text-emerald-600 bg-emerald-50 border-emerald-200 group-hover:bg-emerald-100 group-hover:border-emerald-400',
      hoverBorder: 'hover:border-emerald-400 hover:shadow-xl hover:shadow-emerald-500/10',
    },
  ];

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
    setMobileMenuOpen(false);
  };

  return (
    <div className="relative min-h-screen text-slate-900 selection:bg-red-100 selection:text-red-900 overflow-x-hidden">
      <TacticalBackground />

      {/* ========================================================
          1. HEADER — CLEAN STICKY LIGHT HEADER
          ======================================================== */}
      <header className="sticky top-0 z-40 w-full px-3 sm:px-8 py-2.5 sm:py-3.5 border-b border-slate-300 bg-white/95 backdrop-blur-md flex items-center justify-between shadow-xs">
        {/* Left: RESILIENCE Logo */}
        <div className="flex items-center gap-2">
          <EmergencyEmblem size="sm" theme="light" />
        </div>

        {/* Center: Desktop Nav */}
        <nav className="hidden md:flex items-center gap-1.5 lg:gap-2 text-xs font-sans">
          <button
            onClick={() => {
              setActiveNav('home');
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}
            className={`px-3 py-1.5 rounded-xl transition-all duration-200 ease-out cursor-pointer font-semibold border ${
              activeNav === 'home'
                ? 'bg-red-50 text-[#dc2626] font-bold border-red-200 shadow-2xs'
                : 'text-slate-700 border-transparent hover:text-red-700 hover:bg-red-50/60 hover:border-red-200/80 hover:-translate-y-0.5'
            } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/20 focus-visible:border-red-400 focus-visible:bg-red-50/60 focus-visible:text-red-700`}
          >
            {t('nav.home', 'Home')}
          </button>
          <button
            onClick={() => {
              setActiveNav('about');
              scrollToSection('about');
            }}
            className={`px-3 py-1.5 rounded-xl transition-all duration-200 ease-out cursor-pointer font-semibold border ${
              activeNav === 'about'
                ? 'bg-red-50 text-[#dc2626] font-bold border-red-200 shadow-2xs'
                : 'text-slate-700 border-transparent hover:text-red-700 hover:bg-red-50/60 hover:border-red-200/80 hover:-translate-y-0.5'
            } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/20 focus-visible:border-red-400 focus-visible:bg-red-50/60 focus-visible:text-red-700`}
          >
            {t('nav.about', 'About')}
          </button>
          <button
            onClick={() => {
              setActiveNav('how-it-works');
              scrollToSection('how-it-works');
            }}
            className={`px-3 py-1.5 rounded-xl transition-all duration-200 ease-out cursor-pointer font-semibold border ${
              activeNav === 'how-it-works'
                ? 'bg-red-50 text-[#dc2626] font-bold border-red-200 shadow-2xs'
                : 'text-slate-700 border-transparent hover:text-red-700 hover:bg-red-50/60 hover:border-red-200/80 hover:-translate-y-0.5'
            } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/20 focus-visible:border-red-400 focus-visible:bg-red-50/60 focus-visible:text-red-700`}
          >
            {t('nav.howItWorks', 'How It Works')}
          </button>
          <button
            onClick={() => {
              setActiveNav('operations');
              scrollToSection('operations');
            }}
            className={`px-3 py-1.5 rounded-xl transition-all duration-200 ease-out cursor-pointer font-semibold border ${
              activeNav === 'operations'
                ? 'bg-red-50 text-[#dc2626] font-bold border-red-200 shadow-2xs'
                : 'text-slate-700 border-transparent hover:text-red-700 hover:bg-red-50/60 hover:border-red-200/80 hover:-translate-y-0.5'
            } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/20 focus-visible:border-red-400 focus-visible:bg-red-50/60 focus-visible:text-red-700`}
          >
            {t('nav.operations', 'Operational Portals')}
          </button>
          <button
            onClick={() => {
              setActiveNav('contact');
              scrollToSection('contact');
            }}
            className={`px-3 py-1.5 rounded-xl transition-all duration-200 ease-out cursor-pointer font-semibold border ${
              activeNav === 'contact'
                ? 'bg-red-50 text-[#dc2626] font-bold border-red-200 shadow-2xs'
                : 'text-slate-700 border-transparent hover:text-red-700 hover:bg-red-50/60 hover:border-red-200/80 hover:-translate-y-0.5'
            } focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/20 focus-visible:border-red-400 focus-visible:bg-red-50/60 focus-visible:text-red-700`}
          >
            {t('nav.contact', 'Contact')}
          </button>
        </nav>

        {/* Right: Actions + Language Selector + Mobile Menu Toggle */}
        <div className="flex items-center gap-2 sm:gap-3">
          <LanguageSelector variant="navbar" />

          <button
            onClick={() => scrollToSection('operations')}
            className="hidden sm:inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white hover:bg-slate-50 text-slate-900 border border-slate-300 hover:border-slate-400 font-sans text-xs font-semibold transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 min-h-[40px]"
          >
            <span>{t('nav.operationsBtn', 'Operations')}</span>
            <ExternalLink className="w-3 h-3 text-slate-500" />
          </button>

          <button
            onClick={() => navigate('/report-emergency')}
            className="inline-flex items-center gap-1.5 px-3.5 sm:px-4 py-2 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs font-bold transition-all duration-200 shadow-sm hover:shadow-lg hover:shadow-red-500/20 hover:-translate-y-0.5 min-h-[40px] cursor-pointer touch-manipulation focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
          >
            <Siren className="w-3.5 h-3.5" />
            <span className="whitespace-nowrap">{t('hero.reportBtn', 'Report Emergency Now')}</span>
          </button>

          {/* Mobile Hamburger Button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="md:hidden p-2 rounded-xl text-slate-700 hover:text-slate-900 hover:bg-slate-100 border border-slate-300 hover:border-slate-400 transition-colors cursor-pointer min-h-[40px] min-w-[40px] flex items-center justify-center touch-manipulation"
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
            <div className="pb-2 border-b border-slate-100">
              <LanguageSelector variant="compact" className="w-full" />
            </div>

            <nav className="space-y-2 text-sm font-bold text-slate-800 font-sans">
              <button
                onClick={() => {
                  setActiveNav('home');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                  setMobileMenuOpen(false);
                }}
                className={`w-full text-left py-2.5 px-3.5 rounded-xl flex items-center justify-between border transition-all duration-200 min-h-[44px] cursor-pointer ${
                  activeNav === 'home'
                    ? 'bg-red-50 text-[#dc2626] border-red-200 shadow-2xs'
                    : 'text-slate-700 border-transparent hover:bg-slate-50 hover:border-slate-200 active:bg-red-50 active:text-red-700'
                }`}
              >
                <span>{t('nav.home', 'Home')}</span>
                <ArrowRight className={`w-4 h-4 ${activeNav === 'home' ? 'text-[#dc2626]' : 'text-slate-400'}`} />
              </button>
              <button
                onClick={() => {
                  setActiveNav('about');
                  scrollToSection('about');
                }}
                className={`w-full text-left py-2.5 px-3.5 rounded-xl flex items-center justify-between border transition-all duration-200 min-h-[44px] cursor-pointer ${
                  activeNav === 'about'
                    ? 'bg-red-50 text-[#dc2626] border-red-200 shadow-2xs'
                    : 'text-slate-700 border-transparent hover:bg-slate-50 hover:border-slate-200 active:bg-red-50 active:text-red-700'
                }`}
              >
                <span>{t('nav.about', 'About Platform')}</span>
                <ArrowRight className={`w-4 h-4 ${activeNav === 'about' ? 'text-[#dc2626]' : 'text-slate-400'}`} />
              </button>
              <button
                onClick={() => {
                  setActiveNav('how-it-works');
                  scrollToSection('how-it-works');
                }}
                className={`w-full text-left py-2.5 px-3.5 rounded-xl flex items-center justify-between border transition-all duration-200 min-h-[44px] cursor-pointer ${
                  activeNav === 'how-it-works'
                    ? 'bg-red-50 text-[#dc2626] border-red-200 shadow-2xs'
                    : 'text-slate-700 border-transparent hover:bg-slate-50 hover:border-slate-200 active:bg-red-50 active:text-red-700'
                }`}
              >
                <span>{t('nav.howItWorks', 'How It Works')}</span>
                <ArrowRight className={`w-4 h-4 ${activeNav === 'how-it-works' ? 'text-[#dc2626]' : 'text-slate-400'}`} />
              </button>
              <button
                onClick={() => {
                  setActiveNav('operations');
                  scrollToSection('operations');
                }}
                className={`w-full text-left py-2.5 px-3.5 rounded-xl flex items-center justify-between border transition-all duration-200 min-h-[44px] cursor-pointer ${
                  activeNav === 'operations'
                    ? 'bg-red-50 text-[#dc2626] border-red-200 shadow-2xs'
                    : 'text-slate-700 border-transparent hover:bg-slate-50 hover:border-slate-200 active:bg-red-50 active:text-red-700'
                }`}
              >
                <span>{t('nav.operations', 'Operational Portals')}</span>
                <ArrowRight className={`w-4 h-4 ${activeNav === 'operations' ? 'text-[#dc2626]' : 'text-slate-400'}`} />
              </button>
              <button
                onClick={() => {
                  setActiveNav('contact');
                  scrollToSection('contact');
                }}
                className={`w-full text-left py-2.5 px-3.5 rounded-xl flex items-center justify-between border transition-all duration-200 min-h-[44px] cursor-pointer ${
                  activeNav === 'contact'
                    ? 'bg-red-50 text-[#dc2626] border-red-200 shadow-2xs'
                    : 'text-slate-700 border-transparent hover:bg-slate-50 hover:border-slate-200 active:bg-red-50 active:text-red-700'
                }`}
              >
                <span>{t('nav.contact', 'Contact')}</span>
                <ArrowRight className={`w-4 h-4 ${activeNav === 'contact' ? 'text-[#dc2626]' : 'text-slate-400'}`} />
              </button>
            </nav>

            <div className="pt-4 border-t border-slate-200 space-y-3">
              <div className="text-xs font-mono font-bold uppercase tracking-wider text-slate-400">
                {t('nav.directPortals', 'Direct Operational Portals')}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs font-bold">
                <button
                  onClick={() => { setMobileMenuOpen(false); navigate('/login/officer'); }}
                  className="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 hover:border-red-400 hover:shadow-md transition-all text-center cursor-pointer"
                >
                  {t('roles.officerTitle', 'Officer Command')}
                </button>
                <button
                  onClick={() => { setMobileMenuOpen(false); navigate('/login/resource-manager'); }}
                  className="p-3 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 hover:border-emerald-400 hover:shadow-md transition-all text-center cursor-pointer"
                >
                  {t('roles.rmTitle', 'Resource Manager')}
                </button>
                <button
                  onClick={() => { setMobileMenuOpen(false); navigate('/login/volunteer'); }}
                  className="p-3 rounded-xl bg-blue-50 text-blue-800 border border-blue-200 hover:border-blue-400 hover:shadow-md transition-all text-center cursor-pointer"
                >
                  {t('roles.volTitle', 'Volunteer Portal')}
                </button>
                <button
                  onClick={() => { setMobileMenuOpen(false); navigate('/login/admin'); }}
                  className="p-3 rounded-xl bg-purple-50 text-purple-800 border border-purple-200 hover:border-purple-400 hover:shadow-md transition-all text-center cursor-pointer"
                >
                  {t('roles.adminTitle', 'System Admin')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================
          2. HERO SECTION — TWO COLUMN HERO + LIVE MAP
          ======================================================== */}
      <main className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 sm:pt-12 pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-center mb-16 sm:mb-20">
          
          {/* LEFT SIDE: HERO CONTENT */}
          <div className="lg:col-span-6 text-left space-y-5 sm:space-y-6">
            {/* Live System Badge */}
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-emerald-50 border border-emerald-300 text-emerald-900 font-mono text-[10px] sm:text-[11px] font-bold tracking-wider shadow-2xs hover:border-emerald-400 transition-colors">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>{t('hero.badge', 'AI-ASSISTED • HUMAN-VERIFIED EMERGENCY RESPONSE')}</span>
            </div>

            {/* Main Headline */}
            <h1 className="text-3xl xs:text-4xl sm:text-5xl lg:text-[54px] font-black tracking-tight uppercase font-sans text-slate-900 leading-[1.08] sm:leading-[1.06]">
              {t('hero.headline1', 'STRONGER')}<br />
              {t('hero.headline2', 'COMMUNITIES.')}<br />
              <span className="text-[#dc2626]">
                {t('hero.headline3', 'FASTER RESPONSE.')}
              </span><br />
              {t('hero.headline4', 'SAFER TOMORROW.')}
            </h1>

            {/* Subtitle */}
            <p className="text-xs sm:text-base text-slate-700 max-w-lg leading-relaxed font-sans font-medium">
              {t('hero.subtitle', 'An intelligent emergency coordination platform connecting citizen distress observations, geotagged visual evidence, and 9 specialized AI agents into explainable, human-approved response plans.')}
            </p>

            {/* CTAs (Same row on desktop/tablet, stacked naturally on mobile) */}
            <div className="pt-2">
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 sm:gap-4">
                {/* Primary CTA */}
                <button
                  onClick={() => navigate('/report-emergency')}
                  className="inline-flex items-center justify-center gap-2 px-5 sm:px-6 py-3 sm:py-3.5 rounded-xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-xs sm:text-sm font-bold tracking-wide shadow-sm hover:shadow-xl hover:shadow-red-500/20 hover:-translate-y-0.5 transition-all duration-200 min-h-[44px] touch-manipulation cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400 shrink-0"
                >
                  <Siren className="w-4 h-4" />
                  <span>{t('hero.reportBtn', 'Report Emergency Now')}</span>
                </button>

                {/* Secondary CTA */}
                <button
                  onClick={() => scrollToSection('how-it-works')}
                  className="inline-flex items-center justify-center gap-2 px-4 sm:px-5 py-3 sm:py-3.5 rounded-xl bg-white hover:bg-slate-50 text-slate-800 font-sans text-xs sm:text-sm font-bold tracking-wide border border-slate-300 hover:border-slate-400 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md min-h-[44px] touch-manipulation cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 shrink-0"
                >
                  <span>{t('hero.howProtects', 'How Resilience AI Protects Communities')}</span>
                  <ArrowRight className="w-4 h-4 text-slate-500" />
                </button>
              </div>

              <div className="text-[11px] text-slate-500 font-semibold mt-2.5 pl-1">
                {t('hero.caption', '(Public Reporting • No Account Required • Live GPS Discovery)')}
              </div>
            </div>
          </div>

          {/* RIGHT SIDE: LIVE MAP PREVIEW */}
          <div className="lg:col-span-6 w-full">
            <LiveMapPreview />
          </div>
        </div>

        {/* ========================================================
            3. ABOUT SECTION / WHY RESILIENCE
            ======================================================== */}
        <section id="about" className="scroll-mt-20 mb-20">
          <div className="p-6 sm:p-10 rounded-3xl bg-white border border-slate-300 shadow-sm hover:border-slate-400 hover:shadow-md transition-all duration-200">
            <div className="max-w-3xl mb-8">
              <div className="inline-flex items-center gap-2 font-mono text-[11px] uppercase text-[#dc2626] font-bold tracking-wider mb-2">
                <Shield className="w-3.5 h-3.5" />
                <span>{t('about.tag', 'WHY RESILIENCE?')}</span>
              </div>
              <h2 className="text-2xl sm:text-3xl font-black uppercase font-sans tracking-tight text-slate-900">
                {t('about.title', 'Closing the Critical Gap Between Citizen Distress and Coordinated Action')}
              </h2>
              <p className="text-xs sm:text-sm text-slate-700 mt-2 leading-relaxed">
                {t('about.desc', 'During disasters, unorganized reports overwhelm emergency hotlines while responders struggle with fragmented field data. Resilience unifies real-time citizen signals, AI multimodal analysis, and human command authority into an auditable, transparent operational pipeline.')}
              </p>
            </div>

            {/* Three Core Pillars with Semantic Hover Borders */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="group p-5 rounded-2xl bg-slate-50/90 border border-slate-300 hover:border-red-400 hover:shadow-xl hover:shadow-red-500/10 hover:-translate-y-1 transition-all duration-200 flex flex-col justify-between cursor-default">
                <div>
                  <div className="w-10 h-10 rounded-xl bg-red-50 border border-red-200 group-hover:bg-red-100 group-hover:border-red-300 flex items-center justify-center text-[#dc2626] mb-4 transition-all duration-200">
                    <MapPin className="w-5 h-5 group-hover:scale-105 transition-transform" />
                  </div>
                  <h3 className="font-bold font-sans text-base text-slate-900 group-hover:text-red-950 mb-2 transition-colors">
                    {t('about.p1Title', '1. Instant Account-Free Intake')}
                  </h3>
                  <p className="text-xs text-slate-700 leading-relaxed">
                    {t('about.p1Desc', 'Citizens report emergencies with photos and GPS in seconds. The system provides instant life-safety guidance and real Google road routing to nearby verified shelters or hospitals.')}
                  </p>
                </div>
                <div className="mt-4 pt-3 border-t border-slate-300/80 font-mono text-[11px] font-bold text-red-700">
                  {t('about.p1Badge', 'ZERO ACCESS BARRIERS')}
                </div>
              </div>

              <div className="group p-5 rounded-2xl bg-slate-50/90 border border-slate-300 hover:border-indigo-400 hover:shadow-xl hover:shadow-indigo-500/10 hover:-translate-y-1 transition-all duration-200 flex flex-col justify-between cursor-default">
                <div>
                  <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-200 group-hover:bg-indigo-100 group-hover:border-indigo-300 flex items-center justify-center text-indigo-600 mb-4 transition-all duration-200">
                    <Cpu className="w-5 h-5 group-hover:scale-105 transition-transform" />
                  </div>
                  <h3 className="font-bold font-sans text-base text-slate-900 group-hover:text-indigo-950 mb-2 transition-colors">
                    {t('about.p2Title', '2. Explainable 9-Agent Mesh')}
                  </h3>
                  <p className="text-xs text-slate-700 leading-relaxed">
                    {t('about.p2Desc', 'Nine specialized deterministic agents coordinate priority, needs, resources, routes, shelters, healthcare, volunteers, and conflicts without hallucinations or autonomous dispatch risks.')}
                  </p>
                </div>
                <div className="mt-4 pt-3 border-t border-slate-300/80 font-mono text-[11px] font-bold text-indigo-700">
                  {t('about.p2Badge', 'DETERMINISTIC REASONING')}
                </div>
              </div>

              <div className="group p-5 rounded-2xl bg-slate-50/90 border border-slate-300 hover:border-emerald-400 hover:shadow-xl hover:shadow-emerald-500/10 hover:-translate-y-1 transition-all duration-200 flex flex-col justify-between cursor-default">
                <div>
                  <div className="w-10 h-10 rounded-xl bg-emerald-50 border border-emerald-200 group-hover:bg-emerald-100 group-hover:border-emerald-300 flex items-center justify-center text-emerald-600 mb-4 transition-all duration-200">
                    <UserCheck className="w-5 h-5 group-hover:scale-105 transition-transform" />
                  </div>
                  <h3 className="font-bold font-sans text-base text-slate-900 group-hover:text-emerald-950 mb-2 transition-colors">
                    {t('about.p3Title', '3. Human Authority & Traceability')}
                  </h3>
                  <p className="text-xs text-slate-700 leading-relaxed">
                    {t('about.p3Desc', 'Emergency officers retain final authority to approve or adjust plans. Changes trigger dynamic replanning diffs, while all actions are logged to an immutable audit trail.')}
                  </p>
                </div>
                <div className="mt-4 pt-3 border-t border-slate-300/80 font-mono text-[11px] font-bold text-emerald-700">
                  {t('about.p3Badge', '100% AUDITABLE ACTION')}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ========================================================
            4. HOW IT WORKS — INTERACTIVE 15-STAGE JOURNEY
            ======================================================== */}
        <HowItWorksInteractive />

        {/* ========================================================
            5. CORE CAPABILITIES / USPS
            ======================================================== */}
        <section className="mb-20">
          <div className="text-left mb-8">
            <div className="font-mono text-[11px] uppercase text-[#dc2626] font-bold tracking-wider mb-1">
              {t('usp.tag', 'ENGINEERED FOR RESILIENCE')}
            </div>
            <h2 className="text-2xl sm:text-3xl font-black uppercase font-sans tracking-tight text-slate-900">
              {t('usp.title', 'Core Platform Capabilities')}
            </h2>
            <p className="text-xs sm:text-sm text-slate-700 mt-1 max-w-xl font-medium">
              {t('usp.desc', 'Engineered to operate reliably during severe crises with uncompromising audit standards and human oversight.')}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {coreUSPs.map((usp, idx) => {
              const IconComp = usp.icon;
              return (
                <div
                  key={idx}
                  className={`group p-6 rounded-2xl bg-white border border-slate-300 shadow-sm hover:-translate-y-1 transition-all duration-200 flex flex-col justify-between cursor-default ${usp.hoverBorder}`}
                >
                  <div>
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center border mb-4 transition-all duration-200 ${usp.iconColor}`}>
                      <IconComp className="w-5 h-5 group-hover:scale-105 transition-transform" />
                    </div>
                    <h3 className="text-base font-bold font-sans tracking-tight text-slate-900 uppercase mb-2">
                      {t(usp.titleKey, usp.defaultTitle)}
                    </h3>
                    <p className="text-xs text-slate-700 leading-relaxed">
                      {t(usp.descKey, usp.defaultDesc)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* ========================================================
            6. OPERATIONAL PORTALS (ROLE ACCESS CARDS)
            ======================================================== */}
        <section id="operations" className="scroll-mt-20 mb-20">
          <div className="text-left mb-8">
            <div className="font-mono text-[11px] uppercase text-[#dc2626] font-bold tracking-wider mb-1">
              {t('roles.tag', 'AUTHORIZED ACCESS GATEWAYS')}
            </div>
            <h2 className="text-2xl sm:text-3xl font-black uppercase font-sans tracking-tight text-slate-900">
              {t('roles.title', 'Operational Command Centers')}
            </h2>
            <p className="text-xs sm:text-sm text-slate-700 mt-1 max-w-xl font-medium">
              {t('roles.desc', 'Select your role console to authenticate with verified mobile credentials or authorized Google SSO.')}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
            {roleCards.map((card) => {
              const RoleIcon = card.icon;
              return (
                <div
                  key={card.id}
                  className={`group relative flex flex-col justify-between p-6 rounded-2xl bg-white border border-slate-300 shadow-sm hover:-translate-y-1 transition-all duration-200 ${card.hoverBorder}`}
                >
                  <div>
                    {/* Top: Icon container + Badge */}
                    <div className="flex items-center justify-between mb-4">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${card.iconContainer} transition-all duration-200`}>
                        <RoleIcon className="w-5 h-5 group-hover:scale-105 transition-transform" />
                      </div>
                      <span className={`font-mono text-[10px] uppercase font-bold tracking-wider px-2.5 py-0.5 rounded-md border ${card.badgeClass} transition-colors`}>
                        {t(card.badgeKey, card.defaultBadge)}
                      </span>
                    </div>

                    {/* Card Title & Description */}
                    <h3 className="text-base font-bold font-sans tracking-tight text-slate-900 uppercase mb-1.5">
                      {t(card.titleKey, card.defaultTitle)}
                    </h3>
                    <p className="text-xs text-slate-700 leading-relaxed mb-4">
                      {t(card.descKey, card.defaultDesc)}
                    </p>

                    {/* Capabilities Checklist */}
                    <div className="pt-3 border-t border-slate-200 mb-6 space-y-2">
                      <div className="text-[10px] font-mono uppercase text-slate-500 font-bold tracking-wider mb-1">
                        {t('roles.capabilities', 'Capabilities:')}
                      </div>
                      {card.capabilities.map((cap) => (
                        <div key={cap.key} className="flex items-center gap-2 text-xs text-slate-800 font-medium">
                          <Check className={`w-3.5 h-3.5 flex-shrink-0 ${card.checkColor}`} strokeWidth={2.5} />
                          <span>{t(cap.key, cap.text)}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Card Bottom CTA */}
                  <div className="space-y-2 pt-2">
                    <button
                      onClick={() => navigate(card.route)}
                      className={`w-full inline-flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl font-sans text-xs font-bold transition-all duration-200 shadow-sm cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 ${card.ctaClass}`}
                    >
                      <span>{t(card.ctaKey, card.defaultCta)}</span>
                      <ArrowRight className="w-3.5 h-3.5 opacity-80 group-hover:translate-x-0.5 transition-transform" />
                    </button>

                    {card.registerRoute && (
                      <button
                        onClick={() => navigate(card.registerRoute)}
                        className="w-full inline-flex items-center justify-center py-2 px-3 rounded-xl bg-blue-50 hover:bg-blue-100 text-blue-800 border border-blue-200 hover:border-blue-400 font-sans text-xs font-semibold transition-all duration-200 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
                      >
                        {t(card.registerKey || 'roles.volRegisterBtn', card.defaultRegister || 'Register as Volunteer')}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* ========================================================
            7. EMERGENCY CTA BANNER
            ======================================================== */}
        <section className="mb-20 p-8 sm:p-10 rounded-3xl bg-slate-900 text-white shadow-xl flex flex-col md:flex-row items-center justify-between gap-6 border border-slate-800 hover:border-red-600/60 hover:shadow-2xl hover:shadow-red-500/10 transition-all duration-200">
          <div className="space-y-2 text-center md:text-left">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-500/20 border border-red-500/40 text-red-300 font-mono text-[10px] font-bold tracking-wider uppercase">
              <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
              <span>{t('crisis.tag', 'COMMUNITY CRISIS RESPONSE')}</span>
            </div>
            <h2 className="text-2xl sm:text-3xl font-black uppercase font-sans tracking-tight">
              {t('crisis.title', 'Are You Facing an Immediate Emergency?')}
            </h2>
            <p className="text-xs sm:text-sm text-slate-200 max-w-xl leading-relaxed">
              {t('crisis.desc', 'Submit a report with geotagged photo evidence in under 30 seconds. No account needed. Receive instant life-safety guidance and real-world road navigation immediately.')}
            </p>
          </div>

          <button
            onClick={() => navigate('/report-emergency')}
            className="px-6 py-4 rounded-2xl bg-[#dc2626] hover:bg-[#b91c1c] text-white font-sans text-sm font-bold uppercase tracking-wider shadow-lg hover:shadow-xl hover:shadow-red-500/30 hover:-translate-y-0.5 transition-all duration-200 flex items-center gap-2.5 shrink-0 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
          >
            <Siren className="w-5 h-5" />
            <span>{t('crisis.btn', 'REPORT EMERGENCY NOW')}</span>
          </button>
        </section>

        {/* ========================================================
            8. CONTACT SECTION
            ======================================================== */}
        <section id="contact" className="scroll-mt-20 mb-16">
          <div className="p-6 sm:p-10 rounded-3xl bg-white border border-slate-300 shadow-sm hover:border-slate-400 hover:shadow-md transition-all duration-200">
            <div className="max-w-2xl mb-6">
              <div className="inline-flex items-center gap-2 font-mono text-[11px] uppercase text-[#dc2626] font-bold tracking-wider mb-2">
                <PhoneCall className="w-3.5 h-3.5" />
                <span>{t('contact.tag', 'DIRECT REACHABILITY')}</span>
              </div>
              <h2 className="text-2xl sm:text-3xl font-black uppercase font-sans tracking-tight text-slate-900">
                {t('contact.title', 'Contact')}
              </h2>
              <p className="text-xs sm:text-sm text-slate-700 mt-1 leading-relaxed">
                {t('contact.desc', 'Have questions about Resilience or the emergency coordination platform? Reach out directly to our emergency coordination team.')}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {/* Phone 1 */}
              <a
                href="tel:9801338643"
                className="group flex items-center justify-between p-4 sm:p-5 rounded-2xl bg-slate-50/90 border border-slate-300 hover:border-red-500 hover:bg-red-50/20 hover:shadow-xl hover:shadow-red-500/10 hover:-translate-y-1 focus-visible:outline-none focus-visible:border-red-500 focus-visible:ring-2 focus-visible:ring-red-500/20 transition-all duration-200"
              >
                <div className="flex items-center gap-3.5">
                  <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 group-hover:border-red-400 group-hover:bg-red-50 flex items-center justify-center text-[#dc2626] group-hover:scale-105 transition-all duration-200">
                    <Phone className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-500 group-hover:text-red-700 block transition-colors">
                      {t('contact.c1Label', 'Emergency Contact 1')}
                    </span>
                    <span className="font-mono text-base sm:text-lg font-bold text-slate-900 group-hover:text-[#dc2626] transition-colors">
                      9801338643
                    </span>
                  </div>
                </div>
                <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-[#dc2626] group-hover:translate-x-0.5 transition-all" />
              </a>

              {/* Phone 2 */}
              <a
                href="tel:9608149464"
                className="group flex items-center justify-between p-4 sm:p-5 rounded-2xl bg-slate-50/90 border border-slate-300 hover:border-red-500 hover:bg-red-50/20 hover:shadow-xl hover:shadow-red-500/10 hover:-translate-y-1 focus-visible:outline-none focus-visible:border-red-500 focus-visible:ring-2 focus-visible:ring-red-500/20 transition-all duration-200"
              >
                <div className="flex items-center gap-3.5">
                  <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 group-hover:border-red-400 group-hover:bg-red-50 flex items-center justify-center text-[#dc2626] group-hover:scale-105 transition-all duration-200">
                    <Phone className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-500 group-hover:text-red-700 block transition-colors">
                      {t('contact.c2Label', 'Emergency Contact 2')}
                    </span>
                    <span className="font-mono text-base sm:text-lg font-bold text-slate-900 group-hover:text-[#dc2626] transition-colors">
                      9608149464
                    </span>
                  </div>
                </div>
                <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-[#dc2626] group-hover:translate-x-0.5 transition-all" />
              </a>

              {/* Phone 3 */}
              <a
                href="tel:9955230311"
                className="group flex items-center justify-between p-4 sm:p-5 rounded-2xl bg-slate-50/90 border border-slate-300 hover:border-red-500 hover:bg-red-50/20 hover:shadow-xl hover:shadow-red-500/10 hover:-translate-y-1 focus-visible:outline-none focus-visible:border-red-500 focus-visible:ring-2 focus-visible:ring-red-500/20 transition-all duration-200"
              >
                <div className="flex items-center gap-3.5">
                  <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 group-hover:border-red-400 group-hover:bg-red-50 flex items-center justify-center text-[#dc2626] group-hover:scale-105 transition-all duration-200">
                    <Phone className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-500 group-hover:text-red-700 block transition-colors">
                      {t('contact.c3Label', 'Emergency Contact 3')}
                    </span>
                    <span className="font-mono text-base sm:text-lg font-bold text-slate-900 group-hover:text-[#dc2626] transition-colors">
                      9955230311
                    </span>
                  </div>
                </div>
                <ArrowRight className="w-4 h-4 text-slate-400 group-hover:text-[#dc2626] group-hover:translate-x-0.5 transition-all" />
              </a>
            </div>
          </div>
        </section>

        {/* ========================================================
            9. BOTTOM STATUS STRIP
            ======================================================== */}
        <div className="p-4 sm:p-5 rounded-2xl bg-white border border-slate-300 shadow-sm hover:border-slate-400 hover:shadow-md transition-all duration-200 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3 font-sans text-xs">
            <div className="flex items-center gap-2 font-bold text-emerald-800 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-300 font-mono text-[11px]">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span>{t('status.operational', 'SYSTEM OPERATIONAL')}</span>
            </div>
            <div className="hidden sm:flex items-center gap-2 text-slate-600 text-xs">
              <span className="font-semibold">{t('status.certified', 'Audit Certified')}</span>
              <span>•</span>
              <span className="font-semibold">{t('status.hitl', 'Human-in-the-Loop')}</span>
              <span>•</span>
              <span className="font-semibold">{t('status.realtime', 'Real-Time Ingestion')}</span>
            </div>
          </div>

          <div className="flex items-center gap-2.5 text-slate-700 text-xs sm:text-sm italic font-sans text-center md:text-right font-medium">
            <Activity className="w-4 h-4 text-red-500 flex-shrink-0 animate-pulse" />
            <span>&ldquo;{t('status.quote', "Resilience is not just a platform, it's a community.")}&rdquo;</span>
          </div>
        </div>
      </main>

      {/* ========================================================
          10. FOOTER
          ======================================================== */}
      <footer className="relative z-10 border-t border-slate-300 bg-slate-100/90 py-8 text-center text-xs font-mono text-slate-600">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div>
            {t('footer.tagline', 'RESILIENCE © 2026 • AI Community Resilience & Emergency Coordination Platform')}
          </div>
          <div className="flex items-center gap-4 text-[11px]">
            <span>{t('footer.enterprise', 'ENTERPRISE COMMAND PLATFORM')}</span>
            <span>•</span>
            <span className="text-slate-900 font-bold">{t('footer.audited', 'HUMAN-IN-THE-LOOP AUDITED')}</span>
          </div>
        </div>
      </footer>
    </div>
  );
};
