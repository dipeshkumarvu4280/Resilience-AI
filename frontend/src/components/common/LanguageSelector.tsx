import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useLanguage } from '../../context/LanguageContext';
import { Globe, Check, Edit3, X, Sparkles } from 'lucide-react';

interface LanguageSelectorProps {
  variant?: 'navbar' | 'compact' | 'modal' | 'floating';
  className?: string;
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  variant = 'navbar',
  className = '',
}) => {
  const {
    language,
    currentLanguageOption,
    setLanguage,
    supportedLanguages,
    isAutoDetected,
    resetToAutoDetect,
    t,
  } = useLanguage();

  const [isOpen, setIsOpen] = useState<boolean>(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Position state for desktop popover
  const [popoverStyle, setPopoverStyle] = useState<React.CSSProperties>({});
  const [isMobileModal, setIsMobileModal] = useState<boolean>(false);

  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;

    const isSmall = window.innerWidth < 640;
    setIsMobileModal(isSmall);

    if (isSmall) {
      setPopoverStyle({});
      return;
    }

    const rect = triggerRef.current.getBoundingClientRect();
    const dropdownWidth = Math.min(440, window.innerWidth - 32);
    const viewportHeight = window.innerHeight;
    const viewportWidth = window.innerWidth;

    const spaceBelow = viewportHeight - rect.bottom - 12;
    const spaceAbove = rect.top - 12;

    let top: number | undefined;
    let bottom: number | undefined;
    let maxHeight: number;

    if (spaceBelow < 340 && spaceAbove > spaceBelow) {
      // Open upward above trigger button
      bottom = viewportHeight - rect.top + 8;
      maxHeight = Math.min(500, spaceAbove);
    } else {
      // Open downward below trigger button
      top = rect.bottom + 8;
      maxHeight = Math.min(500, Math.max(260, spaceBelow));
    }

    // Horizontal alignment: align right edge with trigger button right edge
    let right = viewportWidth - rect.right;
    if (right < 16) right = 16;
    if (rect.right - dropdownWidth < 16) {
      right = Math.max(16, viewportWidth - (rect.left + dropdownWidth));
    }

    setPopoverStyle({
      position: 'fixed',
      top: top !== undefined ? `${top}px` : undefined,
      bottom: bottom !== undefined ? `${bottom}px` : undefined,
      right: `${Math.max(16, right)}px`,
      width: `${dropdownWidth}px`,
      maxHeight: `${maxHeight}px`,
      zIndex: 99999,
    });
  }, []);

  // Update position on open, scroll, or resize
  useEffect(() => {
    if (!isOpen) return;

    updatePosition();

    const handleScroll = () => updatePosition();
    const handleResize = () => updatePosition();

    window.addEventListener('scroll', handleScroll, { passive: true, capture: true });
    window.addEventListener('resize', handleResize, { passive: true });

    return () => {
      window.removeEventListener('scroll', handleScroll, { capture: true });
      window.removeEventListener('resize', handleResize);
    };
  }, [isOpen, updatePosition]);

  // Close on outside click or Escape key
  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(event: MouseEvent | TouchEvent) {
      const target = event.target as Node;
      if (triggerRef.current && triggerRef.current.contains(target)) {
        return;
      }
      if (popoverRef.current && !popoverRef.current.contains(target)) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const handleSelect = (code: string) => {
    setLanguage(code);
    setIsOpen(false);
  };

  return (
    <div className={`relative inline-block text-left max-w-full min-w-0 ${className}`}>
      {/* Trigger Button */}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        className={`inline-flex items-center gap-1 sm:gap-2 px-2 sm:px-3.5 py-1.5 sm:py-2 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 hover:border-red-300 text-slate-800 transition-all duration-200 text-xs font-semibold shadow-2xs hover:shadow-sm cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/20 focus-visible:border-red-400 min-h-[36px] sm:min-h-[40px] touch-manipulation max-w-full min-w-0 ${
          variant === 'compact' ? 'w-full justify-between' : ''
        }`}
        aria-label="Select Language"
        title="Select system and guidance language"
      >
        <Globe className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-[#dc2626] shrink-0" />
        <span className="hidden sm:inline text-xs text-slate-500 font-normal">
          {t('nav.language', 'Language')}:
        </span>
        <span className="font-bold text-slate-900 truncate text-[11px] sm:text-xs">
          {currentLanguageOption.nativeName}
        </span>
        {currentLanguageOption.code !== 'en' && (
          <span className="text-[11px] text-slate-500 font-normal hidden lg:inline">
            ({currentLanguageOption.name})
          </span>
        )}
        <span className="inline-flex items-center gap-0.5 sm:gap-1 text-[9px] sm:text-[10px] px-1 sm:px-1.5 py-0.5 rounded-md bg-slate-100 border border-slate-200 text-slate-600 font-bold uppercase tracking-wider hover:text-red-700 hover:bg-red-50 hover:border-red-200 transition-colors ml-0.5 sm:ml-1 shrink-0">
          <Edit3 className="w-2 sm:w-2.5 h-2 sm:h-2.5" />
          <span>{t('nav.edit', 'EDIT')}</span>
        </span>
      </button>

      {/* Top-Level Portal Rendered Dropdown / Modal (Light Resilience Theme) */}
      {isOpen && typeof document !== 'undefined' &&
        createPortal(
          isMobileModal ? (
            /* Mobile Centered Modal Dialog (<640px) */
            <div
              className="fixed inset-0 z-[99999] flex items-center justify-center p-3 sm:p-4 bg-slate-900/50 backdrop-blur-xs animate-in fade-in duration-150"
              role="dialog"
              aria-modal="true"
              aria-label={t('guidance.switchLanguage', 'Select Preferred Language')}
              onClick={(e) => {
                if (e.target === e.currentTarget) setIsOpen(false);
              }}
            >
              <div
                ref={popoverRef}
                className="w-full max-w-md max-h-[90vh] flex flex-col bg-white border border-slate-300 rounded-2xl shadow-2xl p-4 sm:p-5 text-slate-900 ring-1 ring-slate-900/10 overflow-hidden"
              >
                {/* Header */}
                <div className="flex items-center justify-between pb-3 border-b border-slate-200 mb-3 shrink-0">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-xl bg-red-50 border border-red-200 flex items-center justify-center text-[#dc2626] shrink-0">
                      <Globe className="w-4 h-4" />
                    </div>
                    <div>
                      <h3 className="font-bold text-sm text-slate-900 leading-snug">
                        {t('guidance.switchLanguage', 'Select Preferred Language')}
                      </h3>
                      <p className="text-[11px] text-slate-500 leading-tight">
                        Landing, reporting &amp; life-safety guidance
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsOpen(false)}
                    className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer min-h-[36px] min-w-[36px] flex items-center justify-center"
                    aria-label="Close language selector"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Auto-detect info banner */}
                <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 mb-3 text-xs text-slate-700 shadow-2xs shrink-0">
                  <span className="flex items-center gap-1.5 min-w-0">
                    <Sparkles className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                    <span className="truncate">
                      {isAutoDetected ? 'Auto-detected from browser' : 'User custom preference'}
                    </span>
                  </span>
                  {!isAutoDetected && (
                    <button
                      type="button"
                      onClick={resetToAutoDetect}
                      className="text-xs text-[#dc2626] hover:text-red-700 underline font-bold cursor-pointer shrink-0 ml-2"
                    >
                      Reset
                    </button>
                  )}
                </div>

                {/* Language Grid */}
                <div className="flex-1 overflow-y-auto pr-1 space-y-2 max-h-[48vh]">
                  {supportedLanguages.map((opt) => {
                    const isSelected = opt.code === language;
                    return (
                      <button
                        key={opt.code}
                        type="button"
                        onClick={() => handleSelect(opt.code)}
                        className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl border text-left transition-all duration-200 cursor-pointer min-h-[44px] ${
                          isSelected
                            ? 'bg-red-50/90 border-red-500 text-slate-900 font-bold shadow-2xs ring-1 ring-red-500/30'
                            : 'bg-slate-50/70 border-slate-200 text-slate-800 hover:bg-white hover:border-slate-300 hover:shadow-xs'
                        }`}
                      >
                        <div className="flex flex-col">
                          <span className="text-sm font-bold text-slate-900">{opt.nativeName}</span>
                          <span className="text-xs text-slate-500">{opt.name}</span>
                        </div>
                        {isSelected && (
                          <div className="w-5 h-5 rounded-full bg-[#dc2626] flex items-center justify-center text-white shrink-0 shadow-2xs">
                            <Check className="w-3 h-3 stroke-[3]" />
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>

                {/* Footer Notice */}
                <div className="mt-3 pt-2.5 border-t border-slate-200 text-[11px] text-slate-500 text-center font-medium shrink-0">
                  Natural language NLP accepts descriptions in any language.
                </div>
              </div>
            </div>
          ) : (
            /* Desktop/Tablet Positioned Popover (>=640px) */
            <div
              ref={popoverRef}
              style={popoverStyle}
              className="flex flex-col bg-white border border-slate-300 rounded-2xl shadow-2xl p-4 sm:p-5 text-slate-900 ring-1 ring-slate-900/10 animate-in fade-in zoom-in-95 duration-150 overflow-hidden"
              role="dialog"
              aria-modal="true"
              aria-label={t('guidance.switchLanguage', 'Select Preferred Language')}
            >
              {/* Header */}
              <div className="flex items-center justify-between pb-3 border-b border-slate-200 mb-3 shrink-0">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-xl bg-red-50 border border-red-200 flex items-center justify-center text-[#dc2626] shrink-0">
                    <Globe className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="font-bold text-sm text-slate-900 leading-snug">
                      {t('guidance.switchLanguage', 'Select Preferred Language')}
                    </h3>
                    <p className="text-[11px] text-slate-500 leading-tight">
                      Landing, emergency reporting &amp; life-safety guidance
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer min-h-[32px] min-w-[32px] flex items-center justify-center"
                  aria-label="Close language selector"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Auto-detect info banner */}
              <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 mb-3 text-xs text-slate-700 shadow-2xs shrink-0">
                <span className="flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                  <span>
                    {isAutoDetected ? 'Auto-detected from browser' : 'User custom preference saved'}
                  </span>
                </span>
                {!isAutoDetected && (
                  <button
                    type="button"
                    onClick={resetToAutoDetect}
                    className="text-xs text-[#dc2626] hover:text-red-700 underline font-bold cursor-pointer ml-2"
                  >
                    Reset to Auto
                  </button>
                )}
              </div>

              {/* Language Grid */}
              <div className="flex-1 overflow-y-auto pr-1 grid grid-cols-2 gap-2 min-h-0">
                {supportedLanguages.map((opt) => {
                  const isSelected = opt.code === language;
                  return (
                    <button
                      key={opt.code}
                      type="button"
                      onClick={() => handleSelect(opt.code)}
                      className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl border text-left transition-all duration-200 cursor-pointer min-h-[44px] ${
                        isSelected
                          ? 'bg-red-50/90 border-red-500 text-slate-900 font-bold shadow-2xs ring-1 ring-red-500/30'
                          : 'bg-slate-50/70 border-slate-200 text-slate-800 hover:bg-white hover:border-slate-300 hover:shadow-xs'
                      }`}
                    >
                      <div className="flex flex-col">
                        <span className="text-sm font-bold text-slate-900">{opt.nativeName}</span>
                        <span className="text-xs text-slate-500">{opt.name}</span>
                      </div>
                      {isSelected && (
                        <div className="w-5 h-5 rounded-full bg-[#dc2626] flex items-center justify-center text-white shrink-0 shadow-2xs">
                          <Check className="w-3 h-3 stroke-[3]" />
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>

              {/* Footer Notice */}
              <div className="mt-3 pt-2.5 border-t border-slate-200 text-[11px] text-slate-500 text-center font-medium shrink-0">
                Natural language NLP accepts descriptions in any language regardless of selected UI language.
              </div>
            </div>
          ),
          document.body
        )}
    </div>
  );
};

