# DeskSense — Phase Test Plan and Quality Gates

## Purpose

This file is the acceptance-test contract for `PHASES.md`. A phase is complete only when all tests in that phase pass and all earlier phase tests still pass.

The tests validate the behavior promised by `PRD.md`; they do not expand the product scope. DeskSense is a local, single-user Windows application intended for an ordinary laptop, so the test suite must stay small, deterministic, and inexpensive to run.

At present the repository contains planning documents only. The test cases below are ready to be implemented beside each production module as that module is created. A phase cannot be marked passed merely because its test cases have been written.

## Test Responsibilities

The test suite is responsible for:

- proving each phase's required behavior before work starts on the next phase;
- protecting privacy, especially the rule that camera frames are never persisted;
- checking state transitions, thresholds, session totals, and dashboard calculations with deterministic inputs;
- catching regressions by rerunning completed phase tests;
- measuring CPU, RAM, frame rate, and long-run stability on the target Windows laptop;
- keeping failures clear enough that one developer can diagnose them quickly.

The test suite is not responsible for:

- judging medical posture or providing a medical diagnosis;
- claiming exact gaze, focus, or phone-use measurement;
- testing cloud services, multi-user behavior, enterprise administration, or unsupported platforms;
- pursuing broad browser/device matrices for this single-user application.

## Test Types

- **Automated:** Fast unit or integration test using synthetic signals, a fake clock, mocked Windows/camera adapters, and a temporary SQLite database.
- **Windows:** Automated test that requires Windows APIs but no human observation.
- **Manual:** Short check requiring the user's webcam, posture, system tray, or visual confirmation.
- **Performance:** Measured on the target laptop with all DeskSense processes included.

Automated tests must not require a real webcam, real waiting, network access, or a dedicated GPU. Time-dependent logic must use an injected/fake clock. Vision logic should be tested primarily with small landmark/detection fixtures rather than loading full video files. Tests may use a temporary directory and must remove it after the run.

## Universal Pass Rules

1. Every required test for the current phase passes.
2. All automated tests from previous phases pass.
3. No test is skipped without a written reason and an issue to restore it.
4. A failed privacy test blocks release regardless of other results.
5. Performance is measured after a 2-minute warm-up. Record average CPU, peak combined RAM, processed FPS, duration, app version, and machine details.
6. For performance gates, the PRD targets are:
   - normal processing at 640×480 and 5–10 FPS;
   - average CPU below 10%;
   - combined RAM preferably below 500 MB and always below the 1 GB MVP ceiling;
   - no dedicated GPU requirement;
   - no saved webcam images or video.

## Suggested Test Layout When Code Exists

Keep tests beside their owning component where practical. Use only three broader suites:

```text
tests/
  fixtures/       # Small structured landmark/signal fixtures; no private recordings
  integration/    # IPC, SQLite, lifecycle, and state-engine tests
  acceptance/     # Phase gates and Windows/manual checklists
```

Do not start multiple model instances in parallel during the normal test run. Run resource and webcam tests serially to avoid inflated RAM usage and camera contention.

---

## Phase 0 — Technical Foundation and CV Prototype

### Automated and integration tests

| ID | Test | Pass condition |
|---|---|---|
| P0-01 | IPC schema accepts a valid observation | A representative observation containing timestamp, presence, posture, attention, phone flag, active app, and activity is parsed without loss. |
| P0-02 | IPC schema rejects invalid input safely | Missing required fields, invalid enum values, malformed JSON, and unsupported schema versions produce a controlled error; neither process crashes. |
| P0-03 | Sidecar start/stop lifecycle | The host starts the vision sidecar, receives a ready/health response, stops it, and leaves no child process running. |
| P0-04 | Sidecar failure isolation | A simulated sidecar exit changes vision status to unavailable and the desktop host remains responsive. |
| P0-05 | Frame scheduler limits work | A simulated 30 FPS camera stream results in only the configured 5–10 frames per second being submitted to lightweight inference. |
| P0-06 | Camera configuration | The camera adapter requests 640×480 input and does not request 1080p capture. |
| P0-07 | Frames are released | After each synthetic frame is processed, no frame is retained in queues, event payloads, logs, or long-lived history. Queue size stays bounded during a 10-minute synthetic run. |
| P0-08 | Adaptive throttle hook | Changing the configured processing rate changes scheduling without restarting the process or accumulating queued frames. |

