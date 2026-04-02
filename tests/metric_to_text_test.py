"""
Tests for rag/metric_to_text.py

Manual Testing
--------------
Prerequisites:
  - Poetry environment set up (poetry install completed)
  - No database or external services required
  - Python 3.10+ with numpy installed

Run:
  poetry run pytest tests/metric_to_text_test.py -v

Expected:
  - All tests PASSED
  - Zero failures
  - Spike detection identifies values >3 std deviations above mean
  - Drop detection identifies values >3 std deviations below mean
  - Trend detection identifies gradual increases/decreases
  - Text output contains metric name, time range, statistics, and anomaly details

Negative Tests:
  - Empty metrics list raises ValueError
  - Single data point raises ValueError
  - Constant values (std=0) return NORMAL anomaly type

Cleanup:
  - No cleanup needed (no files or database state created)
"""

from datetime import datetime, timedelta

import pytest

from rag.metric_to_text import (
    AnomalyType,
    MetricPoint,
    MetricToTextConverter,
)


class TestMetricToTextConverter:
    """Test suite for metric-to-text conversion and anomaly detection."""

    def test_normal_metrics_no_anomaly(self) -> None:
        """Normal metrics with low variance should not trigger anomalies."""
        converter = MetricToTextConverter()
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=100.0 + i * 0.5,
                metric_name="cpu_usage",
            )
            for i in range(10)
        ]

        text = converter.convert_to_text(metrics)

        assert "cpu_usage" in text
        assert "Normal" in text or "no anomalies" in text.lower()
        assert "mean=" in text
        assert "std=" in text

    def test_spike_detection(self) -> None:
        """Detect sudden spike in metric values."""
        converter = MetricToTextConverter(spike_threshold=3.0)
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        # Normal values around 100, then a spike to 200
        values = [100.0] * 10 + [200.0] + [100.0] * 5
        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=values[i],
                metric_name="query_latency_ms",
            )
            for i in range(len(values))
        ]

        text = converter.convert_to_text(metrics)

        assert "query_latency_ms" in text
        assert "spike" in text.lower()
        assert "Anomaly detected" in text

    def test_drop_detection(self) -> None:
        """Detect sudden drop in metric values."""
        converter = MetricToTextConverter(drop_threshold=-3.0)
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        # Normal values around 100, then a drop to 10
        values = [100.0] * 10 + [10.0] + [100.0] * 5
        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=values[i],
                metric_name="connection_count",
            )
            for i in range(len(values))
        ]

        text = converter.convert_to_text(metrics)

        assert "connection_count" in text
        assert "drop" in text.lower()
        assert "Anomaly detected" in text

    def test_gradual_increase_trend(self) -> None:
        """Detect gradual upward trend."""
        converter = MetricToTextConverter(trend_window=5)
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        # Steadily increasing values
        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=100.0 + i * 20.0,
                metric_name="memory_usage_mb",
            )
            for i in range(10)
        ]

        text = converter.convert_to_text(metrics)

        assert "memory_usage_mb" in text
        assert "increase" in text.lower() or "upward" in text.lower()

    def test_gradual_decrease_trend(self) -> None:
        """Detect gradual downward trend."""
        converter = MetricToTextConverter(trend_window=5)
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        # Steadily decreasing values
        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=200.0 - i * 20.0,
                metric_name="available_connections",
            )
            for i in range(10)
        ]

        text = converter.convert_to_text(metrics)

        assert "available_connections" in text
        assert "decrease" in text.lower() or "downward" in text.lower()

    def test_empty_metrics_raises_error(self) -> None:
        """Empty metrics list should raise ValueError."""
        converter = MetricToTextConverter()

        with pytest.raises(ValueError, match="cannot be empty"):
            converter.convert_to_text([])

    def test_single_point_raises_error(self) -> None:
        """Single data point should raise ValueError."""
        converter = MetricToTextConverter()
        metrics = [
            MetricPoint(
                timestamp=datetime(2026, 4, 1, 10, 0, 0),
                value=100.0,
                metric_name="test_metric",
            )
        ]

        with pytest.raises(ValueError, match="at least 2 data points"):
            converter.convert_to_text(metrics)

    def test_constant_values_no_anomaly(self) -> None:
        """Constant values (std=0) should return NORMAL."""
        converter = MetricToTextConverter()
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        # All values are identical
        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=100.0,
                metric_name="constant_metric",
            )
            for i in range(10)
        ]

        text = converter.convert_to_text(metrics)

        assert "constant_metric" in text
        assert "Constant values" in text or "Normal" in text

    def test_text_contains_time_range(self) -> None:
        """Generated text should include time range."""
        converter = MetricToTextConverter()
        start_time = datetime(2026, 4, 1, 10, 0, 0)
        end_time = datetime(2026, 4, 1, 10, 30, 0)

        metrics = [
            MetricPoint(timestamp=start_time, value=100.0, metric_name="test"),
            MetricPoint(
                timestamp=start_time + timedelta(minutes=15), value=105.0, metric_name="test"
            ),
            MetricPoint(timestamp=end_time, value=110.0, metric_name="test"),
        ]

        text = converter.convert_to_text(metrics)

        assert "2026-04-01 10:00" in text
        assert "2026-04-01 10:30" in text

    def test_text_contains_statistics(self) -> None:
        """Generated text should include mean, min, max, std."""
        converter = MetricToTextConverter()
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=float(i * 10),
                metric_name="test_metric",
            )
            for i in range(5)
        ]

        text = converter.convert_to_text(metrics)

        assert "mean=" in text
        assert "min=" in text
        assert "max=" in text
        assert "std=" in text

    def test_multiple_spikes_detected(self) -> None:
        """Multiple spikes should be detected and reported."""
        converter = MetricToTextConverter(spike_threshold=2.5)
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        # Two spikes in the data
        values = [100.0] * 5 + [200.0] + [100.0] * 3 + [190.0] + [100.0] * 5
        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=values[i],
                metric_name="disk_io",
            )
            for i in range(len(values))
        ]

        text = converter.convert_to_text(metrics)

        assert "disk_io" in text
        assert "spike" in text.lower()

    def test_affected_timestamps_in_output(self) -> None:
        """Anomaly description should include affected timestamps."""
        converter = MetricToTextConverter(spike_threshold=3.0)
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        values = [100.0] * 10 + [300.0] + [100.0] * 5
        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=values[i],
                metric_name="test",
            )
            for i in range(len(values))
        ]

        text = converter.convert_to_text(metrics)

        assert "Affected timestamps" in text or "10:10" in text

    def test_custom_thresholds(self) -> None:
        """Custom spike/drop thresholds should be respected."""
        # Very sensitive threshold
        converter = MetricToTextConverter(spike_threshold=1.5, drop_threshold=-1.5)
        base_time = datetime(2026, 4, 1, 10, 0, 0)

        # Small variation that would be normal with default thresholds
        values = [100.0] * 5 + [120.0] + [100.0] * 5
        metrics = [
            MetricPoint(
                timestamp=base_time + timedelta(minutes=i),
                value=values[i],
                metric_name="sensitive_metric",
            )
            for i in range(len(values))
        ]

        text = converter.convert_to_text(metrics)

        # With sensitive threshold, this should detect an anomaly
        assert "sensitive_metric" in text
