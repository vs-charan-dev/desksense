# DeskSense — Project Implementation Phases & Architecture Plan

## Executive Overview
DeskSense is a privacy-first, local-first Windows desktop workspace intelligence and posture coach. It processes webcam video and Windows desktop signals strictly on-device, discarding video frames immediately without recording or cloud streaming.

This document breaks down the development of DeskSense from architectural groundwork to a fully featured desktop application across structured phases.

---

## Technical Architecture & Stack Selection

- **Desktop Shell & Host:** **Tauri v2 (Rust)** — lightweight footprint (<50MB memory overhead for host), native Windows system tray integration, global hotkeys, Windows notification toasts, and secure IPC.
- **Frontend / Dashboard:** **React 18 + TypeScript + Vite + Tailwind CSS** — modern, responsive UI for dashboard metrics, live status widget, calibration wizard, and timeline visualization.
- **Inference & Vision Engine:** **Python Sidecar / Embedded Engine (OpenCV + MediaPipe Face/Pose + ONNX Runtime YOLO-nano)** — isolated process communicating over local IPC/WebSocket to ensure UI responsiveness even under inference load.
- **System Activity Monitor:** **Native Win32 API / Rust `windows-rs` (or Python Win32)** — non-intrusive polling for active window title, process executable, and user idle duration (`GetLastInputInfo`).
- **Database & Aggregation:** **SQLite (via `rusqlite` or local embedded driver)** with automated retention and temporal aggregation.

---

## Phase Breakdown

```
Phase 0: Technical Foundation & Computer Vision Prototype
   │
Phase 1: Vision Core & Posture Engine (MVP 1 Core)
   │
Phase 2: Desktop Activity Tracking & Local Data Layer (MVP 1 Core)
   │
Phase 3: Desktop Shell, Calibration Wizard & MVP 1 Dashboard
   │
Phase 4: Phone Detection & Signal Fusion Engine (MVP 2)
   │
Phase 5: Timeline Visualizer, Focus Engine & MVP 2 Polish
   │
Phase 6: Performance Optimization, Battery Adaptation & Advanced Insights (MVP 3)
```

---

### Phase 0: Technical Foundation & Computer Vision Prototype
**Objective:** Validate feasibility, resource consumption targets (<10% CPU, <500MB RAM, 5–10 FPS), and local vision pipelines before assembling the full UI shell.

- **0.1 Architecture Setup:**
  - Establish repo structure: Desktop shell (Tauri/React), Sidecar vision engine, and shared schema contracts.
  - Define inter-process communication protocol (JSON-RPC over local socket or stdio).
- **0.2 Standalone Vision Prototype (`cv_prototype`):**
  - Implement OpenCV camera capture constrained to 640×480 resolution at 5–10 FPS.
  - Integrate MediaPipe Pose and Face landmark detection models.
  - Verify zero frame persistence (frames processed strictly in memory and discarded).
- **0.3 Benchmark & Profiling:**
  - Measure CPU and RAM utilization on baseline Intel Core i5 environment.
  - Validate frame skipping and adaptive throttling mechanics.

---

### Phase 1: Vision Core & Posture Engine (MVP 1 Core)
**Objective:** Build the core logic for presence, posture calibration, posture classification, coarse attention, and temporal state smoothing.

- **1.1 Module 1 — Presence Detection:**
  - Detect user face/body presence in camera frame.
  - Implement `PRESENT`, `AWAY`, and `UNKNOWN` states.
  - Introduce absence hysteresis (e.g., mark `AWAY` only after sustained lack of detection for >15 seconds).
- **1.2 Module 2 — Calibration Engine:**
  - Implement 10-second posture baseline capture sequence with quality checks (lighting adequacy, head and shoulder visibility).
  - Compute normalized metrics: inter-eye distance, head-to-shoulder angle, shoulder span, and baseline ear-to-shoulder alignment.
  - Persist calibration profile locally.
