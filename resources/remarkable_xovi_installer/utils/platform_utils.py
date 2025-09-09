"""
Platform-specific utilities for freeMarkable.

This module provides cross-platform functions for determining OS-specific paths
for configuration, cache, and logs, ensuring the application behaves correctly
on Windows, macOS, and Linux.
"""

import os
import sys
from pathlib import Path


def is_windows() -> bool:
    """Check if the current operating system is Windows."""
    return os.name == 'nt'


def get_platform_config_dir(app_name: str) -> Path:
    """
    Get the platform-appropriate configuration directory for the application.

    Args:
        app_name: The name of the application.

    Returns:
        A Path object pointing to the configuration directory.
    """
    if is_windows():
        # Windows: %APPDATA%\app_name
        config_dir = Path(os.getenv('APPDATA', '')) / app_name
    elif sys.platform == 'darwin':  # macOS
        # macOS: ~/Library/Application Support/app_name
        config_dir = Path.home() / 'Library' / 'Application Support' / app_name
    else:  # Linux and other Unix-like
        # Linux: ~/.config/app_name
        config_dir = Path.home() / '.config' / app_name
    
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_platform_cache_dir(app_name: str) -> Path:
    """
    Get the platform-appropriate cache directory for the application.

    Args:
        app_name: The name of the application.

    Returns:
        A Path object pointing to the cache directory.
    """
    if is_windows():
        # Windows: %LOCALAPPDATA%\app_name\Cache
        cache_dir = Path(os.getenv('LOCALAPPDATA', '')) / app_name / 'Cache'
    elif sys.platform == 'darwin':  # macOS
        # macOS: ~/Library/Caches/app_name
        cache_dir = Path.home() / 'Library' / 'Caches' / app_name
    else:  # Linux and other Unix-like
        # Linux: ~/.cache/app_name
        cache_dir = Path.home() / '.cache' / app_name
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_platform_log_dir(app_name: str) -> Path:
    """
    Get the platform-appropriate log directory for the application.

    Args:
        app_name: The name of the application.

    Returns:
        A Path object pointing to the log directory.
    """
    if is_windows():
        # Windows: %LOCALAPPDATA%\app_name\Logs
        log_dir = Path(os.getenv('LOCALAPPDATA', '')) / app_name / 'Logs'
    elif sys.platform == 'darwin':  # macOS
        # macOS: ~/Library/Logs/app_name
        log_dir = Path.home() / 'Library' / 'Logs' / app_name
    else:  # Linux and other Unix-like
        # Linux: ~/.local/share/app_name/logs
        log_dir = Path.home() / '.local' / 'share' / app_name / 'logs'
    
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir