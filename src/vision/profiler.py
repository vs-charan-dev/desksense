"""
DeskSense Profiler & Performance Monitor
Tracks real-time process CPU utilization, RAM usage, and frame processing latency.
Enforces the performance constraints specified in PRD Section 43 (<10% CPU, <500MB RAM).
"""

import time
import os
import psutil

class SystemProfiler:
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        # Initial call to cpu_percent needs to establish baseline
        self.process.cpu_percent(interval=None)
        psutil.cpu_percent(interval=None)
        
        self.start_time = time.time()
        self.num_cpus = os.cpu_count() or 1
        self.last_cpu_time = time.time()
        self.last_proc_cpu_time = self.process.cpu_times()
        self.cached_proc_cpu = 0.0
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.current_fps = 0.0
        self.inference_latencies = []

    def tick(self, latency_ms: float = 0.0):
        """Record frame completion and inference latency."""
        self.frame_count += 1
        now = time.time()
        elapsed = now - self.last_fps_time
        if elapsed >= 1.0:
            self.current_fps = self.frame_count / elapsed
            self.frame_count = 0
            self.last_fps_time = now
        
        if latency_ms > 0:
            self.inference_latencies.append(latency_ms)
            if len(self.inference_latencies) > 60:
                self.inference_latencies.pop(0)

    def get_metrics(self) -> dict:
        """Returns snapshot of current resource utilization."""
        now = time.time()
        elapsed = now - self.last_cpu_time
        
        try:
            mem_info = self.process.memory_info()
            ram_mb = mem_info.rss / (1024 * 1024)
            sys_cpu = psutil.cpu_percent(interval=None)

            # Update CPU calculation on 0.5s intervals to avoid micro-slice noise
            if elapsed >= 0.5:
                curr_cpu_times = self.process.cpu_times()
                proc_delta = (curr_cpu_times.user - self.last_proc_cpu_time.user) + \
                             (curr_cpu_times.system - self.last_proc_cpu_time.system)
                # Normalized CPU: percentage of total machine capacity (same as Windows Task Manager)
                self.cached_proc_cpu = max(0.0, (proc_delta / elapsed / self.num_cpus) * 100.0)
                self.last_cpu_time = now
                self.last_proc_cpu_time = curr_cpu_times
            
            proc_cpu = self.cached_proc_cpu
        except Exception:
            ram_mb = 0.0
            proc_cpu = 0.0
            sys_cpu = 0.0

        avg_latency = (
            sum(self.inference_latencies) / len(self.inference_latencies)
            if self.inference_latencies else 0.0
        )

        return {
            "fps": round(self.current_fps, 1),
            "ram_mb": round(ram_mb, 1),
            "process_cpu_pct": round(proc_cpu, 1),
            "system_cpu_pct": round(sys_cpu, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "uptime_sec": round(time.time() - self.start_time, 1)
        }
