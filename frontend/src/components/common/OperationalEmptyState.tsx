import React from 'react';
import type { LucideIcon } from 'lucide-react';

interface OperationalEmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  phaseBadge?: string;
  actionText?: string;
  onAction?: () => void;
  accentColor?: 'red' | 'emerald' | 'blue' | 'purple' | 'amber' | 'rose' | 'sky';
  className?: string;
}

export const OperationalEmptyState: React.FC<OperationalEmptyStateProps> = ({
  icon: Icon,
  title,
  description,
  phaseBadge,
  actionText,
  onAction,
  accentColor = 'blue',
  className = '',
}) => {
  const colorMap = {
    red: {
      iconBorder: 'border-red-200',
      iconBg: 'bg-red-50',
      iconColor: 'text-red-600',
      badge: 'border-red-200 text-red-700 bg-red-50',
      btn: 'bg-red-600 hover:bg-red-700 text-white',
    },
    rose: {
      iconBorder: 'border-rose-200',
      iconBg: 'bg-rose-50',
      iconColor: 'text-rose-600',
      badge: 'border-rose-200 text-rose-700 bg-rose-50',
      btn: 'bg-rose-600 hover:bg-rose-700 text-white',
    },
    emerald: {
      iconBorder: 'border-emerald-200',
      iconBg: 'bg-emerald-50',
      iconColor: 'text-emerald-600',
      badge: 'border-emerald-200 text-emerald-700 bg-emerald-50',
      btn: 'bg-emerald-600 hover:bg-emerald-700 text-white',
    },
    blue: {
      iconBorder: 'border-blue-200',
      iconBg: 'bg-blue-50',
      iconColor: 'text-blue-600',
      badge: 'border-blue-200 text-blue-700 bg-blue-50',
      btn: 'bg-blue-600 hover:bg-blue-700 text-white',
    },
    sky: {
      iconBorder: 'border-sky-200',
      iconBg: 'bg-sky-50',
      iconColor: 'text-sky-600',
      badge: 'border-sky-200 text-sky-700 bg-sky-50',
      btn: 'bg-sky-600 hover:bg-sky-700 text-white',
    },
    purple: {
      iconBorder: 'border-purple-200',
      iconBg: 'bg-purple-50',
      iconColor: 'text-purple-600',
      badge: 'border-purple-200 text-purple-700 bg-purple-50',
      btn: 'bg-purple-600 hover:bg-purple-700 text-white',
    },
    amber: {
      iconBorder: 'border-amber-200',
      iconBg: 'bg-amber-50',
      iconColor: 'text-amber-600',
      badge: 'border-amber-200 text-amber-700 bg-amber-50',
      btn: 'bg-amber-600 hover:bg-amber-700 text-white',
    },
  }[accentColor];

  return (
    <div
      className={`relative flex flex-col items-center justify-center p-8 text-center rounded-2xl border border-slate-200/90 bg-white shadow-sm overflow-hidden ${className}`}
    >
      {/* Domain Icon with subtle ring */}
      <div className="relative mb-4">
        <div className={`w-14 h-14 rounded-2xl border ${colorMap.iconBorder} ${colorMap.iconBg} flex items-center justify-center shadow-xs`}>
          <Icon className={`w-7 h-7 ${colorMap.iconColor}`} />
        </div>
      </div>

      {/* Phase Badge */}
      {phaseBadge && (
        <div className={`mb-2 text-[11px] font-semibold tracking-wider uppercase px-2.5 py-0.5 rounded-md border ${colorMap.badge}`}>
          {phaseBadge}
        </div>
      )}

      {/* Title */}
      <h4 className="text-base font-bold text-slate-900 tracking-tight mb-1.5">
        {title}
      </h4>

      {/* Description */}
      <p className="text-xs text-slate-500 max-w-sm leading-relaxed mb-5">
        {description}
      </p>

      {/* Optional action */}
      {actionText && onAction && (
        <button
          onClick={onAction}
          className={`text-xs font-semibold px-4 py-2 rounded-xl transition-all shadow-sm ${colorMap.btn}`}
        >
          {actionText}
        </button>
      )}
    </div>
  );
};