### Manual and performance tests

| ID | Test | Pass condition |
|---|---|---|
| P0-09 | Live prototype | For 10 minutes, the webcam preview shows current presence/pose/face output and processed FPS without freezing or steadily increasing delay. |
| P0-10 | Camera unavailable | Starting with the camera blocked or already in use shows a recoverable unavailable state; the app does not crash. |
| P0-11 | Prototype resource budget | After warm-up, a 30-minute run averages below 10% CPU, processes 5–10 FPS, stays below 500 MB combined RAM where possible, and never reaches 1 GB. |
| P0-12 | Zero frame persistence | Compare the application data/temp directories before and after monitoring. No image or video file, frame blob, screenshot, or base64 frame appears. Structured diagnostic logs are allowed. |

**Phase 0 gate:** P0-01 through P0-12 pass. Do not begin the full posture engine until live capture is stable and no-frame-persistence is demonstrated.

---

## Phase 1 — Vision Core and Posture Engine

### Presence

| ID | Test | Pass condition |
|---|---|---|
| P1-01 | Present detection | A valid face/body fixture produces `PRESENT`. |
| P1-02 | Absence hysteresis | Continuous missing-person input for 15 seconds or less does not produce `AWAY`; input beyond the configured 15-second threshold does. |
| P1-03 | Automatic return | A valid person observation after `AWAY` returns the state to `PRESENT` automatically. |
| P1-04 | Unknown input | Low-confidence, invalid, or unavailable-camera observations produce `UNKNOWN`, not a false `PRESENT` or `AWAY`. |

### Calibration and classification

| ID | Test | Pass condition |
|---|---|---|
| P1-05 | Calibration duration and sample window | The engine collects the configured 10 seconds of samples and ignores frames outside that window. The unit test uses a fake clock and completes immediately. |
| P1-06 | Calibration quality rejection | Missing shoulders/head, too few valid samples, or inadequate quality does not overwrite the last valid profile and returns an actionable reason. |
| P1-07 | Normalized calibration profile | A good sample set stores normalized inter-eye distance, head-to-shoulder angle, shoulder span, ear-to-shoulder alignment, and face-size/distance baseline. |
| P1-08 | Calibration persistence | A saved profile reloads with equivalent values after process restart; a missing/corrupt profile requests recalibration without crashing. |
| P1-09 | Posture classes | Controlled landmark fixtures independently produce `POSTURE_GOOD`, `SLOUCHING`, `TOO_CLOSE`, `LEAN_LEFT`, `LEAN_RIGHT`, and `HEAD_TILT`. |
| P1-10 | Relative distance | Increasing face size/inter-eye distance sufficiently above the calibrated baseline produces `TOO_CLOSE`; normal variation does not. |
| P1-11 | Attention classes | Controlled head-pose fixtures produce `SCREEN`, `LEFT`, `RIGHT`, `DOWN`, and `AWAY`; unreliable input produces `UNKNOWN`. |

### Smoothing and notifications

| ID | Test | Pass condition |
|---|---|---|
| P1-12 | Jitter suppression | Alternating good/bad frame predictions do not create a state transition for every frame. The rolling filter produces one stable state. |
| P1-13 | Brief movement ignored | A posture deviation shorter than 20 seconds never requests a notification. |
| P1-14 | Persistent posture alert | A continuous deviation reaches the configured 20–30 second threshold and requests exactly one appropriate alert. |
| P1-15 | Persistence reset | Returning to good posture before the threshold clears the timer; a later deviation must satisfy the full threshold again. |
| P1-16 | Notification cooldown | After an alert, the same condition cannot alert again during the 5-minute cooldown and may alert after it expires if still applicable. |

### Controlled manual evaluation

Run each scenario five times after one normal calibration. Pass when at least 4 of 5 attempts reach the expected stable state. Brief movements must produce zero alerts. This small evaluation is appropriate for a single-user MVP; keep the observed results so thresholds are not tuned from memory.

