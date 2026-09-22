"""
DeskSense Host Sidecar Client
Manages lifecycle of the isolated vision sidecar subprocess.
Handles start, health checks, observation streaming, failure isolation, and clean termination.
"""

import subprocess
import sys
import json
import os
import time
from typing import Optional, Dict, Any

from src.ipc.schema import Observation, IPCValidationError

class SidecarClient:
    def __init__(self, python_path: Optional[str] = None):
        self.python_path = python_path or sys.executable
        self.process: Optional[subprocess.Popen] = None
        self.status = "DISCONNECTED"
        self.sidecar_script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "src", "ipc", "sidecar.py"
        )

    def start(self, timeout_sec: float = 5.0) -> bool:
        """Starts sidecar child process and waits for ready status."""
        try:
            self.process = subprocess.Popen(
                [self.python_path, self.sidecar_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            
            # Wait for ready signal
            t0 = time.time()
            while time.time() - t0 < timeout_sec:
                if self.process.poll() is not None:
                    self.status = "UNAVAILABLE"
                    return False

                line = self.process.stdout.readline()
                if line:
                    data = json.loads(line.strip())
                    if data.get("type") == "status" and data.get("status") == "READY":
                        self.status = "READY"
                        return True
                time.sleep(0.05)

            self.status = "UNAVAILABLE"
            return False
        except Exception as e:
            self.status = "UNAVAILABLE"
            return False

    def send_command(self, cmd: Dict[str, Any], timeout_sec: float = 3.0) -> Optional[Dict[str, Any]]:
        """Sends command to sidecar and receives JSON response."""
        if not self.is_running():
            self.status = "UNAVAILABLE"
            return None

        try:
            cmd_str = json.dumps(cmd) + "\n"
            self.process.stdin.write(cmd_str)
            self.process.stdin.flush()

            # Read response
            line = self.process.stdout.readline()
            if not line:
                self.status = "UNAVAILABLE"
                return None
            return json.loads(line.strip())
        except Exception:
            self.status = "UNAVAILABLE"
            return None

    def health_check(self) -> bool:
        """Sends ping to verify sidecar health."""
        resp = self.send_command({"command": "health"})
        if resp and resp.get("status") == "HEALTHY":
            return True
        return False

    def get_observation(self, active_app: str = "Code.exe") -> Optional[Observation]:
        """Requests an observation from sidecar and parses into Observation schema."""
        resp = self.send_command({"command": "observe", "active_app": active_app})
        if resp and resp.get("type") == "observation" and "data" in resp:
            try:
                return Observation.from_dict(resp["data"])
            except IPCValidationError:
                return None
        return None

    def is_running(self) -> bool:
        """Returns True if child process is currently alive."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def stop(self, timeout_sec: float = 3.0):
        """Stops sidecar process cleanly, ensuring no orphan process remains."""
        if self.process is not None and self.is_running():
            try:
                self.send_command({"command": "stop"})
                self.process.wait(timeout=timeout_sec)
            except Exception:
                # Force terminate if it didn't exit cleanly
                try:
                    self.process.terminate()
                    self.process.wait(timeout=1.0)
                except Exception:
                    self.process.kill()
            finally:
                self._close_streams()
                self.process = None
                self.status = "STOPPED"
        else:
            self._close_streams()
            self.process = None
            self.status = "STOPPED"

    def _close_streams(self):
        """Close stdio pipe handles cleanly."""
        if self.process:
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                if stream and not stream.closed:
                    try:
                        stream.close()
                    except Exception:
                        pass
