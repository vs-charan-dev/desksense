"""
DeskSense Application Runner
Starts the DeskSense core controller, background vision capture loop,
and local embedded API server on port 8765.
"""

import sys
import time
import argparse
import logging
import threading
from typing import Optional

from src.app.core import DeskSenseApp
from src.app.server import EmbeddedAPIServer
from src.app.wizard import WizardState
from src.vision.camera import CameraManager
from src.vision.pipeline import VisionCore
from src.vision.phone_detector import PhoneDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("DeskSense")


def categorize_app(proc: str) -> str:
    proc_lower = (proc or "").lower()
    if any(p in proc_lower for p in ("code", "pycharm", "cursor", "devenv", "notepad", "sublime", "vim", "terminal", "powershell", "cmd")):
        return "productive"
    elif any(p in proc_lower for p in ("slack", "teams", "outlook", "discord", "zoom")):
        return "communication"
    elif any(p in proc_lower for p in ("netflix", "spotify", "steam", "youtube", "game")):
        return "distracting"
    elif any(p in proc_lower for p in ("chrome", "msedge", "firefox", "brave")):
        return "neutral"
    return "neutral"


def main():
    parser = argparse.ArgumentParser(description="DeskSense Workspace Intelligence")
    parser.add_argument("--port", type=int, default=8765, help="Localhost API port (default: 8765)")
    parser.add_argument("--db", type=str, default="desksense.db", help="SQLite database path")
    parser.add_argument("--widget", action="store_true", help="Enable floating status pill widget")
    parser.add_argument("--mock", action="store_true", help="Run with synthetic frames instead of physical camera")
    parser.add_argument("--camera", type=int, default=-1, help="Camera device index (-1 for auto-detect)")
    args = parser.parse_args()

    logger.info("Initializing DeskSense Host Controller...")
    app = DeskSenseApp(db_path=args.db, enable_widget=args.widget)

    logger.info("Initializing Vision Core & Phone Detector...")
    vision_core = VisionCore(
        model_path="models/pose_landmarker_lite.task",
        calibration_path="calibration_profile.json",
        time_func=time.time
    )
    # Connect the app's calibration manager to vision core so wizard captures real frames
    vision_core.calibration_mgr = app.wizard.manager

    phone_detector = PhoneDetector()
    camera = CameraManager(
        camera_index=args.camera,
        target_fps=5,
        mock_mode=args.mock
    )

    logger.info(f"Starting Embedded API Server on http://127.0.0.1:{args.port}...")
    server = EmbeddedAPIServer(app=app, host="127.0.0.1", port=args.port)
    port = server.start()

    def vision_loop():
        logger.info("Vision background processing loop started.")
        last_loop_time = time.time()
        while app.is_running:
            now = time.time()
            dt = now - last_loop_time
            last_loop_time = now

            # Tick calibration wizard if active
            if app.wizard.state in (WizardState.COUNTDOWN, WizardState.CAPTURING):
                app.wizard.update()

            # Read frame from camera
            success, frame_rgb = camera.read_frame()
            if not success or frame_rgb is None:
                app.set_camera_availability(False)
                time.sleep(0.2)
                continue

            app.set_camera_availability(True)

            # Phase 6 Adaptive Performance Target
            target_fps = app.adaptive_perf.target_fps
            camera.target_fps = int(target_fps)
            loop_delay = max(0.01, (1.0 / target_fps) - dt)

            # Update presence for away throttle
            is_present = (res.get("presence") == "PRESENT") if "res" in locals() else True
            app.adaptive_perf.update_presence(is_present)

            # Run vision inference
            res = vision_core.process_frame(frame_rgb, camera_available=True)
            poll_res = app.activity_tracker.poll()
            proc = poll_res.get("application", "Desktop")
            category = app.app_classifier.classify(proc)
            idle_sec = poll_res.get("idle_duration_seconds", 0.0)

            # Record closed app interval if switched
            closed_app = poll_res.get("closed_interval")
            if closed_app and closed_app.get("duration", 0) > 0:
                sess_id = app.session_manager.current_session["id"] if app.session_manager.current_session else None
                app.db.record_app_usage(
                    application=closed_app["application"],
                    window_title=closed_app.get("window_title", ""),
                    start_time=closed_app["start_time"],
                    end_time=closed_app["end_time"],
                    category=category,
                    session_id=sess_id
                )

            is_head_down = (res.get("attention") == "DOWN") or (res.get("metrics", {}).get("pitch", 0.0) > 0.12)
            phone_active_detected = False
            phone_conf = 0.0
            if app.phone_scheduler.should_infer(now):
                phone_res = phone_detector.detect(frame_rgb)
                phone_active_detected = phone_res.detected
                phone_conf = phone_res.confidence

            # Phase 5 focus tracking
            if app.current_work_state:
                app.focus_tracker.update(now, app.current_work_state)

            app.record_observation_extended(
                posture_state=res.get("posture", "UNKNOWN"),
                attention_state=res.get("attention", "SCREEN"),
                confidence=res.get("confidence", 1.0),
                active_app=proc,
                phone_detected=phone_active_detected,
                phone_confidence=phone_conf,
                head_down=is_head_down,
                hand_near_phone=False,
                present=(res.get("presence") == "PRESENT"),
                idle_seconds=idle_sec,
                app_category=category
            )

            if res.get("should_notify"):
                app.notifier.dispatch(res["posture"])

            # Immediately free frame memory (Zero frame persistence mandate)
            del frame_rgb

    vision_thread = threading.Thread(target=vision_loop, daemon=True)
    vision_thread.start()

    print("\n" + "=" * 60)
    print(f"  DeskSense is running on http://127.0.0.1:{port}")
    print("  - To view the Dashboard UI: run 'npm run dev' inside the 'ui/' folder")
    print("  - Hotkey: Press Ctrl+Shift+P to Pause / Resume")
    print("  - Press Ctrl+C in this terminal to stop")
    print("=" * 60 + "\n")

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Shutdown requested...")
    finally:
        server.stop()
        app.quit()
        camera.release()
        logger.info("DeskSense cleanly stopped.")


if __name__ == "__main__":
    main()
