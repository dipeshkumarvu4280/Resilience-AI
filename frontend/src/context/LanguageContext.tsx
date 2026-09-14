import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { SUPPORTED_LANGUAGES, getTranslation } from '../utils/translations';
import type { LanguageOption, TranslationKey } from '../utils/translations';

interface LanguageContextType {
  language: string;
  currentLanguageOption: LanguageOption;
  setLanguage: (code: string) => void;
  t: (key: TranslationKey, defaultText?: string) => string;
  supportedLanguages: LanguageOption[];
  isAutoDetected: boolean;
  resetToAutoDetect: () => void;
}

const STORAGE_KEY = 'resilience_lang_pref';

function detectBrowserLanguage(): string {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return 'en';
  }

  const supportedCodes = SUPPORTED_LANGUAGES.map(l => l.code);
  const candidates: string[] = [];

  if (navigator.languages && navigator.languages.length) {
    for (const l of navigator.languages) {
      if (l) candidates.push(l.toLowerCase());
    }
  }
  if (navigator.language) {
    candidates.push(navigator.language.toLowerCase());
  }

  for (const cand of candidates) {
    const primary = cand.split('-')[0].trim();
    if (supportedCodes.includes(primary)) {
      return primary;
    }
  }

  return 'en';
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export const LanguageProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<string>('en');
  const [isAutoDetected, setIsAutoDetected] = useState<boolean>(true);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved && SUPPORTED_LANGUAGES.some(l => l.code === saved)) {
        setLanguageState(saved);
        setIsAutoDetected(false);
      } else {
        const detected = detectBrowserLanguage();
        setLanguageState(detected);
        setIsAutoDetected(true);
      }
    } catch {
      setLanguageState('en');
    }
  }, []);

  const setLanguage = useCallback((code: string) => {
    const valid = SUPPORTED_LANGUAGES.some(l => l.code === code);
    const target = valid ? code : 'en';
    setLanguageState(target);
    setIsAutoDetected(false);
    try {
      localStorage.setItem(STORAGE_KEY, target);
    } catch {
      // ignore storage errors
    }
  }, []);

  const resetToAutoDetect = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    const detected = detectBrowserLanguage();
    setLanguageState(detected);
    setIsAutoDetected(true);
  }, []);

  const t = useCallback(
    (key: TranslationKey, defaultText?: string): string => {
      return getTranslation(language, key, defaultText);
    },
    [language]
  );

  const currentLanguageOption =
    SUPPORTED_LANGUAGES.find(l => l.code === language) || SUPPORTED_LANGUAGES[0];

  return (
    <LanguageContext.Provider
      value={{
        language,
        currentLanguageOption,
        setLanguage,
        t,
        supportedLanguages: SUPPORTED_LANGUAGES,
        isAutoDetected,
        resetToAutoDetect,
      }}
    >
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = (): LanguageContextType => {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return ctx;
};
