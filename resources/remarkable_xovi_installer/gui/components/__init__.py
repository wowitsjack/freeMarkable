"""
GUI components package for freeMarkable.

This package contains all the individual GUI components that make up
the main application interface. Each component is designed to be
modular and reusable, with clear separation of concerns.

Components:
    - device_panel: Device connection and configuration interface
    - menu_panel: Main menu with installation options
    - progress_panel: Installation progress tracking and display
    - log_panel: Log message display with filtering capabilities

All components integrate with the core application modules and follow
CustomTkinter design patterns for consistency and modern appearance.
"""

from .device_panel import DevicePanel
from .menu_panel import MenuPanel
from .progress_panel import ProgressPanel
from .log_panel import LogPanel

__all__ = [
    'DevicePanel',
    'MenuPanel', 
    'ProgressPanel',
    'LogPanel'
]