| ID | Scenario | Expected result |
|---|---|---|
| P1-17 | Sit normally | `POSTURE_GOOD`, no warning. |
| P1-18 | Deliberately slouch for the configured persistence time | `SLOUCHING`, one warning. |
| P1-19 | Lean very close | `TOO_CLOSE`, one warning after persistence. |
| P1-20 | Lean left, lean right, and tilt head | Matching stable classifications; no rapid flapping. |
| P1-21 | Look at screen, sideways, and down | Matching coarse attention states; the UI does not claim precise eye tracking. |
| P1-22 | Leave and return | `AWAY` only after the absence threshold, then automatic `PRESENT`. |
| P1-23 | Poor lighting/partial visibility | `UNKNOWN` or a quality message rather than a confident false classification. |

**Phase 1 gate:** P1-01 through P1-23 pass, plus the complete Phase 0 regression suite.

---

## Phase 2 — Windows Activity and Local Data

### Windows activity and lifecycle

| ID | Test | Pass condition |
|---|---|---|
| P2-01 | Foreground application | On Windows, switching between two known test applications updates process name and non-empty window title correctly. |
| P2-02 | Idle duration | A mocked `GetLastInputInfo` tick count is converted to idle duration correctly, including tick wrap/invalid values without a crash. |
| P2-03 | Activity polling deduplication | An unchanged foreground app extends/aggregates the existing interval rather than writing a new row on every poll. |
| P2-04 | Lock/sleep/hibernate | Each simulated lifecycle event closes the active session once with a valid end time and duration. |
| P2-05 | Unlock/resume | Resume/unlock starts one new session and never joins time spent asleep/locked to active work. |
| P2-06 | Camera disconnect/contention | Vision-dependent metrics pause, status becomes unavailable, desktop tracking continues, and reconnect can recover without restarting the app. |

### SQLite and notifications

| ID | Test | Pass condition |
|---|---|---|
| P2-07 | Schema creation/migration | A fresh temporary database creates `settings`, `sessions`, `posture_events`, `attention_events`, `app_usage`, and `daily_summary` with required keys/constraints; reopening is idempotent. |
| P2-08 | Structured event round trip | Representative settings, session, posture, attention, and app-usage records read back with equivalent values and timestamps. |
| P2-09 | Restart persistence | After closing and reopening the database/app service, completed sessions and calibration/settings remain available. |
| P2-10 | Batch transaction rollback | A failed batch writes no partial event set and leaves the database usable. |
| P2-11 | Aggregation correctness | Known event intervals produce exact daily desk time, away time, active time, and posture percentage without double-counting overlaps. |
| P2-12 | Compact storage behavior | Repeated identical samples are batched/downsampled into intervals; row count does not grow once per camera frame. |
| P2-13 | Toast payload | Each supported alert maps to a short, understandable Windows toast and contains no image/frame data. |
| P2-14 | Shared cooldown enforcement | Repeated requests inside the configured 5-minute cooldown dispatch only one toast; disabling a notification category dispatches none. |
| P2-15 | Local-only operation | With network access disabled, activity capture, event storage, aggregation, and notifications still work. No test observes an outbound network requirement. |

**Phase 2 gate:** P2-01 through P2-15 pass, plus all Phase 0–1 automated regressions. Manually lock/unlock and sleep/resume once on the target laptop and confirm the session boundary in SQLite.

---

## Phase 3 — Desktop Shell, Calibration, and MVP 1 Dashboard

### Shell and UI tests

