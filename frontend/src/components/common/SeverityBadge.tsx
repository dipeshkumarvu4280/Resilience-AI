import React from 'react';
import type { IncidentSeverity } from '../../types';

interface SeverityBadgeProps {
  severity: IncidentSeverity | 'AI';
  size?: 'sm' | 'md';
  pulse?: boolean;
}

export const SeverityBadge: React.FC<SeverityBadgeProps> = ({
  severity,
  size = 'sm',
  pulse = false,
}) => {
  const configs = {
    CRITICAL: {
      bg: 'bg-red-50',
      border: 'border-red-200',
      text: 'text-red-700',
      dot: 'bg-red-600',
      label: 'CRITICAL',
    },
    HIGH: {
      bg: 'bg-amber-50',
      border: 'border-amber-200',
      text: 'text-amber-800',
      dot: 'bg-amber-600',
      label: 'HIGH PRIORITY',
    },
    WARNING: {
      bg: 'bg-yellow-50',
      border: 'border-yellow-200',
      text: 'text-yellow-800',
      dot: 'bg-yellow-500',
      label: 'WARNING',
    },
    NORMAL: {
      bg: 'bg-emerald-50',
      border: 'border-emerald-200',
      text: 'text-emerald-700',
      dot: 'bg-emerald-600',
      label: 'NORMAL',
    },
    INFO: {
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      text: 'text-blue-700',
      dot: 'bg-blue-600',
      label: 'INFO',
    },
    AI: {
      bg: 'bg-indigo-50',
      border: 'border-indigo-200',
      text: 'text-indigo-700',
      dot: 'bg-indigo-600',
      label: 'AI INTELLIGENCE',
    },
  }[severity];

  const sizeClass = size === 'sm' ? 'text-[10px] px-2 py-0.5' : 'text-xs px-2.5 py-1';

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-sans font-semibold uppercase tracking-wider rounded-md border ${configs.bg} ${configs.border} ${configs.text} ${sizeClass} shadow-xs`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${configs.dot} ${pulse ? 'animate-pulse' : ''}`}
      />
      {configs.label}
    </span>
  );
};
