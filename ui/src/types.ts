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
  timeline?: TimelineSegment[];
  focus?: FocusTotals;
  phone_dashboard?: PhoneDashboardSummary;
  summary?: DailySummaryData;
  category_rules?: CategoryRule[];
  performance?: AdaptivePerfStatus;
  multi_monitor?: MultiMonitorStatus;
  startup_enabled?: boolean;
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

export interface TimelineSegment {
  start_time: number;
  end_time: number;
  start_time_str: string;
  end_time_str: string;
  duration: number;
  state: string;
  label: string;
  color: string;
  category: string;
}

export interface FocusTotals {
  total_focus_time: number;
  session_count: number;
  longest_session: number;
  average_session: number;
  distraction_count: number;
}

export interface PhoneDashboardSummary {
  estimated_phone_usage: number;
  estimated_sessions: number;
  longest_session: number;
  average_session: number;
  wording: string;
}

export interface CategoryRule {
  id: number;
  pattern: string;
  rule_type: 'process' | 'title';
  category: string;
  is_user_override: number;
}

export interface DailySummaryData {
  date: string;
  metrics: {
    focus_seconds: number;
    desk_seconds: number;
    away_seconds: number;
    estimated_phone_seconds: number;
    posture_score: number;
    break_count: number;
    longest_focus_seconds: number;
  };
  score: {
    daily_wellness_score: number;
    components: {
      focus: number;
      posture: number;
      breaks: number;
      phone: number;
      consistency: number;
    };
  };
  insights: string[];
  wording_disclaimer: string;
}

export interface AdaptivePerfStatus {
  power_source: 'AC' | 'BATTERY';
  profile: string;
  target_fps: number;
  phone_scan_fps: number;
  ui_animations_enabled: boolean;
  cpu_usage_pct: number;
  is_thermal_throttled: boolean;
  user_present: boolean;
  is_away_sustained: boolean;
}

export interface MultiMonitorStatus {
  monitors: string[];
  has_left: boolean;
  has_right: boolean;
  has_up: boolean;
}
