"""
Data models for freeMarkable.

This module contains core data structures representing devices, installation
states, and other entities used throughout the application.
"""

from .device import Device
from .installation_state import InstallationState

__all__ = ["Device", "InstallationState"]