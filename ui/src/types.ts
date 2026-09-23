export type PostureState = 
  | 'POSTURE_GOOD' 
  | 'SLOUCHING' 
  | 'TOO_CLOSE' 
  | 'LEAN_LEFT' 
  | 'LEAN_RIGHT' 
  | 'HEAD_TILT' 
  | 'UNKNOWN';

export type AttentionState = 'SCREEN' | 'LEFT' | 'RIGHT' | 'DOWN' | 'AWAY';
export type ActivityState = 'FOCUSED_WORK' | 'ACTIVE_WORK' | 'DISTRACTED' | 'IDLE' | 'AWAY' | 'BREAK' | 'UNKNOWN';

export type MonitoringState = 
  | 'MONITORING' 
  | 'PAUSED' 
  | 'CALIBRATING' 
  | 'CAMERA_UNAVAILABLE' 
  | 'STOPPED';

export interface DashboardMetrics {
  desk_time_sec: number;
  desk_time_formatted: string;
  away_time_sec: number;
  away_time_formatted: string;
  active_time_sec: number;
  active_time_formatted: string;
  posture_score: number;
  posture_score_formatted: string;
}

export interface PostureCategory {
  seconds: number;
  percentage: number;
  formatted: string;
}

export interface PostureDistribution {
  good: PostureCategory;
  slouching: PostureCategory;
  too_close: PostureCategory;
  leaning: PostureCategory;
  total_percentage: number;
}

export interface AlertBanner {
  type: 'error' | 'warning' | 'info' | 'empty';
  message: string;
}

export interface LiveState {
  posture: string;
  attention: string;
  activity: string;
  status_label: string;
  status_category: 'good' | 'warning' | 'neutral' | 'paused';
  session_duration_sec: number;
  session_duration_formatted: string;
  is_paused: boolean;
  pause_remaining_sec: number;
}

export interface DashboardData {
  date: string;
  metrics: DashboardMetrics;
  posture_distribution: PostureDistribution;
  alerts: AlertBanner[];
  has_error: boolean;
  camera_available: boolean;
  has_calibration: boolean;
  live: LiveState;
  window_visible: boolean;
  active_view: 'dashboard' | 'calibration' | 'settings';
  widget: WidgetConfig;
}

export interface WidgetConfig {
  enabled: boolean;
  visible: boolean;
  x: number;
  y: number;
  opacity: number;
  collapsed: boolean;
  always_on_top: boolean;
}

export type WizardStep = 'IDLE' | 'GUIDANCE' | 'COUNTDOWN' | 'CAPTURING' | 'SUCCESS' | 'FAILED';

export interface CalibrationWizardStatus {
  state: WizardStep;
  countdown_sec: number;
  capture_progress_pct: number;
  sample_count: number;
  min_required_samples: number;
  failure_reason: string | null;
  has_profile: boolean;
}
