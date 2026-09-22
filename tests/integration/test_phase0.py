"""
Phase 0 Automated and Integration Tests (P0-01 to P0-08)
Verifies:
- IPC schema parsing, enum validation, rejection of invalid input
- Sidecar start/stop lifecycle and process cleanup
- Failure isolation when sidecar terminates
- Frame scheduler rate limiting (30 FPS -> 5-10 FPS)
- Camera configuration (requests 640x480, not 1080p)
- Strict frame release and zero queue buildup
- Adaptive throttling hook
"""

import unittest
import time
import json
import sys
import os
import numpy as np

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.ipc.schema import (
    Observation, IPCValidationError, UnsupportedSchemaVersionError, MalformedJsonError
)
from src.ipc.client import SidecarClient
from src.vision.camera import CameraManager
from src.vision.scheduler import FrameScheduler
from tests.fixtures.sample_observations import VALID_OBSERVATION_FIXTURE


class TestPhase0Automated(unittest.TestCase):

    # =========================================================================
    # P0-01: IPC schema accepts a valid observation
    # =========================================================================
    def test_p0_01_ipc_schema_accepts_valid_observation(self):
        obs = Observation.from_dict(VALID_OBSERVATION_FIXTURE)
        self.assertEqual(obs.timestamp, "2026-09-22T10:15:22")
        self.assertEqual(obs.presence, "PRESENT")
        self.assertEqual(obs.posture, "POSTURE_GOOD")
        self.assertEqual(obs.attention, "SCREEN")
        self.assertFalse(obs.phone_usage)
        self.assertEqual(obs.active_app, "Code.exe")
        self.assertEqual(obs.activity, "FOCUSED_WORK")
        self.assertEqual(obs.schema_version, "1.0")

        # Verify JSON round-trip without loss
        json_str = obs.to_json()
        restored = Observation.from_json(json_str)
        self.assertEqual(obs.to_dict(), restored.to_dict())

    # =========================================================================
    # P0-02: IPC schema rejects invalid input safely
    # =========================================================================
    def test_p0_02_ipc_schema_rejects_invalid_input_safely(self):
        # 1. Missing required field
        invalid_missing = dict(VALID_OBSERVATION_FIXTURE)
        del invalid_missing["posture"]
        with self.assertRaises(IPCValidationError):
            Observation.from_dict(invalid_missing)

        # 2. Invalid enum value
        invalid_enum = dict(VALID_OBSERVATION_FIXTURE)
        invalid_enum["posture"] = "INVALID_POSTURE_ENUM_VALUE"
        with self.assertRaises(IPCValidationError):
            Observation.from_dict(invalid_enum)

        # 3. Malformed JSON
        with self.assertRaises(MalformedJsonError):
            Observation.from_json("{broken json string")

        # 4. Unsupported schema version
        invalid_version = dict(VALID_OBSERVATION_FIXTURE)
        invalid_version["schema_version"] = "99.0"
        with self.assertRaises(UnsupportedSchemaVersionError):
            Observation.from_dict(invalid_version)

    # =========================================================================
    # P0-03: Sidecar start/stop lifecycle
    # =========================================================================
    def test_p0_03_sidecar_start_stop_lifecycle(self):
        client = SidecarClient()
        started = client.start(timeout_sec=5.0)
        self.assertTrue(started, "Sidecar should start and report READY")
        self.assertTrue(client.is_running(), "Sidecar process should be running")

        # Check health
        self.assertTrue(client.health_check(), "Sidecar should report HEALTHY")

        # Clean stop
        client.stop()
        time.sleep(0.2)
        self.assertFalse(client.is_running(), "No orphan sidecar process should remain")
        self.assertEqual(client.status, "STOPPED")

    # =========================================================================
    # P0-04: Sidecar failure isolation
    # =========================================================================
    def test_p0_04_sidecar_failure_isolation(self):
        client = SidecarClient()
        self.assertTrue(client.start(timeout_sec=5.0))

        # Simulate unexpected sidecar exit by killing its process
        if client.process:
            client.process.kill()
            client.process.wait()

        # Host client must not crash; status becomes UNAVAILABLE
        obs = client.get_observation()
        self.assertIsNone(obs)
        self.assertEqual(client.status, "UNAVAILABLE")
        self.assertFalse(client.is_running())
        client.stop()

    # =========================================================================
    # P0-05: Frame scheduler limits work
    # =========================================================================
    def test_p0_05_frame_scheduler_limits_work(self):
        # Target 5 FPS (interval = 0.20s). Feed frames at simulated 30 FPS for 1.0s (30 frames).
        scheduler = FrameScheduler(target_fps=5)
        simulated_time = 1000.0
        fps_30_step = 1.0 / 30.0

        dispatched = 0
        for _ in range(30):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            if scheduler.submit_frame(frame, current_time=simulated_time):
                dispatched += 1
            simulated_time += fps_30_step

        # At 5 FPS over 1.0 second, dispatched frames should be 5 to 6, not 30
        self.assertGreaterEqual(dispatched, 5)
        self.assertLessEqual(dispatched, 6)
        self.assertEqual(scheduler.skipped_count, 30 - dispatched)

    # =========================================================================
    # P0-06: Camera configuration
    # =========================================================================
    def test_p0_06_camera_configuration(self):
        camera = CameraManager(target_fps=5, width=640, height=480, mock_mode=True)
        self.assertEqual(camera.width, 640)
        self.assertEqual(camera.height, 480)
        self.assertNotEqual(camera.width, 1920, "Must not request 1080p")
        self.assertNotEqual(camera.height, 1080, "Must not request 1080p")

        ret, frame = camera.read_frame()
        self.assertTrue(ret)
        self.assertEqual(frame.shape, (480, 640, 3))
        camera.release()

    # =========================================================================
    # P0-07: Frames are released
    # =========================================================================
    def test_p0_07_frames_are_released(self):
        scheduler = FrameScheduler(target_fps=5)
        simulated_time = 0.0
        fps_step = 1.0 / 30.0

        # Simulate 1000 frames (representing sustained streaming)
        for _ in range(1000):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            dispatched = scheduler.submit_frame(frame, current_time=simulated_time)
            if dispatched:
                # Process and release
                result = scheduler.process_next(lambda f: f.shape)
                self.assertEqual(result, (480, 640, 3))
            
            # Queue size must strictly stay bounded (0 or 1 max)
            self.assertLessEqual(scheduler.queue_size, 1)
            simulated_time += fps_step

        # After processing, queue size should be 0
        self.assertEqual(scheduler.queue_size, 0)

    # =========================================================================
    # P0-08: Adaptive throttle hook
    # =========================================================================
    def test_p0_08_adaptive_throttle_hook(self):
        scheduler = FrameScheduler(target_fps=5)
        self.assertEqual(scheduler.target_fps, 5)
        self.assertAlmostEqual(scheduler.frame_interval, 0.20, places=3)

        # Dynamically change to 2 FPS (e.g. Battery Mode / Idle)
        scheduler.set_target_fps(2)
        self.assertEqual(scheduler.target_fps, 2)
        self.assertAlmostEqual(scheduler.frame_interval, 0.50, places=3)

        # Verify scheduling adapted immediately without restarting
        sim_time = 2000.0
        frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertTrue(scheduler.submit_frame(frame1, current_time=sim_time))

        # A frame arriving at +0.25s (which would pass at 5 FPS) should now be dropped at 2 FPS
        frame2 = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertFalse(scheduler.submit_frame(frame2, current_time=sim_time + 0.25))

        # A frame arriving at +0.51s should be accepted
        frame3 = np.zeros((480, 640, 3), dtype=np.uint8)
        self.assertTrue(scheduler.submit_frame(frame3, current_time=sim_time + 0.51))

    # =========================================================================
    # P0-10: Camera unavailable recoverable state
    # =========================================================================
    def test_p0_10_camera_unavailable_recoverable_state(self):
        # Camera index 999 does not exist, should fail gracefully into fallback without crashing
        camera = CameraManager(camera_index=999, target_fps=5, mock_mode=False)
        self.assertTrue(camera.mock_mode)
        ret, frame = camera.read_frame()
        self.assertTrue(ret)
        self.assertIsNotNone(frame)
        camera.release()

    # =========================================================================
    # P0-12: Zero frame persistence verification
    # =========================================================================
    def test_p0_12_zero_frame_persistence(self):
        # Scan workspace for any image or video file
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".mp4", ".avi", ".mov", ".mkv", ".raw"}
        workspace = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        discovered_media = []
        for root, dirs, files in os.walk(workspace):
            # Skip virtual environments or node_modules if any
            if ".venv" in root or "node_modules" in root or ".git" in root:
                continue
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in image_extensions:
                    discovered_media.append(os.path.join(root, f))

        self.assertEqual(len(discovered_media), 0, f"No image or video files should exist in workspace, found: {discovered_media}")


if __name__ == "__main__":
    unittest.main()
