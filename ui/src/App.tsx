import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { DailyOverview } from './components/DailyOverview';
import { PostureBreakdown } from './components/PostureBreakdown';
import { CalibrationWizardModal } from './components/CalibrationWizardModal';
import { LiveStatusWidget } from './components/LiveStatusWidget';
import { SettingsModal } from './components/SettingsModal';
import { AlertBannerList } from './components/AlertBannerList';
import { DashboardData, CalibrationWizardStatus, WidgetConfig } from './types';

const DEFAULT_DASHBOARD: DashboardData = {
  date: new Date().toISOString().split('T')[0],
  metrics: {
    desk_time_sec: 24720,
    desk_time_formatted: '6h 52m',
    away_time_sec: 6660,
    away_time_formatted: '1h 51m',
    active_time_sec: 20940,
    active_time_formatted: '5h 49m',
    posture_score: 74.2,
    posture_score_formatted: '74%',
  },
  posture_distribution: {
    good: { seconds: 18292.8, percentage: 74.0, formatted: '74%' },
    slouching: { seconds: 4202.4, percentage: 17.0, formatted: '17%' },
    too_close: { seconds: 1483.2, percentage: 6.0, formatted: '6%' },
    leaning: { seconds: 741.6, percentage: 3.0, formatted: '3%' },
    total_percentage: 100.0,
  },
  alerts: [],
  has_error: false,
  camera_available: true,
  has_calibration: true,
  live: {
    posture: 'POSTURE_GOOD',
    attention: 'SCREEN',
    activity: 'ACTIVE_WORK',
    status_label: 'Good Posture',
    status_category: 'good',
    session_duration_sec: 2220,
    session_duration_formatted: '37m',
    is_paused: false,
    pause_remaining_sec: 0,
  },
  window_visible: true,
  active_view: 'dashboard',
  widget: {
    enabled: false,
    visible: false,
    x: 80,
    y: 80,
    opacity: 0.95,
    collapsed: false,
    always_on_top: true,
  },
};

const DEFAULT_WIZARD: CalibrationWizardStatus = {
  state: 'IDLE',
  countdown_sec: 3.0,
  capture_progress_pct: 0.0,
  sample_count: 0,
  min_required_samples: 15,
  failure_reason: null,
  has_profile: true,
};

