import React from 'react';

export const TacticalBackground: React.FC = () => {
  return (
    <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden bg-[#EEF2F6]">
      {/* High-contrast operational blue-grey canvas gradient base */}
      <div 
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse at 50% 0%, #F1F5F9 0%, #EEF2F6 50%, #E2E8F0 100%)',
        }}
      />

      {/* Subtle topographic contour lines (civil response GIS style) */}
      <svg
        className="absolute inset-0 w-full h-full opacity-[0.22] text-slate-300"
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 1600 1000"
        preserveAspectRatio="xMidYMid slice"
      >
        <path
          d="M-100,280 C300,200 600,380 1000,260 C1300,180 1500,290 1700,220"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
        />
        <path
          d="M-100,420 C250,340 700,520 1100,400 C1400,310 1600,460 1700,390"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
          strokeDasharray="4 8"
        />
        <path
          d="M-100,580 C400,460 800,680 1200,560 C1500,470 1700,620 1800,540"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.2"
        />
        <path
          d="M-100,740 C300,660 750,860 1150,740 C1450,650 1650,800 1750,720"
          fill="none"
          stroke="currentColor"
          strokeWidth="1"
        />
        <path
          d="M-50,150 C400,100 800,220 1250,140 C1450,90 1600,180 1750,120"
          fill="none"
          stroke="currentColor"
          strokeWidth="0.8"
        />
      </svg>

      {/* Faint geographic coordinate grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.4]"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(226, 232, 240, 0.6) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(226, 232, 240, 0.6) 1px, transparent 1px)
          `,
          backgroundSize: '48px 48px',
        }}
      />

      {/* Subtle warm environmental illumination */}
      <div className="absolute -top-24 left-1/4 w-[600px] h-[350px] bg-red-100/25 rounded-full blur-[120px]" />
      <div className="absolute top-1/3 right-0 w-[550px] h-[550px] bg-sky-100/30 rounded-full blur-[140px]" />
    </div>
  );
};

