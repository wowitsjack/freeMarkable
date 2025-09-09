"""
freeMarkable - Python Port

A sophisticated Python application for installing XOVI on reMarkable tablets,
ported from the original Bash script with enhanced GUI and functionality.
"""

__version__ = "1.0.4"
__author__ = "freeMarkable Team"
__description__ = "Python port of the freeMarkable installer with CustomTkinter GUI"

# Package-level imports for convenience
from .config.settings import AppConfig
from .models.device import Device
from .models.installation_state import InstallationState
from .utils.logger import get_logger
from .utils.validators import Validator
from .services.file_service import FileService

__all__ = [
    "AppConfig",
    "Device", 
    "InstallationState",
    "get_logger",
    "Validator",
    "FileService"
]