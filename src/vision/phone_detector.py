"""
DeskSense Lightweight Phone Detector (ONNX Runtime)
Provides CPU-optimized inference for mobile phone detection with graceful fallback.
Mandate: Camera frames processed in volatile RAM only; zero frame persistence.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List, Any
import numpy as np

logger = logging.getLogger("DeskSense.PhoneDetector")


@dataclass
class PhoneDetectionResult:
    detected: bool
    confidence: float
    bbox: Optional[Tuple[float, float, float, float]] = None  # (ymin, xmin, ymax, xmax) normalized [0, 1]


class PhoneDetector:
    """
    Lightweight ONNX Runtime-based mobile phone detector.
    Operates strictly on CPU using CPUExecutionProvider.
    Fails gracefully if model is missing or corrupt.
    """

    def __init__(
        self,
        model_path: str = "models/phone_detector_quantized.onnx",
        confidence_threshold: float = 0.5,
    ):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.is_ready = False
        self.session = None
        self.input_name = None
        self.input_shape = (1, 3, 192, 192)

        self._initialize_session()

    def _initialize_session(self) -> None:
        """Initializes the ONNX runtime session safely."""
        if not os.path.exists(self.model_path):
            logger.warning(f"Phone detector model not found at {self.model_path}. Phone detection disabled.")
            self.is_ready = False
            return

        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            # Explicitly require CPUExecutionProvider
            self.session = ort.InferenceSession(
                self.model_path,
                sess_options=opts,
                providers=["CPUExecutionProvider"]
            )
            inputs = self.session.get_inputs()
            if inputs:
                self.input_name = inputs[0].name
                if len(inputs[0].shape) == 4:
                    self.input_shape = tuple(
                        dim if isinstance(dim, int) and dim > 0 else 1 for dim in inputs[0].shape
                    )
            self.is_ready = True
            logger.info(f"Phone detector successfully loaded on CPU from {self.model_path}")
        except Exception as e:
            logger.warning(f"Failed to load ONNX phone detector from {self.model_path}: {e}. Phone detection disabled.")
            self.is_ready = False
            self.session = None

    def detect(self, frame: Optional[np.ndarray]) -> PhoneDetectionResult:
        """
        Performs inference on a frame in volatile memory.
        Returns PhoneDetectionResult. Zero frame persistence.
        """
        if not self.is_ready or self.session is None or frame is None or frame.size == 0:
            return PhoneDetectionResult(detected=False, confidence=0.0, bbox=None)

        try:
            # Preprocess frame into normalized float tensor
            h, w = self.input_shape[2], self.input_shape[3]
            import cv2
            resized = cv2.resize(frame, (w, h))
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB) if len(resized.shape) == 3 and resized.shape[2] == 3 else resized
            tensor = rgb.astype(np.float32) / 255.0
            tensor = np.transpose(tensor, (2, 0, 1))  # HWC -> CHW
            tensor = np.expand_dims(tensor, axis=0)  # BCHW

            outputs = self.session.run(None, {self.input_name: tensor})
            
            # Parse output format
            if len(outputs) >= 2:
                scores = outputs[0].flatten()
                boxes = outputs[1].reshape(-1, 4)
                max_idx = int(np.argmax(scores)) if len(scores) > 0 else -1
                max_score = float(scores[max_idx]) if max_idx >= 0 else 0.0
                if max_score >= self.confidence_threshold and max_idx >= 0:
                    box = tuple(float(c) for c in boxes[max_idx])
                    return PhoneDetectionResult(detected=True, confidence=max_score, bbox=box)
            elif len(outputs) == 1:
                raw = outputs[0].flatten()
                max_score = float(np.max(raw)) if len(raw) > 0 else 0.0
                if max_score >= self.confidence_threshold:
                    return PhoneDetectionResult(detected=True, confidence=max_score, bbox=(0.2, 0.2, 0.8, 0.8))

            return PhoneDetectionResult(detected=False, confidence=0.0, bbox=None)
        except Exception as e:
            logger.error(f"Error during phone detection inference: {e}")
            return PhoneDetectionResult(detected=False, confidence=0.0, bbox=None)
