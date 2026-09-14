import React from 'react';

interface EmergencyEmblemProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  showText?: boolean;
  className?: string;
  theme?: 'light' | 'dark';
}

export const EmergencyEmblem: React.FC<EmergencyEmblemProps> = ({
  size = 'md',
  showText = true,
  className = '',
  theme = 'light',
}) => {
  const iconDimensions = {
    sm: 'w-7 h-7',
    md: 'w-8 h-8',
    lg: 'w-11 h-11',
    xl: 'w-14 h-14',
  }[size];

  const titleSize = {
    sm: 'text-sm font-bold tracking-wider',
    md: 'text-base font-extrabold tracking-widest',
    lg: 'text-xl font-black tracking-widest',
    xl: 'text-2xl font-black tracking-widest',
  }[size];

  const subtitleSize = {
    sm: 'text-[8px] tracking-wider',
    md: 'text-[9px] tracking-widest',
    lg: 'text-[10px] tracking-widest',
    xl: 'text-xs tracking-widest',
  }[size];

  return (
    <div className={`inline-flex items-center gap-2.5 ${className}`}>
      {/* Tactical Emergency Emblem Graphic */}
      <div className={`relative ${iconDimensions} flex items-center justify-center flex-shrink-0`}>
        {/* Outer Red-Shield Ring */}
        <div className={`absolute inset-0 rounded-lg border ${
          theme === 'light' 
            ? 'bg-red-50 border-red-500/40 shadow-sm' 
            : 'bg-red-50/80 border-red-500/40 shadow-xs'
        }`} />
        
        {/* Inner Border Ring */}
        <div className={`absolute inset-0.5 rounded-md border ${
          theme === 'light' ? 'border-red-300/40' : 'border-red-300/40'
        }`} />

        {/* Dynamic Emergency Cross / Pulse Vector */}
        <svg
          className="relative w-3/5 h-3/5 text-[#dc2626]"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {/* Shield Outline */}
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="rgba(220, 38, 38, 0.12)" />
          {/* Emergency Cross */}
          <path d="M12 7v10M7 12h10" stroke="#dc2626" strokeWidth="2.2" />
        </svg>

        {/* Live operational indicator dot */}
        <div className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-500 border border-white shadow-sm" />
      </div>

      {/* Brand Typography */}
      {showText && (
        <div className="flex flex-col text-left min-w-0">
          <div className={`font-sans ${titleSize} tracking-widest uppercase truncate ${
            theme === 'light' ? 'text-slate-900' : 'text-white'
          }`}>
            RESILIENCE
          </div>
          <div className={`font-mono uppercase ${subtitleSize} truncate hidden xs:block ${
            theme === 'light' ? 'text-slate-500 font-medium' : 'text-slate-400'
          }`}>
            EMERGENCY RESPONSE PLATFORM
          </div>
        </div>
      )}
    </div>
  );
};


