import React from 'react';

export const TacticalBackground: React.FC = () => {
  return (
    <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden bg-[#EEF2F6]">
      {/* Clean, seamless, pattern-free cool blue-grey background canvas */}
      <div 
        className="absolute inset-0"
        style={{
          background: 'radial-gradient(ellipse at 50% 0%, #F1F5F9 0%, #EEF2F6 50%, #E2E8F0 100%)',
        }}
      />
    </div>
  );
};


