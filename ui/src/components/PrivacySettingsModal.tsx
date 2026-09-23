import React, { useState } from 'react';

interface PrivacySettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  startupEnabled?: boolean;
  hasLeftMonitor?: boolean;
  hasRightMonitor?: boolean;
  onToggleMonitor: (pos: string) => Promise<void>;
  onToggleStartup: (enabled: boolean) => Promise<void>;
  onApplyRetention: (policy: string) => Promise<void>;
  onWipeData: () => Promise<void>;
}

export const PrivacySettingsModal: React.FC<PrivacySettingsModalProps> = ({
  isOpen,
  onClose,
  startupEnabled = false,
  hasLeftMonitor = false,
  hasRightMonitor = false,
  onToggleMonitor,
  onToggleStartup,
  onApplyRetention,
  onWipeData,
}) => {
  const [retentionPolicy, setRetentionPolicy] = useState('30_days');
  const [showConfirmWipe, setShowConfirmWipe] = useState(false);
  const [isWiping, setIsWiping] = useState(false);

  if (!isOpen) return null;

  const handleExportJson = () => {
    window.open('http://127.0.0.1:8765/api/privacy/export/json', '_blank');
  };

  const handleExportCsv = () => {
    window.open('http://127.0.0.1:8765/api/privacy/export/csv', '_blank');
  };

  const handleConfirmWipe = async () => {
    setIsWiping(true);
    try {
      await onWipeData();
      setShowConfirmWipe(false);
    } finally {
      setIsWiping(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-xl w-full p-6 shadow-2xl flex flex-col max-h-[88vh] overflow-y-auto">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-slate-100">Privacy, Workspace & Storage</h2>
            <p className="text-xs text-slate-400">Manage data retention, multi-display setup, export, and startup</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-2 rounded-xl hover:bg-slate-800 transition"
          >
            ✕
          </button>
        </div>

        <div className="space-y-6 mt-4">
          {/* Multi-Monitor Workspace */}
          <div className="p-4 bg-slate-950/60 rounded-2xl border border-slate-800">
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-2">Multi-Monitor Setup</span>
            <p className="text-xs text-slate-400 mb-3">
              Configure external displays. Looking toward configured displays counts as focused screen attention rather than distraction.
            </p>
            <div className="flex items-center gap-3">
              <button
                onClick={() => onToggleMonitor('LEFT')}
                className={`flex-1 py-2 rounded-xl text-xs font-medium border transition ${
                  hasLeftMonitor
                    ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/40'
                    : 'bg-slate-900 text-slate-400 border-slate-800 hover:bg-slate-800'
                }`}
              >
                Left Display {hasLeftMonitor ? '✓' : '+'}
              </button>
              <div className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold border border-indigo-500 shadow-md">
                Center (Laptop / WebCam)
              </div>
              <button
                onClick={() => onToggleMonitor('RIGHT')}
                className={`flex-1 py-2 rounded-xl text-xs font-medium border transition ${
                  hasRightMonitor
                    ? 'bg-indigo-600/20 text-indigo-300 border-indigo-500/40'
                    : 'bg-slate-900 text-slate-400 border-slate-800 hover:bg-slate-800'
                }`}
              >
                Right Display {hasRightMonitor ? '✓' : '+'}
              </button>
            </div>
          </div>

          {/* Windows Startup */}
          <div className="p-4 bg-slate-950/60 rounded-2xl border border-slate-800 flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-slate-300 block">Launch on Windows Startup</span>
              <p className="text-xs text-slate-400">Starts automatically minimized to the tray when you log in</p>
            </div>
            <button
              onClick={() => onToggleStartup(!startupEnabled)}
              className={`w-12 h-6 rounded-full transition-colors relative ${startupEnabled ? 'bg-indigo-600' : 'bg-slate-800'}`}
            >
              <div
                className={`w-4 h-4 bg-white rounded-full absolute top-1 transition-transform ${
                  startupEnabled ? 'left-7' : 'left-1'
                }`}
              />
            </button>
          </div>

          {/* Retention Policy */}
          <div className="p-4 bg-slate-950/60 rounded-2xl border border-slate-800">
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider block mb-2">Automated Data Retention</span>
            <p className="text-xs text-slate-400 mb-3">
              Automatically prunes local activity history older than the configured period. Settings and calibration are never removed.
            </p>
            <div className="flex items-center gap-3">
              <select
                value={retentionPolicy}
                onChange={(e) => setRetentionPolicy(e.target.value)}
                className="bg-slate-900 border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none flex-1"
              >
                <option value="7_days">7 Days</option>
                <option value="30_days">30 Days (Recommended)</option>
                <option value="90_days">90 Days</option>
                <option value="365_days">1 Year</option>
                <option value="forever">Forever (No auto-delete)</option>
              </select>
              <button
                onClick={() => onApplyRetention(retentionPolicy)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-medium transition"
              >
                Apply
              </button>
            </div>
          </div>

          {/* Export & Wipe */}
          <div className="p-4 bg-slate-950/60 rounded-2xl border border-slate-800 space-y-3">
            <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider block">Portability & Privacy</span>
            <div className="flex gap-3">
              <button
                onClick={handleExportJson}
                className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-medium transition"
              >
                Export JSON
              </button>
              <button
                onClick={handleExportCsv}
                className="flex-1 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-medium transition"
              >
                Export CSV
              </button>
            </div>
            <div className="pt-2 border-t border-slate-800/80">
              {showConfirmWipe ? (
                <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl space-y-2">
                  <p className="text-xs text-rose-300 font-medium">Are you sure? This will permanently delete all activity history.</p>
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setShowConfirmWipe(false)}
                      className="px-3 py-1 bg-slate-800 text-slate-300 rounded-lg text-xs"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleConfirmWipe}
                      disabled={isWiping}
                      className="px-3 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-xs font-semibold"
                    >
                      {isWiping ? 'Wiping...' : 'Confirm Wipe'}
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowConfirmWipe(true)}
                  className="w-full py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 rounded-xl text-xs font-medium transition"
                >
                  Wipe All Activity Data
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="mt-6 pt-4 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-semibold transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
