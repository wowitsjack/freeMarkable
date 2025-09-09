"""
Log display panel for freeMarkable.

This module provides the log display interface including scrollable text area,
color-coded messages matching the logger utility, auto-scroll functionality,
log filtering by level, and save logs to file capability.
"""

import tkinter as tk
from typing import Optional, Callable, Dict, Any, List, Tuple
import customtkinter as ctk
from datetime import datetime
import threading
from pathlib import Path

from remarkable_xovi_installer.utils.logger import LogLevel, ColorCodes, get_logger
from remarkable_xovi_installer.config.settings import get_config


class LogEntry:
    """Represents a single log entry."""
    
    def __init__(self, timestamp: datetime, level: int, level_name: str, 
                 message: str, raw_message: str):
        self.timestamp = timestamp
        self.level = level
        self.level_name = level_name
        self.message = message
        self.raw_message = raw_message
    
    def get_formatted_message(self, show_timestamp: bool = True) -> str:
        """Get formatted message string."""
        if show_timestamp:
            time_str = self.timestamp.strftime("%H:%M:%S")
            return f"[{time_str}] {self.message}"
        return self.message


class LogPanel(ctk.CTkFrame):
    """
    Log display panel component.
    
    Provides interface for log message display including:
    - Scrollable text area for log messages
    - Color-coded messages matching the logger utility
    - Auto-scroll and log filtering by level
    - Save logs to file functionality
    - Clear logs and search functionality
    """
    
    def __init__(self, parent, **kwargs):
        """
        Initialize log panel.
        
        Args:
            parent: Parent widget
            **kwargs: Additional CTkFrame arguments
        """
        super().__init__(parent, **kwargs)
        
        # Core services
        try:
            self.logger = get_logger()
        except RuntimeError:
            self.logger = None
        
        try:
            self.config = get_config()
        except RuntimeError:
            self.config = None
        
        # Log storage
        self.log_entries: List[LogEntry] = []
        self.max_log_entries = 1000  # Limit to prevent memory issues
        
        # Display settings
        self.show_timestamps = True
        self.auto_scroll = True
        self.current_filter_level = LogLevel.DEBUG.value  # Show all by default
        
        # Color mapping for log levels (matching logger utility)
        self.level_colors = {
            LogLevel.DEBUG.value: "#CCCCCC",      # Light gray
            LogLevel.INFO.value: "#4A9EFF",       # Blue
            LogLevel.WARNING.value: "#FFD700",    # Yellow/Gold
            LogLevel.ERROR.value: "#FF4444",      # Red
            LogLevel.HIGHLIGHT.value: "#DA70D6",  # Purple
        }
        
        # Setup UI
        self._setup_ui()
        
        # Add initial welcome message
        self._add_welcome_message()
    
    def _setup_ui(self) -> None:
        """Setup the log panel user interface."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header frame
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(10, 5))
        header_frame.grid_columnconfigure(1, weight=1)
        
        # Panel title
        title_label = ctk.CTkLabel(
            header_frame,
            text="Application Logs",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w")
        
        # Controls frame
        controls_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_frame.grid(row=0, column=1, sticky="e")
        
        # Log level filter
        self.level_filter = ctk.CTkOptionMenu(
            controls_frame,
            values=["All", "Info+", "Warning+", "Error Only"],
            width=100,
            command=self._on_filter_changed
        )
        self.level_filter.grid(row=0, column=0, padx=2)
        self.level_filter.set("All")
        
        # Auto-scroll toggle
        self.auto_scroll_var = tk.BooleanVar(value=True)
        self.auto_scroll_checkbox = ctk.CTkCheckBox(
            controls_frame,
            text="Auto-scroll",
            variable=self.auto_scroll_var,
            width=80,
            command=self._on_auto_scroll_toggled
        )
        self.auto_scroll_checkbox.grid(row=0, column=1, padx=2)
        
        # Clear button
        self.clear_button = ctk.CTkButton(
            controls_frame,
            text="Clear",
            command=self._clear_logs,
            width=60,
            height=25
        )
        self.clear_button.grid(row=0, column=2, padx=2)
        
        # Save button
        self.save_button = ctk.CTkButton(
            controls_frame,
            text="Save",
            command=self._save_logs,
            width=60,
            height=25
        )
        self.save_button.grid(row=0, column=3, padx=2)
        
        # Log display frame
        log_display_frame = ctk.CTkFrame(self)
        log_display_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_display_frame.grid_columnconfigure(0, weight=1)
        log_display_frame.grid_rowconfigure(0, weight=1)
        
        # Log text widget with scrollbar
        self.log_text = ctk.CTkTextbox(
            log_display_frame,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            state="disabled"
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        # Bottom info frame
        info_frame = ctk.CTkFrame(self, fg_color="transparent")
        info_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
        info_frame.grid_columnconfigure(1, weight=1)
        
        # Log count
        self.log_count_label = ctk.CTkLabel(
            info_frame,
            text="0 log entries",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.log_count_label.grid(row=0, column=0, sticky="w")
        
        # Search frame (initially hidden)
        self.search_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        self.search_frame.grid(row=0, column=1, sticky="e")
        self.search_frame.grid_remove()  # Hidden by default
        
        self._setup_search_ui()
    
    def _setup_search_ui(self) -> None:
        """Setup search functionality UI."""
        search_label = ctk.CTkLabel(
            self.search_frame,
            text="Search:",
            font=ctk.CTkFont(size=10)
        )
        search_label.grid(row=0, column=0, padx=(0, 5))
        
        self.search_entry = ctk.CTkEntry(
            self.search_frame,
            width=150,
            height=25,
            placeholder_text="Search logs..."
        )
        self.search_entry.grid(row=0, column=1, padx=2)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)
        
        search_clear_button = ctk.CTkButton(
            self.search_frame,
            text="✕",
            width=25,
            height=25,
            command=self._clear_search
        )
        search_clear_button.grid(row=0, column=2, padx=2)
    
    def _add_welcome_message(self) -> None:
        """Add initial welcome message to log display."""
        welcome_entry = LogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO.value,
            level_name="INFO",
            message="Log display initialized. Ready to capture application logs.",
            raw_message="Log display initialized"
        )
        self._add_log_entry_internal(welcome_entry)
    
    def add_log_entry(self, message: str, level: int) -> None:
        """
        Add a log entry to the display.
        
        Args:
            message: Log message text
            level: Log level (from logging module)
        """
        # Convert level to level name
        level_names = {
            LogLevel.DEBUG.value: "DEBUG",
            LogLevel.INFO.value: "INFO", 
            LogLevel.WARNING.value: "WARNING",
            LogLevel.ERROR.value: "ERROR",
            LogLevel.HIGHLIGHT.value: "HIGHLIGHT"
        }
        
        # Map standard logging levels to our custom levels
        if level == 10:  # logging.DEBUG
            our_level = LogLevel.DEBUG.value
        elif level == 20:  # logging.INFO
            our_level = LogLevel.INFO.value
        elif level == 30:  # logging.WARNING
            our_level = LogLevel.WARNING.value
        elif level == 40:  # logging.ERROR
            our_level = LogLevel.ERROR.value
        elif level == LogLevel.HIGHLIGHT.value:  # Our custom level
            our_level = LogLevel.HIGHLIGHT.value
        else:
            our_level = LogLevel.INFO.value  # Default
        
        level_name = level_names.get(our_level, "INFO")
        
        # Strip ANSI color codes from message for display
        clean_message = ColorCodes.strip_colors(message)
        
        entry = LogEntry(
            timestamp=datetime.now(),
            level=our_level,
            level_name=level_name,
            message=clean_message,
            raw_message=clean_message
        )
        
        # Use after() to ensure thread safety
        self.after(0, self._add_log_entry_internal, entry)
    
    def _add_log_entry_internal(self, entry: LogEntry) -> None:
        """Add log entry to internal storage and display (thread-safe)."""
        # Add to storage
        self.log_entries.append(entry)
        
        # Limit entries to prevent memory issues
        if len(self.log_entries) > self.max_log_entries:
            self.log_entries = self.log_entries[-self.max_log_entries:]
            # Refresh display when we trim
            self._refresh_display()
            return
        
        # Check if entry should be displayed based on current filter
        if not self._should_display_entry(entry):
            self._update_log_count()
            return
        
        # Add to display
        self._append_to_display(entry)
        self._update_log_count()
        
        # Auto-scroll if enabled
        if self.auto_scroll:
            self.log_text.see("end")
    
    def _should_display_entry(self, entry: LogEntry) -> bool:
        """Check if entry should be displayed based on current filter."""
        if self.current_filter_level == LogLevel.DEBUG.value:  # "All"
            return True
        elif self.current_filter_level == LogLevel.INFO.value:  # "Info+"
            return entry.level >= LogLevel.INFO.value
        elif self.current_filter_level == LogLevel.WARNING.value:  # "Warning+"
            return entry.level >= LogLevel.WARNING.value
        elif self.current_filter_level == LogLevel.ERROR.value:  # "Error Only"
            return entry.level >= LogLevel.ERROR.value
        
        return True
    
    def _append_to_display(self, entry: LogEntry) -> None:
        """Append a single entry to the display."""
        # Enable text widget for editing
        self.log_text.configure(state="normal")
        
        # Get formatted message
        formatted_message = entry.get_formatted_message(self.show_timestamps)
        
        # Insert message with appropriate color
        color = self.level_colors.get(entry.level, "#FFFFFF")
        
        # Insert the message
        self.log_text.insert("end", formatted_message + "\n")
        
        # Apply color formatting to the last line
        line_start = f"end-{len(formatted_message) + 1}c linestart"
        line_end = "end-1c"
        
        # Create or get tag for this level
        tag_name = f"level_{entry.level}"
        if tag_name not in self.log_text._textbox.tag_names():
            self.log_text._textbox.tag_configure(tag_name, foreground=color)
        
        self.log_text._textbox.tag_add(tag_name, line_start, line_end)
        
        # Disable text widget
        self.log_text.configure(state="disabled")
    
    def _refresh_display(self) -> None:
        """Refresh the entire log display based on current filter."""
        # Clear display
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        
        # Re-add filtered entries
        for entry in self.log_entries:
            if self._should_display_entry(entry):
                self._append_to_display(entry)
        
        # Auto-scroll to bottom
        if self.auto_scroll:
            self.log_text.see("end")
        
        self._update_log_count()
    
    def _update_log_count(self) -> None:
        """Update the log count display."""
        visible_count = sum(1 for entry in self.log_entries if self._should_display_entry(entry))
        total_count = len(self.log_entries)
        
        if visible_count == total_count:
            self.log_count_label.configure(text=f"{total_count} log entries")
        else:
            self.log_count_label.configure(text=f"{visible_count} of {total_count} log entries")
    
    def _on_filter_changed(self, value: str) -> None:
        """Handle filter level change."""
        filter_mapping = {
            "All": LogLevel.DEBUG.value,
            "Info+": LogLevel.INFO.value,
            "Warning+": LogLevel.WARNING.value,
            "Error Only": LogLevel.ERROR.value
        }
        
        self.current_filter_level = filter_mapping.get(value, LogLevel.DEBUG.value)
        self._refresh_display()
    
    def _on_auto_scroll_toggled(self) -> None:
        """Handle auto-scroll toggle."""
        self.auto_scroll = self.auto_scroll_var.get()
        
        if self.auto_scroll:
            self.log_text.see("end")
    
    def _on_search_changed(self, event) -> None:
        """Handle search input changes."""
        search_term = self.search_entry.get().lower()
        
        if not search_term:
            # Clear any existing highlights
            self._clear_search_highlights()
            return
        
        # Highlight matching entries
        self._highlight_search_matches(search_term)
    
    def _highlight_search_matches(self, search_term: str) -> None:
        """Highlight search matches in the log display."""
        # Clear previous highlights
        self._clear_search_highlights()
        
        # Search through visible text
        text_content = self.log_text.get("1.0", "end-1c")
        lines = text_content.split('\n')
        
        self.log_text.configure(state="normal")
        
        for line_num, line in enumerate(lines, 1):
            if search_term in line.lower():
                line_start = f"{line_num}.0"
                line_end = f"{line_num}.end"
                self.log_text._textbox.tag_add("search_highlight", line_start, line_end)
        
        # Configure highlight tag
        self.log_text._textbox.tag_configure("search_highlight", background="#444444")
        
        self.log_text.configure(state="disabled")
    
    def _clear_search_highlights(self) -> None:
        """Clear search highlights."""
        self.log_text.configure(state="normal")
        self.log_text._textbox.tag_remove("search_highlight", "1.0", "end")
        self.log_text.configure(state="disabled")
    
    def _clear_search(self) -> None:
        """Clear search input and highlights."""
        self.search_entry.delete(0, "end")
        self._clear_search_highlights()
    
    def _clear_logs(self) -> None:
        """Clear all log entries."""
        self.log_entries.clear()
        
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        
        self._update_log_count()
        
        # Add a cleared message
        cleared_entry = LogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO.value,
            level_name="INFO",
            message="Log display cleared by user.",
            raw_message="Log display cleared"
        )
        self._add_log_entry_internal(cleared_entry)
    
    def _save_logs(self) -> None:
        """Save logs to file."""
        try:
            # Get save directory
            if self.config:
                save_dir = self.config.get_config_dir()
            else:
                save_dir = Path.home()
            
            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"xovi_installer_logs_{timestamp}.txt"
            file_path = save_dir / filename
            
            # Write logs to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"freeMarkable - Log Export\n")
                f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total entries: {len(self.log_entries)}\n")
                f.write("=" * 60 + "\n\n")
                
                for entry in self.log_entries:
                    timestamp_str = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp_str}] [{entry.level_name}] {entry.raw_message}\n")
            
            # Add success message to logs
            success_entry = LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.INFO.value,
                level_name="INFO",
                message=f"Logs saved to: {file_path}",
                raw_message=f"Logs saved to {file_path}"
            )
            self._add_log_entry_internal(success_entry)
            
        except Exception as e:
            # Add error message to logs
            error_entry = LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.ERROR.value,
                level_name="ERROR",
                message=f"Failed to save logs: {e}",
                raw_message=f"Failed to save logs: {e}"
            )
            self._add_log_entry_internal(error_entry)
    
    def toggle_search(self) -> None:
        """Toggle search bar visibility."""
        if self.search_frame.winfo_viewable():
            self.search_frame.grid_remove()
            self._clear_search()
        else:
            self.search_frame.grid()
            self.search_entry.focus()
    
    def get_log_entries(self, level_filter: Optional[int] = None) -> List[LogEntry]:
        """
        Get log entries, optionally filtered by level.
        
        Args:
            level_filter: Minimum log level to include
            
        Returns:
            List of log entries
        """
        if level_filter is None:
            return self.log_entries.copy()
        
        return [entry for entry in self.log_entries if entry.level >= level_filter]
    
    def set_max_entries(self, max_entries: int) -> None:
        """Set maximum number of log entries to keep."""
        self.max_log_entries = max_entries
        
        # Trim if necessary
        if len(self.log_entries) > max_entries:
            self.log_entries = self.log_entries[-max_entries:]
            self._refresh_display()
    
    def set_font_size(self, size: int) -> None:
        """Set log display font size."""
        current_font = self.log_text.cget("font")
        if isinstance(current_font, ctk.CTkFont):
            current_font.configure(size=size)
        else:
            new_font = ctk.CTkFont(family="Consolas", size=size)
            self.log_text.configure(font=new_font)
    
    def export_filtered_logs(self, level_filter: int, file_path: Path) -> bool:
        """
        Export filtered logs to file.
        
        Args:
            level_filter: Minimum log level to export
            file_path: Path to save file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            filtered_entries = self.get_log_entries(level_filter)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"freeMarkable - Filtered Log Export\n")
                f.write(f"Filter: Level >= {level_filter}\n")
                f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Entries: {len(filtered_entries)}\n")
                f.write("=" * 60 + "\n\n")
                
                for entry in filtered_entries:
                    timestamp_str = entry.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"[{timestamp_str}] [{entry.level_name}] {entry.raw_message}\n")
            
            return True
            
        except Exception:
            return False
    
    def clear_old_entries(self, keep_count: int = 50) -> None:
        """
        Clear old log entries, keeping only the most recent ones.
        
        Args:
            keep_count: Number of recent entries to keep
        """
        if len(self.log_entries) > keep_count:
            # Keep only the most recent entries
            self.log_entries = self.log_entries[-keep_count:]
            
            # Refresh display
            self._refresh_display()
            
            # Add a message about the cleanup
            cleanup_entry = LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.INFO.value,
                level_name="INFO",
                message=f"Log history cleared - keeping {keep_count} most recent entries.",
                raw_message=f"Log cleanup - kept {keep_count} entries"
            )
            self._add_log_entry_internal(cleanup_entry)