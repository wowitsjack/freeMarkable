"""
Installation orchestration service for freeMarkable.

This module provides the main installation coordination logic, managing the
two-stage installation process, download management, device communication,
and progress tracking for the complete XOVI + AppLoad + KOReader installation.
"""

import os
import time
import logging
import tempfile
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from enum import Enum
from dataclasses import dataclass

from .network_service import NetworkService
from .file_service import FileService  
from .backup_service import BackupService
from ..models.device import Device
from ..models.installation_state import InstallationState, InstallationStage, StageStatus
from ..config.settings import AppConfig


class InstallationType(Enum):
    """Types of installation supported."""
    FULL = "full"  # XOVI + AppLoader + KOReader
    LAUNCHER_ONLY = "launcher_only"  # XOVI + AppLoader only
    STAGE_1_ONLY = "stage_1_only"  # Stage 1 setup only
    STAGE_2_ONLY = "stage_2_only"  # Stage 2 KOReader only


@dataclass
class InstallationProgress:
    """Progress information for installation operations."""
    stage: InstallationStage
    progress_percentage: float
    message: str
    current_step: str
    error_message: Optional[str] = None


class InstallationService:
    """
    Main installation orchestration service.
    
    Coordinates the complete installation process including downloads,
    device communication, backup creation, and two-stage installation.
    """
    
    def __init__(self, config: AppConfig, network_service: NetworkService, 
                 file_service: FileService, device: Device):
        """
        Initialize installation service.
        
        Args:
            config: Application configuration
            network_service: Network service for SSH operations
            file_service: File service for downloads
            device: Target device instance
        """
        self.config = config
        self.network_service = network_service
        self.file_service = file_service
        self.device = device
        
        # State management
        self.installation_state: Optional[InstallationState] = None
        self.current_operation: Optional[str] = None
        
        # Progress callbacks
        self.progress_callback: Optional[Callable[[InstallationProgress], None]] = None
        self.output_callback: Optional[Callable[[str], None]] = None
        
        self._logger = logging.getLogger(__name__)
        
        # Download URLs from config - will be updated based on device architecture
        self.download_urls = {}
        self._update_urls_for_device()
    
    def set_progress_callback(self, callback: Callable[[InstallationProgress], None]) -> None:
        """Set progress callback for installation updates."""
        self.progress_callback = callback
    
    def set_output_callback(self, callback: Callable[[str], None]) -> None:
        """Set output callback for installation messages."""
        self.output_callback = callback
    
    def _update_urls_for_device(self) -> None:
        """Update download URLs based on device architecture."""
        device_type = self.device.device_type if hasattr(self.device, 'device_type') else None
        
        # Get architecture-specific URLs
        self.download_urls = {
            'xovi_extensions': self.config.downloads.get_url_for_architecture('xovi_extensions', device_type),
            'appload': self.config.downloads.get_url_for_architecture('appload', device_type),
            'xovi_binary': self.config.downloads.get_url_for_architecture('xovi_binary', device_type),
            'koreader': self.config.downloads.get_url_for_architecture('koreader', device_type),
            'xovi_tripletap': self.config.downloads.xovi_tripletap_url,  # This doesn't have arch variants
            'appload_extension': 'https://github.com/asivery/rm-xovi-extensions/releases/latest/download/appload.so'
        }
        
        # Get architecture-specific filenames
        self.download_filenames = {
            'xovi_extensions': self.config.downloads.get_filename_for_architecture('xovi_extensions', device_type),
            'appload': self.config.downloads.get_filename_for_architecture('appload', device_type),
            'xovi_binary': self.config.downloads.get_filename_for_architecture('xovi_binary', device_type),
            'koreader': self.config.downloads.get_filename_for_architecture('koreader', device_type)
        }
        
        self._log_output(f"Updated URLs for device architecture: {device_type.architecture if device_type and hasattr(device_type, 'architecture') else 'default'}")
    
    def _log_output(self, message: str) -> None:
        """Log output message."""
        self._logger.info(message)
        if self.output_callback:
            self.output_callback(message)
    
    def _update_progress(self, stage: InstallationStage, progress: float, 
                        message: str, current_step: str = "") -> None:
        """Update installation progress."""
        if self.progress_callback:
            progress_info = InstallationProgress(
                stage=stage,
                progress_percentage=progress,
                message=message,
                current_step=current_step
            )
            self.progress_callback(progress_info)
    
    def start_installation(self, installation_type: InstallationType,
                          continue_from_stage: Optional[InstallationStage] = None) -> bool:
        """
        Start the installation process.
        
        Args:
            installation_type: Type of installation to perform
            continue_from_stage: Stage to continue from (for resuming)
            
        Returns:
            True if installation successful, False otherwise
        """
        try:
            self._log_output(f"Starting {installation_type.value} installation")
            
            # Initialize or load installation state
            if continue_from_stage:
                self.installation_state = InstallationState.load_from_file(
                    self.config.get_stage_file_path()
                )
                if not self.installation_state:
                    self._log_output("No saved state found, starting from beginning")
                    self.installation_state = InstallationState()
            else:
                self.installation_state = InstallationState()
            
            # Set up network service
            if not self._setup_network_connection():
                return False
            
            # Determine stages to run
            stages_to_run = self._determine_stages(installation_type, continue_from_stage)
            
            # Execute installation stages
            for stage in stages_to_run:
                if not self._execute_stage(stage):
                    self._log_output(f"Installation failed at {stage.value}")
                    return False
                
                # Save state after each stage
                self.installation_state.save_to_file(self.config.get_stage_file_path())
            
            # Mark installation complete
            self.installation_state.current_stage = InstallationStage.COMPLETED
            self.installation_state.save_to_file(self.config.get_stage_file_path())
            
            self._log_output("Installation completed successfully!")
            self._update_progress(InstallationStage.COMPLETED, 100, "Installation complete")
            
            return True
            
        except Exception as e:
            self._log_output(f"Installation failed: {e}")
            self._logger.error(f"Installation failed: {e}")
            return False
    
    def _setup_network_connection(self) -> bool:
        """Setup network connection to device."""
        if not self.device.is_configured():
            self._log_output("Device not configured properly")
            return False
        
        self.network_service.set_connection_details(
            hostname=self.device.ip_address,
            password=self.device.ssh_password
        )
        
        if not self.network_service.connect():
            self._log_output("Failed to connect to device")
            return False
        
        self._log_output("Connected to device successfully")
        return True
    
    def _determine_stages(self, installation_type: InstallationType, 
                         continue_from: Optional[InstallationStage]) -> List[InstallationStage]:
        """Determine which stages to run based on installation type."""
        if installation_type == InstallationType.STAGE_1_ONLY:
            return [InstallationStage.STAGE_1]
        elif installation_type == InstallationType.STAGE_2_ONLY:
            return [InstallationStage.STAGE_2]
        elif installation_type == InstallationType.LAUNCHER_ONLY:
            return [InstallationStage.LAUNCHER_ONLY]
        else:  # FULL installation
            stages = [InstallationStage.STAGE_1, InstallationStage.STAGE_2]
            
            # Filter stages if continuing from a specific point
            if continue_from:
                try:
                    start_index = stages.index(continue_from)
                    stages = stages[start_index:]
                except ValueError:
                    pass  # Continue from beginning if stage not found
            
            return stages
    
    def _execute_stage(self, stage: InstallationStage) -> bool:
        """Execute a specific installation stage."""
        self._log_output(f"Executing {stage.value}")
        self.installation_state.current_stage = stage
        
        if stage == InstallationStage.STAGE_1:
            return self._execute_stage_1()
        elif stage == InstallationStage.STAGE_2:
            return self._execute_stage_2()
        elif stage == InstallationStage.LAUNCHER_ONLY:
            return self._execute_launcher_only()
        else:
            self._log_output(f"Unknown stage: {stage}")
            return False
    
    def _execute_stage_1(self) -> bool:
        """Execute Stage 1: Setup, backup, XOVI installation, hashtable rebuild."""
        self._update_progress(InstallationStage.STAGE_1, 0, "Starting Stage 1 setup")
        
        try:
            # Step 1: Create backup
            if not self._create_backup():
                return False
            self._update_progress(InstallationStage.STAGE_1, 20, "Backup created")
            
            # Step 2: Download required files
            if not self._download_stage_1_files():
                return False
            self._update_progress(InstallationStage.STAGE_1, 40, "Files downloaded")
            
            # Step 3: Install XOVI framework
            if not self._install_xovi_framework():
                return False
            self._update_progress(InstallationStage.STAGE_1, 70, "XOVI framework installed")
            
            # Step 4: Install AppLoad launcher
            if not self._install_appload():
                return False
            self._update_progress(InstallationStage.STAGE_1, 85, "AppLoad installed")
            
            # Step 5: Rebuild hashtable and restart
            if not self._rebuild_hashtable_and_restart():
                return False
            self._update_progress(InstallationStage.STAGE_1, 90, "Hashtable rebuilt")
            
            # Note: XOVI activation will be done at the very end of the complete installation
            self._update_progress(InstallationStage.STAGE_1, 100, "Stage 1 complete - XOVI framework ready")
            
            return True
            
        except Exception as e:
            self._log_output(f"Stage 1 failed: {e}")
            return False
    
    def _execute_stage_2(self) -> bool:
        """Execute Stage 2: KOReader installation."""
        self._update_progress(InstallationStage.STAGE_2, 0, "Starting Stage 2 - KOReader installation")
        
        try:
            # Step 1: Download KOReader
            if not self._download_koreader():
                return False
            self._update_progress(InstallationStage.STAGE_2, 30, "KOReader downloaded")
            
            # Step 2: Install KOReader
            if not self._install_koreader():
                return False
            self._update_progress(InstallationStage.STAGE_2, 80, "KOReader installed")
            
            # Step 3: Final configuration and XOVI activation
            if not self._final_configuration():
                return False
            self._update_progress(InstallationStage.STAGE_2, 90, "Final configuration complete")
            
            # Step 4: CRITICAL FIX - Ensure XOVI is activated (in case Stage 2 is run standalone)
            if not self._activate_xovi():
                return False
            self._update_progress(InstallationStage.STAGE_2, 100, "Stage 2 complete - XOVI activated")
            
            return True
            
        except Exception as e:
            self._log_output(f"Stage 2 failed: {e}")
            return False
    
    def _execute_launcher_only(self) -> bool:
        """Execute launcher-only installation (XOVI + AppLoad without KOReader)."""
        self._update_progress(InstallationStage.LAUNCHER_ONLY, 0, "Starting launcher installation")
        
        try:
            # This is essentially Stage 1 without the promise of Stage 2
            if not self._create_backup():
                return False
            self._update_progress(InstallationStage.LAUNCHER_ONLY, 25, "Backup created")
            
            if not self._download_stage_1_files():
                return False
            self._update_progress(InstallationStage.LAUNCHER_ONLY, 50, "Files downloaded")
            
            if not self._install_xovi_framework():
                return False
            self._update_progress(InstallationStage.LAUNCHER_ONLY, 75, "XOVI framework installed")
            
            if not self._install_appload():
                return False
            self._update_progress(InstallationStage.LAUNCHER_ONLY, 90, "AppLoad installed")
            
            if not self._rebuild_hashtable_and_restart():
                return False
            self._update_progress(InstallationStage.LAUNCHER_ONLY, 95, "System restarting with launcher")

            # Final step: Activate XOVI
            if not self._activate_xovi():
                return False

            self._update_progress(InstallationStage.LAUNCHER_ONLY, 100, "Launcher installation complete, XOVI is active")
            
            return True
            
        except Exception as e:
            self._log_output(f"Launcher installation failed: {e}")
            return False
    
    def _create_backup(self) -> bool:
        """Create system backup before installation."""
        self._log_output("Creating system backup...")
        
        try:
            from .backup_service import get_backup_service
            backup_service = get_backup_service()
            
            backup_info = backup_service.create_backup()
            self._log_output(f"Backup created: {backup_info.name}")
            return True
            
        except Exception as e:
            self._log_output(f"Backup creation failed: {e}")
            return False
    
    def _download_stage_1_files(self) -> bool:
        """Download files needed for Stage 1."""
        self._log_output("Downloading required files...")
        
        # Update URLs for current device before downloading
        self._update_urls_for_device()
        
        files_to_download = [
            ('xovi_extensions', self.download_filenames['xovi_extensions']),
            ('appload', self.download_filenames['appload']),
            ('xovi_binary', self.download_filenames['xovi_binary'])
        ]
        
        try:
            for url_key, filename in files_to_download:
                url = self.download_urls[url_key]
                self._log_output(f"Downloading {filename}...")
                
                file_item = self.file_service.download_file(url, filename)
                self._log_output(f"Downloaded {filename} ({file_item.size} bytes)")
            
            # Extract appload package locally like Bash script does (line 556)
            self._log_output("Extracting AppLoad package locally...")
            appload_filename = self.download_filenames['appload']
            appload_zip = self.config.get_downloads_directory() / appload_filename
            if appload_zip.exists():
                import zipfile
                with zipfile.ZipFile(appload_zip, 'r') as zip_ref:
                    zip_ref.extractall(self.config.get_downloads_directory())
                self._log_output("AppLoad package extracted to downloads directory")
            
            return True
            
        except Exception as e:
            self._log_output(f"Download failed: {e}")
            return False
    
    def _download_koreader(self) -> bool:
        """Download KOReader for Stage 2."""
        self._log_output("Downloading KOReader...")
        
        try:
            # Update URLs for current device before downloading
            self._update_urls_for_device()
            
            url = self.download_urls['koreader']
            filename = self.download_filenames['koreader']
            file_item = self.file_service.download_file(url, filename)
            self._log_output(f"Downloaded KOReader ({file_item.size} bytes)")
            return True
            
        except Exception as e:
            self._log_output(f"KOReader download failed: {e}")
            return False
    
    def _install_xovi_framework(self) -> bool:
        """Install XOVI framework on device."""
        self._log_output("Installing XOVI framework...")
        
        try:
            # Upload and extract XOVI extensions
            extensions_filename = self.download_filenames['xovi_extensions']
            extensions_file = self.config.get_downloads_directory() / extensions_filename
            self._log_output(f"Uploading extensions file: {extensions_file}")
            if not self.network_service.upload_file(extensions_file, '/home/root/extensions.zip'):
                self._log_output("Failed to upload extensions file")
                return False
            
            # Upload all required files like Bash script (line 574)
            downloads_dir = self.config.get_downloads_directory()
            xovi_binary_filename = self.download_filenames['xovi_binary']
            files_to_upload = [
                (xovi_binary_filename, xovi_binary_filename),
                ('appload.so', 'appload.so'),  # From extracted appload package
                ('qtfb-shim.so', 'qtfb-shim.so'),  # From extracted appload package
                ('qtfb-shim-32bit.so', 'qtfb-shim-32bit.so')  # From extracted appload package
            ]
            
            for local_file, remote_file in files_to_upload:
                local_path = downloads_dir / local_file
                if local_path.exists():
                    self._log_output(f"Uploading {local_file}...")
                    if not self.network_service.upload_file(local_path, f'/home/root/{remote_file}'):
                        self._log_output(f"Failed to upload {local_file}")
                        return False
                else:
                    self._log_output(f"Warning: {local_file} not found, skipping")
            
            # SIMPLIFIED: Break down the complex command into smaller parts for better error handling
            self._log_output("Starting XOVI framework setup...")
            
            # Step 1: Clean up and extract
            result1 = self.network_service.execute_command("cd /home/root && rm -rf extensions-arm32-testing/ 2>/dev/null || true")
            if not result1.success:
                self._log_output(f"Cleanup failed: {result1.stderr}")
                return False
                
            result2 = self.network_service.execute_command("cd /home/root && unzip -o extensions.zip")
            if not result2.success:
                self._log_output(f"Unzip failed: {result2.stderr}")
                return False
            
            self._log_output(f"Unzip output: {result2.stdout}")
            
            # Step 2b: Check what was actually extracted
            result3 = self.network_service.execute_command("cd /home/root && ls -la")
            self._log_output(f"Root directory contents after unzip: {result3.stdout}")
            
            # The zip extracts files directly, not into a directory! Let's move the .so files
            self._log_output("Zip extracts files directly - moving .so files to extensions directory")
            
            # Step 3: Create directory structure
            result4 = self.network_service.execute_command("cd /home/root && mkdir -p xovi/extensions.d xovi")
            if not result4.success:
                self._log_output(f"Directory creation failed: {result4.stderr}")
                return False
            
            # Step 4: Move all the .so extension files to the extensions directory
            extension_files = [
                "fileman.so",
                "framebuffer-spy.so",
                "qt-command-executor.so",
                "qt-resource-rebuilder.so",
                "random-suspend-screen.so",
                "webserver-remote.so",
                "xovi-message-broker.so"
            ]
            
            for ext_file in extension_files:
                result5 = self.network_service.execute_command(f"cd /home/root && mv {ext_file} xovi/extensions.d/ 2>/dev/null || echo 'File {ext_file} not found'")
                if "not found" in result5.stdout:
                    self._log_output(f"Warning: {ext_file} was not found, skipping")
                else:
                    self._log_output(f"Moved {ext_file} to extensions directory")
            
            # Step 5: Fix permissions for extension files
            result6 = self.network_service.execute_command("cd /home/root && chmod +x xovi/extensions.d/*.so 2>/dev/null || echo 'No .so files to chmod'")
            self._log_output(f"Permission setting result: {result6.stdout}")
            
            # Step 6: Install XOVI binary
            xovi_binary_filename = self.download_filenames['xovi_binary']
            result7 = self.network_service.execute_command(f"cd /home/root && mv {xovi_binary_filename} xovi/xovi.so && chmod +x xovi/xovi.so")
            if not result7.success:
                self._log_output(f"XOVI binary installation failed: {result7.stderr}")
                return False
            
            # Step 6b: Install AppLoad extension to extensions directory (appload.so already uploaded)
            self._log_output("Installing AppLoad extension from uploaded files...")
            result6c = self.network_service.execute_command("cd /home/root && cp appload.so xovi/extensions.d/ && chmod +x xovi/extensions.d/appload.so")
            if not result6c.success:
                self._log_output(f"AppLoad extension installation failed: {result6c.stderr}")
                return False
            
            self._log_output("AppLoad extension binary installed!")
            
            # Step 6c: Setup shim files (exact Bash script logic - lines 735-738)
            self._log_output("Setting up qtfb-shim files...")
            
            # Create shims directory and copy shim files (exact Bash script logic)
            result6d = self.network_service.execute_command("""
                mkdir -p /home/root/shims
                cp /home/root/qtfb-shim.so /home/root/shims/ 2>/dev/null || echo 'qtfb-shim.so not found'
                cp /home/root/qtfb-shim-32bit.so /home/root/shims/ 2>/dev/null || echo 'qtfb-shim-32bit.so not found'
                echo 'Shim files setup completed'
            """)
            if not result6d.success:
                self._log_output(f"Shim files setup failed: {result6d.stderr}")
                return False
                
            self._log_output("Shim files configured successfully!")
            self._log_output("Basic XOVI setup completed, now creating essential scripts...")
            
            # Step 7: Create the CRITICAL start script (MISSING in original Python implementation!)
            start_script_content = '''#!/bin/bash
mkdir -p /etc/systemd/system/xochitl.service.d
mount -t tmpfs tmpfs /etc/systemd/system/xochitl.service.d
cat << END > /etc/systemd/system/xochitl.service.d/xovi.conf
[Service]
Environment="QML_DISABLE_DISK_CACHE=1"
Environment="QML_XHR_ALLOW_FILE_WRITE=1"
Environment="QML_XHR_ALLOW_FILE_READ=1"
Environment="LD_PRELOAD=/home/root/xovi/xovi.so"
END

systemctl daemon-reload
systemctl restart xochitl'''
            
            # Create start script using a safer method - avoid heredoc embedding issues
            result7a = self.network_service.execute_command(f"cd /home/root && echo \"{start_script_content}\" > xovi/start")
            if not result7a.success:
                self._log_output(f"Start script creation failed: {result7a.stderr}")
                return False
            
            result7b = self.network_service.execute_command("cd /home/root && chmod +x xovi/start")
            if not result7b.success:
                self._log_output(f"Start script permission setting failed: {result7b.stderr}")
                return False
            
            # Step 8: Create stop script
            stop_script_content = '''#!/bin/bash
# WARNING: This script stops XOVI and disables USB ethernet gadget
# ONLY use this in restore/uninstall scripts, NEVER during live operations
umount /etc/systemd/system/xochitl.service.d 2>/dev/null || true
rmdir /etc/systemd/system/xochitl.service.d 2>/dev/null || true
systemctl daemon-reload
systemctl restart xochitl'''
            
            result7c = self.network_service.execute_command(f"cd /home/root && echo \"{stop_script_content}\" > xovi/stop")
            if not result7c.success:
                self._log_output(f"Stop script creation failed: {result7c.stderr}")
                return False
            
            result7d = self.network_service.execute_command("cd /home/root && chmod +x xovi/stop")
            if not result7d.success:
                self._log_output(f"Stop script permission setting failed: {result7d.stderr}")
                return False

            # Step 9: Create the rebuild script in a separate step for better debugging
            rebuild_script_content = '''#!/bin/bash

if [[ ! -e '/home/root/xovi/extensions.d/qt-resource-rebuilder.so' ]]; then
    echo "Please install qt-resource-rebuilder before updating the hashtable"
    exit 1
fi

echo "Rebuilding hashtable..."

# stop systemwide gui process
systemctl stop xochitl.service

if pidof xochitl; then
  kill -15 $(pidof xochitl)
fi

# make sure the resource-rebuilder folder exists.
mkdir -p /home/root/xovi/exthome/qt-resource-rebuilder

# remove the actual hashtable
rm -f /home/root/xovi/exthome/qt-resource-rebuilder/hashtab

echo "Starting hashtable rebuild process..."
echo "This may take several minutes. Progress will be shown below:"
echo ""

# start update hashtab process with visible output
QMLDIFF_HASHTAB_CREATE=/home/root/xovi/exthome/qt-resource-rebuilder/hashtab QML_DISABLE_DISK_CACHE=1 LD_PRELOAD=/home/root/xovi/xovi.so /usr/bin/xochitl 2>&1 | while IFS= read line; do
  echo "$line"
  if [[ "$line" == "[qmldiff]: Hashtab saved to /home/root/xovi/exthome/qt-resource-rebuilder/hashtab" ]]; then
    # found the completion line, kill the process
    kill -15 $(pidof xochitl)
  fi
done

echo ""
echo "Hashtable rebuild completed. Restarting xochitl service..."

# wait then restart systemd service
sleep 5
systemctl start xochitl.service

echo "XOVI hashtable rebuild completed successfully!"'''
            
            # Write the script content to a file
            result8 = self.network_service.execute_command(f"cd /home/root && cat > xovi/rebuild-hashtable.sh << 'REBUILD_EOF'\\n{rebuild_script_content}\\nREBUILD_EOF")
            if not result8.success:
                self._log_output(f"Rebuild script creation failed: {result8.stderr}")
                return False
            
            # Make it executable
            result9 = self.network_service.execute_command("cd /home/root && chmod +x xovi/rebuild-hashtable.sh")
            if not result9.success:
                self._log_output(f"Script permission setting failed: {result9.stderr}")
                return False
            
            # Cleanup - remove the zip file and any remaining install script
            result10 = self.network_service.execute_command("cd /home/root && rm -f extensions.zip install-xovi-for-rm")
            if not result10.success:
                self._log_output(f"Cleanup failed: {result10.stderr}")
                # Continue anyway
            
            self._log_output("XOVI framework installation completed successfully!")
            return True
            
        except Exception as e:
            self._log_output(f"XOVI installation failed: {e}")
            return False
    
    def _install_appload(self) -> bool:
        """Install AppLoad launcher - following Bash script exactly (lines 1055-1064, 749-751)."""
        self._log_output("Installing AppLoad launcher...")
        
        try:
            # Step 1: Create AppLoad directory structure (Bash lines 1055-1057)
            self._log_output("Creating AppLoad directory structure...")
            result1 = self.network_service.execute_command("mkdir -p /home/root/xovi/exthome/appload")
            if not result1.success:
                self._log_output(f"AppLoad directory creation failed: {result1.stderr}")
                return False
            
            # Step 2: Configure AppLoad extension (Bash lines 749-751)
            # The appload.so should already be installed to extensions.d by _install_xovi_framework
            self._log_output("Configuring AppLoad extension...")
            result2 = self.network_service.execute_command("echo 'enabled=1' > /home/root/xovi/extensions.d/appload.so.conf")
            if not result2.success:
                self._log_output(f"AppLoad configuration failed: {result2.stderr}")
                return False
            
            # Step 3: Verify AppLoad is properly installed
            verify_result = self.network_service.execute_command("ls -la /home/root/xovi/extensions.d/appload.so* && cat /home/root/xovi/extensions.d/appload.so.conf")
            if verify_result.success:
                self._log_output(f"AppLoad verification: {verify_result.stdout}")
            else:
                self._log_output("Warning: AppLoad verification failed, but continuing...")
            
            self._log_output("AppLoad launcher installed and configured successfully")
            return True
            
        except Exception as e:
            self._log_output(f"AppLoad installation failed: {e}")
            return False
    
    def _install_koreader(self) -> bool:
        """Install KOReader application - following Bash script exactly (lines 1042-1067)."""
        self._log_output("Installing KOReader...")
        
        try:
            # Upload KOReader zip file to device
            koreader_filename = self.download_filenames['koreader']
            koreader_file = self.config.get_downloads_directory() / koreader_filename
            if not self.network_service.upload_file(koreader_file, f'/home/root/{koreader_filename}'):
                return False
            
            # Extract and install following EXACT Bash script logic (lines 1046-1064)
            koreader_filename = self.download_filenames['koreader']
            result = self.network_service.execute_command(f"""
                cd /home/root
                
                # Remove old KOReader if it exists (line 1050)
                rm -rf koreader 2>/dev/null || true
                
                # Extract KOReader (line 1053)
                unzip -q {koreader_filename}
                
                # Create AppLoad directory structure (line 1056)
                mkdir -p /home/root/xovi/exthome/appload
                
                # Remove old KOReader from AppLoad directory (line 1059)
                rm -rf /home/root/xovi/exthome/appload/koreader 2>/dev/null || true
                
                # Move KOReader to AppLoad directory (line 1062) - CRITICAL STEP!
                mv /home/root/koreader /home/root/xovi/exthome/appload/
                
                echo 'KOReader extracted and moved to AppLoad directory'
            """)
            
            if not result.success:
                self._log_output(f"KOReader installation failed: {result.stderr}")
                return False
            
            self._log_output("KOReader installed successfully")
            return True
            
        except Exception as e:
            self._log_output(f"KOReader installation failed: {e}")
            return False
    
    def _rebuild_hashtable_and_restart(self) -> bool:
        """Rebuild hashtable and restart xochitl."""
        self._log_output("Rebuilding hashtable and restarting xochitl...")
        
        try:
            # Stop xochitl
            result = self.network_service.execute_command("systemctl stop xochitl")
            if not result.success:
                self._log_output("Warning: Could not stop xochitl")
            
            # Rebuild hashtable with real-time output and no timeout
            self._log_output("Starting hashtable rebuild - this may take several minutes...")
            result = self.network_service.execute_command(
                "cd /home/root/xovi && ./rebuild-hashtable.sh",
                timeout=None,  # No timeout - let it run as long as needed
                real_time_output=True  # Show real-time progress
            )
            
            if not result.success:
                self._log_output(f"Hashtable rebuild failed: {result.stderr}")
                return False
            
            # Start xochitl
            result = self.network_service.execute_command("systemctl start xochitl")
            if not result.success:
                self._log_output(f"Failed to restart xochitl: {result.stderr}")
                return False
            
            self._log_output("Hashtable rebuilt and xochitl restarted")
            return True
            
        except Exception as e:
            self._log_output(f"Hashtable rebuild failed: {e}")
            return False
    
    def _activate_xovi(self) -> bool:
        """Activates XOVI by creating a tmpfs override for the xochitl service."""
        self._log_output("Activating XOVI via tmpfs service override...")
        
        # This command sequence is taken directly from the Bash script's 'start' function
        # It's the core mechanism for injecting XOVI into the reMarkable UI
        
        # This command sequence is taken directly from the Bash script's 'start' function
        # It's the core mechanism for injecting XOVI into the reMarkable UI
        self._log_output("Activating XOVI via tmpfs service override...")
        
        # Use the start script we just created to ensure consistency
        result = self.network_service.execute_command("cd /home/root/xovi && ./start")
        
        if not result.success:
            self._log_output(f"CRITICAL: Failed to activate XOVI: {result.stderr}")
            self._log_output("This is a fatal error. The UI will likely not show the launcher.")
            return False
            
        self._log_output("XOVI activated successfully. The launcher should be visible after UI restart.")
        return True

    def _final_configuration(self) -> bool:
        """Perform final cleanup and restart xochitl to activate all components."""
        self._log_output("Performing final cleanup and system restart...")
        
        try:
            # Step 1: Cleanup installation files from device
            self._log_output("Cleaning up installation files from device...")
            
            cleanup_script = """
                rm -f /home/root/extensions.zip
                rm -f /home/root/koreader-remarkable.zip
                rm -f /home/root/appload.zip
                echo "Cleanup complete."
            """
            
            result = self.network_service.execute_command(cleanup_script)
            
            if not result.success:
                self._log_output(f"Warning: Cleanup may have failed: {result.stderr}")
                # Continue anyway - cleanup failure shouldn't stop final restart
            else:
                self._log_output("Final cleanup completed.")
            
            # Step 2: CRITICAL - Final restart to activate all installed components
            self._log_output("Performing final xochitl restart to activate all components...")
            
            restart_result = self.network_service.execute_command("systemctl restart xochitl")
            
            if not restart_result.success:
                self._log_output(f"Warning: Final restart failed: {restart_result.stderr}")
                # This is important but not fatal - user can restart manually
                return True
            
            self._log_output("Final restart completed - XOVI and KOReader should now be visible!")
            return True
            
        except Exception as e:
            self._log_output(f"Final configuration failed: {e}")
            return False


# Global installation service instance
_global_installation_service: Optional[InstallationService] = None


def get_installation_service() -> InstallationService:
    """
    Get the global installation service instance.
    
    Returns:
        Global InstallationService instance
        
    Raises:
        RuntimeError: If installation service hasn't been initialized
    """
    global _global_installation_service
    if _global_installation_service is None:
        raise RuntimeError("Installation service not initialized. Call init_installation_service() first.")
    return _global_installation_service


def init_installation_service(config: AppConfig, network_service: NetworkService,
                             file_service: FileService, device: Device) -> InstallationService:
    """
    Initialize the global installation service.
    
    Args:
        config: Application configuration
        network_service: Network service instance
        file_service: File service instance
        device: Target device instance
        
    Returns:
        Initialized InstallationService instance
    """
    global _global_installation_service
    
    _global_installation_service = InstallationService(
        config, network_service, file_service, device
    )
    return _global_installation_service


# Convenience functions

def start_installation(installation_type: InstallationType, **kwargs) -> bool:
    """Start installation (convenience function)."""
    return get_installation_service().start_installation(installation_type, **kwargs)