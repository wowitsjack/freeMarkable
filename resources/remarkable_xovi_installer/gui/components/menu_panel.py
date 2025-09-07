"""
Main menu panel for freeMarkable.

This module provides the main menu interface with all 14 installation options
matching the original bash script. It includes button styling, status-aware
menu options, and integration with device connection state.
"""

import tkinter as tk
from typing import Optional, Callable, Dict, Any, List
import customtkinter as ctk

from remarkable_xovi_installer.models.device import Device, ConnectionStatus
from remarkable_xovi_installer.utils.logger import get_logger


class MenuOption:
    """Represents a menu option with metadata."""
    
    def __init__(self, command: str, title: str, description: str, 
                 requires_connection: bool = True, requires_backup: bool = False,
                 icon: str = "", color: Optional[str] = None):
        self.command = command
        self.title = title
        self.description = description
        self.requires_connection = requires_connection
        self.requires_backup = requires_backup
        self.icon = icon
        self.color = color


class MenuPanel(ctk.CTkScrollableFrame):
    """
    Main menu panel component.
    
    Provides interface for all installation and management options:
    - 14 menu options matching the original Bash script
    - Status-aware menu (disable unavailable options)
    - Button styling and layout
    - Integration with device connection state
    """
    
    def __init__(self, parent, command_callback: Optional[Callable[[str], None]] = None,
                 device: Optional[Device] = None, **kwargs):
        """
        Initialize menu panel.
        
        Args:
            parent: Parent widget
            command_callback: Callback for menu command execution
            device: Current device instance
            **kwargs: Additional CTkScrollableFrame arguments
        """
        super().__init__(parent, **kwargs)
        
        # Callbacks and state
        self.command_callback = command_callback
        self.device = device
        self.connection_status = ConnectionStatus.DISCONNECTED
        
        # Core services
        self.logger = get_logger()
        
        # Menu options (matching original bash script)
        self.menu_options = self._define_menu_options()
        
        # UI components
        self.menu_buttons: Dict[str, ctk.CTkButton] = {}
        
        # Setup UI
        self._setup_ui()
        self._update_menu_state()
    
    def _define_menu_options(self) -> List[MenuOption]:
        """Define all menu options matching the original bash script."""
        return [
            # Primary installation options
            MenuOption(
                command="install_full",
                title="Install XOVI + AppLoader + KOReader",
                description="Complete installation with all components (recommended)",
                requires_connection=True,
                icon="🔧",
                color="green"
            ),
            MenuOption(
                command="install_launcher",
                title="Install XOVI + AppLoader only",
                description="Install launcher without KOReader (faster setup)",
                requires_connection=True,
                icon="⚡",
                color="blue"
            ),
            
            # Status and information
            MenuOption(
                command="show_status",
                title="Show Current Status",
                description="Display current installation status and device info",
                requires_connection=True,
                icon="📊"
            ),
            
            # Backup management
            MenuOption(
                command="create_backup",
                title="Create Backup",
                description="Create a full system backup before installation",
                requires_connection=True,
                icon="💾"
            ),
            MenuOption(
                command="restore_backup",
                title="Restore from Backup",
                description="Restore system from a previous backup",
                requires_connection=True,
                requires_backup=True,
                icon="📦"
            ),
            MenuOption(
                command="list_backups",
                title="List All Backups",
                description="Show all available system backups",
                requires_connection=True,
                icon="📋"
            ),
            MenuOption(
                command="delete_backup",
                title="Delete Backup",
                description="Remove a backup from the device",
                requires_connection=True,
                requires_backup=True,
                icon="🗑",
                color="red"
            ),
            
            # Uninstallation
            MenuOption(
                command="uninstall",
                title="Uninstall without Backup",
                description="Remove XOVI installation (WARNING: No backup created)",
                requires_connection=True,
                icon="⚠️",
                color="red"
            ),
            
            # Device setup and troubleshooting
            MenuOption(
                command="check_requirements",
                title="Check Device Requirements",
                description="Verify device compatibility and requirements",
                requires_connection=True,
                icon="✅"
            ),
            MenuOption(
                command="fix_usb",
                title="Fix USB Ethernet Connection",
                description="Troubleshoot and fix USB ethernet connectivity",
                requires_connection=False,
                icon="🔌"
            ),
            MenuOption(
                command="wifi_setup",
                title="WiFi Setup Instructions",
                description="Show instructions for WiFi configuration",
                requires_connection=False,
                icon="📶"
            ),
            
            # Help and advanced options
            MenuOption(
                command="show_help",
                title="Show Help/Usage",
                description="Display help information and usage instructions",
                requires_connection=False,
                icon="❓"
            ),
            MenuOption(
                command="advanced_options",
                title="Advanced Options",
                description="Access advanced installation and configuration options",
                requires_connection=False,
                icon="⚙️"
            ),
            
            # Exit
            MenuOption(
                command="exit",
                title="Exit",
                description="Close the application",
                requires_connection=False,
                icon="🚪",
                color="gray"
            )
        ]
    
    def _setup_ui(self) -> None:
        """Setup the menu panel user interface."""
        # Configure scrollable frame
        self.grid_columnconfigure(0, weight=1)
        
        # Panel title
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", pady=(10, 15))
        title_frame.grid_columnconfigure(1, weight=1)
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="Installation Menu",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w")
        
        # Status indicator
        self.menu_status_label = ctk.CTkLabel(
            title_frame,
            text="Device Required",
            font=ctk.CTkFont(size=12),
            text_color="orange"
        )
        self.menu_status_label.grid(row=0, column=1, sticky="e")
        
        # Create menu buttons
        self._create_menu_buttons()
        
        # Instructions
        instructions_frame = ctk.CTkFrame(self, fg_color="transparent")
        instructions_frame.grid(row=len(self.menu_options) + 2, column=0, sticky="ew", pady=20)
        
        instructions_label = ctk.CTkLabel(
            instructions_frame,
            text="💡 Tip: Connect your device first to enable installation options",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=300
        )
        instructions_label.grid(row=0, column=0, sticky="w")
    
    def _create_menu_buttons(self) -> None:
        """Create all menu option buttons."""
        current_row = 1
        
        # Group buttons by category
        categories = [
            ("Installation Options", [0, 1]),  # install_full, install_launcher
            ("Status & Information", [2]),      # show_status
            ("Backup Management", [3, 4, 5, 6]), # backup operations
            ("Maintenance", [7, 8]),            # uninstall, check_requirements
            ("Troubleshooting", [9, 10]),       # fix_usb, wifi_setup
            ("Help & Advanced", [11, 12]),      # help, advanced
            ("Application", [13])               # exit
        ]
        
        for category_name, option_indices in categories:
            # Category header
            if len(categories) > 1:  # Only show headers if we have multiple categories
                category_label = ctk.CTkLabel(
                    self,
                    text=category_name,
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color="gray"
                )
                category_label.grid(row=current_row, column=0, sticky="w", pady=(15, 5))
                current_row += 1
            
            # Create buttons for this category
            for option_index in option_indices:
                option = self.menu_options[option_index]
                button = self._create_menu_button(option, current_row)
                self.menu_buttons[option.command] = button
                current_row += 1
    
    def _create_menu_button(self, option: MenuOption, row: int) -> ctk.CTkButton:
        """Create a single menu button."""
        # Determine button color
        button_color = None
        hover_color = None
        text_color = "white"
        
        if option.color == "green":
            button_color = "#2d6e3e"
            hover_color = "#1e4d2b"
        elif option.color == "blue":
            button_color = "#1f538d"
            hover_color = "#144272"
        elif option.color == "red":
            button_color = "#8b2635"
            hover_color = "#6b1c28"
        elif option.color == "gray":
            button_color = "#555555"
            hover_color = "#404040"
            text_color = "lightgray"
        
        # Create button frame for better layout
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.grid(row=row, column=0, sticky="ew", pady=2)
        button_frame.grid_columnconfigure(0, weight=1)
        
        # Main button
        button_text = f"{option.icon} {option.title}" if option.icon else option.title
        
        button = ctk.CTkButton(
            button_frame,
            text=button_text,
            command=lambda cmd=option.command: self._execute_command(cmd),
            height=40,
            font=ctk.CTkFont(size=13, weight="normal"),
            fg_color=button_color,
            hover_color=hover_color,
            text_color=text_color,
            anchor="w"
        )
        button.grid(row=0, column=0, sticky="ew", padx=(10, 5))
        
        # Description label
        if option.description:
            desc_label = ctk.CTkLabel(
                button_frame,
                text=option.description,
                font=ctk.CTkFont(size=10),
                text_color="gray",
                wraplength=280,
                anchor="w",
                justify="left"
            )
            desc_label.grid(row=1, column=0, sticky="ew", padx=(15, 5), pady=(2, 5))
        
        return button
    
    def _execute_command(self, command: str) -> None:
        """Execute a menu command."""
        self.logger.info(f"Menu command selected: {command}")
        
        # Check if command is available
        if not self._is_command_available(command):
            self.logger.warning(f"Command not available: {command}")
            return
        
        # Execute command callback
        if self.command_callback:
            self.command_callback(command)
        else:
            self.logger.warning("No command callback configured")
    
    def _is_command_available(self, command: str) -> bool:
        """Check if a command is currently available."""
        option = next((opt for opt in self.menu_options if opt.command == command), None)
        if not option:
            return False
        
        # Check connection requirement
        if option.requires_connection and self.connection_status != ConnectionStatus.CONNECTED:
            return False
        
        # Check backup requirement
        if option.requires_backup:
            # Check if backups are available by trying to get backup service
            try:
                from ...services.backup_service import get_backup_service
                backup_service = get_backup_service()
                backups = backup_service.list_backups()
                if not backups:
                    return False
            except Exception:
                # If backup service not available or no backups found, disable option
                return False
        
        return True
    
    def _update_menu_state(self) -> None:
        """Update menu button states based on current conditions."""
        is_connected = self.connection_status == ConnectionStatus.CONNECTED
        
        # Update status label
        if is_connected:
            self.menu_status_label.configure(
                text="✓ Device Connected", 
                text_color="green"
            )
        else:
            self.menu_status_label.configure(
                text="⚠ Device Required", 
                text_color="orange"
            )
        
        # Update button states
        for command, button in self.menu_buttons.items():
            is_available = self._is_command_available(command)
            
            if is_available:
                button.configure(state="normal")
                # Restore original colors
                option = next((opt for opt in self.menu_options if opt.command == command), None)
                if option and option.color:
                    if option.color == "green":
                        button.configure(fg_color="#2d6e3e", hover_color="#1e4d2b")
                    elif option.color == "blue":
                        button.configure(fg_color="#1f538d", hover_color="#144272")
                    elif option.color == "red":
                        button.configure(fg_color="#8b2635", hover_color="#6b1c28")
            else:
                button.configure(state="disabled")
                # Use muted colors for disabled buttons
                button.configure(fg_color="#404040", hover_color="#404040")
    
    def set_device(self, device: Optional[Device]) -> None:
        """Set the current device and update menu state."""
        self.device = device
        
        if device:
            self.connection_status = device.connection_status
        else:
            self.connection_status = ConnectionStatus.DISCONNECTED
        
        self._update_menu_state()
        self.logger.debug(f"Menu panel updated for device: {device}")
    
    def set_connection_status(self, status: ConnectionStatus) -> None:
        """Set connection status and update menu state."""
        self.connection_status = status
        self._update_menu_state()
        self.logger.debug(f"Menu panel updated for connection status: {status}")
    
    def get_available_commands(self) -> List[str]:
        """Get list of currently available commands."""
        return [
            option.command 
            for option in self.menu_options 
            if self._is_command_available(option.command)
        ]
    
    def highlight_command(self, command: str, highlight: bool = True) -> None:
        """Highlight or unhighlight a specific command button."""
        if command in self.menu_buttons:
            button = self.menu_buttons[command]
            if highlight:
                button.configure(fg_color="#ff6b35", hover_color="#e55a30")
            else:
                # Restore original color
                option = next((opt for opt in self.menu_options if opt.command == command), None)
                if option and option.color:
                    if option.color == "green":
                        button.configure(fg_color="#2d6e3e", hover_color="#1e4d2b")
                    elif option.color == "blue": 
                        button.configure(fg_color="#1f538d", hover_color="#144272")
                    elif option.color == "red":
                        button.configure(fg_color="#8b2635", hover_color="#6b1c28")
                else:
                    button.configure(fg_color=None, hover_color=None)
    
    def enable_command(self, command: str, enabled: bool = True) -> None:
        """Enable or disable a specific command."""
        if command in self.menu_buttons:
            button = self.menu_buttons[command]
            if enabled:
                button.configure(state="normal")
            else:
                button.configure(state="disabled")
    
    def update_command_description(self, command: str, description: str) -> None:
        """Update the description text for a command."""
        option = next((opt for opt in self.menu_options if opt.command == command), None)
        if option:
            option.description = description
            # Refresh the menu display to show updated description
            self._refresh_menu_display()
    
    def get_menu_option(self, command: str) -> Optional[MenuOption]:
        """Get menu option by command name."""
        return next((opt for opt in self.menu_options if opt.command == command), None)