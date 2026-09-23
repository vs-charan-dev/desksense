import React from 'react';
import { Camera, CheckCircle2, AlertCircle, RefreshCw, X, Shield, ArrowRight, UserCheck } from 'lucide-react';
import { CalibrationWizardStatus } from '../types';

interface CalibrationWizardModalProps {
  status: CalibrationWizardStatus;
  onStartCountdown: () => void;
  onFinish: () => void;
  onRetry: () => void;
  onCancel: () => void;
}

export const CalibrationWizardModal: React.FC<CalibrationWizardModalProps> = ({
  status,
  onStartCountdown,
  onFinish,
  onRetry,
  onCancel,
}) => {
  if (status.state === 'IDLE') return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
              <Camera className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-white">Posture Baseline Calibration</h3>
              <p className="text-xs text-slate-400">Establish your healthy ergonomic baseline</p>
            </div>
          </div>
          <button
            onClick={onCancel}
            className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
            title="Cancel calibration"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step 1: Guidance */}
        {status.state === 'GUIDANCE' && (
          <div className="py-6 space-y-4">
            <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4 space-y-3">
              <div className="flex items-start gap-3">
                <UserCheck className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-medium text-white">1. Sit in your natural healthy posture</h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Sit upright comfortably with your eyes level with the top third of your monitor.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <Camera className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-medium text-white">2. Check camera positioning</h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Ensure both shoulders and your full head are clearly in camera frame.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <Shield className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-medium text-white">3. Adequate lighting & privacy</h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Ensure face is lit. Frames are processed strictly in volatile RAM and immediately discarded.
                  </p>
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={onCancel}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition"
              >
                Cancel
              </button>
              <button
                onClick={onStartCountdown}
                className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition shadow-lg shadow-indigo-600/30"
              >
                <span>Ready — Start Calibration</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* Step 2: 3-Second Countdown */}
        {status.state === 'COUNTDOWN' && (
          <div className="py-12 flex flex-col items-center justify-center text-center">
            <div className="w-20 h-20 rounded-full border-4 border-indigo-500/30 border-t-indigo-500 animate-spin flex items-center justify-center mb-4">
              <span className="text-3xl font-bold font-mono text-indigo-400 animate-none">
                {Math.ceil(status.countdown_sec)}
              </span>
            </div>
            <h4 className="text-base font-semibold text-white">Get into position...</h4>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">
              Sit upright naturally. Calibration begins in {Math.ceil(status.countdown_sec)} seconds.
            </p>
          </div>
        )}

        {/* Step 3: 10-Second Capturing */}
        {status.state === 'CAPTURING' && (
          <div className="py-8 space-y-6 text-center">
            <div className="space-y-2">
              <div className="inline-flex p-3 rounded-full bg-indigo-500/10 text-indigo-400 mb-2 animate-pulse">
                <Camera className="w-8 h-8" />
              </div>
              <h4 className="text-base font-semibold text-white">Capturing Posture Baseline</h4>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                Hold your natural posture. Calculating inter-eye baseline, shoulder span, and head angle...
              </p>
            </div>

            {/* Progress Bar */}
            <div className="space-y-2">
              <div className="flex justify-between text-xs text-slate-400 font-mono px-1">
                <span>Progress: {Math.round(status.capture_progress_pct)}%</span>
                <span>{status.sample_count} / {status.min_required_samples} samples</span>
              </div>
              <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden border border-slate-700">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 to-emerald-500 transition-all duration-300"
                  style={{ width: `${status.capture_progress_pct}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Success */}
        {status.state === 'SUCCESS' && (
          <div className="py-6 space-y-5 text-center">
            <div className="w-16 h-16 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center justify-center mx-auto">
              <CheckCircle2 className="w-8 h-8" />
            </div>
            <div>
              <h4 className="text-lg font-bold text-white">Baseline Calibrated Successfully!</h4>
              <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                Your ergonomic baseline has been computed and securely stored on this device.
              </p>
            </div>

            <div className="flex justify-center pt-2">
              <button
                onClick={onFinish}
                className="px-6 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition shadow-lg shadow-emerald-600/30"
              >
                Complete & Start Monitoring
              </button>
            </div>
          </div>
        )}

        {/* Step 5: Failure / Recovery */}
        {status.state === 'FAILED' && (
          <div className="py-6 space-y-5">
            <div className="flex items-center gap-3 p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400">
              <AlertCircle className="w-6 h-6 shrink-0" />
              <div>
                <h4 className="text-sm font-semibold">Calibration Unsuccessful</h4>
                <p className="text-xs text-rose-300 mt-0.5">
                  {status.failure_reason || 'Quality criteria could not be verified.'}
                </p>
              </div>
            </div>

            <div className="text-xs text-slate-400 space-y-1 bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
              <p className="font-semibold text-slate-300">Suggestions:</p>
              <ul className="list-disc list-inside space-y-0.5">
                <li>Check that camera lens is uncovered and well-lit.</li>
                <li>Ensure your shoulders and upper torso are visible.</li>
                <li>Avoid extreme head tilt or moving rapidly during the 10 seconds.</li>
              </ul>
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={onCancel}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 transition"
              >
                Cancel (Keep Previous)
              </button>
              <button
                onClick={onRetry}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Retry Calibration</span>
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};
