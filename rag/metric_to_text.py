"""
Metric-to-Text Converter

Converts time-series database metrics into semantic text descriptions
for RAG retrieval. Performs statistical analysis to detect anomalies
like spikes, drops, and trends.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List

import numpy as np


class AnomalyType(Enum):
    """Types of detected anomalies in time-series data."""

    SPIKE = "spike"
    DROP = "drop"
    GRADUAL_INCREASE = "gradual_increase"
    GRADUAL_DECREASE = "gradual_decrease"
    NORMAL = "normal"


@dataclass
class MetricPoint:
    """Single time-series data point."""

    timestamp: datetime
    value: float
    metric_name: str


@dataclass
class AnomalyDetection:
    """Result of anomaly detection analysis."""

    anomaly_type: AnomalyType
    severity: float  # 0.0 to 1.0
    description: str
    affected_points: List[int]  # Indices of anomalous points


class MetricToTextConverter:
    """
    Converts time-series metrics to semantic text descriptions.

    Uses statistical analysis (z-score, moving averages) to detect
    anomalies and generate human-readable descriptions suitable
    for RAG embedding and retrieval.
    """

    def __init__(
        self,
        spike_threshold: float = 3.0,
        drop_threshold: float = -3.0,
        trend_window: int = 5,
    ):
        """
        Initialize converter with detection thresholds.

        Args:
            spike_threshold: Z-score threshold for spike detection (default: 3.0)
            drop_threshold: Z-score threshold for drop detection (default: -3.0)
            trend_window: Window size for trend analysis (default: 5)
        """
        self.spike_threshold = spike_threshold
        self.drop_threshold = drop_threshold
        self.trend_window = trend_window

    def convert_to_text(self, metrics: List[MetricPoint]) -> str:
        """
        Convert time-series metrics to semantic text description.

        Args:
            metrics: List of metric data points (must be sorted by timestamp)

        Returns:
            Human-readable text description of the metric behavior

        Raises:
            ValueError: If metrics list is empty or has < 2 points
        """
        if not metrics:
            raise ValueError("Metrics list cannot be empty")
        if len(metrics) < 2:
            raise ValueError("Need at least 2 data points for analysis")

        metric_name = metrics[0].metric_name
        values = np.array([m.value for m in metrics])
        timestamps = [m.timestamp for m in metrics]

        # Detect anomalies
        anomaly = self._detect_anomaly(values)

        # Generate description
        description = self._generate_description(
            metric_name, values, timestamps, anomaly
        )

        return description

    def _detect_anomaly(self, values: np.ndarray) -> AnomalyDetection:
        """
        Detect anomalies using statistical analysis.

        Uses z-score for spike/drop detection and linear regression
        for trend analysis.
        """
        if len(values) < 3:
            return AnomalyDetection(
                anomaly_type=AnomalyType.NORMAL,
                severity=0.0,
                description="Insufficient data for anomaly detection",
                affected_points=[],
            )

        # Calculate z-scores
        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return AnomalyDetection(
                anomaly_type=AnomalyType.NORMAL,
                severity=0.0,
                description="Constant values, no variation",
                affected_points=[],
            )

        z_scores = (values - mean) / std

        # Check for spikes
        spike_indices = np.where(z_scores > self.spike_threshold)[0]
        if len(spike_indices) > 0:
            max_z = np.max(z_scores[spike_indices])
            severity = min(abs(max_z) / 10.0, 1.0)
            return AnomalyDetection(
                anomaly_type=AnomalyType.SPIKE,
                severity=severity,
                description=f"Spike detected at {len(spike_indices)} point(s)",
                affected_points=spike_indices.tolist(),
            )

        # Check for drops
        drop_indices = np.where(z_scores < self.drop_threshold)[0]
        if len(drop_indices) > 0:
            min_z = np.min(z_scores[drop_indices])
            severity = min(abs(min_z) / 10.0, 1.0)
            return AnomalyDetection(
                anomaly_type=AnomalyType.DROP,
                severity=severity,
                description=f"Drop detected at {len(drop_indices)} point(s)",
                affected_points=drop_indices.tolist(),
            )

        # Check for trends (using last N points)
        if len(values) >= self.trend_window:
            recent_values = values[-self.trend_window :]
            x = np.arange(len(recent_values))
            slope = np.polyfit(x, recent_values, 1)[0]

            # Normalize slope by mean to get relative change
            relative_slope = slope / mean if mean != 0 else 0

            if relative_slope > 0.1:  # 10% increase per point
                severity = min(abs(relative_slope), 1.0)
                return AnomalyDetection(
                    anomaly_type=AnomalyType.GRADUAL_INCREASE,
                    severity=severity,
                    description="Gradual upward trend detected",
                    affected_points=list(range(len(values) - self.trend_window, len(values))),
                )
            elif relative_slope < -0.1:  # 10% decrease per point
                severity = min(abs(relative_slope), 1.0)
                return AnomalyDetection(
                    anomaly_type=AnomalyType.GRADUAL_DECREASE,
                    severity=severity,
                    description="Gradual downward trend detected",
                    affected_points=list(range(len(values) - self.trend_window, len(values))),
                )

        return AnomalyDetection(
            anomaly_type=AnomalyType.NORMAL,
            severity=0.0,
            description="No significant anomalies detected",
            affected_points=[],
        )

    def _generate_description(
        self,
        metric_name: str,
        values: np.ndarray,
        timestamps: List[datetime],
        anomaly: AnomalyDetection,
    ) -> str:
        """Generate human-readable description of metric behavior."""
        mean_val = np.mean(values)
        min_val = np.min(values)
        max_val = np.max(values)
        std_val = np.std(values)

        time_range = f"{timestamps[0].strftime('%Y-%m-%d %H:%M')} to {timestamps[-1].strftime('%Y-%m-%d %H:%M')}"

        description_parts = [
            f"Metric: {metric_name}",
            f"Time range: {time_range}",
            f"Statistics: mean={mean_val:.2f}, min={min_val:.2f}, max={max_val:.2f}, std={std_val:.2f}",
        ]

        if anomaly.anomaly_type != AnomalyType.NORMAL:
            description_parts.append(
                f"Anomaly detected: {anomaly.anomaly_type.value} (severity: {anomaly.severity:.2f})"
            )
            description_parts.append(f"Details: {anomaly.description}")

            if anomaly.affected_points:
                affected_times = [
                    timestamps[i].strftime("%H:%M:%S")
                    for i in anomaly.affected_points[:3]
                ]
                description_parts.append(
                    f"Affected timestamps: {', '.join(affected_times)}"
                    + (" ..." if len(anomaly.affected_points) > 3 else "")
                )
        else:
            description_parts.append("Behavior: Normal, no anomalies detected")

        return " | ".join(description_parts)
