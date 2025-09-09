"""
GUI package for freeMarkable.

This package provides a modern CustomTkinter-based graphical user interface
for the freeMarkable application. It includes all the GUI
components, wizards, and utilities needed for a complete user experience.

Components:
    - main_window: Main application window with menu system
    - device_panel: Device connection and status management
    - menu_panel: Primary menu interface with all installation options
    - progress_panel: Installation progress tracking and display
    - log_panel: Log message display with filtering and scrolling
    - setup_wizard: Initial setup and configuration wizard

The GUI integrates seamlessly with the core modules for configuration,
device management, installation state tracking, logging, and file operations.
"""

from .main_window import MainWindow

__all__ = ['MainWindow']