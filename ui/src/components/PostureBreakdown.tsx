import React from 'react';
import { CheckCircle2, AlertTriangle, Maximize2, MoveHorizontal } from 'lucide-react';
import { PostureDistribution } from '../types';

interface PostureBreakdownProps {
  distribution: PostureDistribution;
  deskTimeFormatted: string;
}

export const PostureBreakdown: React.FC<PostureBreakdownProps> = ({
  distribution,
  deskTimeFormatted,
}) => {
  const formatSeconds = (sec: number) => {
    const m = Math.floor(sec / 60);
    const h = Math.floor(m / 60);
    if (h > 0) return `${h}h ${m % 60}m`;
    if (m > 0) return `${m}m`;
    return `${Math.round(sec)}s`;
  };

  return (
    <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-6 shadow-sm mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
        <div>
          <h2 className="text-base font-semibold text-white">Posture Distribution</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Normalized across {deskTimeFormatted} total at-desk time (Total: {distribution.total_percentage}%)
          </p>
        </div>
        <span className="text-xs px-2.5 py-1 rounded-md bg-slate-700/50 text-slate-300 font-mono self-start sm:self-auto">
          Single-Model 33-Keypoint Lite
        </span>
      </div>

      {/* Multi-segment Progress Bar */}
      <div className="w-full h-3 bg-slate-900 rounded-full overflow-hidden flex mb-6 p-0.5 border border-slate-700/60">
        <div
          className="h-full bg-emerald-500 rounded-l transition-all duration-500"
          style={{ width: `${distribution.good.percentage}%` }}
          title={`Good Posture: ${distribution.good.formatted}`}
        />
        <div
          className="h-full bg-amber-500 transition-all duration-500"
          style={{ width: `${distribution.slouching.percentage}%` }}
          title={`Slouching: ${distribution.slouching.formatted}`}
        />
        <div
          className="h-full bg-rose-500 transition-all duration-500"
          style={{ width: `${distribution.too_close.percentage}%` }}
          title={`Too Close: ${distribution.too_close.formatted}`}
        />
        <div
          className="h-full bg-indigo-500 rounded-r transition-all duration-500"
          style={{ width: `${distribution.leaning.percentage}%` }}
          title={`Leaning: ${distribution.leaning.formatted}`}
        />
      </div>

      {/* Categories Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Good Posture */}
        <div className="bg-slate-900/50 border border-slate-700/40 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-medium text-slate-300">Good Posture</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xl font-bold text-emerald-400">
              {distribution.good.formatted}
            </span>
            <span className="text-xs text-slate-400 font-mono">
              {formatSeconds(distribution.good.seconds)}
            </span>
          </div>
        </div>

        {/* Slouching */}
        <div className="bg-slate-900/50 border border-slate-700/40 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1.5">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-medium text-slate-300">Slouching</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xl font-bold text-amber-400">
              {distribution.slouching.formatted}
            </span>
            <span className="text-xs text-slate-400 font-mono">
              {formatSeconds(distribution.slouching.seconds)}
            </span>
          </div>
        </div>

        {/* Too Close */}
        <div className="bg-slate-900/50 border border-slate-700/40 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1.5">
            <Maximize2 className="w-4 h-4 text-rose-400" />
            <span className="text-xs font-medium text-slate-300">Too Close</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xl font-bold text-rose-400">
              {distribution.too_close.formatted}
            </span>
            <span className="text-xs text-slate-400 font-mono">
              {formatSeconds(distribution.too_close.seconds)}
            </span>
          </div>
        </div>

        {/* Leaning */}
        <div className="bg-slate-900/50 border border-slate-700/40 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1.5">
            <MoveHorizontal className="w-4 h-4 text-indigo-400" />
            <span className="text-xs font-medium text-slate-300">Leaning / Tilt</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-xl font-bold text-indigo-400">
              {distribution.leaning.formatted}
            </span>
            <span className="text-xs text-slate-400 font-mono">
              {formatSeconds(distribution.leaning.seconds)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