- **1.3 Module 3 — Posture Classifier:**
  - Classify frame into `POSTURE_GOOD`, `SLOUCHING`, `TOO_CLOSE`, `LEAN_LEFT`, `LEAN_RIGHT`, or `HEAD_TILT`.
  - Calculate relative distance shift using calibrated face bounding box and inter-eye distance.
- **1.4 Module 4 — Coarse Screen Attention Estimation:**
  - Estimate head pose orientation (pitch, yaw, roll).
  - Classify direction: `SCREEN`, `LEFT`, `RIGHT`, `DOWN`, `AWAY`.
- **1.5 Module 5 — Temporal Smoothing & State Filter:**
  - Implement rolling window buffer and majority voting / hysteresis filter to eliminate jitter.
  - Implement notification persistence threshold (e.g., posture deviation must persist continuously for 20–30 seconds before triggering alert).

---

### Phase 2: Desktop Activity Tracking & Local Data Layer (MVP 1 Core)
**Objective:** Monitor Windows system interactions, track session lifecycles, and persist structured telemetry into local SQLite storage.

- **2.1 Module 1 — Windows Foreground Activity Tracker:**
  - Query active window handle via Win32 API (`GetForegroundWindow`, `GetWindowText`, `GetWindowThreadProcessId`).
  - Extract process name and executable path.
  - Track user idle time via `GetLastInputInfo` (keyboard/mouse inactivity).
- **2.2 Module 2 — System Lifecycle Event Listener:**
  - Listen for Windows session lock, sleep, resume, and hibernation events.
  - Automatically close active work sessions on lock/sleep and initialize new sessions on unlock/wake.
  - Handle camera disconnection or camera access contention gracefully without crashing.
- **2.3 Module 3 — SQLite Database Engine:**
  - Design and implement SQLite schema:
    - `settings`
    - `sessions`
    - `posture_events`
    - `attention_events`
    - `app_usage`
    - `daily_summary`
  - Implement efficient downsampling and batch aggregation to keep database size compact.
- **2.4 Module 4 — Notification Subsystem:**
  - Native Windows toast notification dispatcher.
  - Enforce notification cooldowns (e.g., 5-minute cooldown) to prevent alert fatigue.

---

### Phase 3: Desktop Shell, Calibration Wizard & MVP 1 Dashboard
**Objective:** Connect the frontend application, create tray controls, build the calibration wizard, and deliver a working MVP 1 application.

- **3.1 Desktop Shell & System Tray:**
  - Configure Tauri window management (start minimized to tray, hide on close).
  - Build Windows system tray menu:
    - Status indicator (● Monitoring)
    - Open Dashboard
    - Pause monitoring (15 min / 1 hour / custom)
    - Recalibrate Posture
    - Settings & Quit
  - Register global hotkey (`Ctrl + Shift + P`) for instantaneous monitoring pause/resume.
- **3.2 Calibration UI Wizard:**
  - Guided step-by-step UI with visual feedback for camera placement, lighting, and shoulder detection.
  - 3-second countdown and 10-second natural posture calibration run.
- **3.3 Daily Overview Dashboard (MVP 1):**
  - Daily metric cards: At-Desk Time, Away Time, Posture Score (%), Active Computer Time.
  - Posture distribution breakdown (Good vs. Slouching vs. Too Close vs. Leaning).
  - Live session timer and status cards.
- **3.4 Live Status Widget (Optional Overlay):**
  - Minimal floating always-on-top pill widget displaying current state (e.g., `● Focused | Posture: Good`).
  - Draggable, collapsible, with opacity and display toggle settings.

---

### Phase 4: Phone Detection & Signal Fusion Engine (MVP 2)
**Objective:** Add intelligent phone usage detection, work state categorization, and break intelligence.

- **4.1 Module 1 — Lightweight Phone Detection:**
  - Integrate ONNX Runtime with quantized lightweight model (e.g., YOLOv8n / YOLO-nano) focused on mobile phone detection.
  - Implement adaptive inference scheduling:
    - Default: 0.5–1 FPS object detection.
    - Burst mode: 2 FPS when head orientation tilts downward.
