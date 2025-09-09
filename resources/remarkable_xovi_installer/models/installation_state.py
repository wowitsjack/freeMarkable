"""
Installation state management for freeMarkable.

This module handles the InstallationState class with stage tracking,
persistence to/from files, and state validation and recovery mechanisms.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from .device import DeviceType


class InstallationStage(Enum):
    """Installation stages matching the original bash script."""
    NOT_STARTED = "not_started"
    STAGE_1 = "1"  # Setup, backup, XOVI installation, hashtable rebuild
    STAGE_2 = "2"  # KOReader installation and final configuration
    COMPLETED = "completed"
    FAILED = "failed"
    LAUNCHER_ONLY = "launcher_only"  # XOVI + AppLoad without KOReader


class StageStatus(Enum):
    """Status of individual installation steps."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageStep:
    """Individual step within an installation stage."""
    name: str
    description: str
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def start(self) -> None:
        """Mark step as started."""
        self.status = StageStatus.IN_PROGRESS
        self.started_at = datetime.now()
    
    def complete(self) -> None:
        """Mark step as completed successfully."""
        self.status = StageStatus.COMPLETED
        self.completed_at = datetime.now()
        self.error_message = None
    
    def fail(self, error_message: str) -> None:
        """Mark step as failed with error message."""
        self.status = StageStatus.FAILED
        self.completed_at = datetime.now()
        self.error_message = error_message
    
    def skip(self, reason: str = "") -> None:
        """Mark step as skipped."""
        self.status = StageStatus.SKIPPED
        self.completed_at = datetime.now()
        self.error_message = reason
    
    def reset(self) -> None:
        """Reset step to pending state."""
        self.status = StageStatus.PENDING
        self.started_at = None
        self.completed_at = None
        self.error_message = None
    
    def is_complete(self) -> bool:
        """Check if step is completed successfully."""
        return self.status == StageStatus.COMPLETED
    
    def is_failed(self) -> bool:
        """Check if step failed."""
        return self.status == StageStatus.FAILED
    
    def duration_seconds(self) -> Optional[float]:
        """Get step duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class BackupInfo:
    """Information about created backup."""
    backup_name: str
    created_at: datetime
    device_ip: str
    device_type: str
    ssh_password_backed_up: bool = False
    restore_script_path: str = ""
    
    def get_restore_command(self) -> str:
        """Get the command to restore from this backup."""
        return f"ssh root@{self.device_ip} '/home/root/{self.backup_name}/restore.sh'"


class InstallationState:
    """
    Manages installation state with stage tracking and persistence.
    
    This class handles the complex state management required for the staged
    installation process, including persistence across device reboots and
    recovery from interruptions.
    """
    
    def __init__(self, stage_file_path: Union[str, Path] = ".koreader_install_stage"):
        """
        Initialize installation state.
        
        Args:
            stage_file_path: Path to the stage persistence file
        """
        self.stage_file_path = Path(stage_file_path)
        
        # Current state
        self.current_stage = InstallationStage.NOT_STARTED
        self.stage_status = StageStatus.PENDING
        
        # Device and connection info
        self.device_ip: Optional[str] = None
        self.ssh_password: Optional[str] = None
        self.device_type: Optional[DeviceType] = None
        
        # Installation info
        self.backup_info: Optional[BackupInfo] = None
        self.installation_type: str = "full"  # full, launcher_only
        
        # Timestamps
        self.installation_started_at: Optional[datetime] = None
        self.current_stage_started_at: Optional[datetime] = None
        self.last_updated_at: Optional[datetime] = None
        
        # Stage definitions
        self.stage_steps: Dict[InstallationStage, List[StageStep]] = {}
        self._initialize_stage_definitions()
        
        # Error tracking
        self.last_error: Optional[str] = None
        self.failed_steps: List[str] = []
        
        # Progress tracking
        self.total_steps = 0
        self.completed_steps = 0
        
        self._logger = logging.getLogger(__name__)
    
    def _initialize_stage_definitions(self) -> None:
        """Initialize the standard stage and step definitions."""
        
        # Stage 1: Setup, backup, XOVI installation, hashtable rebuild
        stage_1_steps = [
            StageStep("device_setup", "Configure device connection and validation"),
            StageStep("device_detection", "Detect device architecture and type"),  
            StageStep("backup_creation", "Create comprehensive system backup"),
            StageStep("file_download", "Download required installation files"),
            StageStep("xovi_installation", "Install XOVI framework"),
            StageStep("extensions_installation", "Install qt-resource-rebuilder and AppLoad"),
            StageStep("shims_setup", "Configure qtfb-shim files"),
            StageStep("appload_configuration", "Configure AppLoad extension"),
            StageStep("hashtable_rebuild", "Rebuild hashtable (will restart UI)")
        ]
        
        # Stage 2: KOReader installation and final configuration
        stage_2_steps = [
            StageStep("device_ready_wait", "Wait for device to be ready after restart"),
            StageStep("xovi_startup", "Start XOVI services"),
            StageStep("koreader_installation", "Install and configure KOReader"),
            StageStep("ui_restart", "Restart reMarkable UI"),
            StageStep("installation_verification", "Verify installation components"),
            StageStep("cleanup", "Clean up temporary files")
        ]
        
        # Launcher-only installation (subset of full installation)
        launcher_only_steps = [
            StageStep("device_setup", "Configure device connection and validation"),
            StageStep("device_detection", "Detect device architecture and type"),
            StageStep("backup_creation", "Create comprehensive system backup"),
            StageStep("file_download", "Download required installation files"),
            StageStep("xovi_installation", "Install XOVI framework"),
            StageStep("extensions_installation", "Install qt-resource-rebuilder and AppLoad"),
            StageStep("shims_setup", "Configure qtfb-shim files"),
            StageStep("appload_configuration", "Configure AppLoad extension"),
            StageStep("hashtable_rebuild", "Rebuild hashtable (will restart UI)"),
            StageStep("device_ready_wait", "Wait for device to be ready after restart"),
            StageStep("xovi_startup", "Start XOVI services"),
            StageStep("ui_restart", "Restart reMarkable UI"),
            StageStep("installation_verification", "Verify launcher installation"),
            StageStep("cleanup", "Clean up temporary files")
        ]
        
        self.stage_steps = {
            InstallationStage.STAGE_1: stage_1_steps,
            InstallationStage.STAGE_2: stage_2_steps,
            InstallationStage.LAUNCHER_ONLY: launcher_only_steps
        }
        
        # Calculate total steps
        self._update_progress_counters()
    
    def _update_progress_counters(self) -> None:
        """Update total and completed step counters."""
        total = 0
        completed = 0
        
        for steps in self.stage_steps.values():
            for step in steps:
                total += 1
                if step.is_complete():
                    completed += 1
        
        self.total_steps = total
        self.completed_steps = completed
    
    def start_installation(self, installation_type: str = "full",
                          device_ip: Optional[str] = None,
                          ssh_password: Optional[str] = None,
                          device_type: Optional[DeviceType] = None) -> None:
        """
        Start a new installation.
        
        Args:
            installation_type: Type of installation (full, launcher_only)
            device_ip: Device IP address
            ssh_password: SSH password
            device_type: Device type
        """
        self.installation_type = installation_type
        self.device_ip = device_ip
        self.ssh_password = ssh_password
        self.device_type = device_type
        
        self.installation_started_at = datetime.now()
        self.last_updated_at = datetime.now()
        
        # Determine starting stage based on installation type
        if installation_type == "launcher_only":
            self.current_stage = InstallationStage.LAUNCHER_ONLY
        else:
            self.current_stage = InstallationStage.STAGE_1
        
        self.stage_status = StageStatus.PENDING
        self.current_stage_started_at = datetime.now()
        
        # Reset all steps
        for steps in self.stage_steps.values():
            for step in steps:
                step.reset()
        
        self._update_progress_counters()
        self._logger.info(f"Started {installation_type} installation")
    
    def advance_to_stage(self, stage: InstallationStage) -> None:
        """
        Advance to a specific installation stage.
        
        Args:
            stage: Target installation stage
        """
        if self.current_stage != stage:
            self._logger.info(f"Advancing from {self.current_stage.value} to {stage.value}")
            self.current_stage = stage
            self.stage_status = StageStatus.PENDING
            self.current_stage_started_at = datetime.now()
            self.last_updated_at = datetime.now()
    
    def get_current_steps(self) -> List[StageStep]:
        """
        Get the steps for the current stage.
        
        Returns:
            List of steps for current stage
        """
        return self.stage_steps.get(self.current_stage, [])
    
    def get_step_by_name(self, step_name: str) -> Optional[StageStep]:
        """
        Get a step by name from the current stage.
        
        Args:
            step_name: Name of the step to find
            
        Returns:
            StageStep instance or None if not found
        """
        for step in self.get_current_steps():
            if step.name == step_name:
                return step
        return None
    
    def start_step(self, step_name: str) -> bool:
        """
        Start a specific step in the current stage.
        
        Args:
            step_name: Name of the step to start
            
        Returns:
            True if step was started successfully
        """
        step = self.get_step_by_name(step_name)
        if step:
            step.start()
            self.last_updated_at = datetime.now()
            self._logger.info(f"Started step: {step_name}")
            return True
        
        self._logger.error(f"Step not found: {step_name}")
        return False
    
    def complete_step(self, step_name: str) -> bool:
        """
        Mark a step as completed.
        
        Args:
            step_name: Name of the step to complete
            
        Returns:
            True if step was completed successfully
        """
        step = self.get_step_by_name(step_name)
        if step:
            step.complete()
            self.last_updated_at = datetime.now()
            self._update_progress_counters()
            self._logger.info(f"Completed step: {step_name}")
            
            # Check if all steps in current stage are complete
            if self.is_current_stage_complete():
                self._complete_current_stage()
            
            return True
        
        self._logger.error(f"Step not found: {step_name}")
        return False
    
    def fail_step(self, step_name: str, error_message: str) -> bool:
        """
        Mark a step as failed.
        
        Args:
            step_name: Name of the step that failed
            error_message: Error description
            
        Returns:
            True if step was marked as failed
        """
        step = self.get_step_by_name(step_name)
        if step:
            step.fail(error_message)
            self.last_updated_at = datetime.now()
            self.last_error = error_message
            self.failed_steps.append(step_name)
            self._logger.error(f"Step failed: {step_name} - {error_message}")
            return True
        
        self._logger.error(f"Step not found: {step_name}")
        return False
    
    def skip_step(self, step_name: str, reason: str = "") -> bool:
        """
        Mark a step as skipped.
        
        Args:
            step_name: Name of the step to skip
            reason: Reason for skipping
            
        Returns:
            True if step was skipped successfully
        """
        step = self.get_step_by_name(step_name)
        if step:
            step.skip(reason)
            self.last_updated_at = datetime.now()
            self._update_progress_counters()
            self._logger.info(f"Skipped step: {step_name} - {reason}")
            return True
        
        self._logger.error(f"Step not found: {step_name}")
        return False
    
    def is_current_stage_complete(self) -> bool:
        """Check if all steps in the current stage are complete."""
        current_steps = self.get_current_steps()
        return all(step.is_complete() or step.status == StageStatus.SKIPPED 
                  for step in current_steps)
    
    def _complete_current_stage(self) -> None:
        """Handle completion of the current stage."""
        self.stage_status = StageStatus.COMPLETED
        self._logger.info(f"Completed stage: {self.current_stage.value}")
        
        # Advance to next stage or mark as completed
        if self.current_stage == InstallationStage.STAGE_1:
            if self.installation_type == "launcher_only":
                self.current_stage = InstallationStage.COMPLETED
            else:
                self.advance_to_stage(InstallationStage.STAGE_2)
        elif self.current_stage == InstallationStage.STAGE_2:
            self.current_stage = InstallationStage.COMPLETED
        elif self.current_stage == InstallationStage.LAUNCHER_ONLY:
            self.current_stage = InstallationStage.COMPLETED
    
    def set_backup_info(self, backup_name: str, device_ip: str, device_type: str,
                       ssh_password_backed_up: bool = False) -> None:
        """
        Set backup information.
        
        Args:
            backup_name: Name of the backup
            device_ip: Device IP address
            device_type: Device type string
            ssh_password_backed_up: Whether SSH password was backed up
        """
        self.backup_info = BackupInfo(
            backup_name=backup_name,
            created_at=datetime.now(),
            device_ip=device_ip,
            device_type=device_type,
            ssh_password_backed_up=ssh_password_backed_up,
            restore_script_path=f"/home/root/{backup_name}/restore.sh"
        )
        self.last_updated_at = datetime.now()
    
    def get_progress_percentage(self) -> float:
        """Get overall installation progress as percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.completed_steps / self.total_steps) * 100.0
    
    def get_stage_progress_percentage(self) -> float:
        """Get current stage progress as percentage."""
        current_steps = self.get_current_steps()
        if not current_steps:
            return 0.0
        
        completed = sum(1 for step in current_steps 
                       if step.is_complete() or step.status == StageStatus.SKIPPED)
        return (completed / len(current_steps)) * 100.0
    
    def can_continue_from_stage(self, stage: InstallationStage) -> bool:
        """
        Check if installation can continue from a specific stage.
        
        Args:
            stage: Stage to check
            
        Returns:
            True if installation can continue from this stage
        """
        return stage in [InstallationStage.STAGE_1, InstallationStage.STAGE_2]
    
    def save_to_file(self, file_path: Optional[Union[str, Path]] = None) -> None:
        """
        Save installation state to file.
        
        Args:
            file_path: Path to save to. If None, uses default stage file path.
            
        Raises:
            IOError: If file cannot be written
        """
        if file_path is None:
            file_path = self.stage_file_path
        else:
            file_path = Path(file_path)
        
        try:
            state_data = self._to_dict()
            
            # Create parent directory if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2, default=str)
            
            self._logger.debug(f"Installation state saved to {file_path}")
            
        except Exception as e:
            raise IOError(f"Failed to save installation state: {e}")
    
    def _to_dict(self) -> Dict[str, Any]:
        """Convert installation state to dictionary."""
        # Convert steps to serializable format
        steps_data = {}
        for stage, steps in self.stage_steps.items():
            steps_data[stage.value] = [
                {
                    "name": step.name,
                    "description": step.description,
                    "status": step.status.value,
                    "started_at": step.started_at.isoformat() if step.started_at else None,
                    "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                    "error_message": step.error_message
                }
                for step in steps
            ]
        
        # Convert backup info
        backup_data = None
        if self.backup_info:
            backup_data = {
                "backup_name": self.backup_info.backup_name,
                "created_at": self.backup_info.created_at.isoformat(),
                "device_ip": self.backup_info.device_ip,
                "device_type": self.backup_info.device_type,
                "ssh_password_backed_up": self.backup_info.ssh_password_backed_up,
                "restore_script_path": self.backup_info.restore_script_path
            }
        
        return {
            # Core state
            "current_stage": self.current_stage.value,
            "stage_status": self.stage_status.value,
            "installation_type": self.installation_type,
            
            # Device info (compatible with bash script format)
            "STAGE": self.current_stage.value,
            "REMARKABLE_IP": self.device_ip,
            "REMARKABLE_PASSWORD": self.ssh_password,
            "DEVICE_TYPE": self.device_type.short_name if self.device_type else None,
            "BACKUP_NAME": self.backup_info.backup_name if self.backup_info else "",
            
            # Timestamps
            "installation_started_at": self.installation_started_at.isoformat() if self.installation_started_at else None,
            "current_stage_started_at": self.current_stage_started_at.isoformat() if self.current_stage_started_at else None,
            "last_updated_at": self.last_updated_at.isoformat() if self.last_updated_at else None,
            
            # Progress and errors
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "last_error": self.last_error,
            "failed_steps": self.failed_steps,
            
            # Detailed state
            "stage_steps": steps_data,
            "backup_info": backup_data,
            
            # Metadata
            "state_version": "1.0"
        }
    
    @classmethod
    def load_from_file(cls, file_path: Union[str, Path] = ".koreader_install_stage") -> Optional['InstallationState']:
        """
        Load installation state from file.
        
        Args:
            file_path: Path to load from
            
        Returns:
            InstallationState instance or None if file doesn't exist
            
        Raises:
            ValueError: If file format is invalid
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
                # Try to parse as JSON first
                try:
                    state_data = json.loads(content)
                    return cls._from_dict(state_data, file_path)
                except json.JSONDecodeError:
                    # Try to parse as bash script format (legacy compatibility)
                    return cls._from_bash_format(content, file_path)
                    
        except Exception as e:
            raise ValueError(f"Failed to load installation state from {file_path}: {e}")
    
    @classmethod
    def _from_dict(cls, state_data: Dict[str, Any], file_path: Path) -> 'InstallationState':
        """Create InstallationState from dictionary data."""
        instance = cls(file_path)
        
        # Load core state
        instance.current_stage = InstallationStage(state_data.get("current_stage", "not_started"))
        instance.stage_status = StageStatus(state_data.get("stage_status", "pending"))
        instance.installation_type = state_data.get("installation_type", "full")
        
        # Load device info
        instance.device_ip = state_data.get("REMARKABLE_IP") or state_data.get("device_ip")
        instance.ssh_password = state_data.get("REMARKABLE_PASSWORD") or state_data.get("ssh_password")
        
        device_type_str = state_data.get("DEVICE_TYPE") or state_data.get("device_type")
        if device_type_str:
            from .device import DeviceType
            instance.device_type = DeviceType.from_short_name(device_type_str)
        
        # Load timestamps
        for field, key in [
            ("installation_started_at", "installation_started_at"),
            ("current_stage_started_at", "current_stage_started_at"),
            ("last_updated_at", "last_updated_at")
        ]:
            if timestamp_str := state_data.get(key):
                try:
                    setattr(instance, field, datetime.fromisoformat(timestamp_str))
                except ValueError:
                    pass
        
        # Load progress and errors
        instance.total_steps = state_data.get("total_steps", 0)
        instance.completed_steps = state_data.get("completed_steps", 0)
        instance.last_error = state_data.get("last_error")
        instance.failed_steps = state_data.get("failed_steps", [])
        
        # Load backup info
        if backup_data := state_data.get("backup_info"):
            instance.backup_info = BackupInfo(
                backup_name=backup_data["backup_name"],
                created_at=datetime.fromisoformat(backup_data["created_at"]),
                device_ip=backup_data["device_ip"],
                device_type=backup_data["device_type"],
                ssh_password_backed_up=backup_data.get("ssh_password_backed_up", False),
                restore_script_path=backup_data.get("restore_script_path", "")
            )
        
        # Load step details if available
        if steps_data := state_data.get("stage_steps"):
            instance._load_step_details(steps_data)
        
        return instance
    
    @classmethod  
    def _from_bash_format(cls, content: str, file_path: Path) -> 'InstallationState':
        """Create InstallationState from bash script format (legacy compatibility)."""
        instance = cls(file_path)
        
        # Parse bash variable assignments
        variables = {}
        for line in content.split('\n'):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                variables[key] = value
        
        # Map bash variables to state
        if stage := variables.get("STAGE"):
            try:
                instance.current_stage = InstallationStage(stage)
            except ValueError:
                instance.current_stage = InstallationStage.NOT_STARTED
        
        instance.device_ip = variables.get("REMARKABLE_IP")
        instance.ssh_password = variables.get("REMARKABLE_PASSWORD")
        
        if device_type_str := variables.get("DEVICE_TYPE"):
            from .device import DeviceType
            instance.device_type = DeviceType.from_short_name(device_type_str)
        
        if backup_name := variables.get("BACKUP_NAME"):
            instance.backup_info = BackupInfo(
                backup_name=backup_name,
                created_at=datetime.now(),  # Unknown, use current time
                device_ip=instance.device_ip or "",
                device_type=device_type_str or "",
                ssh_password_backed_up=False
            )
        
        return instance
    
    def _load_step_details(self, steps_data: Dict[str, Any]) -> None:
        """Load detailed step information from saved data."""
        for stage_str, step_list in steps_data.items():
            try:
                stage = InstallationStage(stage_str)
                if stage in self.stage_steps:
                    stage_steps = self.stage_steps[stage]
                    
                    for i, step_data in enumerate(step_list):
                        if i < len(stage_steps):
                            step = stage_steps[i]
                            step.status = StageStatus(step_data.get("status", "pending"))
                            step.error_message = step_data.get("error_message")
                            
                            # Parse timestamps
                            if started_str := step_data.get("started_at"):
                                try:
                                    step.started_at = datetime.fromisoformat(started_str)
                                except ValueError:
                                    pass
                            
                            if completed_str := step_data.get("completed_at"):
                                try:
                                    step.completed_at = datetime.fromisoformat(completed_str)
                                except ValueError:
                                    pass
            except ValueError:
                continue
    
    def clear_state_file(self) -> None:
        """Remove the state file from disk."""
        try:
            if self.stage_file_path.exists():
                self.stage_file_path.unlink()
                self._logger.info("Installation state file cleared")
        except Exception as e:
            self._logger.error(f"Failed to clear state file: {e}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the current installation state."""
        return {
            "stage": self.current_stage.value,
            "status": self.stage_status.value,
            "installation_type": self.installation_type,
            "progress_percentage": self.get_progress_percentage(),
            "stage_progress_percentage": self.get_stage_progress_percentage(),
            "device_ip": self.device_ip,
            "device_type": self.device_type.display_name if self.device_type else None,
            "has_backup": self.backup_info is not None,
            "backup_name": self.backup_info.backup_name if self.backup_info else None,
            "failed_steps": self.failed_steps,
            "last_error": self.last_error,
            "can_continue": self.can_continue_from_stage(self.current_stage),
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps
        }