| ID | Test | Pass condition |
|---|---|---|
| P3-01 | Start/minimize/close behavior | The app can start minimized to tray; closing the dashboard hides it while monitoring continues; Quit stops host and sidecar cleanly. |
| P3-02 | Tray commands | Open Dashboard, Pause 15 minutes, Pause 1 hour, custom pause, Recalibrate, Settings, and Quit invoke the correct action once. |
| P3-03 | Pause semantics | While paused, camera inference and event creation stop; the UI shows the pause and automatic/manual resume restores monitoring without inventing data for the gap. |
| P3-04 | Global hotkey | `Ctrl+Shift+P` toggles pause/resume and does not register duplicate handlers after reopening the window. |
| P3-05 | Calibration wizard happy path | Placement guidance → 3-second countdown → 10-second capture → success saves the profile and enters monitoring. Automated timing uses a fake clock. |
| P3-06 | Calibration wizard recovery | Poor quality/camera failure shows the reason and allows retry or cancel without losing the previous valid calibration. |
| P3-07 | Dashboard totals | Seeded SQLite data renders exact At-Desk Time, Away Time, Posture Score, and Active Computer Time. |
| P3-08 | Posture distribution | Good, slouching, too-close, and leaning durations use desk time as the denominator and total 100% subject to display rounding. |
| P3-09 | Live state updates | A new state event updates the current status and session timer without a full page reload or duplicate subscriptions. |
| P3-10 | Empty/error states | A new day, unavailable camera, missing calibration, and database read error each show a useful state without crashing. |
| P3-11 | Optional widget disabled | The application works fully when the optional overlay is off. If enabled, it can be dragged, collapsed, and hidden without affecting monitoring. |

### MVP 1 acceptance run

| ID | Test | Pass condition |
|---|---|---|
| P3-12 | End-to-end desk session | Calibrate, monitor normal posture, briefly move, slouch long enough for one alert, lean close, leave, return, switch apps, and become idle. The dashboard and stored intervals match the observed sequence within polling/smoothing tolerance. |
| P3-13 | Restart continuity | Complete a short session, quit, relaunch, and confirm the prior session and dashboard totals remain. |
| P3-14 | Two-hour stability | A 2-hour normal monitoring run has no crash, frozen UI, orphan sidecar, or steadily growing memory; average CPU is below 10%, peak combined RAM is preferably below 500 MB and must remain below 1 GB. |
| P3-15 | Privacy recheck | No camera image/video/frame blob exists after calibration, monitoring, notification, restart, and dashboard use. |

**Phase 3 gate / MVP 1:** P3-01 through P3-15 pass, all earlier automated tests pass, and the MVP acceptance criteria from the PRD are satisfied: absence/return, prolonged-slouch alert, no brief-movement alert, too-close detection, active app, idle detection, restart persistence, privacy, and acceptable performance.

---

## Phase 4 — Phone Detection and Signal Fusion

### Phone scheduling and fusion

| ID | Test | Pass condition |
|---|---|---|
| P4-01 | Quantized model load | The configured lightweight ONNX model loads on CPU without a dedicated GPU; missing/corrupt model disables phone detection gracefully. |
| P4-02 | Default phone schedule | With no suspicion, object detection runs at 0.5–1 FPS rather than on every camera frame. |
| P4-03 | Burst schedule | Downward head orientation temporarily increases phone inference to the configured burst rate (up to 2 FPS) and returns to default afterward. |
| P4-04 | Multi-signal positive | Phone detection plus proximity/downward-attention evidence sustained for the configured duration starts one `PHONE_USAGE` session. |
| P4-05 | Single-signal negatives | A phone lying on the table, a downward look without a phone, or a single-frame phone detection does not start a phone-use session. |
| P4-06 | Session close/debounce | Loss of the fused condition for the configured end threshold closes the session once with correct start, end, duration, and confidence; brief dropouts do not split it. |
| P4-07 | Phone wording | UI/analytics label results as **estimated phone usage**, never exact usage. |

### Work state and break logic

Use a table-driven test covering every state and priority. `PHONE_USAGE` and `AWAY` must not be counted simultaneously as focused work.

| ID | Input condition | Expected state |
|---|---|---|
| P4-08 | Present + screen + productive app + recent input + no phone | `FOCUSED_WORK` |
| P4-09 | Present + recent input + neutral app + no phone | `ACTIVE_WORK` |
| P4-10 | Present + non-productive app or prolonged look-away | `DISTRACTED` |
| P4-11 | Present + fused phone-use condition | `PHONE_USAGE` |
| P4-12 | Present + no recent computer input | `IDLE` |
| P4-13 | Absent beyond threshold | `AWAY`; after the configured break threshold it becomes/creates `BREAK` as designed. |
| P4-14 | Missing/unreliable required signals | `UNKNOWN` rather than an optimistic work state. |

