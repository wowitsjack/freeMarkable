"""
Main application window for freeMarkable.

This module provides the primary application window with tabbed interface, simplified
connection management, and organized functionality sections.
"""

import tkinter as tk
from typing import Optional, Callable, Dict, Any
import customtkinter as ctk
from pathlib import Path
import threading
import logging

# Core module imports
from remarkable_xovi_installer.config.settings import get_config, init_config, AppConfig
from remarkable_xovi_installer.models.device import Device, DeviceType, ConnectionStatus
from remarkable_xovi_installer.models.installation_state import InstallationState, InstallationStage
from remarkable_xovi_installer.utils.logger import get_logger, setup_logging, XOVILogger
from remarkable_xovi_installer.utils.validators import get_validator
from remarkable_xovi_installer.services.file_service import get_file_service, init_file_service

# GUI component imports
from .components.device_panel import DevicePanel
from .components.menu_panel import MenuPanel
from .components.progress_panel import ProgressPanel
from .components.log_panel import LogPanel
from .components.codexctl_panel import CodexCtlPanel
from .wizards.setup_wizard import SetupWizard


class MainWindow:
    """
    Main application window for freeMarkable.
    
    Provides a modern CustomTkinter interface with tabbed organization,
    simplified connection management, and integrated functionality.
    """
    
    def __init__(self, config=None, device=None, network_service=None,
                 file_service=None, backup_service=None, installation_service=None):
        """Initialize the main application window."""
        
        # Store services passed from main app
        self._external_config = config
        self._external_device = device
        self._external_network_service = network_service
        self._external_file_service = file_service
        self._external_backup_service = backup_service
        self._external_installation_service = installation_service
        
        # Initialize core services first
        self._initialize_core_services()
        
        # Create main window with reasonable default size for standard scaling
        self.root = ctk.CTk()
        self.root.title(self.config.app_name)
        self.root.geometry("800x700")   # Reasonable size for standard displays
        self.root.minsize(700, 600)     # Reasonable minimum size
        
        # Force the window to be resizable and ensure it takes the geometry
        self.root.resizable(True, True)
        
        # Set the window state to normal (not maximized or minimized)
        self.root.state('normal')
        
        # Application state
        self.device: Optional[Device] = None
        self.installation_state: Optional[InstallationState] = None
        self.is_operation_running = False
        
        # GUI components
        self.device_panel: Optional[DevicePanel] = None
        self.menu_panel: Optional[MenuPanel] = None
        self.progress_panel: Optional[ProgressPanel] = None
        self.log_panel: Optional[LogPanel] = None
        self.codexctl_panel: Optional[CodexCtlPanel] = None
        self.setup_wizard: Optional[SetupWizard] = None
        
        # Tabbed interface
        self.tabview: Optional[ctk.CTkTabview] = None
        
        # Setup UI
        self._setup_theme()
        self._setup_layout()
        self._setup_status_bar()
        self._create_main_content()
        self._setup_event_handlers()
        
        # Initialize device from config
        self._initialize_device()
        
        # Setup logging integration
        self._setup_logging_integration()
        
        # Check if first run
        self._check_first_run()
        
        self.logger.info("Main window initialized successfully")
    
    def _initialize_core_services(self) -> None:
        """Initialize all core application services."""
        # Initialize configuration
        try:
            self.config = get_config()
        except RuntimeError:
            # Initialize with defaults if not already done
            self.config = init_config()
        
        # Initialize logging
        try:
            self.logger = get_logger()
        except RuntimeError:
            # Setup logging if not already done
            self.logger = setup_logging(
                colored=self.config.ui.colored_output,
                log_file=self.config.get_config_dir() / 'gui.log',
                level=self.config.log_level
            )
        
        # Use external file service if provided, otherwise get/init default
        if self._external_file_service:
            self.file_service = self._external_file_service
        else:
            try:
                self.file_service = get_file_service()
            except RuntimeError:
                # Initialize file service if not already done
                downloads_dir = self.config.get_downloads_directory()
                self.file_service = init_file_service(
                    downloads_dir=downloads_dir,
                    chunk_size=self.config.downloads.chunk_size,
                    timeout=self.config.downloads.download_timeout,
                    max_retries=self.config.downloads.max_retries
                )
        
        # Initialize CodexCtl service
        self._initialize_codexctl_service()
        
        # Get validator
        self.validator = get_validator()
    
    def _setup_theme(self) -> None:
        """Setup CustomTkinter theme and appearance."""
        # Set appearance mode (light/dark)
        appearance_mode = "dark"  # Default to dark mode
        ctk.set_appearance_mode(appearance_mode)
        
        # Set color theme
        ctk.set_default_color_theme("blue")  # Options: blue, green, dark-blue
        
        # Store current theme for switching
        self.current_theme = appearance_mode
    
    def _setup_layout(self) -> None:
        """Setup main window layout and grid configuration."""
        # Configure root grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)  # Main content area
        
        # Header frame for connection status and controls
        self.header_frame = ctk.CTkFrame(self.root, height=80)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        self.header_frame.grid_columnconfigure(1, weight=1)
        self.header_frame.grid_propagate(False)
        
        # Main content frame for tabbed interface
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        
        # Status bar frame
        self.status_bar_frame = ctk.CTkFrame(self.root, height=30)
        self.status_bar_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))
        self.status_bar_frame.grid_columnconfigure(1, weight=1)
        self.status_bar_frame.grid_propagate(False)
    
    def _setup_status_bar(self) -> None:
        """Setup application status bar."""
        # App title
        title_label = ctk.CTkLabel(
            self.status_bar_frame,
            text=f"🔧 {self.config.app_name}",
            font=ctk.CTkFont(size=12)
        )
        title_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        # Status message
        self.status_label = ctk.CTkLabel(
            self.status_bar_frame,
            text="Ready",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(row=0, column=1, padx=10, pady=5)
        
        # Theme toggle button
        self.theme_button = ctk.CTkButton(
            self.status_bar_frame,
            text="🌙" if self.current_theme == "light" else "☀️",
            width=30,
            height=25,
            command=self._toggle_theme
        )
        self.theme_button.grid(row=0, column=2, padx=5, pady=2)
    
    def _create_main_content(self) -> None:
        """Create main content area with tabbed interface."""
        # Connection header section
        self._create_connection_header()
        
        # Create tabbed interface
        self.tabview = ctk.CTkTabview(self.main_frame)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Create tabs - reorganized for beginner-friendly main tab
        self.tabview.add("Install & Monitor")  # Main tab for beginners
        self.tabview.add("Custom Packages")    # Custom package management
        self.tabview.add("Advanced Backup")   # Advanced backup operations
        self.tabview.add("Device Status")      # Advanced device information
        self.tabview.add("CodexCtl")           # Firmware management
        self.tabview.add("Settings")            # Advanced settings
        
        # Setup tab content
        self._setup_main_tab()           # Combined install + progress + logs
        self._setup_custom_packages_tab() # Custom package management
        self._setup_backup_tab()         # Advanced backup operations
        self._setup_status_tab()         # Device status information
        self._setup_codexctl_tab()       # Firmware management
        self._setup_settings_tab()       # Application settings
    
    def _create_connection_header(self) -> None:
        """Create connection status and control header."""
        # Device info section
        device_info_frame = ctk.CTkFrame(self.header_frame)
        device_info_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        device_info_frame.grid_columnconfigure(1, weight=1)
        
        # Device icon and basic info
        device_icon = ctk.CTkLabel(
            device_info_frame,
            text="📱",
            font=ctk.CTkFont(size=20)
        )
        device_icon.grid(row=0, column=0, padx=10, pady=5)
        
        # Device details
        self.device_label = ctk.CTkLabel(
            device_info_frame,
            text="No Device Connected",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.device_label.grid(row=0, column=1, sticky="w", padx=(0, 10), pady=2)
        
        self.device_details = ctk.CTkLabel(
            device_info_frame,
            text="Connect to your reMarkable device",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.device_details.grid(row=1, column=1, sticky="w", padx=(0, 10), pady=2)
        
        # Connection controls section
        controls_frame = ctk.CTkFrame(self.header_frame)
        controls_frame.grid(row=0, column=1, sticky="ns", padx=5, pady=5)
        
        # Connect/Disconnect button
        self.connect_button = ctk.CTkButton(
            controls_frame,
            text="Connect",
            command=self._toggle_connection,
            width=100,
            height=32
        )
        self.connect_button.grid(row=0, column=0, padx=10, pady=2)
        
        # Connection settings button
        self.settings_button = ctk.CTkButton(
            controls_frame,
            text="Settings",
            command=self._open_connection_settings,
            width=80,
            height=32,
            fg_color="gray",
            hover_color="#606060"
        )
        self.settings_button.grid(row=0, column=1, padx=5, pady=2)
        
        # Connection status indicator
        status_frame = ctk.CTkFrame(self.header_frame)
        status_frame.grid(row=0, column=2, sticky="ns", padx=5, pady=5)
        
        self.connection_status = ctk.CTkLabel(
            status_frame,
            text="● Disconnected",
            font=ctk.CTkFont(size=12),
            text_color="red"
        )
        self.connection_status.grid(row=0, column=0, padx=10, pady=5)
    
    def _setup_main_tab(self) -> None:
        """Setup main beginner-friendly tab with installation, progress, and logs."""
        main_tab = self.tabview.tab("Install & Monitor")
        main_tab.grid_columnconfigure(0, weight=1)
        main_tab.grid_rowconfigure(1, weight=1)  # Make progress/logs area expandable
        
        # Installation options section (top)
        install_frame = ctk.CTkFrame(main_tab)
        install_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 3))
        install_frame.grid_columnconfigure((0, 1, 2), weight=1)
        
        # Section title
        ctk.CTkLabel(
            install_frame,
            text="🚀 Installation Options",
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=0, columnspan=3, pady=(5, 7), sticky="w", padx=5)
        
        # Full installation option
        self.full_install_button = ctk.CTkButton(
            install_frame,
            text="📦 Full Install\n(XOVI + AppLoad + KOReader)",
            command=lambda: self._show_install_prompt("full"),
            width=90,
            height=40,
            font=ctk.CTkFont(size=9, weight="bold")
        )
        self.full_install_button.grid(row=1, column=0, padx=5, pady=3)
        
        # Launcher only option
        self.launcher_install_button = ctk.CTkButton(
            install_frame,
            text="🔧 Launcher Only\n(XOVI + AppLoad)",
            command=lambda: self._show_install_prompt("launcher"),
            width=90,
            height=40,
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="gray",
            hover_color="#606060"
        )
        self.launcher_install_button.grid(row=1, column=1, padx=5, pady=3)
        
        # Uninstall option
        self.uninstall_button = ctk.CTkButton(
            install_frame,
            text="🗑️ Uninstall\n(Remove XOVI)",
            command=lambda: self._uninstall_with_connect(),
            width=90,
            height=40,
            font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#8b2635",
            hover_color="#6b1c28"
        )
        self.uninstall_button.grid(row=1, column=2, padx=5, pady=3)
        
        # Quick backup button
        ctk.CTkButton(
            install_frame,
            text="💾 Create Backup",
            command=lambda: self._create_backup_with_connect(),
            width=120,
            height=35,
            font=ctk.CTkFont(size=11)
        ).grid(row=2, column=0, padx=15, pady=(0, 15), sticky="w")
        
        # Help button
        ctk.CTkButton(
            install_frame,
            text="❓ Help",
            command=self._open_help,
            width=120,
            height=35,
            font=ctk.CTkFont(size=11),
            fg_color="gray",
            hover_color="#606060"
        ).grid(row=2, column=2, padx=15, pady=(0, 15), sticky="e")
        
        # Progress and logs section (bottom - expandable)
        monitor_frame = ctk.CTkFrame(main_tab)
        monitor_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))
        monitor_frame.grid_columnconfigure(0, weight=1)
        monitor_frame.grid_rowconfigure(1, weight=1)
        
        # Section title
        ctk.CTkLabel(
            monitor_frame,
            text="📊 Progress & Logs",
            font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, pady=(15, 10), sticky="w", padx=15)
        
        # Progress section
        # Create horizontal container for progress and logs side by side
        horizontal_container = ctk.CTkFrame(monitor_frame, fg_color="transparent")
        horizontal_container.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        horizontal_container.grid_columnconfigure(0, weight=1)  # Progress panel column
        horizontal_container.grid_columnconfigure(1, weight=1)  # Log panel column
        horizontal_container.grid_rowconfigure(0, weight=1)
        monitor_frame.grid_rowconfigure(1, weight=1)  # Give horizontal container all remaining space
        
        # Progress panel (left side)
        progress_container = ctk.CTkFrame(horizontal_container)
        progress_container.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        
        self.progress_panel = ProgressPanel(progress_container)
        self.progress_panel.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Log panel (right side)
        log_container = ctk.CTkFrame(horizontal_container)
        log_container.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        log_container.grid_columnconfigure(0, weight=1)
        log_container.grid_rowconfigure(0, weight=1)
        
        self.log_panel = LogPanel(log_container)
        self.log_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
    
    def _setup_backup_tab(self) -> None:
        """Setup backup and restore tab content."""
        backup_tab = self.tabview.tab("Advanced Backup")
        backup_tab.grid_columnconfigure(0, weight=1)
        
        # Backup operations frame
        backup_frame = ctk.CTkScrollableFrame(backup_tab, label_text="Backup Operations")
        backup_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        backup_tab.grid_rowconfigure(0, weight=1)
        
        # Create backup
        create_backup_frame = ctk.CTkFrame(backup_frame)
        create_backup_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            create_backup_frame,
            text="💾 Create Backup",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(
            create_backup_frame,
            text="Create a full system backup before making changes",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(anchor="w", padx=15, pady=(0, 10))
        
        self.create_backup_button = ctk.CTkButton(
            create_backup_frame,
            text="Create Backup",
            command=lambda: self._create_backup(),
            width=150,
            height=35
        )
        self.create_backup_button.pack(anchor="w", padx=15, pady=(0, 15))
        
        # Restore from backup
        restore_backup_frame = ctk.CTkFrame(backup_frame)
        restore_backup_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            restore_backup_frame,
            text="🔄 Restore from Backup",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(
            restore_backup_frame,
            text="Restore your device from a previous backup",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(anchor="w", padx=15, pady=(0, 10))
        
        backup_controls_frame = ctk.CTkFrame(restore_backup_frame, fg_color="transparent")
        backup_controls_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        self.restore_backup_button = ctk.CTkButton(
            backup_controls_frame,
            text="Restore Backup",
            command=lambda: self._restore_backup(),
            width=150,
            height=35,
            fg_color="orange",
            hover_color="#cc8800"
        )
        self.restore_backup_button.pack(side="left", padx=(0, 10))
        
        self.list_backups_button = ctk.CTkButton(
            backup_controls_frame,
            text="List Backups",
            command=lambda: self._list_backups(),
            width=120,
            height=35,
            fg_color="gray",
            hover_color="#606060"
        )
        self.list_backups_button.pack(side="left", padx=5)
        
        self.delete_backup_button = ctk.CTkButton(
            backup_controls_frame,
            text="Delete Backup",
            command=lambda: self._delete_backup(),
            width=120,
            height=35,
            fg_color="#8b2635",
            hover_color="#6b1c28"
        )
        self.delete_backup_button.pack(side="left", padx=5)
        
        self.prune_backups_button = ctk.CTkButton(
            backup_controls_frame,
            text="Prune Backups (Keep 3)",
            command=lambda: self._prune_backups(),
            width=150,
            height=35,
            fg_color="orange",
            hover_color="#cc8800"
        )
        self.prune_backups_button.pack(side="left", padx=5)
    
    def _setup_status_tab(self) -> None:
        """Setup device status tab content."""
        status_tab = self.tabview.tab("Device Status")
        status_tab.grid_columnconfigure(0, weight=1)
        
        # Device status frame
        self.status_frame = ctk.CTkScrollableFrame(status_tab, label_text="Device Information")
        self.status_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        status_tab.grid_rowconfigure(0, weight=1)
        
        # Refresh button
        refresh_frame = ctk.CTkFrame(self.status_frame)
        refresh_frame.pack(fill="x", padx=10, pady=5)
        
        self.refresh_button = ctk.CTkButton(
            refresh_frame,
            text="🔄 Refresh Status",
            command=self._refresh_device_info,
            width=150,
            height=35
        )
        self.refresh_button.pack(padx=15, pady=15)
        
        # Status display area
        self.status_text = ctk.CTkTextbox(self.status_frame, wrap="word", height=400)
        self.status_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self._update_device_status_display()
    
    def _show_install_prompt(self, install_type: str) -> None:
        """Show installation option prompt with detailed information."""
        # Installation type descriptions
        install_info = {
            "full": {
                "title": "Full Installation",
                "description": "Complete XOVI suite with all features",
                "components": [
                    "• XOVI Framework - Core system modifications",
                    "• AppLoad Launcher - Application management system",
                    "• KOReader - Advanced PDF/EPUB reader",
                    "• System Extensions - Additional functionality"
                ],
                "benefits": [
                    "✓ Complete reading experience with KOReader",
                    "✓ Full application launching capabilities",
                    "✓ All XOVI extensions and features",
                    "✓ Recommended for most users"
                ],
                "size": "~50-80 MB",
                "time": "5-10 minutes"
            },
            "launcher": {
                "title": "Launcher Only Installation",
                "description": "Basic XOVI with launcher, no KOReader",
                "components": [
                    "• XOVI Framework - Core system modifications",
                    "• AppLoad Launcher - Application management system",
                    "• System Extensions - Additional functionality"
                ],
                "benefits": [
                    "✓ Lighter installation footprint",
                    "✓ Application launching capabilities",
                    "✓ Core XOVI functionality",
                    "✓ Good for users who don't need KOReader"
                ],
                "size": "~20-30 MB",
                "time": "3-5 minutes"
            }
        }
        
        info = install_info[install_type]
        
        # Create confirmation dialog
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(f"Confirm {info['title']}")
        dialog.geometry("500x650")
        dialog.resizable(False, False)
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (dialog.winfo_screenheight() // 2) - (650 // 2)
        dialog.geometry(f"500x650+{x}+{y}")
        
        # Make it modal
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Create scrollable content
        content_frame = ctk.CTkScrollableFrame(dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title_label = ctk.CTkLabel(
            content_frame,
            text=f"🚀 {info['title']}",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(pady=(0, 15))
        
        # Description
        desc_label = ctk.CTkLabel(
            content_frame,
            text=info['description'],
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        desc_label.pack(pady=(0, 20))
        
        # Components section
        components_frame = ctk.CTkFrame(content_frame)
        components_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            components_frame,
            text="What will be installed:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        for component in info['components']:
            ctk.CTkLabel(
                components_frame,
                text=component,
                font=ctk.CTkFont(size=12),
                justify="left"
            ).pack(anchor="w", padx=20, pady=2)
        
        # Benefits section
        benefits_frame = ctk.CTkFrame(content_frame)
        benefits_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            benefits_frame,
            text="Benefits:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        for benefit in info['benefits']:
            ctk.CTkLabel(
                benefits_frame,
                text=benefit,
                font=ctk.CTkFont(size=12),
                justify="left",
                text_color="green"
            ).pack(anchor="w", padx=20, pady=2)
        
        # Installation details
        details_frame = ctk.CTkFrame(content_frame)
        details_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            details_frame,
            text="Installation Details:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        ctk.CTkLabel(
            details_frame,
            text=f"📦 Download Size: {info['size']}",
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=20, pady=2)
        
        ctk.CTkLabel(
            details_frame,
            text=f"⏱️ Estimated Time: {info['time']}",
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=20, pady=2)
        
        ctk.CTkLabel(
            details_frame,
            text="💾 Automatic backup will be created",
            font=ctk.CTkFont(size=12),
            text_color="blue"
        ).pack(anchor="w", padx=20, pady=(2, 15))
        
        # Warning section
        warning_frame = ctk.CTkFrame(content_frame)
        warning_frame.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(
            warning_frame,
            text="⚠️ Important Notes:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="orange"
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        warnings = [
            "• Ensure your device has a stable connection",
            "• Do not power off during installation",
            "• Installation modifies system files safely",
            "• A backup will be created automatically"
        ]
        
        for warning in warnings:
            ctk.CTkLabel(
                warning_frame,
                text=warning,
                font=ctk.CTkFont(size=11),
                text_color="gray"
            ).pack(anchor="w", padx=20, pady=1)
        
        # Optional features section
        options_frame = ctk.CTkFrame(content_frame)
        options_frame.pack(fill="x", pady=(0, 15))
        
        ctk.CTkLabel(
            options_frame,
            text="🔧 Optional Features:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Tripletap checkbox
        self.tripletap_var = tk.BooleanVar(value=False)
        tripletap_checkbox = ctk.CTkCheckBox(
            options_frame,
            text="Enable xovi-tripletap (Power button launcher)",
            variable=self.tripletap_var
        )
        tripletap_checkbox.pack(anchor="w", padx=20, pady=(0, 5))
        
        # Tripletap description
        ctk.CTkLabel(
            options_frame,
            text="• Triple-press power button to launch XOVI",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).pack(anchor="w", padx=35, pady=(0, 10))
        
        # Note about custom packages for advanced users
        if install_type == "full":
            custom_info_frame = ctk.CTkFrame(options_frame)
            custom_info_frame.pack(fill="x", padx=20, pady=(0, 10))
            
            ctk.CTkLabel(
                custom_info_frame,
                text="💡 Advanced Feature Available",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="blue"
            ).pack(anchor="w", padx=15, pady=(15, 5))
            
            ctk.CTkLabel(
                custom_info_frame,
                text="Visit the 'Custom Packages' tab to use your own KOReader package",
                font=ctk.CTkFont(size=11),
                text_color="gray"
            ).pack(anchor="w", padx=20, pady=(0, 15))
        
        # Add some spacing before buttons
        ctk.CTkLabel(content_frame, text="").pack(pady=5)
        
        # Buttons
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))
        
        def proceed_install():
            # Get tripletap preference
            enable_tripletap = self.tripletap_var.get()
            
            # Get custom package info if this is a full install
            custom_package_path = None
            if install_type == "full" and hasattr(self, 'custom_package_var') and self.custom_package_var.get():
                custom_package_path = self.custom_package_path.get()
                if custom_package_path == "No file selected" or not custom_package_path:
                    self._update_status("Please select a custom package file first")
                    return
            
            dialog.destroy()
            # Immediately disable the button to prevent double-clicking
            self.full_install_button.configure(state="disabled")
            self.launcher_install_button.configure(state="disabled")
            
            if install_type == "full":
                self._install_full_with_connect(enable_tripletap=enable_tripletap, custom_package_path=custom_package_path)
            else:
                self._install_launcher_with_connect(enable_tripletap=enable_tripletap)
        
        ctk.CTkButton(
            button_frame,
            text=f"✅ Start {info['title']}",
            command=proceed_install,
            width=200,
            height=40,
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="right", padx=(10, 0))
        
        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=dialog.destroy,
            width=100,
            height=40,
            fg_color="gray",
            hover_color="#606060"
        ).pack(side="right")
    
    def _setup_codexctl_tab(self) -> None:
        """Setup CodexCtl firmware management tab content."""
        codexctl_tab = self.tabview.tab("CodexCtl")
        codexctl_tab.grid_columnconfigure(0, weight=1)
        codexctl_tab.grid_rowconfigure(0, weight=1)
        
        # Create CodexCtl panel - DISABLED by default
        self.codexctl_panel = CodexCtlPanel(
            codexctl_tab,
            progress_callback=self._on_codexctl_progress,
            status_callback=self._on_codexctl_status,
            disabled=True  # Panel is locked off by default
        )
        self.codexctl_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Don't connect to service when disabled
        self.logger.info("CodexCtl panel initialized in disabled state")
    
    def _setup_settings_tab(self) -> None:
        """Setup settings tab content."""
        settings_tab = self.tabview.tab("Settings")
        settings_tab.grid_columnconfigure(0, weight=1)
        
        # Settings frame
        settings_frame = ctk.CTkScrollableFrame(settings_tab, label_text="Application Settings")
        settings_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        settings_tab.grid_rowconfigure(0, weight=1)
        
        # Connection settings
        connection_frame = ctk.CTkFrame(settings_frame)
        connection_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            connection_frame,
            text="🔌 Connection Settings",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Setup wizard button
        ctk.CTkButton(
            connection_frame,
            text="🧙 Run Setup Wizard",
            command=self._show_setup_wizard,
            width=150,
            height=30
        ).pack(anchor="w", padx=15, pady=5)
        
        # Edit connection button
        ctk.CTkButton(
            connection_frame,
            text="Edit Connection Details",
            command=self._open_connection_settings,
            width=150,
            height=30,
            fg_color="gray",
            hover_color="#606060"
        ).pack(anchor="w", padx=15, pady=5)
        
        # Ethernet fix button
        ctk.CTkButton(
            connection_frame,
            text="🔧 Fix USB Ethernet",
            command=self._fix_ethernet_with_connect,
            width=150,
            height=30,
            fg_color="orange",
            hover_color="#cc8800"
        ).pack(anchor="w", padx=15, pady=(5, 15))
        
        # Application settings
        app_settings_frame = ctk.CTkFrame(settings_frame)
        app_settings_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            app_settings_frame,
            text="⚙️ Application Settings",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Debug mode checkbox
        self.debug_var = tk.BooleanVar(value=self.config.debug_mode)
        ctk.CTkCheckBox(
            app_settings_frame,
            text="Enable debug logging",
            variable=self.debug_var,
            command=self._save_settings
        ).pack(anchor="w", padx=20, pady=5)
        
        # Colored output checkbox
        self.colored_var = tk.BooleanVar(value=self.config.ui.colored_output)
        ctk.CTkCheckBox(
            app_settings_frame,
            text="Colored log output",
            variable=self.colored_var,
            command=self._save_settings
        ).pack(anchor="w", padx=20, pady=5)
        
        # Backup checkbox
        self.backup_var = tk.BooleanVar(value=self.config.installation.create_backup)
        ctk.CTkCheckBox(
            app_settings_frame,
            text="Create backup before installation",
            variable=self.backup_var,
            command=self._save_settings
        ).pack(anchor="w", padx=20, pady=(5, 15))
    
    def _setup_event_handlers(self) -> None:
        """Setup window and application event handlers."""
        # Window close handler
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        # Keyboard shortcuts
        self.root.bind("<Control-q>", lambda e: self._on_window_close())
        self.root.bind("<F1>", lambda e: self._open_help())
        self.root.bind("<F5>", lambda e: self._refresh_device_info())
    
    def _initialize_device(self) -> None:
        """Initialize device from configuration."""
        # Use external device if provided
        if self._external_device:
            self.device = self._external_device
        elif self.config.device.ip_address and self.config.device.ssh_password:
            self.device = Device(
                ip_address=self.config.device.ip_address,
                ssh_password=self.config.device.ssh_password,
                device_type=self.config.device.device_type
            )
        
        # Update UI with loaded device
        self._update_device_display()
    
    def _setup_logging_integration(self) -> None:
        """Setup integration between logger and log panel."""
        if self.log_panel:
            # Add GUI log handler to redirect logs to the log panel
            gui_handler = self.logger.add_gui_handler(self.log_panel.add_log_entry)
            self.logger.info("GUI logging integration established")
    
    def _check_first_run(self) -> None:
        """Check if this is the first run and show setup wizard if needed."""
        config_file = self.config.get_config_file_path()
        
        # Only show wizard on true first run (no config file at all)
        # Don't show if they just don't have device config but have used the app before
        if not config_file.exists():
            self.logger.info("First run detected, showing setup wizard")
            self._show_setup_wizard()
        elif not self.config.is_valid_device_config():
            self.logger.info("Device not configured, but config file exists - skipping wizard")
            self._update_status("Device not configured. Use connection settings or run setup wizard.")
    
    def _show_setup_wizard(self) -> None:
        """Show the initial setup wizard."""
        if not self.setup_wizard:
            self.setup_wizard = SetupWizard(
                self.root,
                completion_callback=self._on_setup_wizard_complete
            )
        self.setup_wizard.show()
    
    def _toggle_theme(self) -> None:
        """Toggle between light and dark themes."""
        new_theme = "light" if self.current_theme == "dark" else "dark"
        ctk.set_appearance_mode(new_theme)
        self.current_theme = new_theme
        
        # Update theme button icon
        self.theme_button.configure(text="🌙" if new_theme == "light" else "☀️")
        
        self.logger.info(f"Theme switched to {new_theme} mode")
    
    def _toggle_connection(self) -> None:
        """Toggle device connection."""
        if not self.device or not self.device.is_configured():
            self._open_connection_settings()
            return
        
        if self.device.is_connected():
            self._disconnect_device()
        else:
            self._connect_device()
    
    def _connect_device(self) -> None:
        """Connect to the device."""
        if not self.device:
            self._update_status("No device configured")
            return
        
        self.connect_button.configure(text="Connecting...", state="disabled")
        self._update_connection_status(ConnectionStatus.CONNECTING)
        
        def connect_async():
            try:
                success = self.device.test_connection()
                if success:
                    self.device.detect_device_type()  # Auto-detect device type
                
                self.root.after(0, lambda: self._connection_complete(success))
            except Exception as e:
                self.root.after(0, lambda: self._connection_complete(False, str(e)))
        
        threading.Thread(target=connect_async, daemon=True).start()
    
    def _disconnect_device(self) -> None:
        """Disconnect from the device."""
        if self.device:
            self.device.connection_status = ConnectionStatus.DISCONNECTED
        
        self._update_connection_status(ConnectionStatus.DISCONNECTED)
        self.connect_button.configure(text="Connect", state="normal")
        self._update_device_display()
        self._update_status("Disconnected from device")
    
    def _connection_complete(self, success: bool, error: str = "") -> None:
        """Handle connection completion."""
        self.connect_button.configure(state="normal")
        
        if success and self.device:
            self.connect_button.configure(text="Disconnect")
            self._update_connection_status(ConnectionStatus.CONNECTED)
            self._update_device_display()
            self._update_status("Connected to device successfully")
            self.logger.info(f"Connected to {self.device}")
        else:
            self.connect_button.configure(text="Connect")
            self._update_connection_status(ConnectionStatus.ERROR)
            error_msg = f"Connection failed: {error}" if error else "Connection failed"
            self._update_status(error_msg)
            self.logger.error(error_msg)
    
    def _open_connection_settings(self) -> None:
        """Open connection settings dialog."""
        settings_dialog = ctk.CTkToplevel(self.root)
        settings_dialog.title("Connection Settings")
        settings_dialog.geometry("400x300")
        settings_dialog.resizable(False, False)
        
        # Center the dialog
        settings_dialog.update_idletasks()
        x = (settings_dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (settings_dialog.winfo_screenheight() // 2) - (300 // 2)
        settings_dialog.geometry(f"400x300+{x}+{y}")
        
        # Make it modal
        settings_dialog.transient(self.root)
        settings_dialog.grab_set()
        
        # Create content
        content_frame = ctk.CTkFrame(settings_dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        ctk.CTkLabel(
            content_frame,
            text="Device Connection Settings",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(0, 20))
        
        # IP Address
        ctk.CTkLabel(content_frame, text="IP Address:").pack(anchor="w")
        ip_entry = ctk.CTkEntry(
            content_frame,
            placeholder_text="10.11.99.1 (USB) or 192.168.x.x (WiFi)",
            width=300
        )
        ip_entry.pack(pady=(5, 15))
        
        # SSH Password
        ctk.CTkLabel(content_frame, text="SSH Password:").pack(anchor="w")
        password_entry = ctk.CTkEntry(
            content_frame,
            placeholder_text="Enter SSH password from device",
            show="*",
            width=300
        )
        password_entry.pack(pady=(5, 20))
        
        # Pre-fill with current values
        if self.device:
            if self.device.ip_address:
                ip_entry.insert(0, self.device.ip_address)
            if self.device.ssh_password:
                password_entry.insert(0, self.device.ssh_password)
        
        # Buttons
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(fill="x")
        
        def save_settings():
            ip = ip_entry.get().strip()
            password = password_entry.get().strip()
            
            if not ip or not password:
                self._update_status("Please enter both IP address and password")
                return
            
            # Update or create device
            if self.device:
                self.device.update_connection_info(ip, password)
            else:
                self.device = Device(ip_address=ip, ssh_password=password)
            
            # Save to config
            self.config.update_device_info(
                ip_address=ip,
                ssh_password=password,
                device_type=self.device.device_type
            )
            self.config.save_to_file()
            
            self._update_device_display()
            self._update_status("Connection settings saved")
            settings_dialog.destroy()
        
        ctk.CTkButton(
            button_frame,
            text="Save",
            command=save_settings
        ).pack(side="right", padx=(5, 0))
        
        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=settings_dialog.destroy,
            fg_color="gray",
            hover_color="#606060"
        ).pack(side="right")
    
    def _update_device_display(self) -> None:
        """Update the device display in the header."""
        if self.device:
            device_type_str = self.device.device_type.display_name if self.device.device_type else "Unknown Device"
            self.device_label.configure(text=device_type_str)
            self.device_details.configure(text=f"IP: {self.device.ip_address}")
        else:
            self.device_label.configure(text="No Device Connected")
            self.device_details.configure(text="Connect to your reMarkable device")
    
    def _update_connection_status(self, status: ConnectionStatus) -> None:
        """Update connection status indicator."""
        status_colors = {
            ConnectionStatus.CONNECTED: "green",
            ConnectionStatus.CONNECTING: "orange", 
            ConnectionStatus.DISCONNECTED: "red",
            ConnectionStatus.AUTHENTICATION_FAILED: "red",
            ConnectionStatus.TIMEOUT: "red",
            ConnectionStatus.ERROR: "red"
        }
        
        status_text = {
            ConnectionStatus.CONNECTED: "● Connected",
            ConnectionStatus.CONNECTING: "● Connecting...",
            ConnectionStatus.DISCONNECTED: "● Disconnected",
            ConnectionStatus.AUTHENTICATION_FAILED: "● Auth Failed",
            ConnectionStatus.TIMEOUT: "● Timeout",
            ConnectionStatus.ERROR: "● Error"
        }
        
        color = status_colors.get(status, "gray")
        text = status_text.get(status, f"● {status.value}")
        
        self.connection_status.configure(text=text, text_color=color)
        
        # Update button states based on connection
        connected = status == ConnectionStatus.CONNECTED
        self._update_operation_buttons(connected)
    
    def _update_operation_buttons(self, connected: bool) -> None:
        """Update operation button states based on connection."""
        # Installation buttons
        if hasattr(self, 'full_install_button'):
            self.full_install_button.configure(state="normal" if connected else "disabled")
        if hasattr(self, 'launcher_install_button'):
            self.launcher_install_button.configure(state="normal" if connected else "disabled")
        if hasattr(self, 'uninstall_button'):
            self.uninstall_button.configure(state="normal" if connected else "disabled")
        
        # Backup buttons
        if hasattr(self, 'create_backup_button'):
            self.create_backup_button.configure(state="normal" if connected else "disabled")
        if hasattr(self, 'restore_backup_button'):
            self.restore_backup_button.configure(state="normal" if connected else "disabled")
        if hasattr(self, 'list_backups_button'):
            self.list_backups_button.configure(state="normal" if connected else "disabled")
        if hasattr(self, 'delete_backup_button'):
            self.delete_backup_button.configure(state="normal" if connected else "disabled")
        if hasattr(self, 'prune_backups_button'):
            self.prune_backups_button.configure(state="normal" if connected else "disabled")
        
        # Built-in package buttons
        if hasattr(self, 'install_koreader_button'):
            self.install_koreader_button.configure(state="normal" if connected else "disabled")
        if hasattr(self, 'install_literm_button'):
            self.install_literm_button.configure(state="normal" if connected else "disabled")
        if hasattr(self, 'install_package_button'):
            self.install_package_button.configure(state="normal" if connected else "disabled")
        
        # Status refresh button
        if hasattr(self, 'refresh_button'):
            self.refresh_button.configure(state="normal" if connected else "disabled")
    
    def _update_device_status_display(self) -> None:
        """Update device status display."""
        if not self.device or not self.device.is_connected():
            self.status_text.delete("1.0", "end")
            self.status_text.insert("1.0", "Device not connected.\nPlease connect to view status information.")
            self.status_text.configure(state="disabled")
            return
        
        # Refresh device info and display
        def refresh_and_display():
            try:
                if self.device:
                    self.device.refresh_all_info()
                    self.root.after(0, self._display_device_status)
            except Exception as e:
                self.logger.error(f"Failed to refresh device info: {e}")
        
        threading.Thread(target=refresh_and_display, daemon=True).start()
    
    def _display_device_status(self) -> None:
        """Display current device status information."""
        if not self.device:
            return
        
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        
        # Build status content
        status_content = f"Device: {self.device}\n\n"
        
        if self.device.device_info:
            status_content += "System Information:\n"
            status_content += f"  Hostname: {self.device.device_info.hostname}\n"
            status_content += f"  Kernel: {self.device.device_info.kernel_version}\n"
            status_content += f"  reMarkable Version: {self.device.device_info.remarkable_version}\n"
            if self.device.device_info.free_space:
                free_mb = self.device.device_info.get_free_space_mb()
                total_mb = self.device.device_info.get_total_space_mb()
                status_content += f"  Storage: {free_mb:.1f} MB free / {total_mb:.1f} MB total\n"
            status_content += "\n"
        
        if self.device.network_info:
            status_content += "Network Information:\n"
            if self.device.network_info.usb_ip:
                status_content += f"  USB IP: {self.device.network_info.usb_ip}\n"
            if self.device.network_info.wifi_ip:
                status_content += f"  WiFi IP: {self.device.network_info.wifi_ip}\n"
            status_content += f"  WiFi Enabled: {self.device.network_info.wifi_enabled}\n"
            status_content += f"  Ethernet Enabled: {self.device.network_info.ethernet_enabled}\n"
            status_content += "\n"
        
        if self.device.installation_info:
            status_content += "Installation Status:\n"
            status_content += f"  XOVI Installed: {self.device.installation_info.xovi_installed}\n"
            if self.device.installation_info.xovi_version:
                status_content += f"  XOVI Version: {self.device.installation_info.xovi_version}\n"
            status_content += f"  AppLoad Installed: {self.device.installation_info.appload_installed}\n"
            status_content += f"  KOReader Installed: {self.device.installation_info.koreader_installed}\n"
            status_content += f"  Extensions Count: {self.device.installation_info.extensions_count}\n"
            status_content += f"  Backups Available: {self.device.installation_info.backup_count}\n"
        
        self.status_text.insert("1.0", status_content)
        self.status_text.configure(state="disabled")
    
    def _refresh_device_info(self) -> None:
        """Refresh device information."""
        if self.device and self.device.is_connected():
            self.logger.info("Refreshing device information...")
            self._update_status("Refreshing device information...")
            self.refresh_button.configure(text="🔄 Refreshing...", state="disabled")
            
            def refresh_async():
                try:
                    success = self.device.refresh_all_info()
                    self.root.after(0, lambda: self._refresh_complete(success))
                except Exception as e:
                    self.root.after(0, lambda: self._refresh_complete(False, str(e)))
            
            threading.Thread(target=refresh_async, daemon=True).start()
        else:
            self._update_status("No device connected to refresh")
    
    def _refresh_complete(self, success: bool, error: str = "") -> None:
        """Handle refresh completion."""
        self.refresh_button.configure(text="🔄 Refresh Status", state="normal")
        
        if success:
            self._update_status("Device information refreshed successfully")
            self._display_device_status()
            self._update_device_display()
        else:
            error_msg = f"Failed to refresh device information: {error}" if error else "Failed to refresh device information"
            self._update_status(error_msg)
            self.logger.error(error_msg)
    
    def _save_settings(self) -> None:
        """Save application settings."""
        self.config.debug_mode = self.debug_var.get()
        self.config.ui.colored_output = self.colored_var.get()
        self.config.installation.create_backup = self.backup_var.get()
        self.config.save_to_file()
        self._update_status("Settings saved")
        self.logger.info("Application settings updated")
    
    def _update_status(self, message: str) -> None:
        """Update status bar message."""
        self.status_label.configure(text=message)
    
    def _on_setup_wizard_complete(self, device_info: Dict[str, Any]) -> None:
        """Handle setup wizard completion."""
        self.logger.info("Setup wizard completed")
        
        # Update device configuration
        if device_info:
            self.config.update_device_info(
                ip_address=device_info.get("ip_address"),
                ssh_password=device_info.get("ssh_password"),
                device_type=device_info.get("device_type")
            )
            
            # Save configuration
            self.config.save_to_file()
            
            # Reinitialize device
            self._initialize_device()
        
        self._update_status("Setup completed successfully")
    
    def _on_window_close(self) -> None:
        """Handle window close event."""
        if self.is_operation_running:
            # Show confirmation dialog for running operations
            dialog = ctk.CTkToplevel(self.root)
            dialog.title("Confirm Exit")
            dialog.geometry("350x200")
            dialog.resizable(False, False)
            
            # Center the dialog
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (350 // 2)
            y = (dialog.winfo_screenheight() // 2) - (200 // 2)
            dialog.geometry(f"350x200+{x}+{y}")
            
            # Make it modal
            dialog.transient(self.root)
            dialog.grab_set()
            
            content_frame = ctk.CTkFrame(dialog)
            content_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            title_label = ctk.CTkLabel(
                content_frame,
                text="Operation in Progress",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="orange"
            )
            title_label.pack(pady=(0, 10))
            
            message_label = ctk.CTkLabel(
                content_frame,
                text="An installation or backup operation is currently running.\nAre you sure you want to exit?",
                font=ctk.CTkFont(size=12),
                justify="center"
            )
            message_label.pack(pady=(0, 20))
            
            button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
            button_frame.pack(fill="x")
            
            def force_exit():
                dialog.destroy()
                self.is_operation_running = False
                self._on_window_close()
            
            ctk.CTkButton(
                button_frame, 
                text="Force Exit", 
                command=force_exit,
                fg_color="#8b2635",
                hover_color="#6b1c28"
            ).pack(side="right", padx=(5, 0))
            ctk.CTkButton(button_frame, text="Cancel", command=dialog.destroy).pack(side="right")
            
            return  # Don't continue with close if operation is running
        
        # Save configuration
        try:
            self.config.save_to_file()
            self.logger.info("Configuration saved")
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
        
        # Cleanup
        if self.file_service:
            self.file_service.cleanup_temp_files()
        
        self.logger.info("Application shutting down")
        self.root.quit()
        self.root.destroy()
    
    def run(self) -> None:
        """Start the GUI application main loop."""
        self.logger.info("Starting GUI application")
        self.root.mainloop()
    
    # Actual implementation methods for operations
    
    def _install_full(self, enable_tripletap: bool = False, **kwargs) -> None:
        """Install XOVI + AppLoader + KOReader (full installation)."""
        if not self._validate_installation_prerequisites():
            return
        
        self.logger.info(f"Starting full installation (tripletap: {enable_tripletap})...")
        self._update_status("Installing XOVI + AppLoader + KOReader...")
        self.is_operation_running = True
        self._update_operation_buttons(False)  # Disable buttons during operation
        
        def run_installation():
            try:
                from ..services.installation_service import get_installation_service, InstallationType
                installation_service = get_installation_service()
                
                # Set tripletap preference
                installation_service.config.installation.enable_tripletap = enable_tripletap
                
                # Set up progress callbacks with proper variable capture
                def progress_callback(progress):
                    # Capture values to avoid lambda closure issues
                    percentage = progress.progress_percentage
                    message = progress.message
                    stage = progress.stage
                    current_step = progress.current_step
                    
                    self.root.after(0, lambda p=percentage, m=message:
                        self.progress_panel.update_overall_progress(p, m))
                    self.root.after(0, lambda s=stage, p=percentage, c=current_step:
                        self.progress_panel.update_stage_progress(s, p, c))
                
                def output_callback(message):
                    msg = str(message)  # Capture the message
                    self.root.after(0, lambda m=msg: self.logger.info(m))
                
                installation_service.set_progress_callback(progress_callback)
                installation_service.set_output_callback(output_callback)
                
                # Start progress tracking
                self.root.after(0, lambda: self.progress_panel.start_operation("Full Installation"))
                
                # Run installation
                success = installation_service.start_installation(InstallationType.FULL)
                
                # Update UI in main thread
                self.root.after(0, lambda: self._installation_complete(success, "Full installation"))
                
            except Exception as e:
                self.logger.error(f"Installation failed: {e}")
                self.root.after(0, lambda: self._installation_complete(False, f"Installation failed: {e}"))
        
        threading.Thread(target=run_installation, daemon=True).start()
    
    def _install_launcher(self, enable_tripletap: bool = False, **kwargs) -> None:
        """Install XOVI + AppLoader only (no KOReader)."""
        if not self._validate_installation_prerequisites():
            return
        
        self.logger.info(f"Starting launcher-only installation (tripletap: {enable_tripletap})...")
        self._update_status("Installing XOVI + AppLoader...")
        self.is_operation_running = True
        self._update_operation_buttons(False)
        
        def run_installation():
            try:
                from ..services.installation_service import get_installation_service, InstallationType
                installation_service = get_installation_service()
                
                # Set tripletap preference
                installation_service.config.installation.enable_tripletap = enable_tripletap
                
                # Set up progress callbacks with proper variable capture
                def progress_callback(progress):
                    # Capture values to avoid lambda closure issues
                    percentage = progress.progress_percentage
                    message = progress.message
                    stage = progress.stage
                    current_step = progress.current_step
                    
                    self.root.after(0, lambda p=percentage, m=message:
                        self.progress_panel.update_overall_progress(p, m))
                    self.root.after(0, lambda s=stage, p=percentage, c=current_step:
                        self.progress_panel.update_stage_progress(s, p, c))
                
                def output_callback(message):
                    msg = str(message)  # Capture the message
                    self.root.after(0, lambda m=msg: self.logger.info(m))
                
                installation_service.set_progress_callback(progress_callback)
                installation_service.set_output_callback(output_callback)
                
                # Start progress tracking
                self.root.after(0, lambda: self.progress_panel.start_operation("Launcher Installation"))
                
                # Run installation
                success = installation_service.start_installation(InstallationType.LAUNCHER_ONLY)
                
                # Update UI in main thread
                self.root.after(0, lambda: self._installation_complete(success, "Launcher installation"))
                
            except Exception as e:
                self.logger.error(f"Installation failed: {e}")
                self.root.after(0, lambda: self._installation_complete(False, f"Installation failed: {e}"))
        
        threading.Thread(target=run_installation, daemon=True).start()
    
    def _create_backup(self, **kwargs) -> None:
        """Create system backup."""
        if not self.device or not self.device.is_connected():
            self._update_status("Device not connected for backup")
            return
        
        self.logger.info("Creating backup...")
        self._update_status("Creating backup...")
        self.is_operation_running = True
        self._update_operation_buttons(False)
        
        def run_backup():
            try:
                from ..services.backup_service import get_backup_service
                backup_service = get_backup_service()
                
                # Set up progress callbacks with proper variable capture
                def progress_callback(progress):
                    if isinstance(progress, dict):
                        # Capture values to avoid lambda closure issues
                        prog_val = progress.get('progress', 0)
                        msg_val = progress.get('message', 'Creating backup...')
                        
                        self.root.after(0, lambda p=prog_val, m=msg_val:
                            self.progress_panel.update_overall_progress(p, m))
                
                def output_callback(message):
                    msg = str(message)  # Capture the message
                    self.root.after(0, lambda m=msg: self.logger.info(m))
                
                backup_service.set_progress_callback(progress_callback)
                backup_service.set_output_callback(output_callback)
                
                # Start progress tracking
                self.root.after(0, lambda: self.progress_panel.start_operation("Backup Creation"))
                
                # Create backup
                backup_info = backup_service.create_backup(include_local_copy=True)
                
                # Update UI in main thread
                self.root.after(0, lambda: self._backup_complete(True, f"Backup created: {backup_info.name}"))
                
            except Exception as e:
                self.logger.error(f"Backup failed: {e}")
                self.root.after(0, lambda: self._backup_complete(False, f"Backup failed: {e}"))
        
        threading.Thread(target=run_backup, daemon=True).start()
    
    def _restore_backup(self, **kwargs) -> None:
        """Restore from backup."""
        if not self.device or not self.device.is_connected():
            self._update_status("Device not connected for restore")
            return
        
        # First, list available backups to let user choose
        def list_and_choose_backup():
            try:
                from ..services.backup_service import get_backup_service
                backup_service = get_backup_service()
                backups = backup_service.list_backups()
                
                if not backups:
                    self.root.after(0, lambda: self._update_status("No backups found on device"))
                    return
                
                self.root.after(0, lambda: self._show_backup_selection_dialog(backups, "restore"))
                
            except Exception as e:
                self.logger.error(f"Failed to list backups: {e}")
                self.root.after(0, lambda: self._update_status(f"Backup listing failed: {e}"))
        
        threading.Thread(target=list_and_choose_backup, daemon=True).start()
        self._update_status("Listing available backups...")
    
    def _list_backups(self, **kwargs) -> None:
        """List available backups."""
        if not self.device or not self.device.is_connected():
            self._update_status("Device not connected")
            return
        
        def list_backups():
            try:
                from ..services.backup_service import get_backup_service
                backup_service = get_backup_service()
                backups = backup_service.list_backups()
                
                self.root.after(0, lambda: self._show_backup_list_dialog(backups))
                
            except Exception as e:
                self.logger.error(f"Failed to list backups: {e}")
                self.root.after(0, lambda: self._update_status(f"Backup listing failed: {e}"))
        
        threading.Thread(target=list_backups, daemon=True).start()
        self._update_status("Listing backups...")
    
    def _delete_backup(self, **kwargs) -> None:
        """Delete backup."""
        if not self.device or not self.device.is_connected():
            self._update_status("Device not connected")
            return
        
        # List available backups to let user choose
        def list_and_choose_backup():
            try:
                from ..services.backup_service import get_backup_service
                backup_service = get_backup_service()
                backups = backup_service.list_backups()
                
                if not backups:
                    self.root.after(0, lambda: self._update_status("No backups found on device"))
                    return
                
                self.root.after(0, lambda: self._show_backup_selection_dialog(backups, "delete"))
                
            except Exception as e:
                self.logger.error(f"Failed to list backups: {e}")
                self.root.after(0, lambda: self._update_status(f"Backup listing failed: {e}"))
        
        threading.Thread(target=list_and_choose_backup, daemon=True).start()
        self._update_status("Listing backups for deletion...")
    
    def _uninstall(self, **kwargs) -> None:
        """Uninstall without backup."""
        if not self.device or not self.device.is_connected():
            self._update_status("Device not connected")
            return
        
        # Show confirmation dialog first
        def show_uninstall_confirmation():
            dialog = ctk.CTkToplevel(self.root)
            dialog.title("Confirm Uninstallation")
            dialog.geometry("400x250")
            dialog.resizable(False, False)
            
            # Center the dialog
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
            y = (dialog.winfo_screenheight() // 2) - (250 // 2)
            dialog.geometry(f"400x250+{x}+{y}")
            
            # Make it modal
            dialog.transient(self.root)
            dialog.grab_set()
            
            content_frame = ctk.CTkFrame(dialog)
            content_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            title_label = ctk.CTkLabel(
                content_frame,
                text="Confirm Uninstallation",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="red"
            )
            title_label.pack(pady=(0, 15))
            
            warning_text = ctk.CTkLabel(
                content_frame,
                text="This will remove all XOVI components from your device.\n\nWARNING: No backup will be created!\n\nThis action cannot be undone unless you have\nexisting backups to restore from.",
                font=ctk.CTkFont(size=12),
                justify="center"
            )
            warning_text.pack(pady=(0, 20))
            
            button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
            button_frame.pack(fill="x")
            
            def proceed_uninstall():
                dialog.destroy()
                self._execute_uninstall()
            
            ctk.CTkButton(
                button_frame,
                text="Proceed with Uninstall",
                command=proceed_uninstall,
                fg_color="#8b2635",
                hover_color="#6b1c28"
            ).pack(side="right", padx=(5, 0))
            ctk.CTkButton(button_frame, text="Cancel", command=dialog.destroy).pack(side="right")
        
        show_uninstall_confirmation()
    
    def _show_hard_reboot_popup(self) -> None:
        """Show critical hard reboot warning popup after installation."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("CRITICAL: Hard Reboot Required")
        dialog.geometry("550x400")
        dialog.resizable(False, False)
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (550 // 2)
        y = (dialog.winfo_screenheight() // 2) - (400 // 2)
        dialog.geometry(f"550x400+{x}+{y}")
        
        # Make it modal and force it to stay on top
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()
        
        # Configure frame
        content_frame = ctk.CTkFrame(dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Critical warning title with red color
        title_label = ctk.CTkLabel(
            content_frame,
            text="⚠️ CRITICAL: HARD REBOOT REQUIRED ⚠️",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#ff4444"
        )
        title_label.pack(pady=(10, 20))
        
        # Main warning message
        warning_label = ctk.CTkLabel(
            content_frame,
            text="Installation completed successfully!\n\nYou MUST now perform a HARD REBOOT using the power button:",
            font=ctk.CTkFont(size=14, weight="bold"),
            justify="center"
        )
        warning_label.pack(pady=(0, 15))
        
        # Triple-tap launch instructions
        tripletap_frame = ctk.CTkFrame(content_frame)
        tripletap_frame.pack(fill="x", padx=10, pady=(0, 15))
        
        ctk.CTkLabel(
            tripletap_frame,
            text="🚀 LAUNCH XOVI AFTER REBOOT:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#44ff44"
        ).pack(pady=(15, 5))
        
        ctk.CTkLabel(
            tripletap_frame,
            text="Press the POWER BUTTON 3 times rapidly to launch XOVI",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#88ff88"
        ).pack(pady=(0, 3))
        
        ctk.CTkLabel(
            tripletap_frame,
            text="(This may take a few attempts to get the timing right)",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        ).pack(pady=(0, 15))
        
        # Step-by-step instructions frame
        instructions_frame = ctk.CTkFrame(content_frame)
        instructions_frame.pack(fill="x", padx=10, pady=(0, 15))
        
        ctk.CTkLabel(
            instructions_frame,
            text="POWER BUTTON REBOOT STEPS:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ff8844"
        ).pack(pady=(15, 10))
        
        # Step 1
        step1_frame = ctk.CTkFrame(instructions_frame, fg_color="transparent")
        step1_frame.pack(fill="x", padx=15, pady=2)
        
        ctk.CTkLabel(
            step1_frame,
            text="1. PRESS the power button ONCE (short press)",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w")
        
        # Step 2
        step2_frame = ctk.CTkFrame(instructions_frame, fg_color="transparent")
        step2_frame.pack(fill="x", padx=15, pady=2)
        
        ctk.CTkLabel(
            step2_frame,
            text="2. Then PRESS AND HOLD the power button until device shuts off",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w")
        
        # Step 3
        step3_frame = ctk.CTkFrame(instructions_frame, fg_color="transparent")
        step3_frame.pack(fill="x", padx=15, pady=(2, 15))
        
        ctk.CTkLabel(
            step3_frame,
            text="3. Press power button again to turn device back on",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w")
        
        # Critical warning about boot loop
        loop_warning_frame = ctk.CTkFrame(content_frame)
        loop_warning_frame.pack(fill="x", padx=10, pady=(0, 15))
        
        ctk.CTkLabel(
            loop_warning_frame,
            text="⚠️ WARNING: THE LOADER WILL LOOP UNTIL THIS IS DONE! ⚠️",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ff4444"
        ).pack(pady=(15, 5))
        
        ctk.CTkLabel(
            loop_warning_frame,
            text="If you don't perform the hard reboot, your device may appear stuck\nin a boot loop. This is normal - just follow the steps above.",
            font=ctk.CTkFont(size=11),
            justify="center",
            text_color="gray"
        ).pack(pady=(0, 15))
        
        # Confirmation checkbox
        self.reboot_understood = tk.BooleanVar(value=False)
        checkbox_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        checkbox_frame.pack(fill="x", pady=(0, 15))
        
        reboot_checkbox = ctk.CTkCheckBox(
            checkbox_frame,
            text="I understand and will perform the hard reboot now",
            variable=self.reboot_understood,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        reboot_checkbox.pack()
        
        # Button frame
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(fill="x")
        
        def close_dialog():
            if self.reboot_understood.get():
                dialog.destroy()
            else:
                # Flash the checkbox to draw attention
                reboot_checkbox.configure(text_color="#ff4444")
                self.root.after(500, lambda: reboot_checkbox.configure(text_color=("gray10", "gray90")))
        
        def auto_reboot():
            if not self.reboot_understood.get():
                # Flash the checkbox to draw attention
                reboot_checkbox.configure(text_color="#ff4444")
                self.root.after(500, lambda: reboot_checkbox.configure(text_color=("gray10", "gray90")))
                return
            
            # Close dialog and initiate automatic reboot
            dialog.destroy()
            self._perform_automatic_reboot()
        
        # Button container for side-by-side layout
        buttons_container = ctk.CTkFrame(button_frame, fg_color="transparent")
        buttons_container.pack(expand=True)
        
        # Manual reboot button
        manual_button = ctk.CTkButton(
            buttons_container,
            text="✅ I Will Hard Reboot Manually",
            command=close_dialog,
            width=200,
            height=45,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#28a745",
            hover_color="#218838"
        )
        manual_button.pack(side="left", padx=(0, 10))
        
        # Automatic reboot button
        auto_button = ctk.CTkButton(
            buttons_container,
            text="🔄 Automatic Hard Reboot Now",
            command=auto_reboot,
            width=200,
            height=45,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#dc3545",
            hover_color="#c82333"
        )
        auto_button.pack(side="left", padx=(10, 0))
        
        # Log the critical warning
        self.logger.warning("CRITICAL: Hard reboot popup displayed - user MUST perform power button reboot")
    
    def _perform_automatic_reboot(self) -> None:
        """Perform automatic hard reboot of the device."""
        if not self.device or not self.device.is_connected():
            self._update_status("Cannot perform automatic reboot - device not connected")
            self.logger.error("Automatic reboot failed: device not connected")
            return
        
        self.logger.warning("PERFORMING AUTOMATIC HARD REBOOT - Device will shut down immediately")
        self._update_status("Performing automatic hard reboot...")
        
        # Show immediate feedback to user
        reboot_dialog = ctk.CTkToplevel(self.root)
        reboot_dialog.title("Automatic Hard Reboot In Progress")
        reboot_dialog.geometry("450x250")
        reboot_dialog.resizable(False, False)
        
        # Center the dialog
        reboot_dialog.update_idletasks()
        x = (reboot_dialog.winfo_screenwidth() // 2) - (450 // 2)
        y = (reboot_dialog.winfo_screenheight() // 2) - (250 // 2)
        reboot_dialog.geometry(f"450x250+{x}+{y}")
        
        # Make it modal
        reboot_dialog.transient(self.root)
        reboot_dialog.grab_set()
        
        content_frame = ctk.CTkFrame(reboot_dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_label = ctk.CTkLabel(
            content_frame,
            text="🔄 Automatic Hard Reboot In Progress",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#ff8844"
        )
        title_label.pack(pady=(10, 15))
        
        status_label = ctk.CTkLabel(
            content_frame,
            text="Executing hard reboot command...\n\nYour device will shut down immediately.\nPlease wait for it to turn off completely,\nthen press the power button to turn it back on.",
            font=ctk.CTkFont(size=12),
            justify="center"
        )
        status_label.pack(pady=(0, 20))
        
        # Progress bar
        progress_bar = ctk.CTkProgressBar(content_frame, width=300)
        progress_bar.pack(pady=(0, 15))
        progress_bar.set(0.0)
        
        def execute_reboot():
            try:
                from ..services.network_service import get_network_service
                network_service = get_network_service()
                
                # Update progress
                self.root.after(0, lambda: progress_bar.set(0.3))
                self.root.after(0, lambda: status_label.configure(text="Sending reboot command..."))
                
                # Execute the hard reboot command - this will cut the connection immediately
                # Use nohup to ensure command executes even if SSH connection is lost
                reboot_command = """
                    echo 'Initiating automatic hard reboot...'
                    sync
                    nohup bash -c 'sleep 1; echo s > /proc/sysrq-trigger; sleep 1; echo b > /proc/sysrq-trigger' &
                    exit 0
                """
                
                # Execute with very short timeout since connection will be lost
                result = network_service.execute_command(reboot_command, timeout=5)
                
                # Update progress - command sent successfully
                self.root.after(0, lambda: progress_bar.set(1.0))
                self.root.after(0, lambda: status_label.configure(
                    text="Hard reboot command sent successfully!\n\nYour device is shutting down now.\nWait for it to fully shut off,\nthen press power button to restart."
                ))
                
                # Auto-close dialog after 5 seconds
                self.root.after(5000, lambda: reboot_dialog.destroy())
                
                self.logger.info("Automatic hard reboot command executed successfully")
                self.root.after(0, lambda: self._update_status("Automatic hard reboot initiated - device shutting down"))
                
            except Exception as e:
                # This is expected since the connection will be lost during reboot
                if "timeout" in str(e).lower() or "connection" in str(e).lower():
                    # This is normal - the device is rebooting
                    self.root.after(0, lambda: progress_bar.set(1.0))
                    self.root.after(0, lambda: status_label.configure(
                        text="Hard reboot initiated successfully!\n\nConnection lost as expected.\nYour device is shutting down.\nPress power button when it's fully off."
                    ))
                    self.root.after(5000, lambda: reboot_dialog.destroy())
                    self.logger.info("Automatic hard reboot command sent - connection lost as expected")
                    self.root.after(0, lambda: self._update_status("Hard reboot in progress - connection lost"))
                else:
                    # Actual error
                    self.logger.error(f"Automatic reboot failed: {e}")
                    self.root.after(0, lambda: status_label.configure(
                        text=f"Automatic reboot failed: {e}\n\nPlease perform manual hard reboot using power button.",
                        text_color="#ff4444"
                    ))
                    self.root.after(0, lambda: self._update_status(f"Automatic reboot failed: {e}"))
        
        # Start reboot in background thread
        threading.Thread(target=execute_reboot, daemon=True).start()
    
    def _open_help(self) -> None:
        """Open help dialog."""
        help_dialog = ctk.CTkToplevel(self.root)
        help_dialog.title("Help & Documentation")
        help_dialog.geometry("600x500")
        help_dialog.resizable(True, True)
        
        # Center the dialog
        help_dialog.update_idletasks()
        x = (help_dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (help_dialog.winfo_screenheight() // 2) - (500 // 2)
        help_dialog.geometry(f"600x500+{x}+{y}")
        
        # Make it modal
        help_dialog.transient(self.root)
        help_dialog.grab_set()
        
        # Create help content
        content_frame = ctk.CTkFrame(help_dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title_label = ctk.CTkLabel(
            content_frame,
            text="freeMarkable - Help",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(0, 20))
        
        # Help text
        help_text = ctk.CTkTextbox(content_frame, wrap="word")
        help_text.pack(fill="both", expand=True, pady=(0, 20))
        
        help_content = """
XOVI Installation Guide

This application installs the XOVI framework on your reMarkable device, providing:
• Application launcher (AppLoad)
• Enhanced functionality through extensions
• KOReader for advanced PDF/EPUB reading

GETTING STARTED:
1. Connect your reMarkable device via USB or WiFi
2. Find the SSH password in Settings > Help > Copyrights and licenses
3. Click the Connect button in the header
4. Choose your installation type and click the appropriate button

INSTALLATION TYPES:
• Full Install: XOVI + AppLoader + KOReader (recommended)
• Launcher Only: XOVI + AppLoader without KOReader

SAFETY:
• A backup is automatically created before installation
• You can restore from backup if anything goes wrong
• The installation is reversible

TROUBLESHOOTING:
• If connection fails, check the IP address and password
• For USB connection, use IP 10.11.99.1
• For WiFi, check the IP in your device's network settings

SUPPORT:
• Check the logs for detailed error information
• Visit the project GitHub for documentation and issues
• The original bash script functionality is preserved
        """
        
        help_text.insert("1.0", help_content)
        help_text.configure(state="disabled")
        
        # Close button
        ctk.CTkButton(content_frame, text="Close", command=help_dialog.destroy).pack()
        
        self.logger.info("Help dialog opened")
    
    # Helper methods for installation operations
    
    def _validate_installation_prerequisites(self) -> bool:
        """Validate prerequisites for installation."""
        if not self.device or not self.device.is_connected():
            self._update_status("Device not connected")
            return False
        
        if self.is_operation_running:
            self._update_status("Another operation is already running")
            return False
        
        return True
    
    def _installation_complete(self, success: bool, operation_name: str) -> None:
        """Handle installation completion."""
        self.is_operation_running = False
        self._update_operation_buttons(self.device and self.device.is_connected())
        
        if success:
            self._update_status(f"{operation_name} completed successfully")
            self.progress_panel.complete_operation(True, f"{operation_name} completed successfully")
            
            # Show critical hard reboot popup for successful installations
            self._show_hard_reboot_popup()
            
            # Reset app state after successful installation
            self._reset_app_state()
        else:
            self._update_status(f"{operation_name} failed")
            self.progress_panel.complete_operation(False, f"{operation_name} failed")
    
    def _backup_complete(self, success: bool, message: str) -> None:
        """Handle backup operation completion."""
        self.is_operation_running = False
        self._update_operation_buttons(self.device and self.device.is_connected())
        
        if success:
            self._update_status(message)
            self.progress_panel.complete_operation(True, message)
        else:
            self._update_status(f"Backup failed: {message}")
            self.progress_panel.complete_operation(False, f"Backup failed: {message}")
    
    def _execute_uninstall(self):
        """Execute uninstallation without backup - matching Bash script exactly."""
        self.is_operation_running = True
        self._update_operation_buttons(False)
        self._update_status("Uninstalling XOVI...")
        
        def run_uninstall():
            try:
                from ..services.network_service import get_network_service
                network_service = get_network_service()
                
                self.root.after(0, lambda: self.progress_panel.start_operation("Uninstallation"))
                
                # Execute uninstall commands - EXACT copy of Bash script logic
                result = network_service.execute_command("""
                    echo 'Starting complete KOReader/XOVI removal...'
                    
                    # CRITICAL: Do NOT stop XOVI services during uninstall
                    # The original working script never stops XOVI during uninstall
                    # ./stop is ONLY used in the restore script, not during live operations
                    echo 'Skipping XOVI stop to preserve USB ethernet connectivity'
                    
                    # Remove XOVI completely
                    if [[ -d /home/root/xovi ]]; then
                        rm -rf /home/root/xovi 2>/dev/null || true
                        echo 'XOVI directory removed'
                    fi
                    
                    # Remove shims
                    if [[ -d /home/root/shims ]]; then
                        rm -rf /home/root/shims 2>/dev/null || true
                        echo 'Shims directory removed'
                    fi
                    
                    # Remove xovi-tripletap completely
                    systemctl stop xovi-tripletap 2>/dev/null || true
                    systemctl disable xovi-tripletap 2>/dev/null || true
                    rm -f /etc/systemd/system/xovi-tripletap.service 2>/dev/null || true
                    if [[ -d /home/root/xovi-tripletap ]]; then
                        rm -rf /home/root/xovi-tripletap 2>/dev/null || true
                        echo 'xovi-tripletap directory and service removed'
                    fi
                    systemctl daemon-reload 2>/dev/null || true
                    
                    # Remove any leftover files
                    rm -f /home/root/xovi.so 2>/dev/null || true
                    rm -f /home/root/xovi-arm32.so 2>/dev/null || true
                    rm -f /home/root/install-xovi-for-rm 2>/dev/null || true
                    rm -f /home/root/koreader-remarkable.zip 2>/dev/null || true
                    rm -f /home/root/extensions-arm32-*.zip 2>/dev/null || true
                    rm -f /home/root/qt-resource-rebuilder.so 2>/dev/null || true
                    rm -f /home/root/appload.so 2>/dev/null || true
                    rm -f /home/root/qtfb-shim*.so 2>/dev/null || true
                    
                    # Remove any KOReader directories that might exist
                    rm -rf /home/root/koreader 2>/dev/null || true
                    
                    # Restart UI to ensure clean state
                    systemctl restart xochitl
                    
                    echo 'Complete uninstall finished!'
                    echo 'All KOReader and XOVI components have been permanently removed.'
                """, timeout=120)  # Longer timeout for comprehensive uninstall
                
                success = result.success
                
                if success:
                    completion_msg = "Complete uninstall successful! All XOVI components removed."
                else:
                    completion_msg = f"Uninstall failed: {result.stderr}"
                
                self.root.after(0, lambda: self._installation_complete(success, completion_msg))
                
            except Exception as e:
                self.logger.error(f"Uninstall failed: {e}")
                self.root.after(0, lambda: self._installation_complete(False, f"Uninstall failed: {e}"))
        
        threading.Thread(target=run_uninstall, daemon=True).start()
    
    def _show_backup_selection_dialog(self, backups, operation):
        """Show dialog to select a backup for restore/delete operation."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title(f"Select Backup to {operation.title()}")
        dialog.geometry("500x400")
        dialog.resizable(True, True)
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (dialog.winfo_screenheight() // 2) - (400 // 2)
        dialog.geometry(f"500x400+{x}+{y}")
        
        # Make it modal
        dialog.transient(self.root)
        dialog.grab_set()
        
        content_frame = ctk.CTkFrame(dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_label = ctk.CTkLabel(
            content_frame,
            text=f"Select Backup to {operation.title()}",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(0, 15))
        
        # Backup list
        list_frame = ctk.CTkScrollableFrame(content_frame)
        list_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        selected_backup = tk.StringVar()
        
        for backup in backups:
            backup_frame = ctk.CTkFrame(list_frame)
            backup_frame.pack(fill="x", pady=2)
            
            radio = ctk.CTkRadioButton(
                backup_frame,
                text=f"{backup.name} ({backup.size_mb:.1f} MB)" if backup.size_mb else backup.name,
                variable=selected_backup,
                value=backup.name
            )
            radio.pack(anchor="w", padx=10, pady=5)
        
        # Buttons
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(fill="x")
        
        def execute_operation():
            backup_name = selected_backup.get()
            if not backup_name:
                self._update_status("No backup selected")
                return
            
            dialog.destroy()
            
            if operation == "restore":
                self._execute_restore(backup_name)
            elif operation == "delete":
                self._execute_delete_backup(backup_name)
        
        ctk.CTkButton(
            button_frame,
            text=operation.title(),
            command=execute_operation,
            fg_color="#8b2635" if operation == "delete" else None
        ).pack(side="right", padx=(5, 0))
        ctk.CTkButton(button_frame, text="Cancel", command=dialog.destroy).pack(side="right")
    
    def _show_backup_list_dialog(self, backups):
        """Show dialog with list of all backups."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Available Backups")
        dialog.geometry("600x400")
        dialog.resizable(True, True)
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (dialog.winfo_screenheight() // 2) - (400 // 2)
        dialog.geometry(f"600x400+{x}+{y}")
        
        # Make it modal
        dialog.transient(self.root)
        dialog.grab_set()
        
        content_frame = ctk.CTkFrame(dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_label = ctk.CTkLabel(
            content_frame,
            text=f"Available Backups ({len(backups)} found)",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(0, 15))
        
        if not backups:
            no_backups_label = ctk.CTkLabel(
                content_frame,
                text="No backups found on device",
                font=ctk.CTkFont(size=14),
                text_color="gray"
            )
            no_backups_label.pack(expand=True)
        else:
            # Backup list
            list_text = ctk.CTkTextbox(content_frame, wrap="word")
            list_text.pack(fill="both", expand=True, pady=(0, 15))
            
            backup_content = ""
            for backup in backups:
                backup_content += f"Name: {backup.name}\n"
                backup_content += f"Created: {backup.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                backup_content += f"Device: {backup.device_type}\n"
                if backup.size_mb:
                    backup_content += f"Size: {backup.size_mb:.1f} MB\n"
                if backup.components_backed_up:
                    backup_content += f"Components: {', '.join(backup.components_backed_up)}\n"
                backup_content += "-" * 50 + "\n\n"
            
            list_text.insert("1.0", backup_content)
            list_text.configure(state="disabled")
        
        ctk.CTkButton(content_frame, text="Close", command=dialog.destroy).pack()
    
    def _execute_restore(self, backup_name):
        """Execute backup restore operation."""
        self.is_operation_running = True
        self._update_operation_buttons(False)
        self._update_status(f"Restoring from backup: {backup_name}")
        
        def run_restore():
            try:
                from ..services.backup_service import get_backup_service
                backup_service = get_backup_service()
                
                self.root.after(0, lambda: self.progress_panel.start_operation("Backup Restore"))
                
                success = backup_service.restore_from_backup(backup_name)
                
                self.root.after(0, lambda: self._backup_complete(
                    success,
                    f"Restore {'completed' if success else 'failed'}: {backup_name}"
                ))
                
            except Exception as e:
                self.logger.error(f"Restore failed: {e}")
                self.root.after(0, lambda: self._backup_complete(False, f"Restore failed: {e}"))
        
        threading.Thread(target=run_restore, daemon=True).start()
    
    def _execute_delete_backup(self, backup_name):
        """Execute backup deletion."""
        def run_delete():
            try:
                from ..services.backup_service import get_backup_service
                backup_service = get_backup_service()
                
                success = backup_service.delete_backup(backup_name)
                
                if success:
                    self.root.after(0, lambda: self._update_status(f"Backup deleted: {backup_name}"))
                else:
                    self.root.after(0, lambda: self._update_status(f"Failed to delete backup: {backup_name}"))
                
            except Exception as e:
                self.logger.error(f"Delete backup failed: {e}")
                self.root.after(0, lambda: self._update_status(f"Delete failed: {e}"))
        
        threading.Thread(target=run_delete, daemon=True).start()
        self._update_status(f"Deleting backup: {backup_name}")
    
    def _prune_backups(self, **kwargs) -> None:
        """Prune old backups, keeping only the most recent 3."""
        if not self.device or not self.device.is_connected():
            self._update_status("Device not connected for backup pruning")
            return
        
        # Show confirmation dialog first
        def show_prune_confirmation():
            dialog = ctk.CTkToplevel(self.root)
            dialog.title("Confirm Backup Pruning")
            dialog.geometry("450x300")
            dialog.resizable(False, False)
            
            # Center the dialog
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (450 // 2)
            y = (dialog.winfo_screenheight() // 2) - (300 // 2)
            dialog.geometry(f"450x300+{x}+{y}")
            
            # Make it modal
            dialog.transient(self.root)
            dialog.grab_set()
            
            content_frame = ctk.CTkFrame(dialog)
            content_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            title_label = ctk.CTkLabel(
                content_frame,
                text="Prune Old Backups",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="orange"
            )
            title_label.pack(pady=(0, 15))
            
            warning_text = ctk.CTkLabel(
                content_frame,
                text="This will automatically delete old backup files,\nkeeping only the 3 most recent backups.\n\nThis action will:\n• Free up storage space on your device\n• Remove older backups permanently\n• Keep the 3 newest backups safe\n\nDeleted backups cannot be recovered.",
                font=ctk.CTkFont(size=12),
                justify="center"
            )
            warning_text.pack(pady=(0, 20))
            
            button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
            button_frame.pack(fill="x")
            
            def proceed_prune():
                dialog.destroy()
                self._execute_prune_backups()
            
            ctk.CTkButton(
                button_frame,
                text="Prune Backups",
                command=proceed_prune,
                fg_color="orange",
                hover_color="#cc8800"
            ).pack(side="right", padx=(5, 0))
            ctk.CTkButton(button_frame, text="Cancel", command=dialog.destroy).pack(side="right")
        
        show_prune_confirmation()
    
    def _execute_prune_backups(self):
        """Execute backup pruning operation."""
        self.logger.info("Starting backup pruning...")
        self._update_status("Pruning old backups...")
        
        def run_prune():
            try:
                from ..services.backup_service import get_backup_service
                backup_service = get_backup_service()
                
                # Call the prune_backups method from the service
                deleted_count, kept_count = backup_service.prune_backups()
                
                success_msg = f"Pruning completed: {deleted_count} old backups deleted, {kept_count} backups kept"
                self.root.after(0, lambda: self._update_status(success_msg))
                self.root.after(0, lambda: self.logger.info(success_msg))
                
            except Exception as e:
                error_msg = str(e)  # Capture the error message
                self.logger.error(f"Backup pruning failed: {error_msg}")
                self.root.after(0, lambda msg=error_msg: self._update_status(f"Backup pruning failed: {msg}"))
        
        threading.Thread(target=run_prune, daemon=True).start()

    # Auto-connect wrapper methods for seamless UX
    
    def _install_full_with_connect(self, enable_tripletap: bool = False, custom_package_path: str = None) -> None:
        """Install full with auto-connect."""
        if self._ensure_connected():
            self._install_full(enable_tripletap=enable_tripletap, custom_package_path=custom_package_path)
    
    def _install_launcher_with_connect(self, enable_tripletap: bool = False) -> None:
        """Install launcher with auto-connect."""
        if self._ensure_connected():
            self._install_launcher(enable_tripletap=enable_tripletap)
    
    def _create_backup_with_connect(self) -> None:
        """Create backup with auto-connect."""
        if self._ensure_connected():
            self._create_backup()
    
    def _uninstall_with_connect(self) -> None:
        """Uninstall with auto-connect."""
        if self._ensure_connected():
            self._uninstall()
    
    def _fix_ethernet_with_connect(self) -> None:
        """Fix USB ethernet with auto-connect."""
        if self._ensure_connected():
            self._fix_ethernet()
    
    def _fix_ethernet(self) -> None:
        """Fix USB ethernet adapter connectivity."""
        if not self.device or not self.device.is_connected():
            self._update_status("Device not connected for ethernet fix")
            return
        
        self.logger.info("Installing USB ethernet fix...")
        self._update_status("Fixing USB ethernet adapter...")
        
        def run_ethernet_fix():
            try:
                from ..services.network_service import get_network_service
                network_service = get_network_service()
                
                success = network_service.install_ethernet_fix()
                
                if success:
                    self.root.after(0, lambda: self._update_status("USB ethernet fix completed successfully"))
                    self.root.after(0, lambda: self.logger.info("USB ethernet adapter should now be working at 10.11.99.1"))
                else:
                    self.root.after(0, lambda: self._update_status("USB ethernet fix failed"))
                    
            except Exception as e:
                self.logger.error(f"Ethernet fix failed: {e}")
                self.root.after(0, lambda: self._update_status(f"Ethernet fix failed: {e}"))
        
    
    def _reset_app_state(self) -> None:
        """Reset all application state after install/uninstall operations."""
        self.logger.info("Resetting application state...")
        
        try:
            # Clear installation state files
            from ..models.installation_state import InstallationState
            stage_file = self.config.get_stage_file_path()
            if stage_file.exists():
                stage_file.unlink()
                self.logger.info("Cleared saved installation state")
            
            # Reset installation state object
            self.installation_state = None
            
            # Disconnect device to force fresh connection state
            if self.device:
                self.device.connection_status = ConnectionStatus.DISCONNECTED
                self._update_connection_status(ConnectionStatus.DISCONNECTED)
                self.connect_button.configure(text="Connect", state="normal")
            
            # Reset progress panel
            if self.progress_panel:
                self.progress_panel.reset_progress()
            
            # Clear some log entries to prevent overwhelming logs
            if self.log_panel:
                # Keep last 50 entries, clear the rest
                self.log_panel.clear_old_entries(keep_count=50)
            
            # Update device display to reflect reset state
            self._update_device_display()
            
            # Update button states
            self._update_operation_buttons(False)  # Disable until reconnected
            
            # Clear any cached service data by reinitializing services
            try:
                from ..services.network_service import get_network_service
                network_service = get_network_service()
                if hasattr(network_service, 'clear_cache'):
                    network_service.clear_cache()
            except:
                pass  # Service may not exist or have clear_cache method
            
            # Update status
            self._update_status("App state reset - ready for new operations")
            self.logger.info("Application state reset completed successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to reset app state: {e}")
            self._update_status("App state reset encountered errors")
    
    def _initialize_codexctl_service(self) -> None:
        """Get existing CodexCtl service (don't create a new one)."""
        try:
            from ..services.codexctl_service import get_codexctl_service
            
            # Just get the existing service initialized by main.py
            # Don't create a new one to avoid duplicate downloads
            codexctl_service = get_codexctl_service()
            
            self.logger.info("CodexCtl service connected")
            
            # Note: Panel connection will be done later in _setup_codexctl_tab()
            # when the panel is actually created
                
        except RuntimeError:
            # Service not initialized yet by main app
            self.logger.debug("CodexCtl service not yet initialized by main app")
        except Exception as e:
            self.logger.error(f"Failed to connect to CodexCtl service: {e}")
    
    def _on_codexctl_progress(self, progress) -> None:
        """Handle CodexCtl progress updates."""
        # Forward progress to main progress panel if desired
        if self.progress_panel and hasattr(progress, 'progress_percentage'):
            self.progress_panel.update_overall_progress(
                progress.progress_percentage,
                f"CodexCtl: {progress.message}"
            )
    
    def _on_codexctl_status(self, status: str) -> None:
        """Handle CodexCtl status updates."""
        # Update main status bar
        self._update_status(f"CodexCtl: {status}")
    
    def toggle_codexctl_panel(self, enabled: bool = None) -> None:
        """Enable or disable the CodexCtl panel."""
        if not self.codexctl_panel:
            return
        
        if enabled is None:
            # Toggle current state
            enabled = self.codexctl_panel.is_disabled()
        
        self.codexctl_panel.set_disabled(not enabled)
        
        # Connect to service if enabling
        if enabled and not self.codexctl_panel.is_disabled():
            try:
                from ..services.codexctl_service import get_codexctl_service
                codexctl_service = get_codexctl_service()
                self.codexctl_panel.set_codexctl_service(codexctl_service)
                self.logger.info("CodexCtl panel connected to service")
            except Exception as e:
                self.logger.error(f"Failed to connect CodexCtl panel to service: {e}")
        
        status = "enabled" if enabled else "disabled"
        self.logger.info(f"CodexCtl panel {status}")
    
    def _fix_ethernet(self) -> None:
        """Fix USB ethernet adapter connectivity."""
        if not self.device or not self.device.is_connected():
            self._update_status("Device not connected for ethernet fix")
            return
        
        self.logger.info("Installing USB ethernet fix...")
        self._update_status("Fixing USB ethernet adapter...")
        
        def run_ethernet_fix():
            try:
                from ..services.network_service import get_network_service
                network_service = get_network_service()
                
                success = network_service.install_ethernet_fix()
                
                if success:
                    self.root.after(0, lambda: self._update_status("USB ethernet fix completed successfully"))
                    self.root.after(0, lambda: self.logger.info("USB ethernet adapter should now be working at 10.11.99.1"))
                else:
                    self.root.after(0, lambda: self._update_status("USB ethernet fix failed"))
                    
            except Exception as e:
                self.logger.error(f"Ethernet fix failed: {e}")
                self.root.after(0, lambda: self._update_status(f"Ethernet fix failed: {e}"))
        
        threading.Thread(target=run_ethernet_fix, daemon=True).start()
    
    def _ensure_connected(self) -> bool:
        """Ensure device is connected before proceeding with operations."""
        # Check if device is already connected
        if self.device and self.device.is_connected():
            return True
        
        # Check if device is configured
        if not self.device or not self.device.is_configured():
            self._update_status("Device not configured. Please set up connection first.")
            self._open_connection_settings()
            return False
        
        # Try to connect synchronously
        self._update_status("Connecting to device...")
        try:
            success = self.device.test_connection()
            if success:
                self.device.detect_device_type()  # Auto-detect device type
                self._update_connection_status(self.device.connection_status)
                self._update_device_display()
                self._update_status("Connected to device successfully")
                return True
            else:
                self._update_status("Failed to connect to device. Please check connection settings.")
                return False
        except Exception as e:
            self._update_status(f"Connection failed: {e}")
            return False
    
    def _setup_custom_packages_tab(self) -> None:
        """Setup custom packages management tab."""
        packages_tab = self.tabview.tab("Custom Packages")
        packages_tab.grid_columnconfigure(0, weight=1)
        packages_tab.grid_rowconfigure(0, weight=1)
        
        # Main scrollable frame
        main_frame = ctk.CTkScrollableFrame(packages_tab, label_text="Custom Package Management")
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Information section
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            info_frame,
            text="📦 Custom Application Manager (Work in Progress)",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(pady=(15, 5))
        
        ctk.CTkLabel(
            info_frame,
            text="Install custom applications into your existing XOVI/AppLoad system",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(pady=(0, 15))
        
        # Prerequisites check
        prereq_frame = ctk.CTkFrame(main_frame)
        prereq_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            prereq_frame,
            text="⚠️ Prerequisites",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="orange"
        ).pack(anchor="w", padx=15, pady=(15, 5))
        
        prereq_text = "• XOVI and AppLoad must already be installed on your device\n• Device must be connected via USB or WiFi\n• Custom packages must be valid ZIP files containing applications"
        
        ctk.CTkLabel(
            prereq_frame,
            text=prereq_text,
            font=ctk.CTkFont(size=11),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 15))
        
        # Built-in packages section
        builtin_frame = ctk.CTkFrame(main_frame)
        builtin_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            builtin_frame,
            text="📚 Pre-Built Packages",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        ctk.CTkLabel(
            builtin_frame,
            text="Popular applications ready to install",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        ).pack(anchor="w", padx=15, pady=(0, 10))
        
        # Built-in package buttons
        builtin_buttons_frame = ctk.CTkFrame(builtin_frame, fg_color="transparent")
        builtin_buttons_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        # KOReader button
        self.install_koreader_button = ctk.CTkButton(
            builtin_buttons_frame,
            text="📖 Install KOReader\n(Latest Version)",
            command=self._install_builtin_koreader,
            width=180,
            height=50,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#2E8B57",
            hover_color="#238B45"
        )
        self.install_koreader_button.pack(side="left", padx=(0, 10))
        
        # literm button
        self.install_literm_button = ctk.CTkButton(
            builtin_buttons_frame,
            text="💻 Install rm-literm\n(Terminal Emulator)",
            command=self._install_builtin_literm,
            width=180,
            height=50,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#4169E1",
            hover_color="#3654D1"
        )
        self.install_literm_button.pack(side="left", padx=5)
        
        # Built-in packages info
        builtin_info_frame = ctk.CTkFrame(builtin_frame)
        builtin_info_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkLabel(
            builtin_info_frame,
            text="ℹ️ About Pre-Built Packages",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="blue"
        ).pack(anchor="w", padx=15, pady=(10, 5))
        
        builtin_info_text = "• KOReader: Advanced PDF/EPUB reader with extensive features\n• rm-literm: Terminal emulator specifically built for reMarkable devices\n• These packages are tested and optimized for your device"
        
        ctk.CTkLabel(
            builtin_info_frame,
            text=builtin_info_text,
            font=ctk.CTkFont(size=10),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 10))
        
        # Package installation section
        install_frame = ctk.CTkFrame(main_frame)
        install_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            install_frame,
            text="📥 Install Custom Package",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # File selection
        file_selection_frame = ctk.CTkFrame(install_frame, fg_color="transparent")
        file_selection_frame.pack(fill="x", padx=15, pady=5)
        
        self.custom_app_path = tk.StringVar(value="No package selected")
        self.custom_app_label = ctk.CTkLabel(
            file_selection_frame,
            textvariable=self.custom_app_path,
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.custom_app_label.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ctk.CTkButton(
            file_selection_frame,
            text="Browse Package...",
            command=self._browse_custom_package,
            width=130,
            height=30,
            state="disabled",
            fg_color="gray",
            hover_color="gray"
        ).pack(side="right")
        
        # Install button
        install_button_frame = ctk.CTkFrame(install_frame, fg_color="transparent")
        install_button_frame.pack(fill="x", padx=15, pady=(10, 15))
        
        self.install_package_button = ctk.CTkButton(
            install_button_frame,
            text="🚀 Install Package",
            command=self._install_custom_package,
            width=200,
            height=40,
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
            fg_color="gray",
            hover_color="gray"
        )
        self.install_package_button.pack(side="left", padx=(0, 10))
        
        # Package requirements help
        ctk.CTkButton(
            install_button_frame,
            text="📖 Package Requirements",
            command=self._show_custom_package_help,
            width=170,
            height=40,
            font=ctk.CTkFont(size=11),
            fg_color="gray",
            hover_color="#606060",
            state="disabled"
        ).pack(side="left")
        
        # Package management section
        manage_frame = ctk.CTkFrame(main_frame)
        manage_frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(
            manage_frame,
            text="🗂️ Package Management",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Management buttons
        manage_buttons_frame = ctk.CTkFrame(manage_frame, fg_color="transparent")
        manage_buttons_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkButton(
            manage_buttons_frame,
            text="📋 List Installed Apps",
            command=self._list_installed_packages,
            width=160,
            height=35,
            state="disabled",
            fg_color="gray",
            hover_color="gray"
        ).pack(side="left", padx=(0, 10))
        
        ctk.CTkButton(
            manage_buttons_frame,
            text="🗑️ Remove Package",
            command=self._remove_custom_package,
            width=150,
            height=35,
            fg_color="gray",
            hover_color="gray",
            state="disabled"
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            manage_buttons_frame,
            text="🔄 Restart AppLoad",
            command=self._restart_appload,
            width=140,
            height=35,
            fg_color="gray",
            hover_color="gray",
            state="disabled"
        ).pack(side="left", padx=5)
    
    def _browse_custom_package(self) -> None:
        """Browse for custom package file."""
        from tkinter import filedialog
        
        # File dialog for ZIP files
        file_path = filedialog.askopenfilename(
            title="Select Custom Package",
            filetypes=[
                ("ZIP files", "*.zip"),
                ("All files", "*.*")
            ],
            initialdir=str(Path.home())
        )
        
        if file_path:
            self.custom_app_path.set(file_path)
            self._update_status(f"Selected package: {Path(file_path).name}")
        else:
            self.custom_app_path.set("No package selected")
    
    def _install_custom_package(self) -> None:
        """Install the selected custom package."""
        if not self._ensure_connected():
            return
        
        package_path = self.custom_app_path.get()
        if package_path == "No package selected" or not package_path:
            self._update_status("Please select a package file first")
            return
        
        if not Path(package_path).exists():
            self._update_status("Selected package file does not exist")
            return
        
        # Validate package format
        if not self._validate_custom_package(package_path):
            return
        
        self._update_status("Installing custom package...")
        self.is_operation_running = True
        self._update_operation_buttons(False)
        
        def run_package_install():
            try:
                success = self._execute_custom_package_install(package_path)
                
                if success:
                    self.root.after(0, lambda: self._package_install_complete(True, f"Package installed successfully"))
                else:
                    self.root.after(0, lambda: self._package_install_complete(False, "Package installation failed"))
                    
            except Exception as e:
                self.logger.error(f"Package installation failed: {e}")
                self.root.after(0, lambda: self._package_install_complete(False, f"Installation failed: {e}"))
        
        threading.Thread(target=run_package_install, daemon=True).start()
    
    def _validate_custom_package(self, package_path: str) -> bool:
        """Validate custom package format and contents."""
        try:
            import zipfile
            
            if not package_path.lower().endswith('.zip'):
                self._update_status("Package must be a ZIP file")
                return False
            
            # Check if it's a valid ZIP file
            try:
                with zipfile.ZipFile(package_path, 'r') as zip_ref:
                    file_list = zip_ref.namelist()
            except zipfile.BadZipFile:
                self._update_status("Invalid ZIP file format")
                return False
            
            # Basic validation - should contain some files
            if not file_list:
                self._update_status("Package is empty")
                return False
            
            self.logger.info(f"Package validation passed: {len(file_list)} files found")
            return True
            
        except Exception as e:
            self._update_status(f"Package validation failed: {e}")
            return False
    
    def _execute_custom_package_install(self, package_path: str) -> bool:
        """Execute the custom package installation."""
        try:
            package_name = Path(package_path).stem
            self._update_status(f"Installing package: {package_name}")
            
            # Get network service
            from ..services.network_service import get_network_service
            network_service = get_network_service()
            
            # Upload package to device
            remote_path = f'/home/root/{Path(package_path).name}'
            if not network_service.upload_file(Path(package_path), remote_path):
                self._update_status("Failed to upload package to device")
                return False
            
            # Install package following AppLoad pattern
            result = network_service.execute_command(f"""
                cd /home/root
                
                # Check if AppLoad directory exists
                if [ ! -d "/home/root/xovi/exthome/appload" ]; then
                    echo "ERROR: AppLoad directory not found. Please install XOVI first."
                    exit 1
                fi
                
                # Extract package to temporary directory
                TEMP_DIR="/tmp/custom_package_$$"
                mkdir -p "$TEMP_DIR"
                
                # Extract the package
                unzip -q "{Path(package_path).name}" -d "$TEMP_DIR"
                
                # Find the main directory in the package
                cd "$TEMP_DIR"
                
                # Look for a single directory or install directly
                if [ $(ls -1 | wc -l) -eq 1 ] && [ -d "$(ls -1)" ]; then
                    # Single directory - move its contents
                    APP_SOURCE="$(ls -1)"
                    APP_NAME="$APP_SOURCE"
                else
                    # Multiple files/dirs - create wrapper directory
                    APP_NAME="{package_name}"
                    mkdir -p "$APP_NAME"
                    mv * "$APP_NAME/" 2>/dev/null || true
                    APP_SOURCE="$APP_NAME"
                fi
                
                # Install to AppLoad directory
                TARGET_DIR="/home/root/xovi/exthome/appload/$APP_NAME"
                
                # Remove existing installation if present
                rm -rf "$TARGET_DIR" 2>/dev/null || true
                
                # Move to final location
                mv "$APP_SOURCE" "/home/root/xovi/exthome/appload/"
                
                # Set permissions
                chmod -R 755 "$TARGET_DIR"
                
                # Cleanup
                cd /home/root
                rm -rf "$TEMP_DIR"
                rm -f "{Path(package_path).name}"
                
                echo "Package '$APP_NAME' installed successfully to AppLoad"
                echo "Installed to: $TARGET_DIR"
                
                # List contents
                echo "Package contents:"
                ls -la "$TARGET_DIR"
            """)
            
            if not result.success:
                self._update_status(f"Package installation failed: {result.stderr}")
                return False
            
            self._update_status(f"Package '{package_name}' installed successfully")
            self.logger.info(f"Custom package installation completed: {package_name}")
            return True
            
        except Exception as e:
            self._update_status(f"Package installation error: {e}")
            return False
    
    def _package_install_complete(self, success: bool, message: str) -> None:
        """Handle package installation completion."""
        self.is_operation_running = False
        self._update_operation_buttons(self.device and self.device.is_connected())
        
        if success:
            self._update_status(message)
            # Clear the selected package
            self.custom_app_path.set("No package selected")
        else:
            self._update_status(f"Installation failed: {message}")
    
    def _show_custom_package_help(self) -> None:
        """Show comprehensive help about package requirements."""
        help_dialog = ctk.CTkToplevel(self.root)
        help_dialog.title("Custom Package Requirements")
        help_dialog.geometry("700x600")
        help_dialog.resizable(True, True)
        
        # Center the dialog
        help_dialog.update_idletasks()
        x = (help_dialog.winfo_screenwidth() // 2) - (700 // 2)
        y = (help_dialog.winfo_screenheight() // 2) - (600 // 2)
        help_dialog.geometry(f"700x600+{x}+{y}")
        
        # Make it modal
        help_dialog.transient(self.root)
        help_dialog.grab_set()
        
        # Create help content
        content_frame = ctk.CTkFrame(help_dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Title
        title_label = ctk.CTkLabel(
            content_frame,
            text="📖 Custom Package Requirements Guide",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(0, 20))
        
        # Help content in scrollable text box
        help_text = ctk.CTkTextbox(content_frame, wrap="word")
        help_text.pack(fill="both", expand=True, pady=(0, 20))
        
        help_content = """
CUSTOM PACKAGE REQUIREMENTS

This feature allows you to install custom applications into your existing XOVI/AppLoad system.

📋 PREREQUISITES:
• XOVI and AppLoad must already be installed on your device
• Device must be connected via USB or WiFi
• You must have completed a Full Install or Launcher Install first

📦 PACKAGE FORMAT:
• Must be a ZIP file (.zip extension)
• Can contain a single application directory or multiple files
• No specific internal structure required - the installer will adapt

🏗️ HOW IT WORKS:
1. Your ZIP file is uploaded to the device
2. Contents are extracted to /home/root/xovi/exthome/appload/
3. Permissions are set automatically
4. The app becomes available in AppLoad launcher

📁 PACKAGE STRUCTURE EXAMPLES:

Example 1 - Simple Application:
my-app.zip
└── my-app/
   ├── main.py
   ├── config.json
   └── assets/
       └── icon.png

Example 2 - Complex Application (like KOReader):
complex-app.zip
└── complex-app/
   ├── main.lua
   ├── defaults.lua
   ├── frontend/
   │   └── ui/
   ├── plugins/
   │   └── myplugin.koplugin/
   │       ├── _meta.lua
   │       └── main.lua
   ├── fonts/
   ├── l10n/
   └── resources/

Example 3 - Multiple Files (will be wrapped):
my-tool.zip
├── run.sh
├── README.txt
└── data.json

🎯 APPLOAD INTEGRATION:
• Apps are installed to: /home/root/xovi/exthome/appload/[app-name]/
• AppLoad will detect and list your custom applications
• Use "Restart AppLoad" button to refresh the launcher
• Apps can be launched through the AppLoad interface

⚠️ IMPORTANT NOTES:
• Ensure your app is compatible with reMarkable hardware
• Test apps thoroughly before distribution
• Custom apps should follow reMarkable development guidelines
• This feature is for post-installation app management only

🔧 TROUBLESHOOTING:
• If app doesn't appear: Try "Restart AppLoad" button
• Check "List Installed Apps" to verify installation
• Use "Remove Package" to uninstall if needed
• Ensure XOVI/AppLoad is properly installed first

📚 APPLOAD MANIFEST SYSTEM - CRITICAL:
AppLoad applications require a specific structure with these ESSENTIAL files:

1. EXTERNAL MANIFEST (Required):
   external.manifest.json - Tells AppLoad how to launch your app
   Example structure:
   {
     "name": "Your App Name",
     "application": "launcher.sh",
     "environment": {
       "VARIABLE": "value"
     },
     "qtfb": true
   }

2. LAUNCHER SCRIPT (Required):
   A shell script (.sh) that starts your application
   Must be executable and handle environment setup

REAL KOREADER EXAMPLE:
• Manifest: external.manifest.json
  - name: "KOReader"
  - application: "koreader.sh"
  - environment: LD_PRELOAD, KO_DONT_GRAB_INPUT
  - qtfb: true flag for Qt framebuffer apps

• Launcher: koreader.sh
  - Sets working directory
  - Handles reMarkable 2 RM2FB requirements
  - Exports environment variables
  - Executes the actual application

CRITICAL REQUIREMENTS:
• external.manifest.json must be in app root directory
• Launcher script must be executable (chmod +x)
• Environment variables properly configured
• For Qt apps: qtfb=true and proper shim setup

For technical support and examples, visit the freeMarkable GitHub repository.
        """
        
        help_text.insert("1.0", help_content)
        help_text.configure(state="disabled")
        
        # Close button
        ctk.CTkButton(content_frame, text="Close", command=help_dialog.destroy).pack()
        
        self.logger.info("Custom package help dialog opened")
    
    def _list_installed_packages(self) -> None:
        """List all installed applications in AppLoad."""
        if not self._ensure_connected():
            return
        
        self._update_status("Listing installed applications...")
        
        def list_packages():
            try:
                from ..services.network_service import get_network_service
                network_service = get_network_service()
                result = network_service.execute_command("""
                    if [ ! -d "/home/root/xovi/exthome/appload" ]; then
                        echo "ERROR: AppLoad directory not found. Please install XOVI first."
                        exit 1
                    fi
                    
                    cd /home/root/xovi/exthome/appload
                    
                    echo "=== INSTALLED APPLICATIONS ==="
                    echo ""
                    
                    if [ -z "$(ls -A 2>/dev/null)" ]; then
                        echo "No applications found in AppLoad directory"
                        exit 0
                    fi
                    
                    for app_dir in */; do
                        if [ -d "$app_dir" ]; then
                            app_name="${app_dir%/}"
                            echo "📱 $app_name"
                            echo "   Path: /home/root/xovi/exthome/appload/$app_name"
                            
                            # Get size
                            size=$(du -sh "$app_dir" 2>/dev/null | cut -f1)
                            echo "   Size: $size"
                            
                            # Count files
                            file_count=$(find "$app_dir" -type f 2>/dev/null | wc -l)
                            echo "   Files: $file_count"
                            
                            # Check for common executable files
                            if [ -f "$app_dir/main.py" ]; then
                                echo "   Type: Python Application"
                            elif [ -f "$app_dir/run.sh" ] || [ -f "$app_dir/start.sh" ]; then
                                echo "   Type: Shell Script Application"
                            elif find "$app_dir" -name "*.so" -o -name "*.bin" | head -1 | grep -q .; then
                                echo "   Type: Native Binary Application"
                            else
                                echo "   Type: Unknown"
                            fi
                            
                            echo ""
                        fi
                    done
                    
                    echo "=== APPLOAD STATUS ==="
                    if pgrep -f "appload" > /dev/null; then
                        echo "AppLoad: Running"
                    else
                        echo "AppLoad: Not detected (may be integrated with XOVI)"
                    fi
                """)
                
                if result.success:
                    self.root.after(0, lambda: self._show_package_list_dialog(result.stdout))
                else:
                    self.root.after(0, lambda: self._update_status(f"Failed to list packages: {result.stderr}"))
                    
            except Exception as e:
                self.logger.error(f"Package listing failed: {e}")
                self.root.after(0, lambda: self._update_status(f"Package listing failed: {e}"))
        
        threading.Thread(target=list_packages, daemon=True).start()
    
    def _show_package_list_dialog(self, package_info: str) -> None:
        """Show dialog with installed package information."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Installed Applications")
        dialog.geometry("600x500")
        dialog.resizable(True, True)
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (dialog.winfo_screenheight() // 2) - (500 // 2)
        dialog.geometry(f"600x500+{x}+{y}")
        
        # Make it modal
        dialog.transient(self.root)
        dialog.grab_set()
        
        content_frame = ctk.CTkFrame(dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_label = ctk.CTkLabel(
            content_frame,
            text="📋 Installed Applications",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(0, 15))
        
        # Package list
        list_text = ctk.CTkTextbox(content_frame, wrap="word")
        list_text.pack(fill="both", expand=True, pady=(0, 15))
        
        list_text.insert("1.0", package_info)
        list_text.configure(state="disabled")
        
        ctk.CTkButton(content_frame, text="Close", command=dialog.destroy).pack()
    
    def _remove_custom_package(self) -> None:
        """Remove a custom package from AppLoad."""
        if not self._ensure_connected():
            return
        
        # First get list of installed packages for selection
        def get_packages_for_removal():
            try:
                result = self.network_service.execute_command("""
                    if [ ! -d "/home/root/xovi/exthome/appload" ]; then
                        echo "ERROR: AppLoad directory not found"
                        exit 1
                    fi
                    
                    cd /home/root/xovi/exthome/appload
                    for app_dir in */; do
                        if [ -d "$app_dir" ]; then
                            echo "${app_dir%/}"
                        fi
                    done
                """)
                
                if result.success:
                    packages = [pkg.strip() for pkg in result.stdout.strip().split('\n') if pkg.strip()]
                    if packages:
                        self.root.after(0, lambda: self._show_package_removal_dialog(packages))
                    else:
                        self.root.after(0, lambda: self._update_status("No packages found to remove"))
                else:
                    self.root.after(0, lambda: self._update_status(f"Failed to list packages: {result.stderr}"))
                    
            except Exception as e:
                self.logger.error(f"Package listing for removal failed: {e}")
                self.root.after(0, lambda: self._update_status(f"Failed to get package list: {e}"))
        
        threading.Thread(target=get_packages_for_removal, daemon=True).start()
        self._update_status("Getting package list...")
    
    def _show_package_removal_dialog(self, packages: list) -> None:
        """Show dialog to select package for removal."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Remove Package")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (300 // 2)
        dialog.geometry(f"400x300+{x}+{y}")
        
        # Make it modal
        dialog.transient(self.root)
        dialog.grab_set()
        
        content_frame = ctk.CTkFrame(dialog)
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        title_label = ctk.CTkLabel(
            content_frame,
            text="🗑️ Remove Package",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="red"
        )
        title_label.pack(pady=(0, 15))
        
        ctk.CTkLabel(
            content_frame,
            text="Select a package to remove:",
            font=ctk.CTkFont(size=12)
        ).pack(pady=(0, 10))
        
        # Package selection
        selected_package = tk.StringVar()
        
        for package in packages:
            radio = ctk.CTkRadioButton(
                content_frame,
                text=package,
                variable=selected_package,
                value=package
            )
            radio.pack(anchor="w", padx=20, pady=2)
        
        # Warning
        warning_label = ctk.CTkLabel(
            content_frame,
            text="⚠️ This action cannot be undone!",
            font=ctk.CTkFont(size=11),
            text_color="orange"
        )
        warning_label.pack(pady=(15, 10))
        
        # Buttons
        button_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))
        
        def execute_removal():
            package_name = selected_package.get()
            if not package_name:
                self._update_status("No package selected")
                return
            
            dialog.destroy()
            self._execute_package_removal(package_name)
        
        ctk.CTkButton(
            button_frame,
            text="Remove",
            command=execute_removal,
            fg_color="#8b2635",
            hover_color="#6b1c28"
        ).pack(side="right", padx=(5, 0))
        
        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=dialog.destroy
        ).pack(side="right")
    
    def _execute_package_removal(self, package_name: str) -> None:
        """Execute package removal."""
        self._update_status(f"Removing package: {package_name}")
        
        def remove_package():
            try:
                from ..services.network_service import get_network_service
                network_service = get_network_service()
                result = network_service.execute_command(f"""
                    cd /home/root/xovi/exthome/appload
                    
                    if [ ! -d "{package_name}" ]; then
                        echo "Package '{package_name}' not found"
                        exit 1
                    fi
                    
                    # Remove the package directory
                    rm -rf "{package_name}"
                    
                    echo "Package '{package_name}' removed successfully"
                """)
                
                if result.success:
                    self.root.after(0, lambda: self._update_status(f"Package '{package_name}' removed successfully"))
                else:
                    self.root.after(0, lambda: self._update_status(f"Failed to remove package: {result.stderr}"))
                    
            except Exception as e:
                self.logger.error(f"Package removal failed: {e}")
                self.root.after(0, lambda: self._update_status(f"Package removal failed: {e}"))
        
        threading.Thread(target=remove_package, daemon=True).start()
    
    def _restart_appload(self) -> None:
        """Restart AppLoad system to refresh application list."""
        if not self._ensure_connected():
            return
        
        self._update_status("Restarting AppLoad system...")
        
        def restart_appload():
            try:
                from ..services.network_service import get_network_service
                network_service = get_network_service()
                result = network_service.execute_command("""
                    echo "Restarting AppLoad system..."
                    
                    # Method 1: Try restarting xochitl service (which includes XOVI/AppLoad)
                    systemctl restart xochitl
                    
                    # Wait a moment for restart
                    sleep 3
                    
                    # Check if xochitl is running
                    if systemctl is-active xochitl >/dev/null 2>&1; then
                        echo "AppLoad system restarted successfully"
                        echo "Applications should now be refreshed in the launcher"
                    else
                        echo "Warning: xochitl service may not have restarted properly"
                        echo "You may need to restart your device manually"
                    fi
                """)
                
                if result.success:
                    self.root.after(0, lambda: self._update_status("AppLoad system restarted - applications refreshed"))
                else:
                    self.root.after(0, lambda: self._update_status(f"AppLoad restart failed: {result.stderr}"))
                    
            except Exception as e:
                self.logger.error(f"AppLoad restart failed: {e}")
                self.root.after(0, lambda: self._update_status(f"AppLoad restart failed: {e}"))
        
        threading.Thread(target=restart_appload, daemon=True).start()
    
    def _install_builtin_koreader(self) -> None:
        """Install KOReader using the built-in package system."""
        if not self._ensure_connected():
            return
        
        self._update_status("Installing KOReader...")
        self.is_operation_running = True
        self._update_operation_buttons(False)
        
        def run_koreader_install():
            try:
                from ..services.installation_service import get_installation_service
                installation_service = get_installation_service()
                
                # Set up progress callbacks
                def progress_callback(progress):
                    percentage = progress.progress_percentage
                    message = progress.message
                    stage = progress.stage
                    current_step = progress.current_step
                    
                    self.root.after(0, lambda p=percentage, m=message:
                        self.progress_panel.update_overall_progress(p, m))
                    self.root.after(0, lambda s=stage, p=percentage, c=current_step:
                        self.progress_panel.update_stage_progress(s, p, c))
                
                def output_callback(message):
                    msg = str(message)
                    self.root.after(0, lambda m=msg: self.logger.info(m))
                
                installation_service.set_progress_callback(progress_callback)
                installation_service.set_output_callback(output_callback)
                
                # Start progress tracking
                self.root.after(0, lambda: self.progress_panel.start_operation("KOReader Installation"))
                
                # Run KOReader-only installation
                success = installation_service.install_koreader_only()
                
                # Update UI in main thread
                self.root.after(0, lambda: self._builtin_install_complete(success, "KOReader installation"))
                
            except Exception as e:
                self.logger.error(f"KOReader installation failed: {e}")
                self.root.after(0, lambda: self._builtin_install_complete(False, f"KOReader installation failed: {e}"))
        
        threading.Thread(target=run_koreader_install, daemon=True).start()
    
    def _install_builtin_literm(self) -> None:
        """Install rm-literm using the built-in package system."""
        if not self._ensure_connected():
            return
        
        self._update_status("Installing rm-literm...")
        self.is_operation_running = True
        self._update_operation_buttons(False)
        
        def run_literm_install():
            try:
                from ..services.installation_service import get_installation_service
                installation_service = get_installation_service()
                
                # Set up progress callbacks
                def progress_callback(progress):
                    percentage = progress.progress_percentage
                    message = progress.message
                    stage = progress.stage
                    current_step = progress.current_step
                    
                    self.root.after(0, lambda p=percentage, m=message:
                        self.progress_panel.update_overall_progress(p, m))
                    self.root.after(0, lambda s=stage, p=percentage, c=current_step:
                        self.progress_panel.update_stage_progress(s, p, c))
                
                def output_callback(message):
                    msg = str(message)
                    self.root.after(0, lambda m=msg: self.logger.info(m))
                
                installation_service.set_progress_callback(progress_callback)
                installation_service.set_output_callback(output_callback)
                
                # Start progress tracking
                self.root.after(0, lambda: self.progress_panel.start_operation("rm-literm Installation"))
                
                # Run rm-literm installation
                success = installation_service.install_literm_only()
                
                # Update UI in main thread
                self.root.after(0, lambda: self._builtin_install_complete(success, "rm-literm installation"))
                
            except Exception as e:
                self.logger.error(f"rm-literm installation failed: {e}")
                self.root.after(0, lambda: self._builtin_install_complete(False, f"rm-literm installation failed: {e}"))
        
        threading.Thread(target=run_literm_install, daemon=True).start()
    
    def _builtin_install_complete(self, success: bool, operation_name: str) -> None:
        """Handle built-in package installation completion."""
        self.is_operation_running = False
        self._update_operation_buttons(self.device and self.device.is_connected())
        
        if success:
            self._update_status(f"{operation_name} completed successfully")
            self.progress_panel.complete_operation(True, f"{operation_name} completed successfully")
        else:
            self._update_status(f"{operation_name} failed")
            self.progress_panel.complete_operation(False, f"{operation_name} failed")


def main():
    """Main entry point for the GUI application."""
    try:
        # Initialize core services
        config = init_config()
        logger = setup_logging(
            colored=config.ui.colored_output,
            log_file=config.get_config_dir() / 'installer.log'
        )
        
        # Create and run main window
        app = MainWindow()
        app.run()
        
    except Exception as e:
        # Fallback error handling
        import traceback
        print(f"Failed to start GUI application: {e}")
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())