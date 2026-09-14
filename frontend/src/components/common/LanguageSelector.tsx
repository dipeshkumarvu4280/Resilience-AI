import React, { useState, useRef, useEffect } from 'react';
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
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleSelect = (code: string) => {
    setLanguage(code);
    setIsOpen(false);
  };

  return (
    <div className={`relative inline-block text-left ${className}`} ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={`inline-flex items-center gap-1.5 sm:gap-2 px-3 sm:px-3.5 py-2 rounded-xl border border-slate-300 bg-white hover:bg-slate-50 hover:border-red-300 text-slate-800 transition-all duration-200 text-xs font-semibold shadow-2xs hover:shadow-sm hover:-translate-y-0.5 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/20 focus-visible:border-red-400 min-h-[40px] touch-manipulation ${
          variant === 'compact' ? 'w-full justify-between' : ''
        } ${className}`}
        aria-label="Select Language"
        title="Select system and guidance language"
      >
        <Globe className="w-4 h-4 text-[#dc2626] shrink-0" />
        <span className="hidden sm:inline text-xs text-slate-500 font-normal">
          {t('nav.language', 'Language')}:
        </span>
        <span className="font-bold text-slate-900">
          {currentLanguageOption.nativeName}
        </span>
        {currentLanguageOption.code !== 'en' && (
          <span className="text-[11px] text-slate-500 font-normal hidden lg:inline">
            ({currentLanguageOption.name})
          </span>
        )}
        <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md bg-slate-100 border border-slate-200 text-slate-600 font-bold uppercase tracking-wider hover:text-red-700 hover:bg-red-50 hover:border-red-200 transition-colors ml-1">
          <Edit3 className="w-2.5 h-2.5" />
          {t('nav.edit', 'EDIT')}
        </span>
      </button>

      {/* Language Selection Modal / Popover (Light Theme) */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs sm:absolute sm:inset-auto sm:right-0 sm:top-full sm:mt-2 sm:p-0 sm:bg-transparent sm:backdrop-blur-none">
          <div className="w-full max-w-md bg-white border border-slate-300 rounded-2xl shadow-2xl p-5 text-slate-900 animate-in fade-in zoom-in-95 duration-150 ring-1 ring-slate-900/5">
            {/* Header */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 mb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-red-50 border border-red-200 flex items-center justify-center text-[#dc2626]">
                  <Globe className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">
                    {t('guidance.switchLanguage', 'Select Preferred Language')}
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    Applies to landing, emergency reporting &amp; life-safety guidance
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
                aria-label="Close language selector"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Auto-detect info banner */}
            <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 mb-4 text-xs text-slate-700 shadow-2xs">
              <span className="flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                {isAutoDetected ? (
                  <span>Auto-detected from browser environment</span>
                ) : (
                  <span>Custom user language preference saved</span>
                )}
              </span>
              {!isAutoDetected && (
                <button
                  type="button"
                  onClick={resetToAutoDetect}
                  className="text-xs text-[#dc2626] hover:text-red-700 underline font-bold cursor-pointer"
                >
                  Reset to Auto
                </button>
              )}
            </div>

            {/* Language Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-72 overflow-y-auto pr-1">
              {supportedLanguages.map((opt) => {
                const isSelected = opt.code === language;
                return (
                  <button
                    key={opt.code}
                    type="button"
                    onClick={() => handleSelect(opt.code)}
                    className={`flex items-center justify-between px-3.5 py-2.5 rounded-xl border text-left transition-all duration-200 cursor-pointer ${
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
            <div className="mt-4 pt-3 border-t border-slate-200 text-[11px] text-slate-500 text-center font-medium">
              Natural language NLP accepts descriptions in any language regardless of selected UI language.
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