| ID | Test | Pass condition |
|---|---|---|
| P4-15 | State transition accounting | A synthetic day with known transitions produces non-overlapping intervals whose durations equal elapsed monitored time. |
| P4-16 | Automatic break | A sustained absence creates one break with correct duration; return closes it automatically. |
| P4-17 | Sedentary reminder | More than 60 uninterrupted seated minutes requests one reminder; a qualifying break resets the timer. |
| P4-18 | Manual focus mode | Start, pause/cancel, and completion work for Pomodoro/custom durations; phone sensitivity changes only during the focus session and is restored afterward. |

### Controlled phone evaluation

Run each scenario five times. Active use must be detected in at least 4 of 5 attempts. Each negative scenario may produce at most 1 false session in 5 attempts, and the combined negative sequence must not create a long false session.

| ID | Scenario | Expected result |
|---|---|---|
| P4-19 | Actively use phone while looking down | Estimated phone session. |
| P4-20 | Phone on table | No session. |
| P4-21 | Hold phone without using it | No session unless the sustained fusion threshold is genuinely met. |
| P4-22 | Look down with no phone | No session. |
| P4-23 | Write/read on paper | No session. |
| P4-24 | Put phone down after use | Existing session closes after the end threshold and is stored once. |

**Phase 4 gate:** P4-01 through P4-24 pass, plus all earlier automated regressions. False-positive control is more important than labeling every ambiguous phone event.

---

## Phase 5 — Timeline, Focus, Categories, and MVP 2 Dashboard

| ID | Test | Pass condition |
|---|---|---|
| P5-01 | Focus session boundaries | Productive activity starts/extends one focus session; phone, away, idle, or qualifying distraction closes it at the correct timestamp. |
| P5-02 | Focus totals | Seeded intervals produce exact total focus time, session count, longest session, average session, and distraction count. |
| P5-03 | Timeline mapping | A synthetic day renders ordered, non-overlapping Work, Phone, Away/Break, and Idle segments at positions proportional to their timestamps. |
| P5-04 | Timeline gaps/overlaps | Gaps become unknown/unmonitored time and overlapping raw events are resolved by state priority without double-counting. |
| P5-05 | Timeline interaction | Hover/keyboard focus shows correct state, start, end, and duration; scrubbing/selecting cannot mutate source data. |
| P5-06 | Default app categories | Seeded Productive, Communication, Entertainment, and Browser rules return the expected category. Unknown apps remain neutral/unclassified. |
| P5-07 | User reclassification | A process or title-keyword rule can be added, edited, removed, persisted across restart, and applied to later classification. |
| P5-08 | Rule precedence | User rules override defaults deterministically; process and title matching are case-insensitive and do not use unsafe arbitrary code/regex execution. |
| P5-09 | Phone dashboard | Known phone sessions produce exact estimated total, count, longest, and average durations. |
| P5-10 | Presence dashboard | Known presence intervals produce exact desk time, away intervals, and break log. |
| P5-11 | Daily summary | Known data produces exact focus, desk, away, phone, posture, longest-focus, and break metrics with no duration counted twice. |
| P5-12 | Daily score boundaries | Score components use documented weights, handle missing data without division by zero, and clamp the result to 0–100. |
| P5-13 | Actionable wording | Summary/insight text is factual and motivational; estimated signals are described as estimates and posture text contains no medical claim. |
| P5-14 | End-of-day preference | Summary appears only at the configured time when enabled and at most once per day. |
| P5-15 | MVP 2 end-to-end day | A seeded or accelerated day containing work, phone, away, idle, posture, and app changes yields a matching timeline and all five required totals: focus, desk, away, phone, and posture score. |

**Phase 5 gate / MVP 2:** P5-01 through P5-15 pass, all earlier automated tests pass, phone estimates are useful under the Phase 4 controlled scenarios, focus sessions generate automatically, the timeline represents all required states, and app categories are editable.

---

## Phase 6 — Optimization, Battery, Privacy Tools, and Production Readiness

