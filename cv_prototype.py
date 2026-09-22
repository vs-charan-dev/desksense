"""
DeskSense — Computer Vision Prototype (Phase 1)
Live vision prototype with HUD overlay, presence tracking, baseline calibration,
posture evaluation, screen attention, and real-time CPU/RAM profiling.
Integrated with Phase 1 VisionCore.
"""

import argparse
import sys
import time
import os
import cv2
import numpy as np

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.vision.camera import CameraManager
from src.vision.pipeline import VisionCore
from src.vision.profiler import SystemProfiler


def draw_hud(
    frame_bgr: np.ndarray,
    result: dict,
    metrics: dict,
    vision_core: VisionCore
) -> np.ndarray:
    """Renders diagnostic HUD overlay onto the live preview frame."""
    h, w, _ = frame_bgr.shape
    
    # Semi-transparent top bar for telemetry
    overlay = frame_bgr.copy()
    cv2.rectangle(overlay, (0, 0), (w, 85), (20, 20, 20), -1)
    # Bottom instructions bar
    cv2.rectangle(overlay, (0, h - 35), (w, h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, frame_bgr, 0.25, 0, frame_bgr)

    presence = result.get("presence", "AWAY")
    posture = result.get("posture", "UNKNOWN")
    raw_post = result.get("raw_posture", posture)
    attention = result.get("attention", "AWAY")
    latency = result.get("latency_ms", 0.0)
    should_notify = result.get("should_notify", False)

    # Color definitions (BGR)
    COLOR_GREEN = (40, 200, 40)
    COLOR_YELLOW = (40, 210, 240)
    COLOR_RED = (50, 50, 230)
    COLOR_WHITE = (240, 240, 240)
    COLOR_GRAY = (160, 160, 160)

    pres_color = COLOR_GREEN if presence == "PRESENT" else COLOR_RED
    if posture == "POSTURE_GOOD":
        post_color = COLOR_GREEN
    elif posture in ("SLOUCHING", "TOO_CLOSE"):
        post_color = COLOR_RED
    else:
        post_color = COLOR_YELLOW

    # Row 1: States
    cv2.putText(frame_bgr, f"Presence: {presence}", (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, pres_color, 2)
    cv2.putText(frame_bgr, f"Posture: {posture}", (185, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, post_color, 2)
    cv2.putText(frame_bgr, f"Gaze: {attention}", (410, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_WHITE, 2)

    # Row 2: Diagnostics / Temporal Smoothing info
    filter_diag = result.get("filter_diag", {})
    dev_sec = filter_diag.get("deviation_duration_sec", 0.0)
    if should_notify:
        alert_text = "! NOTIFICATION TRIGGERED !"
        cv2.putText(frame_bgr, alert_text, (15, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_RED, 2)
    elif dev_sec > 0:
        cv2.putText(frame_bgr, f"Deviation: {dev_sec:.1f}s / 20.0s", (15, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_YELLOW, 1)
    else:
        cv2.putText(frame_bgr, "Posture Stable", (15, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_GREEN, 1)

    # Row 3: Performance Profiler metrics
    prof_text = (
        f"FPS: {metrics['fps']}  |  "
        f"CPU: {metrics['process_cpu_pct']}%  |  "
        f"RAM: {metrics['ram_mb']} MB  |  "
        f"Latency: {latency}ms"
    )
    cv2.putText(frame_bgr, prof_text, (15, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_GRAY, 1)

    # Calibration status text
    calib_mgr = vision_core.calibration_mgr
    if calib_mgr.is_calibrating:
        pct = int(calib_mgr.progress_pct)
        calib_text = f"CALIBRATING... Hold good posture ({pct}%)"
        cv2.putText(frame_bgr, calib_text, (15, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_YELLOW, 2)
    elif calib_mgr.profile:
        cv2.putText(frame_bgr, "[Calibrated]", (w - 120, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_GREEN, 1)
    else:
        cv2.putText(frame_bgr, "[Not Calibrated - Press C]", (w - 210, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_YELLOW, 1)

    # Bottom bar controls
    controls_text = "Press: [C] Calibrate  |  [R] Reset  |  [Q] Quit"
    cv2.putText(frame_bgr, controls_text, (15, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_WHITE, 1)

    # Draw shoulder & nose keypoint markers if present
    keypoints = result.get("keypoints", {})
    if "nose" in keypoints and presence == "PRESENT":
        nx, ny = int(keypoints["nose"][0] * w), int(keypoints["nose"][1] * h)
        cv2.circle(frame_bgr, (nx, ny), 5, COLOR_GREEN, -1)

    if "left_shoulder" in keypoints and "right_shoulder" in keypoints and presence == "PRESENT":
        lsx, lsy = int(keypoints["left_shoulder"][0] * w), int(keypoints["left_shoulder"][1] * h)
        rsx, rsy = int(keypoints["right_shoulder"][0] * w), int(keypoints["right_shoulder"][1] * h)
        cv2.circle(frame_bgr, (lsx, lsy), 5, COLOR_YELLOW, -1)
        cv2.circle(frame_bgr, (rsx, rsy), 5, COLOR_YELLOW, -1)
        cv2.line(frame_bgr, (lsx, lsy), (rsx, rsy), COLOR_YELLOW, 2)

    return frame_bgr


def run_prototype(args):
    print("=" * 60)
    print("DeskSense — Computer Vision Pipeline (Phase 1)")
    print("=" * 60)
    print(f"Target FPS   : {args.fps}")
    print(f"Headless     : {args.headless}")
    print(f"Mock Camera  : {args.mock}")
    print(f"Model Path   : {args.model}")
    print("-" * 60)

    profiler = SystemProfiler()
    core = VisionCore(model_path=args.model, calibration_path="calibration_profile.json")
    camera = CameraManager(
        camera_index=args.camera,
        target_fps=args.fps,
        width=640,
        height=480,
        mock_mode=args.mock
    )

    if args.calibrate:
        print("[Prototype] Auto-triggering calibration sequence...")
        core.start_calibration(duration_sec=10.0)

    start_time = time.time()
    benchmark_samples = []

    try:
        while True:
            t_frame_start = time.perf_counter()
            ret, frame_rgb = camera.read_frame()
            if not ret or frame_rgb is None:
                time.sleep(0.05)
                continue

            # Run detection through Phase 1 full core pipeline
            result = core.process_frame(frame_rgb, camera_available=True)

            if result.get("calib_finished"):
                print(f"\n[Prototype] Calibration status: {result.get('calib_msg')}")

            # Update profiler
            latency_ms = (time.perf_counter() - t_frame_start) * 1000.0
            profiler.tick(latency_ms=latency_ms)
            metrics = profiler.get_metrics()

            # Record sample for benchmark mode
            if args.benchmark > 0:
                benchmark_samples.append({
                    "fps": metrics["fps"],
                    "cpu": metrics["process_cpu_pct"],
                    "ram": metrics["ram_mb"],
                    "latency": result.get("latency_ms", 0.0),
                    "presence": result.get("presence", "AWAY"),
                    "posture": result.get("posture", "UNKNOWN")
                })
                elapsed = time.time() - start_time
                if elapsed >= args.benchmark:
                    print(f"\n[Benchmark] Target duration of {args.benchmark}s reached.")
                    break

            # Headless logging vs GUI Window
            if args.headless:
                sys.stdout.write(
                    f"\r[DeskSense] Presence: {result['presence']:<7} | "
                    f"Posture: {result['posture']:<12} | "
                    f"Gaze: {result['attention']:<6} | "
                    f"FPS: {metrics['fps']:<4} | "
                    f"CPU: {metrics['process_cpu_pct']:>4.1f}% | "
                    f"RAM: {metrics['ram_mb']:>5.1f}MB"
                )
                sys.stdout.flush()
            else:
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                hud_frame = draw_hud(frame_bgr, result, metrics, core)
                cv2.imshow("DeskSense - Vision Prototype (Phase 1)", hud_frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # 'q' or ESC
                    print("\n[Prototype] Quit requested by user.")
                    break
                elif key == ord('c'):
                    print("\n[Prototype] Starting guided 10-second calibration...")
                    core.start_calibration(duration_sec=10.0)
                elif key == ord('r'):
                    print("\n[Prototype] Calibration reset.")
                    core.calibration_mgr.profile = None
                    if os.path.exists("calibration_profile.json"):
                        try:
                            os.remove("calibration_profile.json")
                        except Exception:
                            pass

            # Explicitly delete frame buffers from memory (Privacy contract)
            del frame_rgb
            if 'frame_bgr' in locals():
                del frame_bgr

    except KeyboardInterrupt:
        print("\n[Prototype] Stopped by user interrupt.")
    finally:
        camera.release()
        if not args.headless:
            cv2.destroyAllWindows()

    # Benchmark summary reporting
    if benchmark_samples:
        avg_cpu = sum(s["cpu"] for s in benchmark_samples) / len(benchmark_samples)
        avg_ram = sum(s["ram"] for s in benchmark_samples) / len(benchmark_samples)
        avg_latency = sum(s["latency"] for s in benchmark_samples) / len(benchmark_samples)
        print("\n" + "=" * 60)
        print("PHASE 1 BENCHMARK REPORT")
        print("=" * 60)
        print(f"Total Frames Sampled : {len(benchmark_samples)}")
        print(f"Average Process CPU  : {avg_cpu:.2f}% (Target: < 10.0%)")
        print(f"Average Memory (RAM) : {avg_ram:.1f} MB (Target: < 500.0 MB)")
        print(f"Average Latency      : {avg_latency:.1f} ms / frame")
        print(f"Target FPS           : {args.fps}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="DeskSense Phase 1 Vision Prototype")
    parser.add_argument("--fps", type=int, default=5, help="Target processing FPS (default: 5)")
    parser.add_argument("--headless", action="store_true", help="Run without graphical display window")
    parser.add_argument("--mock", action="store_true", help="Use synthetic mock video stream")
    parser.add_argument("--camera", type=int, default=-1, help="Camera device index (-1 for auto-detect laptop webcam)")
    parser.add_argument("--model", type=str, default="models/pose_landmarker_lite.task", help="Path to pose model")
    parser.add_argument("--calibrate", action="store_true", help="Trigger calibration at startup")
    parser.add_argument("--benchmark", type=int, default=0, help="Run benchmark mode for N seconds and exit")

    args = parser.parse_args()
    run_prototype(args)


if __name__ == "__main__":
    main()
