"""Utilities for capturing and annotating VM diagnostic metadata."""

DMESG_CAPTURE_COMMAND = "dmesg --color=never 2>&1 || dmesg 2>&1 || true"

__all__ = ["DMESG_CAPTURE_COMMAND"]
