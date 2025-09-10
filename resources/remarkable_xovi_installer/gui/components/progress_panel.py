"""
Progress tracking panel for freeMarkable.

This module provides the progress tracking interface including installation
progress bars, stage tracking display, real-time status updates, and
operation cancellation functionality.
"""

import tkinter as tk
from typing import Optional, Callable, Dict, Any, List
import customtkinter as ctk
import threading
import time
from datetime import datetime, timedelta

from remarkable_xovi_installer.models.installation_state import (
    InstallationState, InstallationStage, StageStatus, StageStep
)
from remarkable_xovi_installer.services.file_service import DownloadProgress, DownloadStatus
from remarkable_xovi_installer.utils.logger import get_logger


class ProgressPanel(ctk.CTkFrame):
    """
    Progress tracking panel component.
    
    Provides interface for installation progress including:
    - Installation progress bar and status
    - Stage tracking display (Stage 1/2)
    - Real-time progress updates
    - Cancel operation button
    - Progress details and ETA estimation
    """
    
    def __init__(self, parent, cancel_callback: Optional[Callable[[], None]] = None, **kwargs):
        """
        Initialize progress panel.
        
        Args:
            parent: Parent widget
            cancel_callback: Callback for operation cancellation
            **kwargs: Additional CTkFrame arguments
        """
        super().__init__(parent, **kwargs)
        
        # Callbacks
        self.cancel_callback = cancel_callback
        
        # Core services
        self.logger = get_logger()
        
        # Progress state
        self.installation_state: Optional[InstallationState] = None
        self.current_operation = "Ready"
        self.is_operation_running = False
        self.operation_start_time: Optional[datetime] = None
        self.current_step_start_time: Optional[datetime] = None
        
        # Progress tracking
        self.overall_progress = 0.0
        self.stage_progress = 0.0
        self.download_progress = 0.0
        
        # UI components
        self.progress_widgets: Dict[str, ctk.CTkWidget] = {}
        
        # Setup UI
        self._setup_ui()
        self._reset_progress_display()
    
    def _setup_ui(self) -> None:
        """Setup the progress panel user interface."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        
        # Panel title
        title_frame = ctk.CTkFrame(self, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", pady=(5, 3))
        title_frame.grid_columnconfigure(1, weight=1)
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="Installation Progress",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w")
        
        # Operation status
        self.operation_status_label = ctk.CTkLabel(
            title_frame,
            text="Ready",
            font=ctk.CTkFont(size=9),
            text_color="gray"
        )
        self.operation_status_label.grid(row=0, column=1, sticky="e")
        
        # Main progress section
        progress_frame = ctk.CTkFrame(self)
        progress_frame.grid(row=1, column=0, sticky="ew", padx=3, pady=2)
        progress_frame.grid_columnconfigure(0, weight=1)
        
        # Overall progress
        overall_label = ctk.CTkLabel(
            progress_frame,
            text="Overall Progress:",
            font=ctk.CTkFont(size=10, weight="bold")
        )
        overall_label.grid(row=0, column=0, sticky="w", padx=3, pady=(3, 2))
        
        self.overall_progress_bar = ctk.CTkProgressBar(
            progress_frame,
            height=10,
            progress_color="#2d6e3e"
        )
        self.overall_progress_bar.grid(row=1, column=0, sticky="ew", padx=3, pady=(0, 2))
        self.overall_progress_bar.set(0)
        
        self.overall_progress_label = ctk.CTkLabel(
            progress_frame,
            text="0% - Ready to start",
            font=ctk.CTkFont(size=8)
        )
        self.overall_progress_label.grid(row=2, column=0, sticky="w", padx=3, pady=(0, 3))
        
        # Stage progress section
        stage_frame = ctk.CTkFrame(self)
        stage_frame.grid(row=2, column=0, sticky="ew", padx=3, pady=2)
        stage_frame.grid_columnconfigure(1, weight=1)
        
        # Stage indicator
        self.stage_label = ctk.CTkLabel(
            stage_frame,
            text="Stage: Not Started",
            font=ctk.CTkFont(size=10, weight="bold")
        )
        self.stage_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=3, pady=(3, 2))
        
        # Current step
        self.step_label = ctk.CTkLabel(
            stage_frame,
            text="Waiting to begin...",
            font=ctk.CTkFont(size=8),
            wraplength=250
        )
        self.step_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=3, pady=(0, 2))
        
        # Stage progress bar
        self.stage_progress_bar = ctk.CTkProgressBar(
            stage_frame,
            height=8,
            progress_color="#1f538d"
        )
        self.stage_progress_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=3, pady=(0, 2))
        self.stage_progress_bar.set(0)
        
        self.stage_progress_label = ctk.CTkLabel(
            stage_frame,
            text="0% - No active stage",
            font=ctk.CTkFont(size=7)
        )
        self.stage_progress_label.grid(row=3, column=0, sticky="w", padx=3, pady=(0, 3))
        
        # Time information
        self.time_label = ctk.CTkLabel(
            stage_frame,
            text="",
            font=ctk.CTkFont(size=7),
            text_color="gray"
        )
        self.time_label.grid(row=3, column=1, sticky="e", padx=3, pady=(0, 3))
        
        # Download progress section (initially hidden)
        self.download_frame = ctk.CTkFrame(self)
        self.download_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        self.download_frame.grid_columnconfigure(0, weight=1)
        self.download_frame.grid_remove()  # Hidden by default
        
        # Download progress components
        self._setup_download_progress()
        
        # Controls section
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.grid(row=4, column=0, sticky="ew", pady=10)
        controls_frame.grid_columnconfigure(1, weight=1)
        
        # Cancel button
        self.cancel_button = ctk.CTkButton(
            controls_frame,
            text="Cancel Operation",
            command=self._cancel_operation,
            width=120,
            fg_color="#8b2635",
            hover_color="#6b1c28",
            state="disabled"
        )
        self.cancel_button.grid(row=0, column=0, padx=10)
        
        # Progress details toggle
        self.details_button = ctk.CTkButton(
            controls_frame,
            text="Show Details",
            command=self._toggle_details,
            width=100
        )
        self.details_button.grid(row=0, column=2, padx=10)
        
        # Details section (initially hidden)
        self.details_frame = ctk.CTkFrame(self)
        self.details_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.details_frame.grid_columnconfigure(0, weight=1)
        self.details_frame.grid_remove()  # Hidden by default
        
        self._setup_details_section()
    
    def _setup_download_progress(self) -> None:
        """Setup download progress display components."""
        download_title = ctk.CTkLabel(
            self.download_frame,
            text="Download Progress:",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        download_title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        
        self.download_progress_bar = ctk.CTkProgressBar(
            self.download_frame,
            height=12,
            progress_color="#ff6b35"
        )
        self.download_progress_bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        self.download_progress_bar.set(0)
        
        # Download info frame
        download_info_frame = ctk.CTkFrame(self.download_frame, fg_color="transparent")
        download_info_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        download_info_frame.grid_columnconfigure(2, weight=1)
        
        self.download_file_label = ctk.CTkLabel(
            download_info_frame,
            text="",
            font=ctk.CTkFont(size=10)
        )
        self.download_file_label.grid(row=0, column=0, sticky="w")
        
        self.download_size_label = ctk.CTkLabel(
            download_info_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.download_size_label.grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        self.download_speed_label = ctk.CTkLabel(
            download_info_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.download_speed_label.grid(row=0, column=2, sticky="e")
    
    def _setup_details_section(self) -> None:
        """Setup detailed progress information section."""
        details_title = ctk.CTkLabel(
            self.details_frame,
            text="Progress Details:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        details_title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        
        # Steps list
        self.steps_frame = ctk.CTkScrollableFrame(
            self.details_frame,
            height=150,
            label_text="Installation Steps"
        )
        self.steps_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.steps_frame.grid_columnconfigure(0, weight=1)
        
        # Timing information
        timing_frame = ctk.CTkFrame(self.details_frame, fg_color="transparent")
        timing_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        timing_frame.grid_columnconfigure(1, weight=1)
        
        self.start_time_label = ctk.CTkLabel(
            timing_frame,
            text="Start Time: Not started",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.start_time_label.grid(row=0, column=0, sticky="w")
        
        self.elapsed_time_label = ctk.CTkLabel(
            timing_frame,
            text="Elapsed: 00:00:00",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.elapsed_time_label.grid(row=0, column=1, sticky="e")
        
        self.eta_label = ctk.CTkLabel(
            timing_frame,
            text="ETA: Calculating...",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.eta_label.grid(row=1, column=0, columnspan=2, sticky="w")
    
    def _reset_progress_display(self) -> None:
        """Reset all progress displays to initial state."""
        self.overall_progress_bar.set(0)
        self.stage_progress_bar.set(0)
        self.download_progress_bar.set(0)
        
        self.overall_progress_label.configure(text="0% - Ready to start")
        self.stage_label.configure(text="Stage: Not Started")
        self.step_label.configure(text="Waiting to begin...")
        self.stage_progress_label.configure(text="0% - No active stage")
        self.time_label.configure(text="")
        self.operation_status_label.configure(text="Ready", text_color="gray")
        
        # Hide download progress
        self.download_frame.grid_remove()
        
        # Reset controls
        self.cancel_button.configure(state="disabled")
        
        # Clear details
        self._clear_steps_display()
    
    def _clear_steps_display(self) -> None:
        """Clear the steps display in details section."""
        for widget in self.steps_frame.winfo_children():
            widget.destroy()
    
    def _toggle_details(self) -> None:
        """Toggle visibility of progress details."""
        if self.details_frame.winfo_viewable():
            self.details_frame.grid_remove()
            self.details_button.configure(text="Show Details")
        else:
            self.details_frame.grid()
            self.details_button.configure(text="Hide Details")
    
    def _cancel_operation(self) -> None:
        """Cancel the current operation."""
        if self.cancel_callback:
            self.cancel_callback()
        else:
            self.logger.warning("No cancel callback configured")
        
        self.operation_status_label.configure(text="Cancelling...", text_color="orange")
        self.cancel_button.configure(state="disabled", text="Cancelling...")
    
    def _update_time_display(self) -> None:
        """Update elapsed time and ETA displays."""
        if not self.operation_start_time:
            return
        
        elapsed = datetime.now() - self.operation_start_time
        elapsed_str = str(elapsed).split('.')[0]  # Remove microseconds
        
        self.elapsed_time_label.configure(text=f"Elapsed: {elapsed_str}")
        
        # Calculate ETA if we have progress
        if self.overall_progress > 0:
            total_estimated = elapsed / (self.overall_progress / 100.0)
            remaining = total_estimated - elapsed
            if remaining.total_seconds() > 0:
                remaining_str = str(remaining).split('.')[0]
                self.eta_label.configure(text=f"ETA: {remaining_str}")
            else:
                self.eta_label.configure(text="ETA: Almost done")
        else:
            self.eta_label.configure(text="ETA: Calculating...")
    
    def start_operation(self, operation_name: str, installation_state: Optional[InstallationState] = None) -> None:
        """
        Start a new operation.
        
        Args:
            operation_name: Name of the operation
            installation_state: Installation state for tracking
        """
        self.current_operation = operation_name
        self.installation_state = installation_state
        self.is_operation_running = True
        self.operation_start_time = datetime.now()
        self.current_step_start_time = datetime.now()
        
        # Update UI
        self.operation_status_label.configure(text=f"Running: {operation_name}", text_color="orange")
        self.cancel_button.configure(state="normal", text="Cancel Operation")
        self.start_time_label.configure(text=f"Start Time: {self.operation_start_time.strftime('%H:%M:%S')}")
        
        # Update steps display if installation state provided
        if installation_state:
            self._update_steps_display()
        
        # Start time update thread
        self._start_time_update_thread()
        
        self.logger.info(f"Progress tracking started for operation: {operation_name}")
    
    def complete_operation(self, success: bool = True, message: str = "") -> None:
        """
        Complete the current operation.
        
        Args:
            success: Whether operation completed successfully
            message: Completion message
        """
        self.is_operation_running = False
        
        if success:
            self.operation_status_label.configure(text="✓ Completed", text_color="green")
            self.overall_progress_bar.set(1.0)
            self.overall_progress_label.configure(text="100% - Operation completed successfully")
            if message:
                self.step_label.configure(text=message)
        else:
            self.operation_status_label.configure(text="✗ Failed", text_color="red")
            if message:
                self.step_label.configure(text=f"Error: {message}")
        
        self.cancel_button.configure(state="disabled", text="Cancel Operation")
        
        self.logger.info(f"Progress tracking completed for operation: {self.current_operation}")
    
    def update_overall_progress(self, progress: float, message: str = "") -> None:
        """
        Update overall progress.
        
        Args:
            progress: Progress value (0.0 to 100.0)
            message: Progress message
        """
        self.overall_progress = max(0.0, min(100.0, progress))
        self.overall_progress_bar.set(self.overall_progress / 100.0)
        
        if message:
            self.overall_progress_label.configure(text=f"{self.overall_progress:.1f}% - {message}")
        else:
            self.overall_progress_label.configure(text=f"{self.overall_progress:.1f}%")
    
    def update_stage_progress(self, stage: InstallationStage, progress: float, current_step: str = "") -> None:
        """
        Update stage progress.
        
        Args:
            stage: Current installation stage
            progress: Stage progress (0.0 to 100.0)
            current_step: Current step description
        """
        self.stage_progress = max(0.0, min(100.0, progress))
        self.stage_progress_bar.set(self.stage_progress / 100.0)
        
        # Update stage label
        stage_names = {
            InstallationStage.STAGE_1: "Stage 1: Setup & XOVI Installation",
            InstallationStage.STAGE_2: "Stage 2: KOReader Installation",
            InstallationStage.LAUNCHER_ONLY: "Launcher Installation",
            InstallationStage.COMPLETED: "Installation Complete"
        }
        
        stage_name = stage_names.get(stage, f"Stage: {stage.value}")
        self.stage_label.configure(text=stage_name)
        
        # Update progress label
        self.stage_progress_label.configure(text=f"{self.stage_progress:.1f}% - Stage progress")
        
        # Update current step
        if current_step:
            self.step_label.configure(text=current_step)
            self.current_step_start_time = datetime.now()
    
    def update_download_progress(self, download_progress: DownloadProgress) -> None:
        """
        Update download progress display.
        
        Args:
            download_progress: Download progress information
        """
        # Show download frame
        self.download_frame.grid()
        
        # Update progress bar
        progress_percent = download_progress.progress_percentage
        self.download_progress_bar.set(progress_percent / 100.0)
        
        # Update file name
        self.download_file_label.configure(text=f"Downloading: {download_progress.filename}")
        
        # Update size information
        if download_progress.total_size:
            total_mb = download_progress.total_size / (1024 * 1024)
            downloaded_mb = download_progress.downloaded_size / (1024 * 1024)
            self.download_size_label.configure(
                text=f"{downloaded_mb:.1f} / {total_mb:.1f} MB ({progress_percent:.1f}%)"
            )
        else:
            downloaded_mb = download_progress.downloaded_size / (1024 * 1024)
            self.download_size_label.configure(text=f"{downloaded_mb:.1f} MB")
        
        # Update speed
        if download_progress.download_speed:
            speed_mbps = download_progress.download_speed / (1024 * 1024)
            self.download_speed_label.configure(text=f"{speed_mbps:.1f} MB/s")
            
            # Show ETA
            if download_progress.eta_seconds:
                eta = timedelta(seconds=int(download_progress.eta_seconds))
                self.time_label.configure(text=f"ETA: {eta}")
        
        # Hide download frame when complete
        if download_progress.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]:
            self.after(2000, self.download_frame.grid_remove)  # Hide after 2 seconds
    
    def _update_steps_display(self) -> None:
        """Update the steps display in details section."""
        if not self.installation_state:
            return
        
        # Clear existing steps
        self._clear_steps_display()
        
        # Get current steps
        current_steps = self.installation_state.get_current_steps()
        
        for i, step in enumerate(current_steps):
            step_frame = ctk.CTkFrame(self.steps_frame, fg_color="transparent")
            step_frame.grid(row=i, column=0, sticky="ew", pady=1)
            step_frame.grid_columnconfigure(1, weight=1)
            
            # Status indicator
            status_icons = {
                StageStatus.PENDING: "⏳",
                StageStatus.IN_PROGRESS: "🔄", 
                StageStatus.COMPLETED: "✅",
                StageStatus.FAILED: "❌",
                StageStatus.SKIPPED: "⏭️"
            }
            
            status_colors = {
                StageStatus.PENDING: "gray",
                StageStatus.IN_PROGRESS: "orange",
                StageStatus.COMPLETED: "green", 
                StageStatus.FAILED: "red",
                StageStatus.SKIPPED: "gray"
            }
            
            icon = status_icons.get(step.status, "⏳")
            color = status_colors.get(step.status, "gray")
            
            status_label = ctk.CTkLabel(
                step_frame,
                text=icon,
                width=20,
                text_color=color
            )
            status_label.grid(row=0, column=0, padx=(5, 10))
            
            # Step name
            step_label = ctk.CTkLabel(
                step_frame,
                text=step.name.replace('_', ' ').title(),
                font=ctk.CTkFont(size=10),
                anchor="w"
            )
            step_label.grid(row=0, column=1, sticky="ew")
            
            # Duration if available
            if step.duration_seconds():
                duration_label = ctk.CTkLabel(
                    step_frame,
                    text=f"{step.duration_seconds():.1f}s",
                    font=ctk.CTkFont(size=9),
                    text_color="gray",
                    width=40
                )
                duration_label.grid(row=0, column=2, padx=(5, 10))
    
    def _start_time_update_thread(self) -> None:
        """Start background thread for time updates."""
        def update_time():
            while self.is_operation_running:
                self.after(0, self._update_time_display)
                time.sleep(1)
        
        threading.Thread(target=update_time, daemon=True).start()
    
    def set_installation_state(self, installation_state: InstallationState) -> None:
        """Set installation state and update display."""
        self.installation_state = installation_state
        self._update_steps_display()
    
    def is_running(self) -> bool:
        """Check if an operation is currently running."""
        return self.is_operation_running
    
    def get_operation_name(self) -> str:
        """Get the current operation name."""
        return self.current_operation
    
    def reset_progress(self) -> None:
        """Reset all progress tracking to initial state."""
        self.is_operation_running = False
        self.operation_start_time = None
        self.current_step_start_time = None
        self.overall_progress = 0.0
        self.stage_progress = 0.0
        self.download_progress = 0.0
        self.current_operation = "Ready"
        self.installation_state = None
        
        # Reset UI display
        self._reset_progress_display()
        
        self.logger.info("Progress panel reset to initial state")