- **4.2 Module 2 — Multi-Signal Phone Usage Fusion:**
  - Combine signals to eliminate false positives:
    - Phone bounding box detection.
    - Hand/arm proximity or downward head pose.
    - Temporal persistence (> configured duration).
  - Produce high-confidence `phone_sessions` (start, end, duration, confidence).
- **4.3 Module 3 — Work State Engine (State Machine):**
  - Synthesize vision, input, and app context into unified behavioral states:
    - `FOCUSED_WORK` (Present + Facing Screen + Productive App + Input active + No Phone)
    - `ACTIVE_WORK` (Present + Neutral App/Input active)
    - `DISTRACTED` (Non-productive apps or prolonged look-away)
    - `PHONE_USAGE` (Phone condition active)
    - `IDLE` (Present + No computer input)
    - `AWAY` (User absent > threshold)
    - `BREAK` (Absence > configured break threshold)
- **4.4 Module 4 — Break Intelligence & Manual Focus Mode:**
  - Automatic break detection and break duration tracking.
  - Sedentary reminder triggers (e.g., >60 minutes uninterrupted sitting).
  - Manual Focus Mode timer (Pomodoro / custom durations) with heightened phone sensitivity.

---

### Phase 5: Timeline Visualizer, Focus Engine & MVP 2 Polish
**Objective:** Deliver comprehensive daily dashboards, application classification, and an interactive day timeline.

- **5.1 Interactive Day Timeline:**
  - Visual color-coded ribbon of the workday showing transitions between Work, Phone, Away, Breaks, and Idle.
  - Tooltips and scrubbing capability across the timeline.
- **5.2 Application Categorization System:**
  - Pre-seeded default categories (Productive, Communication, Entertainment, Browser).
  - User-configurable rules for reclassifying processes and window title keywords.
- **5.3 Dedicated Dashboards:**
  - **Focus Dashboard:** Deep-focus time, focus sessions, longest session, distraction count.
  - **Phone Dashboard:** Total estimated usage, session counts, longest/average session.
  - **Presence Dashboard:** Desk time, away intervals, break log.
- **5.4 End-of-Day Summary & Daily Score:**
  - Configurable end-of-day summary dialog with actionable behavioral insights.
  - Daily Workspace Wellness Score calculation (balanced weights for focus, posture, breaks, phone).

---

### Phase 6: Performance Optimization, Battery Adaptation & Advanced Insights (MVP 3)
**Objective:** Harden system efficiency, add battery preservation profiles, multi-monitor configuration, and long-term trend intelligence.

- **6.1 Adaptive Performance & Battery Profiles:**
  - Detect Windows battery status (AC vs. Battery power).
  - Automatically activate Battery Saver Mode (reduce vision FPS to 3, lower phone scan frequency, throttle UI animations).
  - CPU thermal watchdog: automatically decrease inference rate if CPU spikes.
- **6.2 Multi-Monitor Workspace Support:**
  - Monitor arrangement configuration (e.g., Center Laptop, Right External Monitor).
  - Adapt attention classifier so looking towards configured monitor coordinates counts as screen focus rather than distraction.
- **6.3 Weekly & Long-Term Trend Insights:**
  - Statistical analysis engine discovering user patterns (e.g., peak focus hours, correlation between session length and posture degradation).
  - Week-over-week comparison metrics.
- **6.4 Privacy Controls & Data Retention Automation:**
  - Configurable retention cycles (7 days, 30 days, 90 days, 1 year, Forever).
  - Single-click "Export My Data" (JSON/CSV) and "Wipe All Activity Data".
- **6.5 Production Packaging & Installer:**
  - Build lightweight Windows installer (`.msi` / `.exe` via WiX or NSIS in Tauri).
  - Automatic startup configuration minimized to system tray.
