"""
Pre-flight checklist dialog for freeMarkable installer.

This module provides a mandatory checklist dialog that appears on every application
launch to ensure users have properly configured their WiFi and SSH connectivity
before attempting to use the installer.
"""

import tkinter as tk
from typing import Optional, Callable
import customtkinter as ctk
from remarkable_xovi_installer.utils.logger import get_logger


class PreflightDialog:
    """
    Pre-flight checklist dialog that must be completed before app launch.
    
    Ensures users have:
    - reMarkable and computer connected to WiFi
    - Tested SSH connectivity works
    """
    
    def __init__(self, parent: Optional[tk.Tk] = None, on_complete: Optional[Callable] = None):
        """
        Initialize the pre-flight dialog.
        
        Args:
            parent: Parent window (optional)
            on_complete: Callback function when checklist is completed
        """
        self.logger = get_logger()
        self.parent = parent
        self.on_complete = on_complete
        self.dialog: Optional[ctk.CTkToplevel] = None
        self.wifi_checked: Optional[tk.BooleanVar] = None
        self.ssh_checked: Optional[tk.BooleanVar] = None
        self.passcode_checked: Optional[tk.BooleanVar] = None
        self.proceed_button: Optional[ctk.CTkButton] = None
        
    def show(self) -> None:
        """Display the pre-flight checklist dialog."""
        try:
            self._create_dialog()
            self._setup_ui()
            self._center_dialog()
            
            # Make dialog modal and always on top
            if self.dialog:
                if self.parent:
                    self.dialog.transient(self.parent)
                self.dialog.grab_set()
                self.dialog.focus()
                self.dialog.lift()  # Bring to front
                self.dialog.attributes('-topmost', True)
                
                # Prevent closing with X button
                self.dialog.protocol("WM_DELETE_WINDOW", self._on_close_attempt)
                
                # Start the dialog's own event loop if no parent
                if not self.parent:
                    self.dialog.mainloop()
                
            self.logger.debug("Pre-flight checklist dialog displayed")
            
        except Exception as e:
            self.logger.error(f"Error showing pre-flight dialog: {e}")
            # If dialog fails, allow app to continue
            if self.on_complete:
                self.on_complete()
    
    def _create_dialog(self) -> None:
        """Create the dialog window."""
        if self.parent:
            self.dialog = ctk.CTkToplevel(self.parent)
        else:
            # Create a standalone CTk window instead of toplevel
            self.dialog = ctk.CTk()
            
        self.dialog.title("Pre-Flight Checklist - freeMarkable")
        self.dialog.geometry("500x400")
        self.dialog.resizable(False, False)
        
        # Configure grid
        self.dialog.grid_columnconfigure(0, weight=1)
        self.dialog.grid_rowconfigure(2, weight=1)
    
    def _setup_ui(self) -> None:
        """Setup the user interface components."""
        if not self.dialog:
            return
        
        # Initialize variables first
        self.wifi_checked = tk.BooleanVar()
        self.ssh_checked = tk.BooleanVar()
        self.passcode_checked = tk.BooleanVar()
            
        # Header
        header_frame = ctk.CTkFrame(self.dialog)
        header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        header_frame.grid_columnconfigure(0, weight=1)
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="🔧 Pre-Flight Checklist",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.grid(row=0, column=0, pady=15)
        
        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Please verify these requirements before proceeding:",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        subtitle_label.grid(row=1, column=0, pady=(0, 15))
        
        # Checklist frame
        checklist_frame = ctk.CTkFrame(self.dialog)
        checklist_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        checklist_frame.grid_columnconfigure(0, weight=1)
        
        # WiFi connectivity check
        wifi_frame = ctk.CTkFrame(checklist_frame)
        wifi_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))
        wifi_frame.grid_columnconfigure(1, weight=1)
        
        self.wifi_checkbox = ctk.CTkCheckBox(
            wifi_frame,
            text="",
            variable=self.wifi_checked,
            command=self._update_proceed_button
        )
        self.wifi_checkbox.grid(row=0, column=0, padx=(10, 15), pady=10)
        
        wifi_text = ctk.CTkLabel(
            wifi_frame,
            text="Both my reMarkable and this computer are connected to WiFi",
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        wifi_text.grid(row=0, column=1, sticky="ew", pady=10, padx=(0, 10))
        
        # SSH connectivity check
        ssh_frame = ctk.CTkFrame(checklist_frame)
        ssh_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        ssh_frame.grid_columnconfigure(1, weight=1)
        
        self.ssh_checkbox = ctk.CTkCheckBox(
            ssh_frame,
            text="",
            variable=self.ssh_checked,
            command=self._update_proceed_button
        )
        self.ssh_checkbox.grid(row=0, column=0, padx=(10, 15), pady=10)
        
        ssh_text = ctk.CTkLabel(
            ssh_frame,
            text="I have tested that SSH works to my reMarkable device",
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        ssh_text.grid(row=0, column=1, sticky="ew", pady=10, padx=(0, 10))
        
        # Passcode disabled check
        passcode_frame = ctk.CTkFrame(checklist_frame)
        passcode_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))
        passcode_frame.grid_columnconfigure(1, weight=1)
        
        self.passcode_checkbox = ctk.CTkCheckBox(
            passcode_frame,
            text="",
            variable=self.passcode_checked,
            command=self._update_proceed_button
        )
        self.passcode_checkbox.grid(row=0, column=0, padx=(10, 15), pady=10)
        
        passcode_text = ctk.CTkLabel(
            passcode_frame,
            text="I have disabled the passcode on my reMarkable device",
            font=ctk.CTkFont(size=13),
            anchor="w"
        )
        passcode_text.grid(row=0, column=1, sticky="ew", pady=10, padx=(0, 10))
        
        # Instructions
        instructions_frame = ctk.CTkFrame(self.dialog)
        instructions_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=10)
        instructions_frame.grid_columnconfigure(0, weight=1)
        
        instructions_text = ctk.CTkLabel(
            instructions_frame,
            text="📋 If you need help with SSH setup:\n"
                 "• Enable SSH in reMarkable Settings > Storage\n"
                 "• Test connection: ssh root@<remarkable-ip>\n"
                 "• Default password is usually shown on device",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            justify="left"
        )
        instructions_text.grid(row=0, column=0, pady=15, padx=15, sticky="ew")
        
        # Buttons
        button_frame = ctk.CTkFrame(self.dialog)
        button_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 20))
        button_frame.grid_columnconfigure(1, weight=1)
        
        # Exit button
        exit_button = ctk.CTkButton(
            button_frame,
            text="Exit",
            command=self._exit_app,
            fg_color="gray",
            hover_color="darkgray",
            width=100
        )
        exit_button.grid(row=0, column=0, padx=(15, 10), pady=15)
        
        # Proceed button (initially disabled)
        self.proceed_button = ctk.CTkButton(
            button_frame,
            text="Proceed to freeMarkable",
            command=self._proceed,
            state="disabled",
            width=200
        )
        self.proceed_button.grid(row=0, column=2, padx=(10, 15), pady=15)
    
    def _center_dialog(self) -> None:
        """Center the dialog on screen."""
        if not self.dialog:
            return
            
        self.dialog.update_idletasks()
        
        # Get screen dimensions
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        
        # Get dialog dimensions
        dialog_width = self.dialog.winfo_reqwidth()
        dialog_height = self.dialog.winfo_reqheight()
        
        # Calculate position
        x = (screen_width - dialog_width) // 2
        y = (screen_height - dialog_height) // 2
        
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
    
    def _update_proceed_button(self) -> None:
        """Update proceed button state based on checkbox selections."""
        if not self.proceed_button:
            return
            
        if (self.wifi_checked and self.ssh_checked and self.passcode_checked and
            self.wifi_checked.get() and self.ssh_checked.get() and self.passcode_checked.get()):
            self.proceed_button.configure(state="normal")
        else:
            self.proceed_button.configure(state="disabled")
    
    def _proceed(self) -> None:
        """Handle proceed button click."""
        try:
            self.logger.info("Pre-flight checklist completed successfully")
            
            if self.dialog:
                self.dialog.grab_release()
                self.dialog.destroy()
                
            # Call completion callback
            if self.on_complete:
                self.on_complete()
                
        except Exception as e:
            self.logger.error(f"Error in proceed action: {e}")
    
    def _exit_app(self) -> None:
        """Handle exit button click."""
        try:
            self.logger.info("User chose to exit from pre-flight checklist")
            
            if self.dialog:
                self.dialog.grab_release()
                self.dialog.destroy()
                
            # Exit the entire application
            if self.parent:
                self.parent.quit()
            else:
                exit(0)
                
        except Exception as e:
            self.logger.error(f"Error in exit action: {e}")
            exit(1)
    
    def _on_close_attempt(self) -> None:
        """Handle attempts to close dialog with X button."""
        # Do nothing - force user to make a choice
        pass


def show_preflight_checklist(parent: Optional[tk.Tk] = None, on_complete: Optional[Callable] = None) -> None:
    """
    Convenience function to show the pre-flight checklist dialog.
    
    Args:
        parent: Parent window (optional)
        on_complete: Callback function when checklist is completed
    """
    dialog = PreflightDialog(parent, on_complete)
    dialog.show()