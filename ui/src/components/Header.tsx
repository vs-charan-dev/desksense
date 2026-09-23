import React from 'react';
import { Play, Pause, Compass, Settings, Minus, X, ShieldCheck } from 'lucide-react';
import { DashboardData } from '../types';

interface HeaderProps {
  data: DashboardData;
  onPause: (durationSec: number) => void;
  onResume: () => void;
  onRecalibrate: () => void;
  onOpenSettings: () => void;
  onCloseToTray: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  data,
  onPause,
  onResume,
  onRecalibrate,
  onOpenSettings,
  onCloseToTray,
}) => {
  const isPaused = data.live.is_paused;
  const statusLabel = data.live.status_label;
  const statusCat = data.live.status_category;

  const getStatusColor = () => {
    switch (statusCat) {
      case 'good':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40';
      case 'warning':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/40';
      case 'paused':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/40';
      default:
        return 'bg-slate-700/40 text-slate-300 border-slate-600';
    }
  };

  const getDotColor = () => {
    switch (statusCat) {
      case 'good':
        return 'bg-emerald-400';
      case 'warning':
        return 'bg-amber-400 animate-pulse';
      case 'paused':
        return 'bg-blue-400';
      default:
        return 'bg-slate-400';
    }
  };

  return (
    <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-30 select-none">
      {/* Brand & Status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-600/30">
            D
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight text-white">DeskSense</h1>
              <span className="text-[11px] font-medium px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center gap-1">
                <ShieldCheck className="w-3 h-3" /> Local Only
              </span>
            </div>
          </div>
        </div>

        <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${getStatusColor()}`}>
          <span className={`w-2 h-2 rounded-full ${getDotColor()}`} />
          <span>{statusLabel}</span>
        </div>
      </div>

      {/* Session Timer & Action Controls */}
      <div className="flex items-center gap-3">
        <div className="text-right mr-2 hidden sm:block">
          <div className="text-xs text-slate-400">Current Session</div>
          <div className="text-sm font-mono font-semibold text-slate-200">
            {data.live.session_duration_formatted}
          </div>
        </div>

        {/* Pause/Resume Toggle */}
        {isPaused ? (
          <button
            onClick={onResume}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition shadow-sm"
            title="Resume monitoring"
          >
            <Play className="w-3.5 h-3.5" />
            <span>Resume</span>
          </button>
        ) : (
          <div className="flex items-center gap-1">
            <button
              onClick={() => onPause(900)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition"
              title="Pause monitoring for 15 minutes"
            >
              <Pause className="w-3.5 h-3.5 text-slate-400" />
              <span>Pause 15m</span>
            </button>
            <button
              onClick={() => onPause(3600)}
              className="hidden md:flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition"
              title="Pause monitoring for 1 hour"
            >
              <span>1h</span>
            </button>
          </div>
        )}

        {/* Recalibrate Posture */}
        <button
          onClick={onRecalibrate}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition"
          title="Recalibrate natural baseline posture"
        >
          <Compass className="w-3.5 h-3.5 text-indigo-400" />
          <span className="hidden sm:inline">Calibrate</span>
        </button>

        {/* Settings */}
        <button
          onClick={onOpenSettings}
          className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700 transition"
          title="Settings"
        >
          <Settings className="w-4 h-4" />
        </button>

        {/* Window controls (minimize & hide to tray) */}
        <div className="flex items-center border-l border-slate-800 pl-3 ml-1 gap-1">
          <button
            onClick={onCloseToTray}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
            title="Minimize to Tray"
          >
            <Minus className="w-4 h-4" />
          </button>
          <button
            onClick={onCloseToTray}
            className="p-1.5 rounded-lg hover:bg-red-500/20 text-slate-400 hover:text-red-400 transition"
            title="Hide to Tray (Monitoring continues)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
