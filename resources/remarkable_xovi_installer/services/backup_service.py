"""
Backup and restore operations service for freeMarkable.

This module provides comprehensive backup creation with SSH password extraction,
backup listing and management, full system restore capability, and backup validation.
"""

import os
import time
import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from .network_service import NetworkService, CommandResult
from .file_service import FileService


class BackupStatus(Enum):
    """Backup operation status."""
    PENDING = "pending"
    CREATING = "creating"
    COMPLETED = "completed"
    FAILED = "failed"
    VALIDATING = "validating"
    RESTORING = "restoring"


@dataclass
class BackupInfo:
    """Information about a backup."""
    name: str
    created_at: datetime
    device_ip: str
    device_type: str
    size_bytes: Optional[int] = None
    ssh_password_backed_up: bool = False
    restore_script_path: str = ""
    local_archive_path: Optional[str] = None
    components_backed_up: List[str] = None
    
    def __post_init__(self):
        if self.components_backed_up is None:
            self.components_backed_up = []
    
    @property
    def size_mb(self) -> Optional[float]:
        """Get backup size in MB."""
        return self.size_bytes / (1024 * 1024) if self.size_bytes else None
    
    def get_restore_command(self) -> str:
        """Get the command to restore from this backup."""
        return f"ssh root@{self.device_ip} '/home/root/{self.name}/restore.sh'"


