"""
Setup wizard for freeMarkable.

This module provides the initial setup wizard interface including welcome screen,
device connection setup, WiFi configuration guidance, pre-flight checks, and
beginner-friendly step-by-step flow for first-time users.
"""

import tkinter as tk
from typing import Optional, Callable, Dict, Any, List
import customtkinter as ctk
import threading
from enum import Enum

from remarkable_xovi_installer.models.device import Device, DeviceType, ConnectionStatus
from remarkable_xovi_installer.utils.validators import get_validator, ValidationResult
from remarkable_xovi_installer.utils.logger import get_logger
from remarkable_xovi_installer.config.settings import get_config


class WizardStep(Enum):
    """Setup wizard steps."""
    WELCOME = "welcome"
    DEVICE_CONNECTION = "device_connection"
    DEVICE_TEST = "device_test"
    WIFI_SETUP = "wifi_setup"
    REQUIREMENTS_CHECK = "requirements_check"
    SUMMARY = "summary"
    COMPLETE = "complete"


class SetupWizard:
    """
    Initial setup wizard for first-time users.
    
    Provides a guided step-by-step setup process including:
    - Welcome screen with overview
    - Device connection configuration
    - Connection testing and device detection
    - WiFi setup guidance
    - System requirements verification
    - Configuration summary and completion
    """
    
    def __init__(self, parent, completion_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initialize setup wizard.
        
        Args:
            parent: Parent window
            completion_callback: Callback for wizard completion
        """
        self.parent = parent
        self.completion_callback = completion_callback
        
        # Core services
        self.validator = get_validator()
        self.logger = get_logger()
        
        try:
            self.config = get_config()
        except RuntimeError:
            self.config = None
        
        # Wizard state
        self.current_step = WizardStep.WELCOME
        self.wizard_data: Dict[str, Any] = {}
        self.device: Optional[Device] = None
        
        # UI components
        self.wizard_window: Optional[ctk.CTkToplevel] = None
        self.step_frames: Dict[WizardStep, ctk.CTkFrame] = {}
        self.navigation_frame: Optional[ctk.CTkFrame] = None
        
        # Navigation buttons
        self.back_button: Optional[ctk.CTkButton] = None
        self.next_button: Optional[ctk.CTkButton] = None
        self.cancel_button: Optional[ctk.CTkButton] = None
        
        # Step-specific widgets
        self.step_widgets: Dict[str, ctk.CTkWidget] = {}
        
        # Setup wizard window
        self._create_wizard_window()
        self._setup_navigation()
        self._create_all_steps()
        self._show_step(WizardStep.WELCOME)
    
    def _create_wizard_window(self) -> None:
        """Create the main wizard window."""
        self.wizard_window = ctk.CTkToplevel(self.parent)
        self.wizard_window.title("freeMarkable - Setup Wizard")
        self.wizard_window.geometry("700x500")
        self.wizard_window.resizable(False, False)
        
        # Center the window
        self.wizard_window.update_idletasks()
        x = (self.wizard_window.winfo_screenwidth() // 2) - (700 // 2)
        y = (self.wizard_window.winfo_screenheight() // 2) - (500 // 2)
        self.wizard_window.geometry(f"700x500+{x}+{y}")
        
        # Make it modal
        self.wizard_window.transient(self.parent)
        self.wizard_window.grab_set()
        
        # Handle window close
        self.wizard_window.protocol("WM_DELETE_WINDOW", self._on_cancel)
        
        # Configure grid
        self.wizard_window.grid_columnconfigure(0, weight=1)
        self.wizard_window.grid_rowconfigure(0, weight=1)
        
        # Main content frame
        self.content_frame = ctk.CTkFrame(self.wizard_window)
        self.content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(1, weight=1)
        
        # Header frame
        header_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        header_frame.grid_columnconfigure(1, weight=1)
        
        # Wizard title
        title_label = ctk.CTkLabel(
            header_frame,
            text="🔧 Setup Wizard",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w")
        
        # Step indicator
        self.step_indicator = ctk.CTkLabel(
            header_frame,
            text="Step 1 of 6",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.step_indicator.grid(row=0, column=1, sticky="e")
        
        # Steps container
        self.steps_container = ctk.CTkFrame(self.content_frame)
        self.steps_container.grid(row=1, column=0, sticky="nsew")
        self.steps_container.grid_columnconfigure(0, weight=1)
        self.steps_container.grid_rowconfigure(0, weight=1)
    
    def _setup_navigation(self) -> None:
        """Setup navigation buttons."""
        self.navigation_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.navigation_frame.grid(row=2, column=0, sticky="ew", pady=(20, 0))
        self.navigation_frame.grid_columnconfigure(1, weight=1)
        
        # Cancel button
        self.cancel_button = ctk.CTkButton(
            self.navigation_frame,
            text="Cancel",
            command=self._on_cancel,
            width=80,
            fg_color="gray",
            hover_color="#606060"
        )
        self.cancel_button.grid(row=0, column=0, sticky="w")
        
        # Navigation buttons frame
        nav_buttons_frame = ctk.CTkFrame(self.navigation_frame, fg_color="transparent")
        nav_buttons_frame.grid(row=0, column=2, sticky="e")
        
        # Back button
        self.back_button = ctk.CTkButton(
            nav_buttons_frame,
            text="< Back",
            command=self._on_back,
            width=80,
            state="disabled"
        )
        self.back_button.grid(row=0, column=0, padx=(0, 10))
        
        # Next button
        self.next_button = ctk.CTkButton(
            nav_buttons_frame,
            text="Next >",
            command=self._on_next,
            width=80
        )
        self.next_button.grid(row=0, column=1)
    
    def _create_all_steps(self) -> None:
        """Create all wizard step frames."""
        steps = [
            WizardStep.WELCOME,
            WizardStep.DEVICE_CONNECTION,
            WizardStep.DEVICE_TEST,
            WizardStep.WIFI_SETUP,
            WizardStep.REQUIREMENTS_CHECK,
            WizardStep.SUMMARY
        ]
        
        for step in steps:
            frame = ctk.CTkFrame(self.steps_container, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(0, weight=1)
            frame.grid_remove()  # Hide initially
            
            self.step_frames[step] = frame
            
            # Create step content
            if step == WizardStep.WELCOME:
                self._create_welcome_step(frame)
            elif step == WizardStep.DEVICE_CONNECTION:
                self._create_device_connection_step(frame)
            elif step == WizardStep.DEVICE_TEST:
                self._create_device_test_step(frame)
            elif step == WizardStep.WIFI_SETUP:
                self._create_wifi_setup_step(frame)
            elif step == WizardStep.REQUIREMENTS_CHECK:
                self._create_requirements_check_step(frame)
            elif step == WizardStep.SUMMARY:
                self._create_summary_step(frame)
    
    def _create_welcome_step(self, parent: ctk.CTkFrame) -> None:
        """Create welcome step content."""
        # Welcome content frame
        content_frame = ctk.CTkFrame(parent)
        content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        content_frame.grid_columnconfigure(0, weight=1)
        
        # Welcome title
        welcome_title = ctk.CTkLabel(
            content_frame,
            text="Welcome to freeMarkable!",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        welcome_title.grid(row=0, column=0, pady=(20, 15))
        
        # Welcome message
        welcome_message = ctk.CTkLabel(
            content_frame,
            text=(
                "This wizard will guide you through the initial setup process for installing "
                "XOVI (Extended XOCHITL Interface) on your reMarkable device.\n\n"
                "XOVI provides enhanced functionality including:\n"
                "• Application launcher for third-party apps\n"
                "• KOReader integration for advanced reading\n"
                "• Extended customization options\n"
                "• Plugin system for additional features\n\n"
                "Before we begin, please ensure:\n"
                "• Your reMarkable device is powered on\n"
                "• USB cable is connected (or WiFi is configured)\n"
                "• You have your device's SSH password ready\n\n"
                "This process will take approximately 10-15 minutes."
            ),
            font=ctk.CTkFont(size=13),
            wraplength=600,
            justify="left"
        )
        welcome_message.grid(row=1, column=0, pady=(0, 20), sticky="ew")
        
        # Important notice
        notice_frame = ctk.CTkFrame(content_frame)
        notice_frame.grid(row=2, column=0, sticky="ew", pady=(10, 20))
        
        notice_title = ctk.CTkLabel(
            notice_frame,
            text="⚠️ Important Notice",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FFD700"
        )
        notice_title.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        
        notice_text = ctk.CTkLabel(
            notice_frame,
            text=(
                "• This installer will modify your reMarkable device's software\n"
                "• A backup will be created automatically before installation\n"
                "• Installation can be reversed using the backup if needed\n"
                "• Ensure your device has sufficient storage space (>100MB free)"
            ),
            font=ctk.CTkFont(size=12),
            wraplength=580,
            justify="left"
        )
        notice_text.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
    
    def _create_device_connection_step(self, parent: ctk.CTkFrame) -> None:
        """Create device connection step content."""
        content_frame = ctk.CTkFrame(parent)
        content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        content_frame.grid_columnconfigure(0, weight=1)
        
        # Step title
        title = ctk.CTkLabel(
            content_frame,
            text="Device Connection Setup",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.grid(row=0, column=0, pady=(20, 15))
        
        # Instructions
        instructions = ctk.CTkLabel(
            content_frame,
            text=(
                "Please enter your reMarkable device connection details below.\n"
                "You can find your SSH password in Settings > Help > Copyrights and licenses."
            ),
            font=ctk.CTkFont(size=13),
            wraplength=600
        )
        instructions.grid(row=1, column=0, pady=(0, 20))
        
        # Connection form
        form_frame = ctk.CTkFrame(content_frame)
        form_frame.grid(row=2, column=0, sticky="ew", pady=(0, 20))
        form_frame.grid_columnconfigure(1, weight=1)
        
        # IP Address
        ip_label = ctk.CTkLabel(form_frame, text="IP Address:")
        ip_label.grid(row=0, column=0, padx=(20, 10), pady=15, sticky="w")
        
        self.step_widgets["ip_entry"] = ctk.CTkEntry(
            form_frame,
            placeholder_text="10.11.99.1 (USB) or 192.168.x.x (WiFi)",
            width=300
        )
        self.step_widgets["ip_entry"].grid(row=0, column=1, padx=(0, 20), pady=15, sticky="ew")
        self.step_widgets["ip_entry"].insert(0, "10.11.99.1")  # Default USB IP
        
        # Bind validation to IP entry changes
        self.step_widgets["ip_entry"].bind("<KeyRelease>", self._on_connection_field_change)
        self.step_widgets["ip_entry"].bind("<FocusOut>", self._on_connection_field_change)
        
        # SSH Password
        password_label = ctk.CTkLabel(form_frame, text="SSH Password:")
        password_label.grid(row=1, column=0, padx=(20, 10), pady=15, sticky="w")
        
        self.step_widgets["password_entry"] = ctk.CTkEntry(
            form_frame,
            placeholder_text="Enter SSH password from device settings",
            show="*",
            width=300
        )
        self.step_widgets["password_entry"].grid(row=1, column=1, padx=(0, 20), pady=15, sticky="ew")
        
        # Bind validation to password entry changes
        self.step_widgets["password_entry"].bind("<KeyRelease>", self._on_connection_field_change)
        self.step_widgets["password_entry"].bind("<FocusOut>", self._on_connection_field_change)
        
        # Help section
        help_frame = ctk.CTkFrame(content_frame)
        help_frame.grid(row=3, column=0, sticky="ew")
        
        help_title = ctk.CTkLabel(
            help_frame,
            text="📖 How to find your SSH password:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        help_title.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        
        help_text = ctk.CTkLabel(
            help_frame,
            text=(
                "1. On your reMarkable device, go to Settings\n"
                "2. Scroll down and tap 'Help'\n"
                "3. Tap 'Copyrights and licenses'\n"
                "4. Look for the SSH password (usually starts with letters/numbers)\n"
                "5. The password is case-sensitive and contains no spaces"
            ),
            font=ctk.CTkFont(size=12),
            justify="left"
        )
        help_text.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
    
    def _create_device_test_step(self, parent: ctk.CTkFrame) -> None:
        """Create device test step content."""
        content_frame = ctk.CTkFrame(parent)
        content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        content_frame.grid_columnconfigure(0, weight=1)
        
        # Step title
        title = ctk.CTkLabel(
            content_frame,
            text="Device Connection Test",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.grid(row=0, column=0, pady=(20, 15))
        
        # Test status frame
        status_frame = ctk.CTkFrame(content_frame)
        status_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        status_frame.grid_columnconfigure(1, weight=1)
        
        # Test button
        self.step_widgets["test_button"] = ctk.CTkButton(
            status_frame,
            text="Test Connection",
            command=self._test_device_connection,
            width=120
        )
        self.step_widgets["test_button"].grid(row=0, column=0, padx=20, pady=20)
        
        # Status display
        self.step_widgets["test_status"] = ctk.CTkLabel(
            status_frame,
            text="Click 'Test Connection' to verify device connectivity",
            font=ctk.CTkFont(size=13)
        )
        self.step_widgets["test_status"].grid(row=0, column=1, padx=(10, 20), pady=20, sticky="w")
        
        # Device info frame (initially hidden)
        self.step_widgets["device_info_frame"] = ctk.CTkFrame(content_frame)
        self.step_widgets["device_info_frame"].grid(row=2, column=0, sticky="ew", pady=(0, 20))
        self.step_widgets["device_info_frame"].grid_remove()
        
        # Device info content
        info_title = ctk.CTkLabel(
            self.step_widgets["device_info_frame"],
            text="Device Information:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        info_title.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        
        self.step_widgets["device_info_text"] = ctk.CTkLabel(
            self.step_widgets["device_info_frame"],
            text="",
            font=ctk.CTkFont(size=12),
            justify="left"
        )
        self.step_widgets["device_info_text"].grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
    
    def _create_wifi_setup_step(self, parent: ctk.CTkFrame) -> None:
        """Create WiFi setup step content."""
        content_frame = ctk.CTkFrame(parent)
        content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        content_frame.grid_columnconfigure(0, weight=1)
        
        # Step title
        title = ctk.CTkLabel(
            content_frame,
            text="WiFi Configuration (Optional)",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.grid(row=0, column=0, pady=(20, 15))
        
        # WiFi info
        wifi_info = ctk.CTkLabel(
            content_frame,
            text=(
                "WiFi connectivity allows you to use the installer without a USB cable.\n"
                "This step is optional - you can skip it if you prefer to use USB connection."
            ),
            font=ctk.CTkFont(size=13),
            wraplength=600
        )
        wifi_info.grid(row=1, column=0, pady=(0, 20))
        
        # WiFi instructions
        instructions_frame = ctk.CTkFrame(content_frame)
        instructions_frame.grid(row=2, column=0, sticky="ew", pady=(0, 20))
        
        instructions_title = ctk.CTkLabel(
            instructions_frame,
            text="📶 WiFi Setup Instructions:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        instructions_title.grid(row=0, column=0, padx=15, pady=(15, 10), sticky="w")
        
        instructions_text = ctk.CTkLabel(
            instructions_frame,
            text=(
                "1. On your reMarkable device, swipe down from the top\n"
                "2. Tap the WiFi icon (📶) to open WiFi settings\n"
                "3. Select your WiFi network from the list\n"
                "4. Enter your WiFi password when prompted\n"
                "5. Wait for the connection to establish\n"
                "6. Note the IP address shown in the network info\n"
                "7. Update the IP address in the previous step if needed"
            ),
            font=ctk.CTkFont(size=12),
            justify="left"
        )
        instructions_text.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
        
        # Skip option
        skip_frame = ctk.CTkFrame(content_frame)
        skip_frame.grid(row=3, column=0, sticky="ew")
        
        self.step_widgets["wifi_skip_checkbox"] = ctk.CTkCheckBox(
            skip_frame,
            text="Skip WiFi setup - I'll use USB connection only",
            font=ctk.CTkFont(size=12),
            command=self._on_wifi_field_change
        )
        self.step_widgets["wifi_skip_checkbox"].grid(row=0, column=0, padx=15, pady=15)
    
    def _create_requirements_check_step(self, parent: ctk.CTkFrame) -> None:
        """Create requirements check step content."""
        content_frame = ctk.CTkFrame(parent)
        content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        content_frame.grid_columnconfigure(0, weight=1)
        
        # Step title
        title = ctk.CTkLabel(
            content_frame,
            text="System Requirements Check",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.grid(row=0, column=0, pady=(20, 15))
        
        # Check button
        check_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        check_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        
        self.step_widgets["check_button"] = ctk.CTkButton(
            check_frame,
            text="Check Requirements",
            command=self._check_requirements,
            width=150
        )
        self.step_widgets["check_button"].grid(row=0, column=0, padx=20, pady=10)
        
        # Requirements results
        self.step_widgets["requirements_frame"] = ctk.CTkScrollableFrame(
            content_frame,
            label_text="Requirements Check Results"
        )
        self.step_widgets["requirements_frame"].grid(row=2, column=0, sticky="nsew", pady=(0, 20))
        
        # Initial message
        initial_message = ctk.CTkLabel(
            self.step_widgets["requirements_frame"],
            text="Click 'Check Requirements' to verify system compatibility",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        initial_message.grid(row=0, column=0, pady=20)
    
    def _create_summary_step(self, parent: ctk.CTkFrame) -> None:
        """Create summary step content."""
        content_frame = ctk.CTkFrame(parent)
        content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        content_frame.grid_columnconfigure(0, weight=1)
        
        # Step title
        title = ctk.CTkLabel(
            content_frame,
            text="Setup Summary",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.grid(row=0, column=0, pady=(20, 15))
        
        # Summary frame
        self.step_widgets["summary_frame"] = ctk.CTkFrame(content_frame)
        self.step_widgets["summary_frame"].grid(row=1, column=0, sticky="ew", pady=(0, 20))
        
        # Summary content will be populated when step is shown
        self.step_widgets["summary_content"] = ctk.CTkLabel(
            self.step_widgets["summary_frame"],
            text="",
            font=ctk.CTkFont(size=12),
            justify="left"
        )
        self.step_widgets["summary_content"].grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        # Ready message
        ready_frame = ctk.CTkFrame(content_frame)
        ready_frame.grid(row=2, column=0, sticky="ew")
        
        ready_title = ctk.CTkLabel(
            ready_frame,
            text="✅ Ready to Complete Setup",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="green"
        )
        ready_title.grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        
        ready_text = ctk.CTkLabel(
            ready_frame,
            text=(
                "Click 'Finish' to save your configuration and close the setup wizard.\n"
                "You can then use the main application to install XOVI on your device."
            ),
            font=ctk.CTkFont(size=12),
            wraplength=580
        )
        ready_text.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="w")
    
    def _show_step(self, step: WizardStep) -> None:
        """Show a specific wizard step."""
        # Hide all steps
        for frame in self.step_frames.values():
            frame.grid_remove()
        
        # Show current step
        if step in self.step_frames:
            self.step_frames[step].grid()
        
        self.current_step = step
        self._update_navigation()
        self._update_step_indicator()
        
        # Step-specific actions
        if step == WizardStep.DEVICE_TEST:
            self._reset_device_test_step()
        elif step == WizardStep.SUMMARY:
            self._populate_summary()
    
    def _update_navigation(self) -> None:
        """Update navigation button states."""
        # Back button
        if self.current_step == WizardStep.WELCOME:
            self.back_button.configure(state="disabled")
        else:
            self.back_button.configure(state="normal")
        
        # Next/Finish button
        if self.current_step == WizardStep.SUMMARY:
            self.next_button.configure(text="Finish")
        else:
            self.next_button.configure(text="Next >")
        
        # Enable/disable next based on step validation
        if self._validate_current_step():
            self.next_button.configure(state="normal")
        else:
            self.next_button.configure(state="disabled")
    
    def _update_step_indicator(self) -> None:
        """Update step indicator display."""
        step_numbers = {
            WizardStep.WELCOME: 1,
            WizardStep.DEVICE_CONNECTION: 2,
            WizardStep.DEVICE_TEST: 3,
            WizardStep.WIFI_SETUP: 4,
            WizardStep.REQUIREMENTS_CHECK: 5,
            WizardStep.SUMMARY: 6
        }
        
        current_num = step_numbers.get(self.current_step, 1)
        self.step_indicator.configure(text=f"Step {current_num} of 6")
    
    def _validate_current_step(self) -> bool:
        """Validate current step and return if it's complete."""
        if self.current_step == WizardStep.WELCOME:
            return True
        elif self.current_step == WizardStep.DEVICE_CONNECTION:
            ip = self.step_widgets["ip_entry"].get().strip()
            password = self.step_widgets["password_entry"].get().strip()
            return bool(ip and password)
        elif self.current_step == WizardStep.DEVICE_TEST:
            return self.device is not None and self.device.is_connected()
        elif self.current_step == WizardStep.WIFI_SETUP:
            return True  # Optional step
        elif self.current_step == WizardStep.REQUIREMENTS_CHECK:
            return True  # Will be validated when requirements are checked
        elif self.current_step == WizardStep.SUMMARY:
            return True
        
        return False
    
    def _on_connection_field_change(self, event=None) -> None:
        """Handle changes to connection fields to update validation."""
        if self.current_step == WizardStep.DEVICE_CONNECTION:
            # Clear any previous device connection when details change
            if self.device:
                current_ip = self.step_widgets["ip_entry"].get().strip()
                current_password = self.step_widgets["password_entry"].get().strip()
                
                # Check if connection details have changed
                if (self.device.ip_address != current_ip or
                    self.device.ssh_password != current_password):
                    # Connection details changed, invalidate previous connection
                    self.device = None
                    self.wizard_data.pop("device", None)
                    self.wizard_data.pop("device_type", None)
            
            # Re-validate and update navigation
            self._update_navigation()
    
    def _on_wifi_field_change(self) -> None:
        """Handle changes to WiFi fields to update validation."""
        if self.current_step == WizardStep.WIFI_SETUP:
            # Re-validate and update navigation
            self._update_navigation()
    
    def _on_next(self) -> None:
        """Handle next button click."""
        if not self._validate_current_step():
            return
        
        # Save current step data
        self._save_step_data()
        
        # Determine next step
        next_step = self._get_next_step()
        if next_step:
            self._show_step(next_step)
        else:
            # Wizard complete
            self._complete_wizard()
    
    def _on_back(self) -> None:
        """Handle back button click."""
        previous_step = self._get_previous_step()
        if previous_step:
            self._show_step(previous_step)
    
    def _on_cancel(self) -> None:
        """Handle cancel/close."""
        self.wizard_window.destroy()
    
    def _get_next_step(self) -> Optional[WizardStep]:
        """Get the next step in the wizard."""
        steps = [
            WizardStep.WELCOME,
            WizardStep.DEVICE_CONNECTION,
            WizardStep.DEVICE_TEST,
            WizardStep.WIFI_SETUP,
            WizardStep.REQUIREMENTS_CHECK,
            WizardStep.SUMMARY
        ]
        
        try:
            current_index = steps.index(self.current_step)
            if current_index < len(steps) - 1:
                return steps[current_index + 1]
        except ValueError:
            pass
        
        return None
    
    def _get_previous_step(self) -> Optional[WizardStep]:
        """Get the previous step in the wizard."""
        steps = [
            WizardStep.WELCOME,
            WizardStep.DEVICE_CONNECTION,
            WizardStep.DEVICE_TEST,
            WizardStep.WIFI_SETUP,
            WizardStep.REQUIREMENTS_CHECK,
            WizardStep.SUMMARY
        ]
        
        try:
            current_index = steps.index(self.current_step)
            if current_index > 0:
                return steps[current_index - 1]
        except ValueError:
            pass
        
        return None
    
    def _save_step_data(self) -> None:
        """Save data from current step."""
        if self.current_step == WizardStep.DEVICE_CONNECTION:
            self.wizard_data["ip_address"] = self.step_widgets["ip_entry"].get().strip()
            self.wizard_data["ssh_password"] = self.step_widgets["password_entry"].get().strip()
            # Clear previous device connection state when connection details change
            if self.device:
                self.device = None
                self.wizard_data.pop("device", None)
                self.wizard_data.pop("device_type", None)
        elif self.current_step == WizardStep.WIFI_SETUP:
            self.wizard_data["wifi_skip"] = self.step_widgets["wifi_skip_checkbox"].get()
    
    def _reset_device_test_step(self) -> None:
        """Reset the device test step to initial state."""
        # Reset test button
        self.step_widgets["test_button"].configure(state="normal", text="Test Connection")
        
        # Reset status message
        self.step_widgets["test_status"].configure(
            text="Click 'Test Connection' to verify device connectivity",
            text_color="white"  # Default color
        )
        
        # Hide device info frame
        self.step_widgets["device_info_frame"].grid_remove()
        
        # Clear any previous device connection if connection details changed
        current_ip = self.wizard_data.get("ip_address", "").strip()
        current_password = self.wizard_data.get("ssh_password", "").strip()
        
        if self.device:
            # Check if connection details have changed
            if (self.device.ip_address != current_ip or
                self.device.ssh_password != current_password):
                # Connection details changed, clear previous device
                self.device = None
                self.wizard_data.pop("device", None)
                self.wizard_data.pop("device_type", None)
    
    def _test_device_connection(self) -> None:
        """Test device connection."""
        # Get connection details from previous step
        ip_address = self.wizard_data.get("ip_address", "").strip()
        ssh_password = self.wizard_data.get("ssh_password", "").strip()
        
        if not ip_address or not ssh_password:
            self.step_widgets["test_status"].configure(
                text="❌ Please go back and enter connection details",
                text_color="red"
            )
            return
        
        # Update UI
        self.step_widgets["test_button"].configure(state="disabled", text="Testing...")
        self.step_widgets["test_status"].configure(
            text="🔄 Testing connection...",
            text_color="orange"
        )
        
        # Test in background thread
        threading.Thread(target=self._test_connection_async, args=(ip_address, ssh_password), daemon=True).start()
    
    def _test_connection_async(self, ip_address: str, ssh_password: str) -> None:
        """Test connection in background thread."""
        try:
            # Create device
            self.device = Device(ip_address=ip_address, ssh_password=ssh_password)
            
            # Test connection
            success = self.device.test_connection()
            
            # If connection successful, detect device type
            if success:
                self.device.detect_device_type()
            
            # Update UI in main thread
            self.wizard_window.after(0, self._connection_test_complete, success)
            
        except Exception as e:
            self.wizard_window.after(0, self._connection_test_complete, False, str(e))
    
    def _connection_test_complete(self, success: bool, error: str = "") -> None:
        """Handle connection test completion."""
        self.step_widgets["test_button"].configure(state="normal", text="Test Connection")
        
        if success and self.device:
            self.step_widgets["test_status"].configure(
                text="✅ Connection successful!",
                text_color="green"
            )
            
            # Show device info
            device_info = f"Device Type: {self.device.device_type.display_name if self.device.device_type else 'Unknown'}\n"
            device_info += f"IP Address: {self.device.ip_address}\n"
            device_info += f"Status: Connected"
            
            self.step_widgets["device_info_text"].configure(text=device_info)
            self.step_widgets["device_info_frame"].grid()
            
            # Save device info
            self.wizard_data["device"] = self.device
            self.wizard_data["device_type"] = self.device.device_type
            
        else:
            error_msg = f"❌ Connection failed"
            if error:
                error_msg += f": {error}"
            
            self.step_widgets["test_status"].configure(
                text=error_msg,
                text_color="red"
            )
            self.step_widgets["device_info_frame"].grid_remove()
        
        # Update navigation
        self._update_navigation()
    
    def _check_requirements(self) -> None:
        """Check system requirements."""
        # Clear previous results
        for widget in self.step_widgets["requirements_frame"].winfo_children():
            widget.destroy()
        
        self.step_widgets["check_button"].configure(state="disabled", text="Checking...")
        
        # Run checks in background
        threading.Thread(target=self._check_requirements_async, daemon=True).start()
    
    def _check_requirements_async(self) -> None:
        """Check requirements in background thread."""
        results = []
        
        # Check SSH availability
        ssh_result = self.validator.check_ssh_requirements()
        results.append(("SSH Tools", ssh_result.is_valid, ssh_result.message))
        
        # Check device storage (if connected)
        if self.device and self.device.is_connected():
            try:
                # Refresh device info to get storage information
                if self.device.refresh_device_info():
                    if self.device.device_info and self.device.device_info.free_space:
                        # Check if we have at least 100MB free space
                        free_mb = self.device.device_info.get_free_space_mb()
                        if free_mb and free_mb >= 100:
                            results.append(("Device Storage", True, f"Sufficient storage: {free_mb:.1f} MB free"))
                        else:
                            results.append(("Device Storage", False, f"Insufficient storage: {free_mb:.1f} MB free (need 100MB)"))
                    else:
                        results.append(("Device Storage", True, "Storage check completed (details unavailable)"))
                else:
                    results.append(("Device Storage", False, "Could not check device storage"))
            except Exception as e:
                results.append(("Device Storage", False, f"Storage check failed: {e}"))
        else:
            results.append(("Device Storage", False, "Device not connected for check"))
        
        # Update UI in main thread
        self.wizard_window.after(0, self._requirements_check_complete, results)
    
    def _requirements_check_complete(self, results: List[tuple]) -> None:
        """Handle requirements check completion."""
        self.step_widgets["check_button"].configure(state="normal", text="Check Requirements")
        
        for i, (name, passed, message) in enumerate(results):
            result_frame = ctk.CTkFrame(self.step_widgets["requirements_frame"], fg_color="transparent")
            result_frame.grid(row=i, column=0, sticky="ew", pady=2)
            result_frame.grid_columnconfigure(1, weight=1)
            
            # Status icon
            icon = "✅" if passed else "❌"
            color = "green" if passed else "red"
            
            status_label = ctk.CTkLabel(result_frame, text=icon, text_color=color, width=30)
            status_label.grid(row=0, column=0, padx=(10, 5))
            
            # Requirement name
            name_label = ctk.CTkLabel(result_frame, text=name, font=ctk.CTkFont(size=12, weight="bold"))
            name_label.grid(row=0, column=1, sticky="w")
            
            # Message
            message_label = ctk.CTkLabel(result_frame, text=message, font=ctk.CTkFont(size=11), text_color="gray")
            message_label.grid(row=1, column=1, sticky="w", padx=(0, 10))
        
        # Save results
        self.wizard_data["requirements_passed"] = all(result[1] for result in results)
    
    def _populate_summary(self) -> None:
        """Populate the summary step with configuration details."""
        summary_text = "Configuration Summary:\n\n"
        
        # Device info
        if "ip_address" in self.wizard_data:
            summary_text += f"Device IP: {self.wizard_data['ip_address']}\n"
        
        if "device_type" in self.wizard_data and self.wizard_data["device_type"]:
            summary_text += f"Device Type: {self.wizard_data['device_type'].display_name}\n"
        
        # WiFi setup
        wifi_skip = self.wizard_data.get("wifi_skip", False)
        summary_text += f"WiFi Setup: {'Skipped' if wifi_skip else 'Configured'}\n"
        
        # Requirements
        requirements_passed = self.wizard_data.get("requirements_passed", False)
        summary_text += f"Requirements Check: {'✅ Passed' if requirements_passed else '❌ Failed'}\n\n"
        
        summary_text += "The wizard will save these settings for use in the main application."
        
        self.step_widgets["summary_content"].configure(text=summary_text)
    
    def _complete_wizard(self) -> None:
        """Complete the wizard and return data."""
        if self.completion_callback:
            self.completion_callback(self.wizard_data)
        
        self.wizard_window.destroy()
    
    def show(self) -> None:
        """Show the wizard window."""
        if self.wizard_window:
            self.wizard_window.deiconify()
            self.wizard_window.lift()
    
    def hide(self) -> None:
        """Hide the wizard window."""
        if self.wizard_window:
            self.wizard_window.withdraw()