import React from 'react';
import { FocusTotals, PhoneDashboardSummary, DailySummaryData } from '../types';

interface FocusDashboardProps {
  focus?: FocusTotals;
  phone?: PhoneDashboardSummary;
  summary?: DailySummaryData;
}

export const FocusDashboard: React.FC<FocusDashboardProps> = ({ focus, phone, summary }) => {
  const formatDuration = (sec: number = 0) => {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  };

  const wellnessScore = summary?.score?.daily_wellness_score ?? 85;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
      {/* Focus Overview Card */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 backdrop-blur-md shadow-xl flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">Deep Focus Time</span>
            <span className="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full font-medium">
              {focus?.session_count ?? 0} sessions
            </span>
          </div>
          <div className="text-3xl font-bold text-slate-100 tracking-tight mb-2">
            {formatDuration(focus?.total_focus_time ?? 0)}
          </div>
          <div className="text-xs text-slate-400 flex items-center justify-between">
            <span>Longest Block: <strong className="text-slate-200">{formatDuration(focus?.longest_session ?? 0)}</strong></span>
            <span>Avg Session: <strong className="text-slate-200">{formatDuration(focus?.average_session ?? 0)}</strong></span>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-800/80 text-xs text-slate-400 flex items-center justify-between">
          <span>Distractions recorded:</span>
          <span className="font-semibold text-rose-400">{focus?.distraction_count ?? 0}</span>
        </div>
      </div>

      {/* Estimated Phone Card */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 backdrop-blur-md shadow-xl flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">Estimated Phone Usage</span>
            <span className="text-xs bg-amber-500/10 text-amber-400 border border-amber-500/20 px-2 py-0.5 rounded-full font-medium">
              {phone?.estimated_sessions ?? 0} pickups
            </span>
          </div>
          <div className="text-3xl font-bold text-slate-100 tracking-tight mb-2">
            {formatDuration(phone?.estimated_phone_usage ?? 0)}
          </div>
          <div className="text-xs text-slate-400 flex items-center justify-between">
            <span>Longest Pickup: <strong className="text-slate-200">{formatDuration(phone?.longest_session ?? 0)}</strong></span>
            <span>Avg Pickup: <strong className="text-slate-200">{formatDuration(phone?.average_session ?? 0)}</strong></span>
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-800/80 text-[11px] text-slate-500 italic">
          * Strictly camera & posture-based estimates; zero personal screen tracking.
        </div>
      </div>

      {/* Wellness & Behavioral Insights Card */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 backdrop-blur-md shadow-xl flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">Daily Wellness Score</span>
            <span className="text-xs bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 px-2.5 py-0.5 rounded-full font-semibold">
              {wellnessScore} / 100
            </span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden mb-3">
            <div
              className="bg-gradient-to-r from-emerald-500 via-indigo-500 to-sky-400 h-full rounded-full transition-all duration-700"
              style={{ width: `${Math.min(100, Math.max(0, wellnessScore))}%` }}
            />
          </div>
          <div className="text-xs text-slate-300 space-y-1.5 max-h-24 overflow-y-auto pr-1">
            {summary?.insights && summary.insights.length > 0 ? (
              summary.insights.map((insight, idx) => (
                <p key={idx} className="leading-snug text-slate-300 flex items-start gap-1.5">
                  <span className="text-emerald-400 font-bold">•</span>
                  <span>{insight}</span>
                </p>
              ))
            ) : (
              <p className="text-slate-400 italic">Maintain balanced focus and regular breaks to build your daily score.</p>
            )}
          </div>
        </div>
        <div className="mt-4 pt-3 border-t border-slate-800/80 text-[10px] text-slate-500 leading-tight">
          Non-medical wellness indicators for ergonomic comfort.
        </div>
      </div>
    </div>
  );
};
