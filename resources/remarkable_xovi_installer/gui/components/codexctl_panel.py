"""
CodexCtl panel for freeMarkable.

This module provides the CodexCtl interface for firmware management including
firmware status display, version selection, installation controls, and 
progress tracking for firmware operations.
"""

import tkinter as tk
from typing import Optional, Callable, Dict, Any, List
import customtkinter as ctk
import threading
import sys
from datetime import datetime

from remarkable_xovi_installer.services.codexctl_service import (
    get_codexctl_service, 
    CodexCtlService,
    FirmwareVersion,
    CodexCtlProgress,
    CodexCtlOperation
)
from remarkable_xovi_installer.utils.logger import get_logger
from remarkable_xovi_installer.config.settings import get_config


class CodexCtlPanel(ctk.CTkFrame):
    """
    CodexCtl panel component for firmware management.
    
    Provides interface for firmware operations including:
    - Current firmware status display
    - Available firmware version selection
    - Install and restore operations
    - Progress tracking and status updates
    - Error handling and user feedback
    """
    
    def __init__(self, parent, 
                 progress_callback: Optional[Callable[[CodexCtlProgress], None]] = None,
                 status_callback: Optional[Callable[[str], None]] = None,
                 **kwargs):
        """
        Initialize CodexCtl panel.
        
        Args:
            parent: Parent widget
            progress_callback: Callback for progress updates
            status_callback: Callback for status messages
            **kwargs: Additional CTkFrame arguments
        """
        super().__init__(parent, **kwargs)
        
        # Callbacks
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        
        # Core services
        try:
            self.logger = get_logger()
        except RuntimeError:
            import logging
            self.logger = logging.getLogger(__name__)
        
        try:
            self.config = get_config()
        except RuntimeError:
            self.config = None
        
        # Service state (initialize early for all cases)
        self.codexctl_service: Optional[CodexCtlService] = None
        self.available_versions: List[FirmwareVersion] = []
        self.current_status: Dict[str, Any] = {}
        self.is_operation_running = False
        
        # UI variables (initialize early for all cases)
        self.selected_version_var = tk.StringVar()
        self.status_text_var = tk.StringVar(value="Not connected")
        self.backup_enabled_var = tk.BooleanVar(value=True)
        
        # Loading state (initialize early for all cases)
        self.is_loading = True
        self.loading_overlay = None
        self.spinner_angle = 0
        self.spinner_job = None
        
        # Check Python version compatibility
        if not self._check_python_version():
            self._create_version_error_ui()
            return
        
        # Setup UI (only if version check passed)
        self._setup_ui()
        self._show_loading_overlay()
        self._initialize_service()
    
    def _setup_ui(self) -> None:
        """Setup the CodexCtl panel user interface."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        
        # Header frame
        self._setup_header()
        
        # Controls frame
        self._setup_controls()
        
        # Status frame
        self._setup_status_display()
        
        # Progress frame (initially hidden)
        self._setup_progress_display()
    
    def _setup_header(self) -> None:
        """Setup panel header with title and refresh button."""
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        header_frame.grid_columnconfigure(1, weight=1)
        
        # Panel title
        title_label = ctk.CTkLabel(
            header_frame,
            text="🔧 Firmware Management (CodexCtl)",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w")
        
        # Refresh button
        self.refresh_button = ctk.CTkButton(
            header_frame,
            text="🔄 Refresh",
            command=self._refresh_data,
            width=100,
            height=32
        )
        self.refresh_button.grid(row=0, column=1, sticky="e")
        
        # Status indicator
        self.connection_status_label = ctk.CTkLabel(
            header_frame,
            textvariable=self.status_text_var,
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.connection_status_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
    
    def _setup_controls(self) -> None:
        """Setup firmware operation controls."""
        controls_frame = ctk.CTkFrame(self)
        controls_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        controls_frame.grid_columnconfigure(1, weight=1)
        
        # Current firmware section
        current_frame = ctk.CTkFrame(controls_frame)
        current_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        current_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            current_frame,
            text="Current Firmware:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        
        self.current_firmware_label = ctk.CTkLabel(
            current_frame,
            text="Unknown",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.current_firmware_label.grid(row=0, column=1, sticky="w", padx=5, pady=(10, 5))
        
        self.firmware_details_label = ctk.CTkLabel(
            current_frame,
            text="Status: Not checked",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.firmware_details_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))
        
        # Version selection section
        selection_frame = ctk.CTkFrame(controls_frame)
        selection_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        selection_frame.grid_columnconfigure(1, weight=1)
        
        ctk.CTkLabel(
            selection_frame,
            text="Available Versions:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        
        self.version_dropdown = ctk.CTkOptionMenu(
            selection_frame,
            variable=self.selected_version_var,
            values=["Loading..."],
            width=200,
            command=self._on_version_selected
        )
        self.version_dropdown.grid(row=0, column=1, sticky="w", padx=5, pady=(10, 5))
        
        # Backup option
        self.backup_checkbox = ctk.CTkCheckBox(
            selection_frame,
            text="Create backup before install",
            variable=self.backup_enabled_var,
            font=ctk.CTkFont(size=11)
        )
        self.backup_checkbox.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(5, 10))
        
        # Action buttons
        buttons_frame = ctk.CTkFrame(controls_frame)
        buttons_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        
        self.install_button = ctk.CTkButton(
            buttons_frame,
            text="📦 Install Firmware",
            command=self._install_firmware,
            width=150,
            height=40,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        self.install_button.grid(row=0, column=0, padx=10, pady=10)
        
        self.restore_button = ctk.CTkButton(
            buttons_frame,
            text="🔄 Restore Backup",
            command=self._restore_firmware,
            width=150,
            height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="orange",
            hover_color="#cc8800"
        )
        self.restore_button.grid(row=0, column=1, padx=10, pady=10)
        
        self.cancel_button = ctk.CTkButton(
            buttons_frame,
            text="❌ Cancel",
            command=self._cancel_operation,
            width=100,
            height=40,
            fg_color="#8b2635",
            hover_color="#6b1c28",
            state="disabled"
        )
        self.cancel_button.grid(row=0, column=2, padx=10, pady=10)
    
    def _setup_status_display(self) -> None:
        """Setup status and information display."""
        status_frame = ctk.CTkFrame(self)
        status_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        status_frame.grid_columnconfigure(0, weight=1)
        status_frame.grid_rowconfigure(1, weight=1)
        
        # Status title
        ctk.CTkLabel(
            status_frame,
            text="📊 Firmware Information",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        
        # Status text display
        self.status_textbox = ctk.CTkTextbox(
            status_frame,
            wrap="word",
            height=150,
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled"
        )
        self.status_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # Initialize with placeholder text
        self._update_status_display("CodexCtl panel initialized.\nConnect to device to check firmware status.")
    
    def _setup_progress_display(self) -> None:
        """Setup progress display (initially hidden)."""
        self.progress_frame = ctk.CTkFrame(self)
        self.progress_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.progress_frame.grid_columnconfigure(1, weight=1)
        self.progress_frame.grid_remove()  # Hidden by default
        
        # Progress title
        self.progress_title_label = ctk.CTkLabel(
            self.progress_frame,
            text="Operation Progress",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.progress_title_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 5))
        
        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            width=300,
            height=20
        )
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        self.progress_bar.set(0)
        
        # Progress details
        self.progress_details_label = ctk.CTkLabel(
            self.progress_frame,
            text="Ready...",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.progress_details_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))
    
    def _initialize_service(self) -> None:
        """Initialize CodexCtl service."""
        try:
            self.codexctl_service = get_codexctl_service()
            self.logger.info("CodexCtl service connected")
            
            # Set up service callbacks if available
            if self.codexctl_service:
                self.codexctl_service.set_progress_callback(self._on_progress_update)
                self.codexctl_service.set_output_callback(self._on_output_update)
                self.codexctl_service.set_binary_ready_callback(self._on_binary_ready)
                
        except RuntimeError as e:
            # Service not initialized yet, will be handled later
            self.logger.debug(f"CodexCtl service not yet initialized: {e}")
            self.codexctl_service = None
        except Exception as e:
            self.logger.error(f"Failed to connect CodexCtl panel to service: {e}")
            self.codexctl_service = None
            # Hide loading overlay on failure - but only if it exists and was properly initialized
            try:
                if (hasattr(self, 'loading_overlay') and
                    self.loading_overlay and
                    hasattr(self, '_update_loading_status')):
                    self._update_loading_status(f"Service initialization failed: {e}")
                    # Don't hide overlay immediately, let user see the error
                    self.after(3000, self._hide_loading_overlay)  # Hide after 3 seconds
                elif hasattr(self, 'loading_overlay'):
                    # If loading_overlay exists but update method doesn't work, just hide it
                    self.after(1000, self._hide_loading_overlay)
            except Exception as overlay_error:
                self.logger.debug(f"Could not update loading overlay on service init error: {overlay_error}")
    
    def set_codexctl_service(self, service: CodexCtlService) -> None:
        """Set the CodexCtl service instance."""
        self.codexctl_service = service
        service.set_progress_callback(self._on_progress_update)
        service.set_output_callback(self._on_output_update)
        service.set_binary_ready_callback(self._on_binary_ready)
        
        # Check binary availability and hide loading overlay if ready
        self._check_binary_availability()
    
    def _refresh_data(self) -> None:
        """Refresh firmware data and device status."""
        if not self.codexctl_service:
            self._update_status("CodexCtl service not available")
            return
        
        # Check if UI elements exist (they won't if Python version check failed)
        if hasattr(self, 'refresh_button') and self.refresh_button:
            self.refresh_button.configure(text="🔄 Refreshing...", state="disabled")
        
        self._update_status("Refreshing firmware data...")
        
        # Run refresh in background thread
        threading.Thread(target=self._refresh_data_async, daemon=True).start()
    
    def _refresh_data_async(self) -> None:
        """Perform async data refresh."""
        try:
            # Check if binary is available
            if not self.codexctl_service.ensure_binary_available():
                self.after(0, lambda: self._refresh_complete(False, "CodexCtl binary not available"))
                return
            
            # Get available versions
            versions = self.codexctl_service.get_firmware_versions(force_refresh=True)
            
            # Get device status
            status = self.codexctl_service.get_device_status()
            
            # Update UI in main thread
            self.after(0, lambda: self._refresh_complete(True, None, versions, status))
            
        except Exception as e:
            self.logger.error(f"Data refresh failed: {e}")
            self.after(0, lambda: self._refresh_complete(False, str(e)))
    
    def _refresh_complete(self, success: bool, error: Optional[str] = None,
                         versions: Optional[List[FirmwareVersion]] = None,
                         status: Optional[Dict[str, Any]] = None) -> None:
        """Handle refresh completion."""
        # Check if UI elements exist (they won't if Python version check failed)
        if hasattr(self, 'refresh_button') and self.refresh_button:
            self.refresh_button.configure(text="🔄 Refresh", state="normal")
        
        if success and versions is not None:
            self.available_versions = versions
            if hasattr(self, '_update_version_dropdown'):
                self._update_version_dropdown()
            
            if status:
                self.current_status = status
                if hasattr(self, '_update_current_firmware_display'):
                    self._update_current_firmware_display()
            
            self._update_status("Firmware data refreshed successfully")
        else:
            error_msg = error or "Failed to refresh firmware data"
            self._update_status(f"Refresh failed: {error_msg}")
    
    def _update_version_dropdown(self) -> None:
        """Update the version selection dropdown."""
        # Check if UI elements exist (they won't if Python version check failed)
        if not hasattr(self, 'version_dropdown') or not self.version_dropdown:
            return
        
        if not self.available_versions:
            self.version_dropdown.configure(values=["No versions available"])
            self.version_dropdown.set("No versions available")
            return
        
        # Create version list with descriptions
        version_options = []
        for version in self.available_versions:
            if version.is_supported:
                option = f"{version.version} ({version.release_date})"
                version_options.append(option)
        
        if not version_options:
            version_options = ["No supported versions"]
        
        self.version_dropdown.configure(values=version_options)
        if version_options and version_options[0] != "No supported versions":
            self.version_dropdown.set(version_options[0])
    
    def _update_current_firmware_display(self) -> None:
        """Update current firmware information display."""
        # Check if UI elements exist (they won't if Python version check failed)
        if not hasattr(self, 'current_firmware_label') or not self.current_firmware_label:
            return
        
        if not self.current_status or "error" in self.current_status:
            if hasattr(self, 'current_firmware_label') and self.current_firmware_label:
                self.current_firmware_label.configure(text="Unknown", text_color="gray")
            error_msg = self.current_status.get("error", "Status unavailable") if self.current_status else "Not checked"
            if hasattr(self, 'firmware_details_label') and self.firmware_details_label:
                self.firmware_details_label.configure(text=f"Status: {error_msg}", text_color="orange")
            return
        
        # Extract firmware info
        version = self.current_status.get("current_version", "Unknown")
        build_id = self.current_status.get("build_id", "")
        
        if hasattr(self, 'current_firmware_label') and self.current_firmware_label:
            self.current_firmware_label.configure(text=version, text_color="white")
        
        # Additional details
        details = []
        if build_id:
            details.append(f"Build: {build_id}")
        
        update_available = self.current_status.get("update_available", False)
        if update_available:
            details.append("Update available")
            detail_color = "orange"
        else:
            details.append("Up to date")
            detail_color = "green"
        
        detail_text = " | ".join(details) if details else "Status: OK"
        if hasattr(self, 'firmware_details_label') and self.firmware_details_label:
            self.firmware_details_label.configure(text=detail_text, text_color=detail_color)
        
        # Update status display with detailed info
        status_info = self._format_status_info(self.current_status)
        self._update_status_display(status_info)
    
    def _format_status_info(self, status: Dict[str, Any]) -> str:
        """Format status information for display."""
        info_lines = [
            "=== Current Firmware Status ===",
            f"Version: {status.get('current_version', 'Unknown')}",
            f"Build ID: {status.get('build_id', 'Unknown')}",
            f"Release Date: {status.get('release_date', 'Unknown')}",
            ""
        ]
        
        if status.get("update_available"):
            info_lines.extend([
                "📢 UPDATE AVAILABLE",
                f"Latest Version: {status.get('latest_version', 'Unknown')}",
                ""
            ])
        
        if "device_info" in status:
            device_info = status["device_info"]
            info_lines.extend([
                "=== Device Information ===",
                f"Model: {device_info.get('model', 'Unknown')}",
                f"Serial: {device_info.get('serial', 'Unknown')}",
                f"Hardware: {device_info.get('hardware_version', 'Unknown')}",
                ""
            ])
        
        if "backup_info" in status:
            backup_info = status["backup_info"]
            info_lines.extend([
                "=== Backup Information ===",
                f"Available Backups: {backup_info.get('count', 0)}",
                f"Latest Backup: {backup_info.get('latest_date', 'None')}",
                ""
            ])
        
        info_lines.append(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(info_lines)
    
    def _update_status_display(self, message: str) -> None:
        """Update the status text display."""
        self.status_textbox.configure(state="normal")
        self.status_textbox.delete("1.0", "end")
        self.status_textbox.insert("1.0", message)
        self.status_textbox.configure(state="disabled")
    
    def _update_status(self, message: str) -> None:
        """Update status message."""
        self.status_text_var.set(message)
        if self.status_callback:
            self.status_callback(message)
        self.logger.info(f"CodexCtl: {message}")
    
    def _on_version_selected(self, selected: str) -> None:
        """Handle version selection."""
        if selected and selected not in ["Loading...", "No versions available", "No supported versions"]:
            # Extract version from display string
            version = selected.split(" (")[0] if " (" in selected else selected
            self.logger.debug(f"Selected firmware version: {version}")
    
    def _install_firmware(self) -> None:
        """Install selected firmware version."""
        if self.is_operation_running:
            self._update_status("Another operation is already running")
            return
        
        selected = self.selected_version_var.get()
        if not selected or selected in ["Loading...", "No versions available", "No supported versions"]:
            self._update_status("Please select a firmware version to install")
            return
        
        # Extract version from display string
        version = selected.split(" (")[0] if " (" in selected else selected
        backup = self.backup_enabled_var.get()
        
        # Confirm installation
        if not self._confirm_operation(f"install firmware version {version}", backup):
            return
        
        self._start_operation("Installing Firmware")
        
        # Run installation in background
        threading.Thread(
            target=self._install_firmware_async,
            args=(version, backup),
            daemon=True
        ).start()
    
    def _install_firmware_async(self, version: str, backup: bool) -> None:
        """Perform async firmware installation."""
        try:
            success = self.codexctl_service.install_firmware(version, backup)
            operation_name = f"Firmware installation ({version})"
            self.after(0, lambda: self._operation_complete(success, operation_name))
        except Exception as e:
            self.logger.error(f"Installation failed: {e}")
            self.after(0, lambda: self._operation_complete(False, f"Installation error: {e}"))
    
    def _restore_firmware(self) -> None:
        """Restore firmware from backup."""
        if self.is_operation_running:
            self._update_status("Another operation is already running")
            return
        
        # Confirm restoration
        if not self._confirm_operation("restore firmware from backup", False):
            return
        
        self._start_operation("Restoring Firmware")
        
        # Run restoration in background
        threading.Thread(target=self._restore_firmware_async, daemon=True).start()
    
    def _restore_firmware_async(self) -> None:
        """Perform async firmware restoration."""
        try:
            success = self.codexctl_service.restore_firmware()
            self.after(0, lambda: self._operation_complete(success, "Firmware restoration"))
        except Exception as e:
            self.logger.error(f"Restoration failed: {e}")
            self.after(0, lambda: self._operation_complete(False, f"Restoration error: {e}"))
    
    def _cancel_operation(self) -> None:
        """Cancel current operation."""
        if not self.is_operation_running:
            return
        
        if self.codexctl_service:
            success = self.codexctl_service.cancel_operation()
            if success:
                self._update_status("Operation cancellation requested")
            else:
                self._update_status("Could not cancel operation")
    
    def _confirm_operation(self, operation: str, backup: bool) -> bool:
        """Show confirmation dialog for operation."""
        # Create confirmation dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Confirm Operation")
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (200 // 2)
        dialog.geometry(f"400x200+{x}+{y}")
        
        # Make it modal
        dialog.transient(self)
        dialog.grab_set()
        
        result = [False]  # Mutable container for result
        
        content_frame = ctk.CTkFrame(dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_label = ctk.CTkLabel(
            content_frame,
            text="⚠️ Confirm Firmware Operation",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="orange"
        )
        title_label.pack(pady=(0, 10))
        
        message_text = f"Are you sure you want to {operation}?"
        if backup:
            message_text += "\n\nA backup will be created before proceeding."
        else:
            message_text += "\n\n⚠️ This operation will proceed without creating a backup."
        
        message_label = ctk.CTkLabel(
            content_frame,
            text=message_text,
            font=ctk.CTkFont(size=12),
            justify="center"
        )
        message_label.pack(pady=(0, 20))
        
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(fill="x")
        
        def confirm():
            result[0] = True
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        ctk.CTkButton(
            button_frame,
            text="Proceed",
            command=confirm,
            fg_color="#2b7bd4"
        ).pack(side="right", padx=(5, 0))
        
        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=cancel,
            fg_color="gray"
        ).pack(side="right")
        
        # Wait for dialog to close
        dialog.wait_window()
        
        return result[0]
    
    def _start_operation(self, operation_name: str) -> None:
        """Start an operation and update UI."""
        self.is_operation_running = True
        
        # Update UI state
        self.install_button.configure(state="disabled")
        self.restore_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.refresh_button.configure(state="disabled")
        
        # Show progress display
        self.progress_frame.grid()
        self.progress_title_label.configure(text=f"{operation_name} - In Progress")
        self.progress_bar.set(0)
        self.progress_details_label.configure(text="Starting operation...")
        
        self._update_status(f"{operation_name} started")
    
    def _operation_complete(self, success: bool, operation_name: str) -> None:
        """Handle operation completion."""
        self.is_operation_running = False
        
        # Update UI state
        self.install_button.configure(state="normal")
        self.restore_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.refresh_button.configure(state="normal")
        
        # Update progress display
        if success:
            self.progress_bar.set(1.0)
            self.progress_details_label.configure(text="Operation completed successfully", text_color="green")
            self._update_status(f"{operation_name} completed successfully")
        else:
            self.progress_details_label.configure(text="Operation failed", text_color="red")
            self._update_status(f"{operation_name} failed")
        
        # Refresh data after successful operation
        if success:
            threading.Timer(2.0, self._refresh_data).start()
    
    def _on_progress_update(self, progress: CodexCtlProgress) -> None:
        """Handle progress updates from CodexCtl service."""
        # Update UI in main thread
        self.after(0, self._update_progress_display, progress)
        
        # Forward to external callback
        if self.progress_callback:
            self.progress_callback(progress)
    
    def _update_progress_display(self, progress: CodexCtlProgress) -> None:
        """Update progress display with new information."""
        # Update progress bar
        self.progress_bar.set(progress.progress_percentage / 100.0)
        
        # Update details
        details_text = f"{progress.stage}: {progress.current_step}"
        self.progress_details_label.configure(text=details_text, text_color="white")
        
        # Update title with stage
        operation_name = progress.operation.value.replace("_", " ").title()
        self.progress_title_label.configure(text=f"{operation_name} - {progress.stage}")
    
    def _on_output_update(self, output: str) -> None:
        """Handle output updates from CodexCtl service."""
        # Log output
        self.logger.info(f"CodexCtl: {output}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current panel status."""
        return {
            "is_operation_running": self.is_operation_running,
            "current_status": self.current_status,
            "available_versions": len(self.available_versions),
            "selected_version": self.selected_version_var.get(),
            "service_available": self.codexctl_service is not None
        }
    
    def _show_loading_overlay(self) -> None:
        """Show loading overlay with spinner."""
        if self.loading_overlay:
            return
        
        # Create semi-transparent overlay
        self.loading_overlay = ctk.CTkFrame(
            self,
            fg_color=("gray75", "gray25"),
            corner_radius=0
        )
        self.loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        
        # Loading content frame
        content_frame = ctk.CTkFrame(
            self.loading_overlay,
            fg_color="transparent"
        )
        content_frame.place(relx=0.5, rely=0.5, anchor="center")
        
        # Spinner canvas
        self.spinner_canvas = tk.Canvas(
            content_frame,
            width=60,
            height=60,
            highlightthickness=0,
            bg=self.loading_overlay.cget("fg_color")[1] if isinstance(self.loading_overlay.cget("fg_color"), tuple) else self.loading_overlay.cget("fg_color")
        )
        self.spinner_canvas.pack(pady=(0, 10))
        
        # Loading text
        loading_label = ctk.CTkLabel(
            content_frame,
            text="Downloading CodexCtl binary...",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        loading_label.pack()
        
        # Status text
        self.loading_status_label = ctk.CTkLabel(
            content_frame,
            text="Checking binary availability...",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.loading_status_label.pack(pady=(5, 0))
        
        # Start spinner animation
        self._start_spinner()
    
    def _hide_loading_overlay(self) -> None:
        """Hide loading overlay."""
        self._stop_spinner()
        
        if self.loading_overlay:
            self.loading_overlay.destroy()
            self.loading_overlay = None
        
        self.is_loading = False
    
    def _start_spinner(self) -> None:
        """Start spinner animation."""
        self._stop_spinner()  # Stop any existing animation
        self._animate_spinner()
    
    def _stop_spinner(self) -> None:
        """Stop spinner animation."""
        if self.spinner_job:
            self.after_cancel(self.spinner_job)
            self.spinner_job = None
    
    def _animate_spinner(self) -> None:
        """Animate the spinner."""
        if not self.loading_overlay or not hasattr(self, 'spinner_canvas'):
            return
        
        # Clear canvas
        self.spinner_canvas.delete("all")
        
        # Draw spinner arcs
        import math
        center_x, center_y = 30, 30
        radius = 20
        
        for i in range(8):
            angle = (self.spinner_angle + i * 45) % 360
            alpha = 1.0 - (i * 0.12)  # Fade effect
            
            # Calculate arc positions
            start_angle = angle - 10
            end_angle = angle + 10
            
            # Color with alpha effect
            if alpha > 0.3:
                color = f"#{int(255 * alpha):02x}{int(255 * alpha):02x}{int(255 * alpha):02x}"
                
                # Draw arc segment
                x1 = center_x - radius
                y1 = center_y - radius
                x2 = center_x + radius
                y2 = center_y + radius
                
                self.spinner_canvas.create_arc(
                    x1, y1, x2, y2,
                    start=start_angle,
                    extent=20,
                    outline=color,
                    width=3,
                    style="arc"
                )
        
        # Update angle and schedule next frame
        self.spinner_angle = (self.spinner_angle + 15) % 360
        self.spinner_job = self.after(50, self._animate_spinner)
    
    def _update_loading_status(self, status: str) -> None:
        """Update loading status text."""
        if (self.loading_overlay and
            hasattr(self, 'loading_status_label') and
            self.loading_status_label and
            self.loading_status_label.winfo_exists()):
            try:
                self.loading_status_label.configure(text=status)
            except Exception as e:
                self.logger.debug(f"Failed to update loading status: {e}")
    
    def _check_binary_availability(self) -> None:
        """Check binary availability and hide loading overlay when ready."""
        if not self.codexctl_service:
            # Service not available, keep checking
            self.after(1000, self._check_binary_availability)
            return
        
        # Update loading status
        self._update_loading_status("Checking CodexCtl binary...")
        
        # Check in background thread to avoid blocking UI
        threading.Thread(target=self._check_binary_async, daemon=True).start()
    
    def _check_binary_async(self) -> None:
        """Check binary availability in background thread."""
        try:
            # Check system compatibility first to prevent loops
            if hasattr(self.codexctl_service, 'is_system_compatible') and not self.codexctl_service.is_system_compatible():
                # System is incompatible, hide loading overlay and stop checking permanently
                self.after(0, lambda: self._update_loading_status("System incompatible with CodexCtl requirements"))
                self.after(3000, self._hide_loading_overlay)  # Hide after showing message
                return  # Stop all further checking
            
            if self.codexctl_service.is_binary_available():
                # Binary is ready, hide loading overlay
                self.after(0, self._binary_ready)
            else:
                # Binary not ready, check again soon
                self.after(0, lambda: self._update_loading_status("Downloading CodexCtl binary..."))
                self.after(2000, self._check_binary_availability)  # Check again in 2 seconds
        except Exception as e:
            self.logger.error(f"Error checking binary availability: {e}")
            self.after(0, lambda: self._update_loading_status(f"Error: {e}"))
            # For errors, don't retry indefinitely on incompatible systems
            if hasattr(self.codexctl_service, 'is_system_compatible') and not self.codexctl_service.is_system_compatible():
                self.after(3000, self._hide_loading_overlay)  # Hide overlay and stop
            else:
                self.after(5000, self._check_binary_availability)  # Retry in 5 seconds only if system is compatible
    
    def _binary_ready(self) -> None:
        """Handle when binary becomes available."""
        try:
            # Check if the system is actually compatible before proceeding
            if self.codexctl_service and hasattr(self.codexctl_service, 'is_system_compatible'):
                if not self.codexctl_service.is_system_compatible():
                    self.logger.info("CodexCtl binary downloaded but system is incompatible - skipping operations")
                    self._hide_loading_overlay()
                    return
            
            self.logger.info("CodexCtl binary is now available")
            self._hide_loading_overlay()
            
            # Now refresh data since binary is available (in background to avoid blocking)
            threading.Thread(target=self._refresh_data, daemon=True).start()
        except Exception as e:
            self.logger.error(f"Error in binary ready handler: {e}")
    
    def _on_binary_ready(self) -> None:
        """Callback when binary download completes."""
        # Run in main thread (non-blocking)
        try:
            self.after(0, self._binary_ready)
        except Exception as e:
            self.logger.error(f"Error in binary ready callback: {e}")
    
    def _check_python_version(self) -> bool:
        """Check if Python version is compatible with CodexCtl."""
        try:
            # CodexCtl requires Python 3.12+
            current_version = sys.version_info
            required_version = (3, 12)
            
            if current_version < required_version:
                self.logger.warn(
                    f"Python {current_version.major}.{current_version.minor} is not compatible with CodexCtl. "
                    f"Requires Python {required_version[0]}.{required_version[1]}+"
                )
                return False
            
            return True
        except Exception as e:
            self.logger.error(f"Error checking Python version: {e}")
            return False
    
    def _create_version_error_ui(self) -> None:
        """Create error UI for Python version incompatibility."""
        # Clear any existing content
        for widget in self.winfo_children():
            widget.destroy()
        
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Error frame
        error_frame = ctk.CTkFrame(self)
        error_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        error_frame.grid_columnconfigure(0, weight=1)
        
        # Error icon and title
        ctk.CTkLabel(
            error_frame,
            text="⚠️ Python Version Incompatibility",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="orange"
        ).grid(row=0, column=0, pady=(20, 10))
        
        # Current version info
        current_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        
        ctk.CTkLabel(
            error_frame,
            text=f"Current Python Version: {current_version}",
            font=ctk.CTkFont(size=14)
        ).grid(row=1, column=0, pady=5)
        
        ctk.CTkLabel(
            error_frame,
            text="Required Python Version: 3.12+",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="red"
        ).grid(row=2, column=0, pady=5)
        
        # Error message
        message_text = (
            "CodexCtl requires Python 3.12 or newer to function properly.\n\n"
            "The firmware management features are not available with your\n"
            "current Python version. Please upgrade Python to access\n"
            "CodexCtl functionality."
        )
        
        ctk.CTkLabel(
            error_frame,
            text=message_text,
            font=ctk.CTkFont(size=12),
            justify="center"
        ).grid(row=3, column=0, pady=(15, 20))
        
        # Status message
        ctk.CTkLabel(
            error_frame,
            text="Other freeMarkable features remain fully functional.",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).grid(row=4, column=0, pady=(0, 20))

    def cleanup(self) -> None:
        """Cleanup panel resources."""
        self._stop_spinner()
        if self.codexctl_service:
            self.codexctl_service.cleanup()
        self.logger.info("CodexCtl panel cleaned up")