### Adaptive performance

| ID | Test | Pass condition |
|---|---|---|
| P6-01 | AC profile | Normal monitoring targets 5 FPS (and never exceeds the configured 5–10 FPS range). |
| P6-02 | Away profile | Sustained absence reduces expensive inference to approximately 1 FPS and restores normal rate on return. |
| P6-03 | Battery profile | Switching to battery reduces vision to approximately 3 FPS, lowers phone-scan frequency, and throttles optional UI animation; returning to AC restores settings. |
| P6-04 | Thermal/CPU throttle | Sustained CPU above the configured limit reduces inference/phone frequency; recovery uses hysteresis so rates do not flap. |
| P6-05 | Bounded queues/caches | Slow inference, database delay, and repeated UI navigation do not cause unbounded frame queues, event buffers, subscriptions, or model instances. |

### Configuration, trends, and privacy controls

| ID | Test | Pass condition |
|---|---|---|
| P6-06 | Multi-monitor attention | Configured monitor directions count as screen attention; an unconfigured direction retains normal away/side classification. |
| P6-07 | Weekly aggregation | A seeded two-week dataset produces exact daily/weekly totals, week-over-week changes, and peak-focus windows; missing days do not become fabricated zero-activity days. |
| P6-08 | Insight minimum evidence | No trend/correlation claim is generated below the documented minimum data threshold. Generated insights agree with seeded data. |
| P6-09 | Retention policies | 7-, 30-, 90-, and 365-day policies delete only records older than the boundary. `Forever` deletes none. Settings/calibration are retained. |
| P6-10 | Export | JSON/CSV export contains documented structured records and timestamps, opens successfully, and contains no image/video/frame bytes. |
| P6-11 | Wipe activity data | After explicit confirmation, all activity/session/summary data is removed and dashboard totals reset; app settings remain unless the UI explicitly says otherwise. Cancel leaves all data untouched. |
| P6-12 | Startup setting | Enabling startup creates one valid minimized-to-tray entry; disabling removes it; repeating either action is idempotent. |
| P6-13 | Installer smoke test | Install, first launch, monitoring, dashboard open, clean quit, relaunch, and uninstall succeed on supported Windows without requiring a dedicated GPU. |

### Final performance and endurance gate

Run serially on the target Windows 10/11 laptop (Intel i5 class, 8 GB RAM acceptable, integrated graphics). Include host, sidecar, webview, and helper processes in totals.

| ID | Test | Pass condition |
|---|---|---|
| P6-14 | Eight-hour endurance | Eight hours of representative monitoring completes without crash, frozen UI, lost database, orphan process, or monotonic memory growth. |
| P6-15 | Normal resource budget | After warm-up, average CPU is below 10%; peak combined RAM is preferably below 500 MB and must be below 1 GB; normal lightweight tracking remains usable at its configured rate. |
| P6-16 | Battery resource behavior | Battery mode visibly lowers inference work compared with AC mode and remains functional at approximately 3 FPS. |
| P6-17 | Data growth | One simulated/real workday stores structured intervals/events rather than frames; database growth is small enough for the selected retention period and contains no frame blobs. |
| P6-18 | Offline/privacy audit | With networking disabled, every core feature still operates. Application directories and database contain no raw camera frames, recordings, screenshots, or cloud-upload queue. |
| P6-19 | Final regression | All Phase 0–6 automated tests pass in a clean production-like build. Required Windows/manual checks have dated results attached to the release record. |

**Phase 6 gate / production-ready single-user build:** P6-01 through P6-19 pass. Any breach of the 1 GB RAM ceiling, persisted camera frame, endurance crash, or corrupt/lost session is a release blocker.

---

## Phase Result Record

Copy this small block for each phase rather than creating a separate QA system:

```text
Phase:
Build/commit:
Date and Windows version:
Machine CPU/RAM:
Automated result:
Manual result:
Average CPU / peak combined RAM / processed FPS:
Failures or skipped tests:
Decision: PASS / FAIL
```

Only a `PASS` decision permits work to move to the next phase. If a completed phase later regresses, stop advancement until its gate passes again.
