"""
GUI wizards package for freeMarkable.

This package contains wizard-style interfaces that guide users through
complex setup and configuration processes. Wizards provide step-by-step
flows for tasks that require multiple inputs or decisions.

Wizards:
    - setup_wizard: Initial application setup and device configuration
                   Guides users through first-time setup including device
                   connection, WiFi configuration, and pre-flight checks

All wizards are designed to be user-friendly and accessible, with clear
navigation and helpful instructions at each step.
"""

from .setup_wizard import SetupWizard

__all__ = ['SetupWizard']