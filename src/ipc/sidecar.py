"""
DeskSense Vision Sidecar Process (Phase 1)
Runs in an isolated child process, listens on stdin for JSON-RPC commands,
executes camera and vision workloads via VisionCore, and streams status/observations to stdout.
Ensures zero frame persistence and clean process termination.
"""

import sys
import json
import os
import signal
import datetime

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ipc.schema import Observation
from src.vision.camera import CameraManager
from src.vision.pipeline import VisionCore


def run_sidecar():
    # Send ready signal upon startup
    sys.stdout.write(json.dumps({"type": "status", "status": "READY", "message": "Sidecar initialized"}) + "\n")
    sys.stdout.flush()

    camera = None
    core = None

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break  # Stdin closed, parent exited
            
            line = line.strip()
            if not line:
                continue

            try:
                cmd = json.loads(line)
            except Exception as e:
                sys.stdout.write(json.dumps({"type": "error", "error": f"Invalid command JSON: {e}"}) + "\n")
                sys.stdout.flush()
                continue

            action = cmd.get("command")

            if action in ("ping", "health"):
                sys.stdout.write(json.dumps({"type": "health", "status": "HEALTHY"}) + "\n")
                sys.stdout.flush()

            elif action == "init":
                mock = cmd.get("mock", True)
                fps = cmd.get("fps", 5)
                camera = CameraManager(target_fps=fps, mock_mode=mock)
                core = VisionCore()
                sys.stdout.write(json.dumps({"type": "init_ok", "status": "RUNNING"}) + "\n")
                sys.stdout.flush()

            elif action == "start_calibration":
                duration = float(cmd.get("duration_sec", 10.0))
                if core is None:
                    core = VisionCore()
                core.start_calibration(duration_sec=duration)
                sys.stdout.write(json.dumps({"type": "calibration_started", "duration_sec": duration}) + "\n")
                sys.stdout.flush()

            elif action == "observe":
                if camera is None:
                    camera = CameraManager(target_fps=5, mock_mode=True)
                if core is None:
                    core = VisionCore()

                ret, frame_rgb = camera.read_frame()
                if ret and frame_rgb is not None:
                    res = core.process_frame(frame_rgb, camera_available=True)
                    # Immediate in-memory release
                    del frame_rgb

                    obs = Observation(
                        timestamp=datetime.datetime.now().isoformat(),
                        presence=res.get("presence", "AWAY"),
                        posture=res.get("posture", "UNKNOWN"),
                        attention=res.get("attention", "AWAY"),
                        phone_usage=False,
                        active_app=cmd.get("active_app", "unknown.exe"),
                        activity="ACTIVE_WORK" if res.get("presence") == "PRESENT" else "AWAY",
                        confidence=res.get("confidence", 1.0)
                    )
                    payload = {
                        "type": "observation",
                        "data": obs.to_dict(),
                        "should_notify": res.get("should_notify", False),
                        "is_calibrating": res.get("is_calibrating", False),
                        "calibration_progress": res.get("calibration_progress", 0.0),
                        "metrics": res.get("metrics", {}),
                        "latency_ms": res.get("latency_ms", 0.0)
                    }
                    sys.stdout.write(json.dumps(payload) + "\n")
                else:
                    res = core.process_frame(None, camera_available=False)
                    obs = Observation(
                        timestamp=datetime.datetime.now().isoformat(),
                        presence="UNKNOWN",
                        posture="UNKNOWN",
                        attention="AWAY",
                        phone_usage=False,
                        active_app=cmd.get("active_app", "unknown.exe"),
                        activity="UNKNOWN",
                        confidence=0.0
                    )
                    sys.stdout.write(json.dumps({"type": "observation", "data": obs.to_dict(), "error": "Camera frame read failed"}) + "\n")
                sys.stdout.flush()

            elif action == "stop":
                if camera:
                    camera.release()
                sys.stdout.write(json.dumps({"type": "status", "status": "STOPPED"}) + "\n")
                sys.stdout.flush()
                break

            else:
                sys.stdout.write(json.dumps({"type": "error", "error": f"Unknown command '{action}'"}) + "\n")
                sys.stdout.flush()

        except Exception as e:
            sys.stdout.write(json.dumps({"type": "error", "error": str(e)}) + "\n")
            sys.stdout.flush()

    if camera:
        camera.release()


if __name__ == "__main__":
    run_sidecar()
