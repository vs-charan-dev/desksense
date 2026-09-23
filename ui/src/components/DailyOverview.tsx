import React from 'react';
import { Clock, UserX, Activity, Monitor } from 'lucide-react';
import { DashboardMetrics } from '../types';

interface DailyOverviewProps {
  metrics: DashboardMetrics;
}

export const DailyOverview: React.FC<DailyOverviewProps> = ({ metrics }) => {
  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10';
    if (score >= 60) return 'text-amber-400 border-amber-500/30 bg-amber-500/10';
    return 'text-rose-400 border-rose-500/30 bg-rose-500/10';
  };

  const getScoreBarColor = (score: number) => {
    if (score >= 80) return 'bg-emerald-500';
    if (score >= 60) return 'bg-amber-500';
    return 'bg-rose-500';
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {/* Posture Score */}
      <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4 flex flex-col justify-between shadow-sm backdrop-blur">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            Posture Score
          </span>
          <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400">
            <Activity className="w-4 h-4" />
          </div>
        </div>
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold tracking-tight text-white">
              {metrics.posture_score_formatted}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold ${getScoreColor(metrics.posture_score)}`}>
              {metrics.posture_score >= 80 ? 'Optimal' : metrics.posture_score >= 60 ? 'Fair' : 'Attention'}
            </span>
          </div>
          <div className="w-full bg-slate-700/50 h-1.5 rounded-full mt-3 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${getScoreBarColor(metrics.posture_score)}`}
              style={{ width: `${Math.min(100, Math.max(0, metrics.posture_score))}%` }}
            />
          </div>
        </div>
      </div>

      {/* At-Desk Time */}
      <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4 flex flex-col justify-between shadow-sm backdrop-blur">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            At-Desk Time
          </span>
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400">
            <Clock className="w-4 h-4" />
          </div>
        </div>
        <div>
          <div className="text-3xl font-bold tracking-tight text-white">
            {metrics.desk_time_formatted}
          </div>
          <p className="text-xs text-slate-400 mt-2">
            Total presence time detected in front of screen
          </p>
        </div>
      </div>

      {/* Away Time */}
      <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4 flex flex-col justify-between shadow-sm backdrop-blur">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            Away Time
          </span>
          <div className="p-2 rounded-lg bg-slate-700 text-slate-300">
            <UserX className="w-4 h-4" />
          </div>
        </div>
        <div>
          <div className="text-3xl font-bold tracking-tight text-slate-200">
            {metrics.away_time_formatted}
          </div>
          <p className="text-xs text-slate-400 mt-2">
            Breaks and absences away from desk
          </p>
        </div>
      </div>

      {/* Active Computer Time */}
      <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4 flex flex-col justify-between shadow-sm backdrop-blur">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            Active Computer Time
          </span>
          <div className="p-2 rounded-lg bg-sky-500/10 text-sky-400">
            <Monitor className="w-4 h-4" />
          </div>
        </div>
        <div>
          <div className="text-3xl font-bold tracking-tight text-white">
            {metrics.active_time_formatted}
          </div>
          <p className="text-xs text-slate-400 mt-2">
            Active mouse & keyboard engagement
          </p>
        </div>
      </div>
    </div>
  );
};
