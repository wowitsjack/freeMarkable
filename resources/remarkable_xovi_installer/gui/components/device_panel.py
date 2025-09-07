"""
Device connection panel for freeMarkable.

This module provides the device connection interface including IP address input,
password entry, connection status display, device type detection, and connection
testing functionality.
"""

import tkinter as tk
from typing import Optional, Callable, Dict, Any
import customtkinter as ctk
import threading
import re

from remarkable_xovi_installer.models.device import Device, DeviceType, ConnectionStatus
from remarkable_xovi_installer.utils.validators import get_validator, ValidationResult
from remarkable_xovi_installer.utils.logger import get_logger


class DevicePanel(ctk.CTkFrame):
    """
    Device connection panel component.
    
    Provides interface for device connection configuration including:
    - IP address input with validation
    - Password entry (secure)
    - Connection status display
    - Device type detection display
    - Connection test and retry functionality
    """
    
    def __init__(self, parent, device_callback: Optional[Callable[[Device], None]] = None,
                 connection_callback: Optional[Callable[[ConnectionStatus], None]] = None,
                 **kwargs):
        """
        Initialize device panel.
        
        Args:
            parent: Parent widget
            device_callback: Callback for device updates
            connection_callback: Callback for connection status changes
            **kwargs: Additional CTkFrame arguments
        """
        super().__init__(parent, **kwargs)
        
        # Callbacks
        self.device_callback = device_callback
        self.connection_callback = connection_callback
        
        # Core services
        self.validator = get_validator()
        self.logger = get_logger()
        
        # Device state
        self.device: Optional[Device] = None
        self.is_connecting = False
        
        # Variables for form inputs
        self.ip_var = tk.StringVar(value="10.11.99.1")
        self.password_var = tk.StringVar()
        self.device_type_var = tk.StringVar(value="Auto-detect")
        
        # Setup UI
        self._setup_ui()
        self._setup_validation()
        
        # Initialize with default device
        self._create_device()
    
    def _setup_ui(self) -> None:
        """Setup the device panel user interface."""
        # Configure grid
        self.grid_columnconfigure(1, weight=1)
        
        # Panel title
        title_label = ctk.CTkLabel(
            self,
            text="Device Connection",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, columnspan=3, pady=(10, 15), sticky="w")
        
        # IP Address input
        ip_label = ctk.CTkLabel(self, text="IP Address:")
        ip_label.grid(row=1, column=0, padx=(10, 5), pady=5, sticky="w")
        
        self.ip_entry = ctk.CTkEntry(
            self,
            textvariable=self.ip_var,
            placeholder_text="10.11.99.1",
            width=200
        )
        self.ip_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        # IP validation indicator
        self.ip_status_label = ctk.CTkLabel(
            self,
            text="✓",
            text_color="green",
            width=20
        )
        self.ip_status_label.grid(row=1, column=2, padx=(5, 10), pady=5)
        
        # Password input
        password_label = ctk.CTkLabel(self, text="SSH Password:")
        password_label.grid(row=2, column=0, padx=(10, 5), pady=5, sticky="w")
        
        self.password_entry = ctk.CTkEntry(
            self,
            textvariable=self.password_var,
            placeholder_text="Enter SSH password",
            show="*",
            width=200
        )
        self.password_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        
        # Password show/hide toggle
        self.password_toggle = ctk.CTkButton(
            self,
            text="👁",
            width=30,
            height=28,
            command=self._toggle_password_visibility
        )
        self.password_toggle.grid(row=2, column=2, padx=(5, 10), pady=5)
        
        # Device type display
        device_type_label = ctk.CTkLabel(self, text="Device Type:")
        device_type_label.grid(row=3, column=0, padx=(10, 5), pady=5, sticky="w")
        
        self.device_type_display = ctk.CTkLabel(
            self,
            textvariable=self.device_type_var,
            text_color="gray"
        )
        self.device_type_display.grid(row=3, column=1, padx=5, pady=5, sticky="w")
        
        # Connection controls frame
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.grid(row=4, column=0, columnspan=3, pady=10, sticky="ew")
        controls_frame.grid_columnconfigure(1, weight=1)
        
        # Test connection button
        self.test_button = ctk.CTkButton(
            controls_frame,
            text="Test Connection",
            command=self._test_connection,
            width=120
        )
        self.test_button.grid(row=0, column=0, padx=(10, 5), pady=5)
        
        # Connection status
        self.connection_status_label = ctk.CTkLabel(
            controls_frame,
            text="● Disconnected",
            text_color="red"
        )
        self.connection_status_label.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        # Advanced button
        self.advanced_button = ctk.CTkButton(
            controls_frame,
            text="Advanced",
            command=self._show_advanced_options,
            width=80
        )
        self.advanced_button.grid(row=0, column=2, padx=(5, 10), pady=5)
        
        # Device info frame (initially hidden)
        self.info_frame = ctk.CTkFrame(self)
        self.info_frame.grid(row=5, column=0, columnspan=3, padx=10, pady=(0, 10), sticky="ew")
        self.info_frame.grid_columnconfigure(1, weight=1)
        self.info_frame.grid_remove()  # Hidden by default
        
        # Device info labels
        self._setup_device_info_display()
    
    def _setup_device_info_display(self) -> None:
        """Setup device information display area."""
        info_title = ctk.CTkLabel(
            self.info_frame,
            text="Device Information",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        info_title.grid(row=0, column=0, columnspan=2, pady=(10, 5), sticky="w")
        
        # Device info fields
        self.hostname_label = ctk.CTkLabel(self.info_frame, text="Hostname: Unknown")
        self.hostname_label.grid(row=1, column=0, columnspan=2, padx=10, pady=2, sticky="w")
        
        self.version_label = ctk.CTkLabel(self.info_frame, text="Version: Unknown") 
        self.version_label.grid(row=2, column=0, columnspan=2, padx=10, pady=2, sticky="w")
        
        self.space_label = ctk.CTkLabel(self.info_frame, text="Free Space: Unknown")
        self.space_label.grid(row=3, column=0, columnspan=2, padx=10, pady=2, sticky="w")
        
        self.network_label = ctk.CTkLabel(self.info_frame, text="Network: Unknown")
        self.network_label.grid(row=4, column=0, columnspan=2, padx=10, pady=(2, 10), sticky="w")
    
    def _setup_validation(self) -> None:
        """Setup input validation and callbacks."""
        # IP address validation
        self.ip_var.trace_add("write", self._validate_ip_input)
        
        # Password validation  
        self.password_var.trace_add("write", self._validate_password_input)
        
        # Enter key bindings
        self.ip_entry.bind("<Return>", lambda e: self._test_connection())
        self.password_entry.bind("<Return>", lambda e: self._test_connection())
    
    def _validate_ip_input(self, *args) -> None:
        """Validate IP address input in real-time."""
        ip_address = self.ip_var.get().strip()
        
        if not ip_address:
            self.ip_status_label.configure(text="", text_color="gray")
            return
        
        # Validate IP format
        result = self.validator.validate_ip_address(ip_address, allow_hostnames=True)
        
        if result.is_valid:
            self.ip_status_label.configure(text="✓", text_color="green")
            # Update device with new IP
            self._create_device()
        else:
            self.ip_status_label.configure(text="✗", text_color="red")
            # Show tooltip with error message
            self._set_tooltip(self.ip_status_label, result.message)
    
    def _validate_password_input(self, *args) -> None:
        """Validate password input."""
        password = self.password_var.get()
        
        if password:
            # Update device with new password
            self._create_device()
    
    def _set_tooltip(self, widget, text: str) -> None:
        """Set tooltip text for a widget (simplified implementation)."""
        # Simple tooltip implementation using widget configure
        try:
            # For CustomTkinter widgets, we can use the built-in tooltip-like functionality
            # by temporarily updating the widget text or using hover events
            def on_enter(event):
                # Store original text and show tooltip
                if hasattr(widget, '_original_text'):
                    return
                widget._original_text = widget.cget("text") if hasattr(widget, "cget") else ""
                # For simple implementation, we'll log the tooltip instead of showing it
                self.logger.debug(f"Tooltip: {text}")
            
            def on_leave(event):
                # Restore original text
                if hasattr(widget, '_original_text'):
                    delattr(widget, '_original_text')
            
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            
        except Exception as e:
            self.logger.debug(f"Could not set tooltip: {e}")
    
    def _toggle_password_visibility(self) -> None:
        """Toggle password visibility."""
        current_show = self.password_entry.cget("show")
        if current_show == "*":
            self.password_entry.configure(show="")
            self.password_toggle.configure(text="🙈")
        else:
            self.password_entry.configure(show="*") 
            self.password_toggle.configure(text="👁")
    
    def _create_device(self) -> None:
        """Create or update device instance from current inputs."""
        ip_address = self.ip_var.get().strip()
        password = self.password_var.get()
        
        if not ip_address:
            return
        
        # Create new device or update existing
        if not self.device:
            self.device = Device(ip_address=ip_address, ssh_password=password)
        else:
            self.device.update_connection_info(ip_address=ip_address, ssh_password=password)
        
        # Notify callback
        if self.device_callback:
            self.device_callback(self.device)
    
    def _test_connection(self) -> None:
        """Test connection to the device."""
        if self.is_connecting:
            self.logger.warning("Connection test already in progress")
            return
        
        if not self.device or not self.device.is_configured():
            self.logger.error("Device not properly configured")
            self._update_connection_status(ConnectionStatus.ERROR)
            return
        
        # Validate inputs first
        ip_result = self.validator.validate_ip_address(
            self.device.ip_address, 
            allow_hostnames=True
        )
        if not ip_result.is_valid:
            self.logger.error(f"Invalid IP address: {ip_result.message}")
            self._update_connection_status(ConnectionStatus.ERROR)
            return
        
        password_result = self.validator.validate_ssh_password(self.device.ssh_password)
        if not password_result.is_valid:
            self.logger.error(f"Invalid password: {password_result.message}")
            self._update_connection_status(ConnectionStatus.ERROR)
            return
        
        # Start connection test in background
        self.is_connecting = True
        self.test_button.configure(text="Connecting...", state="disabled")
        self._update_connection_status(ConnectionStatus.CONNECTING)
        
        # Run test in thread
        threading.Thread(target=self._test_connection_async, daemon=True).start()
    
    def _test_connection_async(self) -> None:
        """Perform async connection test."""
        try:
            success = self.device.test_connection()
            
            # Schedule UI update in main thread
            self.after(0, self._connection_test_complete, success)
            
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            self.after(0, self._connection_test_complete, False)
    
    def _connection_test_complete(self, success: bool) -> None:
        """Handle connection test completion."""
        self.is_connecting = False
        self.test_button.configure(text="Test Connection", state="normal")
        
        if success:
            self.logger.info("Device connection successful")
            self._update_connection_status(ConnectionStatus.CONNECTED)
            
            # Detect device type if not already known
            if not self.device.device_type:
                self._detect_device_type()
            
            # Refresh device information
            self._refresh_device_info()
            
        else:
            error_msg = self.device.last_error or "Connection failed"
            self.logger.error(f"Device connection failed: {error_msg}")
            
            # Determine specific failure reason
            if "authentication" in error_msg.lower():
                self._update_connection_status(ConnectionStatus.AUTHENTICATION_FAILED)
            elif "timeout" in error_msg.lower():
                self._update_connection_status(ConnectionStatus.TIMEOUT)
            else:
                self._update_connection_status(ConnectionStatus.ERROR)
    
    def _detect_device_type(self) -> None:
        """Detect and display device type."""
        if not self.device or not self.device.is_connected():
            return
        
        self.logger.info("Detecting device type...")
        
        # Run detection in background
        threading.Thread(target=self._detect_device_type_async, daemon=True).start()
    
    def _detect_device_type_async(self) -> None:
        """Perform async device type detection."""
        try:
            device_type = self.device.detect_device_type()
            
            # Schedule UI update
            self.after(0, self._device_type_detected, device_type)
            
        except Exception as e:
            self.logger.error(f"Device type detection failed: {e}")
            self.after(0, self._device_type_detected, None)
    
    def _device_type_detected(self, device_type: Optional[DeviceType]) -> None:
        """Handle device type detection completion."""
        if device_type:
            self.device_type_var.set(device_type.display_name)
            self.device_type_display.configure(text_color="white")
            self.logger.info(f"Device type detected: {device_type.display_name}")
        else:
            self.device_type_var.set("Detection failed")
            self.device_type_display.configure(text_color="orange")
    
    def _refresh_device_info(self) -> None:
        """Refresh device information display."""
        if not self.device or not self.device.is_connected():
            return
        
        threading.Thread(target=self._refresh_device_info_async, daemon=True).start()
    
    def _refresh_device_info_async(self) -> None:
        """Perform async device info refresh."""
        try:
            success = self.device.refresh_all_info()
            self.after(0, self._device_info_refreshed, success)
        except Exception as e:
            self.logger.error(f"Device info refresh failed: {e}")
            self.after(0, self._device_info_refreshed, False)
    
    def _device_info_refreshed(self, success: bool) -> None:
        """Handle device info refresh completion."""
        if success and self.device:
            # Show device info panel
            self.info_frame.grid()
            
            # Update info labels
            if self.device.device_info:
                hostname = self.device.device_info.hostname or "Unknown"
                self.hostname_label.configure(text=f"Hostname: {hostname}")
                
                version = self.device.device_info.remarkable_version or "Unknown"
                self.version_label.configure(text=f"Version: {version}")
                
                if self.device.device_info.free_space:
                    free_mb = self.device.device_info.get_free_space_mb()
                    total_mb = self.device.device_info.get_total_space_mb()
                    if free_mb and total_mb:
                        self.space_label.configure(
                            text=f"Free Space: {free_mb:.1f} MB / {total_mb:.1f} MB"
                        )
            
            if self.device.network_info:
                network_info = "USB" if self.device.network_info.ethernet_enabled else "WiFi"
                if self.device.network_info.wifi_enabled:
                    network_info += " + WiFi"
                self.network_label.configure(text=f"Network: {network_info}")
        else:
            # Hide device info on failure
            self.info_frame.grid_remove()
    
    def _update_connection_status(self, status: ConnectionStatus) -> None:
        """Update connection status display."""
        if self.device:
            self.device.connection_status = status
        
        status_text = {
            ConnectionStatus.CONNECTED: "● Connected",
            ConnectionStatus.CONNECTING: "● Connecting...",
            ConnectionStatus.DISCONNECTED: "● Disconnected", 
            ConnectionStatus.AUTHENTICATION_FAILED: "● Auth Failed",
            ConnectionStatus.TIMEOUT: "● Timeout",
            ConnectionStatus.ERROR: "● Error"
        }
        
        status_colors = {
            ConnectionStatus.CONNECTED: "green",
            ConnectionStatus.CONNECTING: "orange",
            ConnectionStatus.DISCONNECTED: "red",
            ConnectionStatus.AUTHENTICATION_FAILED: "red", 
            ConnectionStatus.TIMEOUT: "red",
            ConnectionStatus.ERROR: "red"
        }
        
        text = status_text.get(status, f"● {status.value}")
        color = status_colors.get(status, "gray")
        
        self.connection_status_label.configure(text=text, text_color=color)
        
        # Notify callback
        if self.connection_callback:
            self.connection_callback(status)
        
        # Hide device info if disconnected
        if status != ConnectionStatus.CONNECTED:
            self.info_frame.grid_remove()
    
    def _show_advanced_options(self) -> None:
        """Show advanced connection options dialog."""
        self.logger.info("Advanced options dialog opened")
    
    def set_device(self, device: Device) -> None:
        """Set device and update UI."""
        self.device = device
        
        if device:
            # Update form inputs
            if device.ip_address:
                self.ip_var.set(device.ip_address)
            if device.ssh_password:
                self.password_var.set(device.ssh_password)
            if device.device_type:
                self.device_type_var.set(device.device_type.display_name)
            
            # Update connection status
            self._update_connection_status(device.connection_status)
            
            # Refresh device info if connected
            if device.is_connected():
                self._refresh_device_info()
    
    def get_device(self) -> Optional[Device]:
        """Get current device instance."""
        return self.device
    
    def update_device_info(self) -> None:
        """Update device information display."""
        if self.device and self.device.is_connected():
            self._refresh_device_info()