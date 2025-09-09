"""
Service modules for freeMarkable.

This module provides service layers for file operations, network communication,
firmware management, and other core functionalities that support the application's business logic.
"""

from .file_service import FileService
from .codexctl_service import CodexCtlService

__all__ = ["FileService", "CodexCtlService"]