import React from 'react';
import { X, Bell, Layout, ShieldAlert, Cpu } from 'lucide-react';
import { WidgetConfig } from '../types';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  widgetConfig: WidgetConfig;
  onUpdateWidgetConfig: (newConfig: Partial<WidgetConfig>) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  widgetConfig,
  onUpdateWidgetConfig,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 shadow-2xl relative animate-in fade-in zoom-in-95 duration-200">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <h3 className="text-base font-semibold text-white">DeskSense Settings</h3>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="py-5 space-y-6">
          {/* Notifications */}
          <div>
            <div className="flex items-center gap-2 mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Bell className="w-4 h-4 text-indigo-400" />
              <span>Notification Preferences</span>
            </div>
            <div className="space-y-2 bg-slate-800/50 p-3 rounded-xl border border-slate-700/50 text-xs">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-slate-200">Slouching Alerts</div>
                  <div className="text-[11px] text-slate-400">Toast after 25s continuous slouch</div>
                </div>
                <input type="checkbox" defaultChecked className="rounded text-indigo-600 focus:ring-0" />
              </div>
              <div className="flex items-center justify-between pt-2 border-t border-slate-700/40">
                <div>
                  <div className="font-medium text-slate-200">Distance Alerts</div>
                  <div className="text-[11px] text-slate-400">Alert when leaning too close to screen</div>
                </div>
                <input type="checkbox" defaultChecked className="rounded text-indigo-600 focus:ring-0" />
              </div>
              <div className="flex items-center justify-between pt-2 border-t border-slate-700/40">
                <div>
                  <div className="font-medium text-slate-200">Shared Alert Cooldown</div>
                  <div className="text-[11px] text-slate-400">Minimum 5 minutes between notifications</div>
                </div>
                <span className="text-slate-400 font-mono">5 min</span>
              </div>
            </div>
          </div>

          {/* Live Status Widget */}
          <div>
            <div className="flex items-center gap-2 mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Layout className="w-4 h-4 text-indigo-400" />
              <span>Floating Status Widget</span>
            </div>
            <div className="space-y-3 bg-slate-800/50 p-3 rounded-xl border border-slate-700/50 text-xs">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-slate-200">Enable Floating Widget</div>
                  <div className="text-[11px] text-slate-400">Minimal desktop status pill overlay</div>
                </div>
                <input
                  type="checkbox"
                  checked={widgetConfig.enabled}
                  onChange={(e) => {
                    const enabled = e.target.checked;
                    onUpdateWidgetConfig({ enabled, visible: enabled });
                  }}
                  className="rounded text-indigo-600 focus:ring-0"
                />
              </div>

              {widgetConfig.enabled && (
                <>
                  <div className="pt-2 border-t border-slate-700/40">
                    <div className="flex justify-between text-[11px] text-slate-400 mb-1">
                      <span>Widget Opacity</span>
                      <span>{Math.round(widgetConfig.opacity * 100)}%</span>
                    </div>
                    <input
                      type="range"
                      min="0.2"
                      max="1.0"
                      step="0.05"
                      value={widgetConfig.opacity}
                      onChange={(e) => onUpdateWidgetConfig({ opacity: parseFloat(e.target.value) })}
                      className="w-full accent-indigo-500"
                    />
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-slate-700/40">
                    <span className="text-slate-200">Always on Top</span>
                    <input
                      type="checkbox"
                      checked={widgetConfig.always_on_top}
                      onChange={(e) => onUpdateWidgetConfig({ always_on_top: e.target.checked })}
                      className="rounded text-indigo-600 focus:ring-0"
                    />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Privacy & Hardware Engine */}
          <div>
            <div className="flex items-center gap-2 mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              <Cpu className="w-4 h-4 text-indigo-400" />
              <span>Engine & Privacy Guarantees</span>
            </div>
            <div className="bg-slate-800/30 p-3 rounded-xl border border-slate-700/40 text-[11px] text-slate-400 space-y-1">
              <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
                <ShieldAlert className="w-3.5 h-3.5" />
                <span>Zero Frame Persistence Active</span>
              </div>
              <p>
                Video frames exist strictly in volatile memory during inference and are immediately freed via in-memory garbage collection. No frames, video files, or screenshots are written to disk or transmitted over the internet.
              </p>
            </div>
          </div>
        </div>

        <div className="flex justify-end pt-2 border-t border-slate-800">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