class BackupService:
    """
    Backup and restore service for reMarkable device state management.
    
    Provides comprehensive backup creation, validation, listing, and restoration
    capabilities with proper error handling and progress tracking.
    """
    
    def __init__(self, network_service: NetworkService, file_service: FileService):
        """
        Initialize backup service.
        
        Args:
            network_service: Network service for SSH operations
            file_service: File service for local file operations
        """
        self.network_service = network_service
        self.file_service = file_service
        
        # Progress tracking
        self.progress_callback: Optional[callable] = None
        self.output_callback: Optional[callable] = None
        
        # Operation state
        self.current_operation: Optional[BackupStatus] = None
        self.current_backup_name: Optional[str] = None
        
        self._logger = logging.getLogger(__name__)
    
    def set_progress_callback(self, callback: callable) -> None:
        """Set callback for backup operation progress."""
        self.progress_callback = callback
    
    def set_output_callback(self, callback: callable) -> None:
        """Set callback for backup operation output."""
        self.output_callback = callback
    
    def _log_output(self, message: str) -> None:
        """Log output message."""
        self._logger.info(message)
        if self.output_callback:
            self.output_callback(message)
    
    def _update_progress(self, operation: BackupStatus, progress: float, message: str) -> None:
        """Update operation progress."""
        self.current_operation = operation
        if self.progress_callback:
            self.progress_callback({
                "operation": operation.value,
                "progress": progress,
                "message": message,
                "backup_name": self.current_backup_name
            })
    
    def create_backup(self, backup_name: Optional[str] = None,
                     include_local_copy: bool = False,
                     custom_components: Optional[List[str]] = None) -> BackupInfo:
        """
        Create a comprehensive system backup.
        
        Args:
            backup_name: Custom backup name (auto-generated if None)
            include_local_copy: Whether to create a local archive copy
            custom_components: Additional paths to backup
            
        Returns:
            BackupInfo with backup details
            
        Raises:
            Exception: If backup creation fails
        """
        if not self.network_service.is_connected():
            if not self.network_service.connect():
                raise Exception("Cannot connect to device for backup creation")
        
        # Generate backup name if not provided
        if not backup_name:
            timestamp = int(time.time())
            backup_name = f"koreader_backup_{timestamp}"
        
        self.current_backup_name = backup_name
        self._update_progress(BackupStatus.CREATING, 0, "Starting backup creation...")
        
        try:
            device_info = self.network_service.get_device_info()
            device_type = device_info.get("architecture", "unknown")
            device_ip = self.network_service.hostname or "unknown"
            
            self._log_output(f"Creating comprehensive backup: {backup_name}")
            
            # Create backup script
            backup_script = self._generate_backup_script(backup_name, device_type, device_ip, custom_components)
            
            self._update_progress(BackupStatus.CREATING, 25, "Executing backup script on device...")
            
            # Execute backup creation on device
            result = self.network_service.execute_command(backup_script, timeout=120)
            if not result.success:
                raise Exception(f"Backup creation failed: {result.stderr}")
            
            self._update_progress(BackupStatus.CREATING, 50, "Extracting backup information...")
            
            # Extract backup information
            backup_info = self._extract_backup_info(backup_name, device_ip, device_type)
            
            self._update_progress(BackupStatus.CREATING, 75, "Validating backup integrity...")
            
            # Validate backup
            if not self._validate_backup(backup_name):
                raise Exception("Backup validation failed")
            
            # Create local copy if requested
            if include_local_copy:
                self._update_progress(BackupStatus.CREATING, 85, "Creating local backup copy...")
                local_path = self._create_local_backup_copy(backup_name)
                backup_info.local_archive_path = str(local_path)
            
            self._update_progress(BackupStatus.COMPLETED, 100, "Backup creation completed successfully")
            self._log_output(f"Backup created successfully: {backup_name}")
            
            if backup_info.ssh_password_backed_up:
                self._log_output("SSH password has been backed up for recovery")
            
            return backup_info
            
        except Exception as e:
            self._update_progress(BackupStatus.FAILED, 0, f"Backup creation failed: {e}")
            raise Exception(f"Backup creation failed: {e}")
        
        finally:
            self.current_operation = None
            self.current_backup_name = None
            
            # Prune old backups after successful creation
            if 'backup_info' in locals():
                self._prune_old_backups()
    
    def _generate_backup_script(self, backup_name: str, device_type: str, device_ip: str,
                               custom_components: Optional[List[str]] = None) -> str:
        """Generate the backup creation script."""
        custom_backup = ""
        if custom_components:
            for component in custom_components:
                custom_backup += f'''
if [[ -e {component} ]]; then
    echo 'Backing up custom component: {component}' >> /home/root/{backup_name}/backup_info.txt
    cp -r {component} /home/root/{backup_name}/custom_$(basename {component}) 2>/dev/null || true
fi'''
        
        return f'''
mkdir -p /home/root/{backup_name}

# Create backup information file
echo 'KOReader Installation Backup' > /home/root/{backup_name}/backup_info.txt
echo 'Created: $(date)' >> /home/root/{backup_name}/backup_info.txt
echo 'Device: {device_type}' >> /home/root/{backup_name}/backup_info.txt
echo 'IP: {device_ip}' >> /home/root/{backup_name}/backup_info.txt
echo '' >> /home/root/{backup_name}/backup_info.txt

# Check and backup XOVI installation
if [[ -d /home/root/xovi ]]; then
    echo 'Previous XOVI installation found - backing up' >> /home/root/{backup_name}/backup_info.txt
    cp -r /home/root/xovi /home/root/{backup_name}/xovi_backup 2>/dev/null || true
    echo 'XOVI' >> /home/root/{backup_name}/components.txt
else
    echo 'No previous XOVI installation found' >> /home/root/{backup_name}/backup_info.txt
fi

# Backup shims directory if it exists
if [[ -d /home/root/shims ]]; then
    echo 'Previous shims found - backing up' >> /home/root/{backup_name}/backup_info.txt
    cp -r /home/root/shims /home/root/{backup_name}/shims_backup 2>/dev/null || true
    echo 'Shims' >> /home/root/{backup_name}/components.txt
fi

# Backup xovi-tripletap if it exists
if [[ -d /home/root/xovi-tripletap ]]; then
    echo 'xovi-tripletap installation found - backing up' >> /home/root/{backup_name}/backup_info.txt
    cp -r /home/root/xovi-tripletap /home/root/{backup_name}/xovi_tripletap_backup 2>/dev/null || true
    # Also backup the service file
    if [[ -f /etc/systemd/system/xovi-tripletap.service ]]; then
        cp /etc/systemd/system/xovi-tripletap.service /home/root/{backup_name}/ 2>/dev/null || true
    fi
    echo 'xovi-tripletap' >> /home/root/{backup_name}/components.txt
fi

# Backup xochitl.conf (contains SSH password and device settings)
if [[ -f /home/root/.config/remarkable/xochitl.conf ]]; then
    echo 'Backing up xochitl.conf (contains SSH password)' >> /home/root/{backup_name}/backup_info.txt
    mkdir -p /home/root/{backup_name}/config
    cp /home/root/.config/remarkable/xochitl.conf /home/root/{backup_name}/config/ 2>/dev/null || echo 'Failed to backup xochitl.conf' >> /home/root/{backup_name}/backup_info.txt
    
    # Extract SSH password for backup record
    if [[ -f /home/root/{backup_name}/config/xochitl.conf ]]; then
        ssh_password=$(grep -E '^DeveloperPassword=' /home/root/{backup_name}/config/xochitl.conf | cut -d'=' -f2 2>/dev/null || echo 'not found')
        echo "SSH Password: $ssh_password" >> /home/root/{backup_name}/backup_info.txt
        echo 'SSH_PASSWORD_BACKED_UP=true' >> /home/root/{backup_name}/metadata.txt
    fi
    echo 'xochitl.conf' >> /home/root/{backup_name}/components.txt
else
    echo 'xochitl.conf not found - SSH password not backed up' >> /home/root/{backup_name}/backup_info.txt
    echo 'SSH_PASSWORD_BACKED_UP=false' >> /home/root/{backup_name}/metadata.txt
fi

# Record current system state
echo '' >> /home/root/{backup_name}/backup_info.txt
echo 'System State:' >> /home/root/{backup_name}/backup_info.txt
systemctl is-active xochitl > /home/root/{backup_name}/xochitl_status.txt 2>/dev/null || echo 'unknown' > /home/root/{backup_name}/xochitl_status.txt
echo "xochitl status: $(cat /home/root/{backup_name}/xochitl_status.txt)" >> /home/root/{backup_name}/backup_info.txt

# Directory listings
ls -la /home/root/ > /home/root/{backup_name}/root_directory_before.txt 2>/dev/null || true
ls -la /etc/systemd/system/ | grep xovi > /home/root/{backup_name}/xovi_services.txt 2>/dev/null || true

# System information
uname -a > /home/root/{backup_name}/system_info.txt 2>/dev/null || true
df -h > /home/root/{backup_name}/disk_usage.txt 2>/dev/null || true

{custom_backup}

# Create restore script
cat > /home/root/{backup_name}/restore.sh << 'RESTORE_EOF'
#!/bin/bash
# KOReader Installation Restore Script
# This script will completely remove KOReader and XOVI installations
# Created: $(date)

echo 'Starting KOReader/XOVI removal and system restore...'

# Stop XOVI if running (ONLY used in restore script, not during live backup)
if [[ -f /home/root/xovi/stop ]]; then
    cd /home/root/xovi && ./stop 2>/dev/null || true
fi

# Stop and remove xovi-tripletap service
systemctl stop xovi-tripletap 2>/dev/null || true
systemctl disable xovi-tripletap 2>/dev/null || true
rm -f /etc/systemd/system/xovi-tripletap.service 2>/dev/null || true

# Remove XOVI completely
rm -rf /home/root/xovi 2>/dev/null || true
echo 'XOVI directory removed'

# Remove shims
rm -rf /home/root/shims 2>/dev/null || true
echo 'Shims directory removed'

# Remove xovi-tripletap completely
rm -rf /home/root/xovi-tripletap 2>/dev/null || true
echo 'xovi-tripletap directory removed'

# Reload systemd after service removal
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

echo 'All installation files removed'

# Restore previous installations if they existed
if [[ -d ./xovi_backup ]]; then
    echo 'Restoring previous XOVI installation...'
    cp -r ./xovi_backup /home/root/xovi
    echo 'Previous XOVI installation restored'
fi

if [[ -d ./shims_backup ]]; then
    echo 'Restoring previous shims...'
    cp -r ./shims_backup /home/root/shims
    echo 'Previous shims restored'
fi

if [[ -d ./xovi_tripletap_backup ]]; then
    echo 'Restoring previous xovi-tripletap...'
    cp -r ./xovi_tripletap_backup /home/root/xovi-tripletap
    # Restore service file if it exists
    if [[ -f ./xovi-tripletap.service ]]; then
        cp ./xovi-tripletap.service /etc/systemd/system/
        systemctl daemon-reload
        systemctl enable xovi-tripletap
        systemctl start xovi-tripletap
    fi
    echo 'Previous xovi-tripletap restored'
fi

# Restart UI to ensure clean state
echo 'Restarting reMarkable UI...'
systemctl restart xochitl

echo 'System restore completed!'
echo 'All KOReader and XOVI traces have been removed.'
echo 'Any previous installations have been restored.'
RESTORE_EOF

chmod +x /home/root/{backup_name}/restore.sh

# Create backup completion marker
echo 'BACKUP_COMPLETED=true' >> /home/root/{backup_name}/metadata.txt
echo "BACKUP_SIZE=$(du -sb /home/root/{backup_name} | cut -f1)" >> /home/root/{backup_name}/metadata.txt

echo 'Backup creation completed successfully'
'''
    
    def _extract_backup_info(self, backup_name: str, device_ip: str, device_type: str) -> BackupInfo:
        """Extract backup information from the created backup."""
        # Get backup metadata
        metadata_result = self.network_service.execute_command(
            f"cat /home/root/{backup_name}/metadata.txt 2>/dev/null || echo 'No metadata'"
        )
        
        # Get backup size
        size_result = self.network_service.execute_command(
            f"du -sb /home/root/{backup_name} | cut -f1"
        )
        
        # Get components list
        components_result = self.network_service.execute_command(
            f"cat /home/root/{backup_name}/components.txt 2>/dev/null || echo ''"
        )
        
        # Parse metadata
        ssh_password_backed_up = False
        if metadata_result.success and "SSH_PASSWORD_BACKED_UP=true" in metadata_result.stdout:
            ssh_password_backed_up = True
        
        # Parse size
        size_bytes = None
        if size_result.success:
            try:
                size_bytes = int(size_result.stdout.strip())
            except ValueError:
                pass
        
        # Parse components
        components = []
        if components_result.success:
            components = [comp.strip() for comp in components_result.stdout.split('\n') if comp.strip()]
        
        return BackupInfo(
            name=backup_name,
            created_at=datetime.now(),
            device_ip=device_ip,
            device_type=device_type,
            size_bytes=size_bytes,
            ssh_password_backed_up=ssh_password_backed_up,
            restore_script_path=f"/home/root/{backup_name}/restore.sh",
            components_backed_up=components
        )
    
    def _validate_backup(self, backup_name: str) -> bool:
        """Validate backup integrity."""
        self._log_output("Validating backup integrity...")
        
        # Check if backup directory exists
        check_result = self.network_service.execute_command(
            f"test -d /home/root/{backup_name} && echo 'exists' || echo 'missing'"
        )
        
        if not check_result.success or "missing" in check_result.stdout:
            self._log_output(f"Backup directory missing: {backup_name}")
            return False
        
        # Check for required files
        required_files = ["backup_info.txt", "restore.sh", "metadata.txt"]
        for file in required_files:
            file_check = self.network_service.execute_command(
                f"test -f /home/root/{backup_name}/{file} && echo 'exists' || echo 'missing'"
            )
            if not file_check.success or "missing" in file_check.stdout:
                self._log_output(f"Required backup file missing: {file}")
                return False
        
        # Verify restore script is executable
        script_check = self.network_service.execute_command(
            f"test -x /home/root/{backup_name}/restore.sh && echo 'executable' || echo 'not executable'"
        )
        if not script_check.success or "not executable" in script_check.stdout:
            self._log_output("Restore script is not executable")
            return False
        
        self._log_output("Backup validation successful")
        return True
    
    def _create_local_backup_copy(self, backup_name: str) -> Path:
        """Create a local archive copy of the backup."""
        self._log_output("Creating local backup archive...")
        
        # Create temporary directory for download
        temp_dir = self.file_service.create_temp_dir(prefix="backup_")
        local_backup_dir = temp_dir / backup_name
        
        # Download backup directory recursively
        download_result = self.network_service.execute_command(
            f"cd /home/root && tar czf {backup_name}.tar.gz {backup_name}"
        )
        
        if not download_result.success:
            raise Exception(f"Failed to create backup archive on device: {download_result.stderr}")
        
        # Download the archive
        local_archive = temp_dir / f"{backup_name}.tar.gz"
        if not self.network_service.download_file(f"/home/root/{backup_name}.tar.gz", local_archive):
            raise Exception("Failed to download backup archive")
        
        # Clean up remote archive
        self.network_service.execute_command(f"rm -f /home/root/{backup_name}.tar.gz")
        
        # Move to permanent location
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        final_path = backup_dir / f"{backup_name}.tar.gz"
        
        local_archive.rename(final_path)
        
        self._log_output(f"Local backup archive created: {final_path}")
        return final_path
    
    def list_backups(self) -> List[BackupInfo]:
        """
        List all available backups on the device.
        
        Returns:
            List of BackupInfo objects for available backups
        """
        if not self.network_service.is_connected():
            if not self.network_service.connect():
                raise Exception("Cannot connect to device to list backups")
        
        self._log_output("Listing available backups...")
        
        # Find backup directories - simplified for BusyBox compatibility
        result = self.network_service.execute_command(
            "cd /home/root && ls -1d koreader_backup_* 2>/dev/null || echo 'No backups found'"
        )
        
        if not result.success or "No backups found" in result.stdout:
            self._log_output("No backups found on device")
            return []
        
        backup_names = [name.strip() for name in result.stdout.split('\n') if name.strip() and 'koreader_backup_' in name and name != 'No backups found']
        backups = []
        
        for backup_name in backup_names:
            try:
                # Extract basic info for each backup - BusyBox compatible
                info_result = self.network_service.execute_command(
                    f"cat /home/root/{backup_name}/backup_info.txt 2>/dev/null | head -n 10"
                )
                
                if info_result.success:
                    device_type = "Unknown"
                    device_ip = "Unknown"
                    created_at = datetime.now()
                    
                    for line in info_result.stdout.split('\n'):
                        if line.startswith('Device:'):
                            device_type = line.split(':', 1)[1].strip()
                        elif line.startswith('IP:'):
                            device_ip = line.split(':', 1)[1].strip()
                        elif line.startswith('Created:'):
                            try:
                                # Try to parse the date (basic parsing)
                                date_str = line.split(':', 1)[1].strip()
                                # This is a simplified parser - could be enhanced
                                created_at = datetime.now()  # Fallback to now
                            except:
                                pass
                    
                    # Get size
                    size_result = self.network_service.execute_command(
                        f"du -sb /home/root/{backup_name} | cut -f1"
                    )
                    size_bytes = None
                    if size_result.success:
                        try:
                            size_bytes = int(size_result.stdout.strip())
                        except ValueError:
                            pass
                    
                    backup_info = BackupInfo(
                        name=backup_name,
                        created_at=created_at,
                        device_ip=device_ip,
                        device_type=device_type,
                        size_bytes=size_bytes,
                        restore_script_path=f"/home/root/{backup_name}/restore.sh"
                    )
                    
                    backups.append(backup_info)
                    
            except Exception as e:
                self._log_output(f"Warning: Could not read info for backup {backup_name}: {e}")
                continue
        
        self._log_output(f"Found {len(backups)} backups")
        return backups
    
    def restore_from_backup(self, backup_name: str, 
                           verify_before_restore: bool = True) -> bool:
        """
        Restore system from a backup.
        
        Args:
            backup_name: Name of backup to restore from
            verify_before_restore: Whether to verify backup before restoring
            
        Returns:
            True if restore successful
            
        Raises:
            Exception: If restore fails
        """
        if not self.network_service.is_connected():
            if not self.network_service.connect():
                raise Exception("Cannot connect to device for restore")
        
        self.current_backup_name = backup_name
        self._update_progress(BackupStatus.RESTORING, 0, "Starting system restore...")
        
        try:
            # Verify backup exists and is valid
            if verify_before_restore:
                self._update_progress(BackupStatus.VALIDATING, 10, "Validating backup...")
                if not self._validate_backup(backup_name):
                    raise Exception(f"Backup validation failed: {backup_name}")
            
            self._update_progress(BackupStatus.RESTORING, 25, "Executing restore script...")
            self._log_output(f"Restoring system from backup: {backup_name}")
            
            # Execute restore script
            restore_result = self.network_service.execute_command(
                f"/home/root/{backup_name}/restore.sh",
                timeout=120
            )
            
            if not restore_result.success:
                raise Exception(f"Restore script failed: {restore_result.stderr}")
            
            self._update_progress(BackupStatus.RESTORING, 75, "Verifying restore...")
            
            # Give the system time to restart services
            time.sleep(10)
            
            self._update_progress(BackupStatus.RESTORING, 90, "Checking system status...")
            
            # Verify system is responsive after restore
            status_check = self.network_service.execute_command("systemctl is-active xochitl", timeout=30)
            if status_check.success:
                self._log_output("System restore completed successfully")
                self._update_progress(BackupStatus.COMPLETED, 100, "Restore completed successfully")
                return True
            else:
                self._log_output("Warning: System may still be restarting after restore")
                self._update_progress(BackupStatus.COMPLETED, 100, "Restore completed (system restarting)")
                return True
                
        except Exception as e:
            self._update_progress(BackupStatus.FAILED, 0, f"Restore failed: {e}")
            raise Exception(f"System restore failed: {e}")
        
        finally:
            self.current_operation = None
            self.current_backup_name = None
    
    def delete_backup(self, backup_name: str) -> bool:
        """
        Delete a backup from the device.
        
        Args:
            backup_name: Name of backup to delete
            
        Returns:
            True if deletion successful
        """
        if not self.network_service.is_connected():
            if not self.network_service.connect():
                raise Exception("Cannot connect to device to delete backup")
        
        self._log_output(f"Deleting backup: {backup_name}")
        
        # Verify backup exists before attempting deletion
        check_result = self.network_service.execute_command(
            f"test -d /home/root/{backup_name} && echo 'exists' || echo 'not found'"
        )
        
        if not check_result.success or "not found" in check_result.stdout:
            self._log_output(f"Backup not found: {backup_name}")
            return False
        
        # Delete backup directory
        delete_result = self.network_service.execute_command(
            f"rm -rf /home/root/{backup_name}"
        )
        
        if delete_result.success:
            self._log_output(f"Backup deleted successfully: {backup_name}")
            return True
        else:
            self._log_output(f"Failed to delete backup: {delete_result.stderr}")
            return False
    
    def prune_backups(self, keep_count: int = 3) -> tuple:
        """
        Prune old backups, keeping only a specified number of recent backups.
        This is the public method that can be called manually via a button.
        Also cleans up scattered backup files and obsolete shims.
        
        Args:
            keep_count: The number of recent backups to keep (default: 3)
            
        Returns:
            Tuple of (deleted_count, kept_count)
        """
        deleted_count = self._prune_old_backups(keep_count, is_manual=True)
        
        # Clean up scattered backup files
        scattered_count = self._cleanup_scattered_backup_files()
        deleted_count += scattered_count
        
        # Get current backup count after pruning
        try:
            current_backups = self.list_backups()
            kept_count = len(current_backups)
        except Exception:
            kept_count = keep_count  # Fallback estimate
        
        return (deleted_count, kept_count)
    
    def _prune_old_backups(self, keep_count: int = 3, is_manual: bool = False) -> int:
        """
        Prune old backups, keeping only a specified number of recent backups.
        
        Args:
            keep_count: The number of recent backups to keep (default: 3)
            is_manual: Whether this is a manual pruning operation
            
        Returns:
            Number of backups that were deleted
        """
        operation_type = "Manual backup pruning" if is_manual else "Automatic backup pruning"
        self._log_output(f"{operation_type}: Checking for old backups to prune...")
        
        deleted_count = 0
        
        try:
            # Get all existing backups
            backups = self.list_backups()
            
            if len(backups) <= keep_count:
                self._log_output(f"Found {len(backups)} backups, which is within the limit of {keep_count}")
                return deleted_count
            
            self._log_output(f"Found {len(backups)} backups, need to prune {len(backups) - keep_count} old ones")
            
            # Sort backups by timestamp (extract from backup name)
            # Backup names are in format: koreader_backup_<timestamp>
            def get_timestamp(backup_info):
                try:
                    # Extract timestamp from backup name
                    parts = backup_info.name.split('_')
                    if len(parts) >= 3 and parts[-1].isdigit():
                        return int(parts[-1])
                    else:
                        # Fallback to created_at if timestamp extraction fails
                        return int(backup_info.created_at.timestamp())
                except (ValueError, AttributeError):
                    # Fallback timestamp if all else fails
                    return 0
            
            # Sort backups by timestamp (oldest first)
            sorted_backups = sorted(backups, key=get_timestamp)
            
            # Calculate how many to delete
            num_to_delete = len(sorted_backups) - keep_count
            backups_to_delete = sorted_backups[:num_to_delete]
            
            # Delete old backups
            for backup_info in backups_to_delete:
                self._log_output(f"Deleting old backup: {backup_info.name}")
                success = self.delete_backup(backup_info.name)
                if success:
                    self._log_output(f"Successfully deleted old backup: {backup_info.name}")
                    deleted_count += 1
                else:
                    self._log_output(f"Warning: Failed to delete old backup: {backup_info.name}")
            
            self._log_output(f"Backup pruning completed. Deleted {deleted_count} backups, keeping {keep_count} most recent backups.")
            return deleted_count
            
        except Exception as e:
            self._log_output(f"Warning: Backup pruning failed: {e}")
            if is_manual:
                raise Exception(f"Manual backup pruning failed: {e}")
            # For automatic pruning, don't raise the exception - pruning failure shouldn't stop backup creation
            return deleted_count
    
    def get_backup_details(self, backup_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific backup.
        
        Args:
            backup_name: Name of backup to examine
            
        Returns:
            Dictionary with detailed backup information
        """
        if not self.network_service.is_connected():
            if not self.network_service.connect():
                return None
        
        # Get backup info file
        info_result = self.network_service.execute_command(
            f"cat /home/root/{backup_name}/backup_info.txt 2>/dev/null"
        )
        
        # Get components list
        components_result = self.network_service.execute_command(
            f"cat /home/root/{backup_name}/components.txt 2>/dev/null"
        )
        
        # Get metadata
        metadata_result = self.network_service.execute_command(
            f"cat /home/root/{backup_name}/metadata.txt 2>/dev/null"
        )
        
        if not info_result.success:
            return None
        
        details = {
            "name": backup_name,
            "info_text": info_result.stdout,
            "components": [],
            "metadata": {},
            "files": []
        }
        
        # Parse components
        if components_result.success:
            details["components"] = [
                comp.strip() for comp in components_result.stdout.split('\n') 
                if comp.strip()
            ]
        
        # Parse metadata
        if metadata_result.success:
            for line in metadata_result.stdout.split('\n'):
                if '=' in line:
                    key, value = line.split('=', 1)
                    details["metadata"][key] = value
        
        # List backup files - BusyBox compatible
        files_result = self.network_service.execute_command(
            f"find /home/root/{backup_name} -type f | head -n 20"
        )
        if files_result.success:
            details["files"] = [
                f.strip() for f in files_result.stdout.split('\n') 
                if f.strip()
            ]
        
        return details
    
    def _cleanup_scattered_backup_files(self) -> int:
        """
        Clean up ONLY scattered backup-related files that are clearly safe to remove.
        Does NOT remove any .so files or active system components.
        
        Returns:
            Number of scattered files deleted
        """
        self._log_output("Cleaning up scattered backup files (log files only)...")
        deleted_count = 0
        
        try:
            # ONLY clean up log files that are clearly backup-related
            # DO NOT remove .so files, shims, or any active system components
            backup_log_files = [
                "/home/root/system_backup_log.txt",
                "/home/root/recovery_log.txt",
                "/tmp/backups.list"
            ]
            
            # Clean up only backup log files
            for file_path in backup_log_files:
                result = self.network_service.execute_command(
                    f"test -f {file_path} && rm -f {file_path} && echo 'deleted' || echo 'not found'"
                )
                if result.success and "deleted" in result.stdout:
                    self._log_output(f"Removed backup log file: {file_path}")
                    deleted_count += 1
            
            # DO NOT touch .so files or shims - they are needed for the system
            self._log_output("NOTE: Preserving all .so files and shims as they are needed for system operation")
            
            if deleted_count > 0:
                self._log_output(f"Safe backup cleanup completed: {deleted_count} log files removed")
            else:
                self._log_output("No scattered backup log files found to clean up")
                
            return deleted_count
            
        except Exception as e:
            self._log_output(f"Warning: Failed to clean up scattered backup files: {e}")
            return 0


# Global backup service instance
_global_backup_service: Optional[BackupService] = None


def get_backup_service() -> BackupService:
    """
    Get the global backup service instance.
    
    Returns:
        Global BackupService instance
        
    Raises:
        RuntimeError: If backup service hasn't been initialized
    """
    global _global_backup_service
    if _global_backup_service is None:
        raise RuntimeError("Backup service not initialized. Call init_backup_service() first.")
    return _global_backup_service


def init_backup_service(network_service: NetworkService, file_service: FileService) -> BackupService:
    """
    Initialize the global backup service.
    
    Args:
        network_service: Network service instance
        file_service: File service instance
        
    Returns:
        Initialized BackupService instance
    """
    global _global_backup_service
    
    _global_backup_service = BackupService(network_service, file_service)
    return _global_backup_service


# Convenience functions

def create_backup(**kwargs) -> BackupInfo:
    """Create a backup (convenience function)."""
    return get_backup_service().create_backup(**kwargs)


def list_backups() -> List[BackupInfo]:
    """List backups (convenience function)."""
    return get_backup_service().list_backups()


def restore_from_backup(backup_name: str, **kwargs) -> bool:
    """Restore from backup (convenience function)."""
    return get_backup_service().restore_from_backup(backup_name, **kwargs)


def delete_backup(backup_name: str) -> bool:
    """Delete backup (convenience function)."""
    return get_backup_service().delete_backup(backup_name)


def prune_backups(keep_count: int = 3) -> int:
    """Prune old backups (convenience function)."""
    return get_backup_service().prune_backups(keep_count)