export const App: React.FC = () => {
  const [data, setData] = useState<DashboardData>(DEFAULT_DASHBOARD);
  const [wizard, setWizard] = useState<CalibrationWizardStatus>(DEFAULT_WIZARD);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [widgetConfig, setWidgetConfig] = useState<WidgetConfig>(DEFAULT_DASHBOARD.widget);

  const fetchDashboard = useCallback(async () => {
    try {
      const res = await fetch('http://127.0.0.1:8765/api/dashboard');
      if (res.ok) {
        const json = await res.json();
        setData(json);
        if (json.widget) {
          setWidgetConfig(json.widget);
        }
      }
    } catch {
      // Backend not running or offline; keep in-memory data
    }
  }, []);

  const fetchWizard = useCallback(async () => {
    try {
      const res = await fetch('http://127.0.0.1:8765/api/wizard');
      if (res.ok) {
        const json = await res.json();
        setWizard(json);
      }
    } catch {
      // Offline fallback
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
    const timer = setInterval(() => {
      fetchDashboard();
      if (wizard.state !== 'IDLE') {
        fetchWizard();
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [fetchDashboard, fetchWizard, wizard.state]);

  const handlePause = async (durationSec: number) => {
    try {
      await fetch('http://127.0.0.1:8765/api/tray', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          command: durationSec >= 3600 ? 'pause_1_hour' : 'pause_15_min',
        }),
      });
      fetchDashboard();
    } catch {
      // Fallback local update
      setData((prev) => ({
        ...prev,
        live: {
          ...prev.live,
          is_paused: true,
          status_label: `Paused (${Math.round(durationSec / 60)}m remaining)`,
          status_category: 'paused',
        },
      }));
    }
  };

  const handleResume = async () => {
    try {
      await fetch('http://127.0.0.1:8765/api/tray', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: 'resume' }),
      });
      fetchDashboard();
    } catch {
      setData((prev) => ({
        ...prev,
        live: {
          ...prev.live,
          is_paused: false,
          status_label: 'Good Posture',
          status_category: 'good',
        },
      }));
    }
  };

  const handleStartCalibration = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8765/api/wizard/start', { method: 'POST' });
      if (res.ok) {
        const json = await res.json();
        setWizard(json);
      }
    } catch {
      setWizard((prev) => ({ ...prev, state: 'GUIDANCE', failure_reason: null }));
    }
  };

  const handleStartCountdown = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8765/api/wizard/countdown', { method: 'POST' });
      if (res.ok) {
        const json = await res.json();
        setWizard(json);
      }
    } catch {
      setWizard((prev) => ({ ...prev, state: 'COUNTDOWN', countdown_sec: 3.0 }));
    }
  };

  const handleFinishCalibration = async () => {
    try {
      await fetch('http://127.0.0.1:8765/api/wizard/finish', { method: 'POST' });
    } catch {
      // Fallback
    }
    setWizard((prev) => ({ ...prev, state: 'IDLE' }));
    fetchDashboard();
  };

  const handleRetryCalibration = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8765/api/wizard/retry', { method: 'POST' });
      if (res.ok) {
        const json = await res.json();
        setWizard(json);
      }
    } catch {
      setWizard((prev) => ({ ...prev, state: 'GUIDANCE', failure_reason: null }));
    }
  };

  const handleCancelCalibration = async () => {
    try {
      await fetch('http://127.0.0.1:8765/api/wizard/cancel', { method: 'POST' });
    } catch {
      // Fallback
    }
    setWizard((prev) => ({ ...prev, state: 'IDLE' }));
  };

  const handleCloseToTray = async () => {
    try {
      await fetch('http://127.0.0.1:8765/api/window/close', { method: 'POST' });
    } catch {
      // Fallback
    }
  };

  const handleUpdateWidgetConfig = async (newConfig: Partial<WidgetConfig>) => {
    const updated = { ...widgetConfig, ...newConfig };
    setWidgetConfig(updated);
    try {
      await fetch('http://127.0.0.1:8765/api/widget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig),
      });
    } catch {
      // Fallback
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Header */}
      <Header
        data={data}
        onPause={handlePause}
        onResume={handleResume}
        onRecalibrate={handleStartCalibration}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onCloseToTray={handleCloseToTray}
      />

      {/* Main Dashboard Content */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-6">
        {/* System Alert Banners (Empty Day, Disconnected Camera, Missing Calibration) */}
        <AlertBannerList
          alerts={data.alerts}
          onStartCalibration={handleStartCalibration}
        />

        {/* Daily Overview Metric Cards */}
        <DailyOverview metrics={data.metrics} />

        {/* Posture Distribution Breakdown */}
        <PostureBreakdown
          distribution={data.posture_distribution}
          deskTimeFormatted={data.metrics.desk_time_formatted}
        />

        {/* Live Details & Context */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-slate-400">
          <div className="flex items-center gap-4">
            <div>
              <span className="font-semibold text-slate-300">Active Window:</span>{' '}
              <span className="font-mono text-indigo-300">{data.live.activity}</span>
            </div>
            <div>
              <span className="font-semibold text-slate-300">Attention:</span>{' '}
              <span className="font-mono text-emerald-300">{data.live.attention}</span>
            </div>
          </div>
          <div className="text-right">
            <span>Global Hotkey: </span>
            <kbd className="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-[11px] font-mono text-slate-200">
              Ctrl + Shift + P
            </kbd>{' '}
            to Pause/Resume
          </div>
        </div>
      </main>

      {/* Floating Status Widget (Overlay) */}
      <LiveStatusWidget
        config={widgetConfig}
        live={data.live}
        onUpdateConfig={handleUpdateWidgetConfig}
      />

      {/* Calibration Wizard Modal */}
      <CalibrationWizardModal
        status={wizard}
        onStartCountdown={handleStartCountdown}
        onFinish={handleFinishCalibration}
        onRetry={handleRetryCalibration}
        onCancel={handleCancelCalibration}
      />

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        widgetConfig={widgetConfig}
        onUpdateWidgetConfig={handleUpdateWidgetConfig}
      />
    </div>
  );
};
