import React from 'react';
import { AlertCircle, AlertTriangle, Info, Calendar } from 'lucide-react';
import { AlertBanner } from '../types';

interface AlertBannerListProps {
  alerts: AlertBanner[];
  onStartCalibration?: () => void;
}

export const AlertBannerList: React.FC<AlertBannerListProps> = ({
  alerts,
  onStartCalibration,
}) => {
  if (!alerts || alerts.length === 0) return null;

  return (
    <div className="space-y-3 mb-6">
      {alerts.map((alert, idx) => {
        if (alert.type === 'error') {
          return (
            <div
              key={idx}
              className="flex items-center gap-3 p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs"
            >
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{alert.message}</span>
            </div>
          );
        }

        if (alert.type === 'warning') {
          return (
            <div
              key={idx}
              className="flex items-center gap-3 p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs"
            >
              <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
              <span>{alert.message}</span>
            </div>
          );
        }

        if (alert.type === 'info') {
          return (
            <div
              key={idx}
              className="flex items-center justify-between gap-3 p-3.5 rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs"
            >
              <div className="flex items-center gap-3">
                <Info className="w-4 h-4 shrink-0 text-indigo-400" />
                <span>{alert.message}</span>
              </div>
              {onStartCalibration && (
                <button
                  onClick={onStartCalibration}
                  className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs transition shrink-0"
                >
                  Start Calibration
                </button>
              )}
            </div>
          );
        }

        if (alert.type === 'empty') {
          return (
            <div
              key={idx}
              className="flex items-center gap-3 p-4 rounded-xl bg-slate-800/40 border border-slate-700/40 text-slate-300 text-xs"
            >
              <Calendar className="w-4 h-4 shrink-0 text-slate-400" />
              <span>{alert.message} Monitoring is running in the background.</span>
            </div>
          );
        }

        return null;
      })}
    </div>
  );
};
