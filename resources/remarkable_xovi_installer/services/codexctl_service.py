"""
CodexCtl service for freeMarkable.

This module provides codexctl binary management, firmware operations, and integration
with the reMarkable device for firmware installation and restoration.
"""

import os
import platform
import subprocess
import threading
import time
import json
import zipfile
import tarfile
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Union, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import requests
from concurrent.futures import ThreadPoolExecutor

# SSL imports for macOS compatibility
try:
    import ssl
    import certifi
    # Create default SSL context for macOS
    ssl._create_default_https_context = ssl._create_unverified_context
except ImportError:
    pass  # SSL modules not available

from remarkable_xovi_installer.utils.logger import get_logger
from remarkable_xovi_installer.config.settings import get_config
from remarkable_xovi_installer.services.network_service import get_network_service


class CodexCtlOperation(Enum):
    """CodexCtl operation types."""
    INSTALL_FIRMWARE = "install_firmware"
    RESTORE_FIRMWARE = "restore_firmware"
    LIST_VERSIONS = "list_versions"
    GET_STATUS = "get_status"


@dataclass
class FirmwareVersion:
    """Represents a firmware version."""
    version: str
    build_id: str
    release_date: str
    is_supported: bool
    download_url: Optional[str] = None
    file_size: Optional[int] = None


@dataclass
class CodexCtlProgress:
    """Progress information for CodexCtl operations."""
    operation: CodexCtlOperation
    stage: str
    progress_percentage: float
    current_step: str
    message: str
    output_lines: List[str]


@dataclass
class CodexCtlResult:
    """Result of a CodexCtl operation."""
    success: bool
    operation: CodexCtlOperation
    output: str
    error: str
    execution_time: float
    firmware_info: Optional[Dict[str, Any]] = None


class CodexCtlService:
    """
    CodexCtl service for firmware management operations.
    
    Provides binary management, firmware operations, and progress tracking
    for codexctl integration with freeMarkable.
    """
    
    def __init__(self, binary_dir: Optional[Path] = None,
                 github_repo: str = "Jayy001/codexctl",
                 timeout: int = 300):
        """
        Initialize CodexCtl service.
        
        Args:
            binary_dir: Directory to store codexctl binaries
            github_repo: GitHub repository for codexctl releases
            timeout: Default timeout for operations in seconds
        """
        self.timeout = timeout
        self.github_repo = github_repo
        
        # Core services
        try:
            self.logger = get_logger()
        except RuntimeError:
            self.logger = logging.getLogger(__name__)
        
        try:
            self.config = get_config()
            if binary_dir is None:
                binary_dir = self.config.get_config_dir() / "codexctl"
        except RuntimeError:
            if binary_dir is None:
                binary_dir = Path.home() / ".freemarkable" / "codexctl"
        
        # Binary management
        self.binary_dir = Path(binary_dir)
        self.binary_dir.mkdir(parents=True, exist_ok=True)
        
        # Operation state
        self.current_operation: Optional[CodexCtlOperation] = None
        self.is_operation_running = False
        
        # Progress callbacks
        self.progress_callback: Optional[Callable[[CodexCtlProgress], None]] = None
        self.output_callback: Optional[Callable[[str], None]] = None
        self.binary_ready_callback: Optional[Callable[[], None]] = None
        
        # Thread management
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._operation_lock = threading.Lock()
        self._download_lock = threading.Lock()  # Prevent concurrent downloads
        self._download_in_progress = False  # Track download state
        
        # Cached data
        self._cached_versions: Optional[List[FirmwareVersion]] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_duration = 300  # 5 minutes
        
        # Compatibility tracking to avoid repeated warnings
        self._compatibility_warned = False
        self._glibc_issue_detected = False
        
        self.logger.info("CodexCtl service initialized")
        
        # Attempt to auto-fetch binary on launch if conditions are met
        try:
            self._auto_fetch_binary_on_launch()
        except Exception as e:
            self.logger.debug(f"Auto-fetch binary on launch failed: {e}")
    
    def set_progress_callback(self, callback: Callable[[CodexCtlProgress], None]) -> None:
        """Set callback for operation progress updates."""
        self.progress_callback = callback
    
    def set_output_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for real-time output."""
        self.output_callback = callback
    
    def set_binary_ready_callback(self, callback: Callable[[], None]) -> None:
        """Set callback to notify when binary becomes available."""
        self.binary_ready_callback = callback
    
    def get_platform_info(self) -> Tuple[str, str]:
        """
        Get platform information for binary selection.
        
        Returns:
            Tuple of (os_name, architecture)
        """
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        # Normalize OS names
        if system == "linux":
            os_name = "linux"
        elif system == "darwin":
            os_name = "macos"
        elif system == "windows":
            os_name = "windows"
        else:
            os_name = "linux"  # Default fallback
        
        # Normalize architecture
        if machine in ["x86_64", "amd64"]:
            arch = "x64"
        elif machine in ["aarch64", "arm64"]:
            arch = "arm64"
        elif machine.startswith("arm"):
            arch = "arm"
        else:
            arch = "x64"  # Default fallback
        
        return os_name, arch
    
    def get_binary_path(self) -> Path:
        """Get the path to the codexctl binary for current platform."""
        os_name, arch = self.get_platform_info()
        
        if os_name == "windows":
            binary_name = f"codexctl-{os_name}-{arch}.exe"
        else:
            binary_name = f"codexctl-{os_name}-{arch}"
        
        return self.binary_dir / binary_name
    
    def is_binary_available(self) -> bool:
        """Check if codexctl binary is available and executable."""
        binary_path = self.get_binary_path()
        
        if not binary_path.exists():
            return False
        
        # Check file size - should be reasonable (>1MB for codexctl)
        try:
            file_size = binary_path.stat().st_size
            if file_size < 1024 * 1024:  # Less than 1MB
                self.logger.debug(f"Binary file too small: {file_size} bytes")
                return False
        except Exception as e:
            self.logger.debug(f"Failed to check binary size: {e}")
            return False
        
        # Check if executable
        try:
            if os.name != 'nt':  # Not Windows
                os.chmod(binary_path, 0o755)
            
            # Test execution with version command
            result = subprocess.run(
                [str(binary_path), "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return True
            else:
                # Check if it's a GLIBC compatibility issue
                error_output = result.stderr.lower()
                if "glibc" in error_output or "version" in error_output:
                    self.logger.warning("CodexCtl binary has GLIBC compatibility issues - CodexCtl functionality disabled")
                    # Mark as incompatible due to GLIBC issues
                    return False
                else:
                    self.logger.debug(f"Binary execution failed: {result.stderr}")
                    return False
                    
        except Exception as e:
            self.logger.debug(f"Binary test failed: {e}")
            return False
    
    def is_system_compatible(self) -> bool:
        """Check if system is compatible with CodexCtl requirements."""
        import sys
        
        # Check Python version (3.12+ required)
        current_version = sys.version_info
        required_version = (3, 12)
        
        if current_version < required_version:
            return False
        
        # Check if binary can actually execute (GLIBC compatibility)
        if not self.is_binary_available():
            return False
        
        return True
    
    def download_binary(self, force: bool = False) -> bool:
        """
        Download codexctl binary from GitHub releases.
        
        Args:
            force: Force download even if binary exists
            
        Returns:
            True if download successful
        """
        # Prevent concurrent downloads with locking
        with self._download_lock:
            # Check if another download is already in progress
            if self._download_in_progress and not force:
                self.logger.debug("Download already in progress, waiting...")
                # Wait for other download to complete
                return self._wait_for_download_completion()
            
            binary_path = self.get_binary_path()
            
            # Double-check after acquiring lock - another thread might have succeeded
            if binary_path.exists() and not force:
                if self.is_binary_available():
                    self.logger.debug("CodexCtl binary already available (checked after lock)")
                    return True
            
            # Mark download as in progress
            self._download_in_progress = True
            
            try:
                self.logger.info("Downloading codexctl binary...")
                
                # Get latest release info
                release_info = self._get_latest_release()
                if not release_info:
                    self.logger.error("Could not get release information")
                    return False
                
                # Find appropriate asset
                os_name, arch = self.get_platform_info()
                asset_url = self._find_asset_url(release_info, os_name, arch)
                
                if not asset_url:
                    self.logger.error(f"No binary found for {os_name}-{arch}")
                    return False
                
                # Download and extract
                success = self._download_and_extract_binary(asset_url, binary_path)
                
                # Notify when binary is ready
                if success and self.binary_ready_callback:
                    self.binary_ready_callback()
                    
                return success
                
            except Exception as e:
                self.logger.error(f"Failed to download binary: {e}")
                return False
            finally:
                # Always clear download flag
                self._download_in_progress = False
                
    def _wait_for_download_completion(self) -> bool:
        """Wait for ongoing download to complete."""
        import time
        max_wait = 60  # Maximum 60 seconds
        wait_time = 0
        
        while self._download_in_progress and wait_time < max_wait:
            time.sleep(1)
            wait_time += 1
        
        # Check if binary is now available
        return self.is_binary_available()
    
    def _get_latest_release(self) -> Optional[Dict[str, Any]]:
        """Get latest release information from GitHub with retry logic."""
        url = f"https://api.github.com/repos/{self.github_repo}/releases/latest"
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Add headers to potentially avoid rate limiting
                headers = {
                    'User-Agent': 'freeMarkable-installer/1.0',
                    'Accept': 'application/vnd.github.v3+json'
                }
                
                response = requests.get(url, timeout=30, headers=headers)
                
                # Handle rate limiting specifically
                if response.status_code == 403:
                    # Check if it's rate limiting
                    if 'rate limit' in response.text.lower() or 'x-ratelimit-remaining' in response.headers:
                        remaining = response.headers.get('x-ratelimit-remaining', '0')
                        reset_time = response.headers.get('x-ratelimit-reset', 'unknown')
                        
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)  # Exponential backoff
                            self.logger.warning(f"GitHub API rate limit exceeded (remaining: {remaining}, reset: {reset_time}). Retrying in {delay}s...")
                            time.sleep(delay)
                            continue
                        else:
                            self.logger.error(f"GitHub API rate limit exceeded after {max_retries} attempts. Rate limit remaining: {remaining}, reset time: {reset_time}")
                            return None
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    self.logger.warning(f"GitHub API request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                else:
                    self.logger.error(f"Failed to get release info after {max_retries} attempts: {e}")
                    return None
            except Exception as e:
                self.logger.error(f"Unexpected error getting release info: {e}")
                return None
        
        return None
    
    def _find_asset_url(self, release_info: Dict[str, Any],
                       os_name: str, arch: str) -> Optional[str]:
        """Find download URL for the appropriate binary asset."""
        assets = release_info.get("assets", [])
        
        # Map our OS names to GitHub asset names
        asset_name_map = {
            "linux": "ubuntu-latest.zip",
            "macos": "macos-latest.zip",
            "windows": "windows-latest.zip"
        }
        
        target_name = asset_name_map.get(os_name)
        if not target_name:
            self.logger.error(f"No asset mapping for OS: {os_name}")
            return None
        
        # Look for exact matching asset
        for asset in assets:
            if asset["name"] == target_name:
                return asset["browser_download_url"]
        
        self.logger.error(f"Asset not found: {target_name}")
        self.logger.debug(f"Available assets: {[a['name'] for a in assets]}")
        return None
    
    def _download_and_extract_binary(self, url: str, target_path: Path) -> bool:
        """Download and extract binary from URL."""
        import tempfile
        import uuid
        
        try:
            self.logger.info(f"Downloading from {url}")
            
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            # Use unique temp file name to avoid race conditions
            temp_file = target_path.parent / f"{target_path.name}.tmp.{uuid.uuid4().hex[:8]}"
            
            try:
                with open(temp_file, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # Handle different archive types
                if url.endswith(".zip"):
                    self._extract_zip(temp_file, target_path)
                elif url.endswith((".tar.gz", ".tgz")):
                    self._extract_tar(temp_file, target_path)
                else:
                    # Direct binary file
                    temp_file.rename(target_path)
                
                # Make executable
                if os.name != 'nt':
                    os.chmod(target_path, 0o755)
                
                self.logger.info("Binary downloaded successfully")
                return True
                
            finally:
                # Always clean up temp file
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except Exception as cleanup_error:
                        self.logger.debug(f"Failed to cleanup temp file: {cleanup_error}")
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return False
    
    def _extract_zip(self, zip_path: Path, target_path: Path) -> None:
        """Extract binary from ZIP archive."""
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Find the binary file in the archive
            # Look for files that contain "codexctl" in the name
            for file_info in zip_ref.filelist:
                if file_info.is_dir():
                    continue
                
                filename = file_info.filename
                # Match codexctl binary (exact name or with platform suffix)
                if (filename == "codexctl" or
                    filename.startswith("codexctl-") or
                    filename.endswith("/codexctl") or
                    "codexctl" in filename.lower()):
                    
                    self.logger.debug(f"Extracting {filename} from ZIP")
                    with zip_ref.open(file_info) as src, open(target_path, 'wb') as dst:
                        dst.write(src.read())
                    return
        
        # List available files for debugging
        available_files = [f.filename for f in zip_ref.filelist if not f.is_dir()]
        raise RuntimeError(f"Binary not found in ZIP archive. Available files: {available_files}")
    
    def _extract_tar(self, tar_path: Path, target_path: Path) -> None:
        """Extract binary from TAR archive."""
        with tarfile.open(tar_path, 'r:gz') as tar_ref:
            # Find the binary file in the archive
            for member in tar_ref.getmembers():
                if member.isfile() and ("codexctl" in member.name):
                    with tar_ref.extractfile(member) as src, open(target_path, 'wb') as dst:
                        dst.write(src.read())
                    return
        
        raise RuntimeError("Binary not found in TAR archive")
    
    def ensure_binary_available(self) -> bool:
        """Ensure codexctl binary is available, downloading if necessary."""
        if self.is_binary_available():
            return True
        
        self.logger.info("CodexCtl binary not found, downloading...")
        return self.download_binary()
    
    def get_firmware_versions(self, force_refresh: bool = False) -> List[FirmwareVersion]:
        """
        Get available firmware versions.
        
        Args:
            force_refresh: Force refresh of cached data
            
        Returns:
            List of available firmware versions
        """
        # Check cache
        if (not force_refresh and self._cached_versions and 
            self._cache_timestamp and 
            time.time() - self._cache_timestamp < self._cache_duration):
            return self._cached_versions
        
        if not self.ensure_binary_available():
            self.logger.error("CodexCtl binary not available")
            return []
        
        try:
            binary_path = self.get_binary_path()
            result = subprocess.run(
                [str(binary_path), "list", "--json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.logger.error(f"Failed to list versions: {result.stderr}")
                return []
            
            # Parse JSON output
            data = json.loads(result.stdout)
            versions = []
            
            for item in data.get("versions", []):
                version = FirmwareVersion(
                    version=item.get("version", ""),
                    build_id=item.get("build_id", ""),
                    release_date=item.get("release_date", ""),
                    is_supported=item.get("supported", True),
                    download_url=item.get("download_url"),
                    file_size=item.get("file_size")
                )
                versions.append(version)
            
            # Cache results
            self._cached_versions = versions
            self._cache_timestamp = time.time()
            
            return versions
            
        except Exception as e:
            self.logger.error(f"Failed to get firmware versions: {e}")
            return []
    
    def get_device_status(self) -> Dict[str, Any]:
        """Get current device firmware status."""
        if not self.ensure_binary_available():
            return {"error": "CodexCtl binary not available"}
        
        try:
            # Get network service for device connection
            network_service = get_network_service()
            if not network_service.is_connected():
                return {"error": "Device not connected"}
            
            binary_path = self.get_binary_path()
            device_ip = network_service.hostname
            
            result = subprocess.run(
                [str(binary_path), "status", "--device", device_ip, "--json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return {"error": f"Status check failed: {result.stderr}"}
            
            return json.loads(result.stdout)
            
        except Exception as e:
            self.logger.error(f"Failed to get device status: {e}")
            return {"error": str(e)}
    
    def install_firmware(self, version: str, backup: bool = True) -> bool:
        """
        Install firmware version on device.
        
        Args:
            version: Firmware version to install
            backup: Whether to create backup before install
            
        Returns:
            True if installation successful
        """
        with self._operation_lock:
            if self.is_operation_running:
                self.logger.error("Another operation is already running")
                return False
            
            self.is_operation_running = True
            self.current_operation = CodexCtlOperation.INSTALL_FIRMWARE
        
        try:
            return self._execute_firmware_operation("install", version, backup)
        finally:
            with self._operation_lock:
                self.is_operation_running = False
                self.current_operation = None
    
    def restore_firmware(self, backup_path: Optional[str] = None) -> bool:
        """
        Restore firmware from backup.
        
        Args:
            backup_path: Path to backup file (optional)
            
        Returns:
            True if restore successful
        """
        with self._operation_lock:
            if self.is_operation_running:
                self.logger.error("Another operation is already running")
                return False
            
            self.is_operation_running = True
            self.current_operation = CodexCtlOperation.RESTORE_FIRMWARE
        
        try:
            return self._execute_firmware_operation("restore", backup_path or "latest")
        finally:
            with self._operation_lock:
                self.is_operation_running = False
                self.current_operation = None
    
    def _execute_firmware_operation(self, operation: str, target: str, 
                                   backup: bool = False) -> bool:
        """Execute firmware operation with progress tracking."""
        if not self.ensure_binary_available():
            self._report_error("CodexCtl binary not available")
            return False
        
        try:
            # Get network service for device connection
            network_service = get_network_service()
            if not network_service.is_connected():
                self._report_error("Device not connected")
                return False
            
            # Build command
            binary_path = self.get_binary_path()
            device_ip = network_service.hostname
            
            cmd = [str(binary_path), operation, "--device", device_ip, "--target", target]
            if backup and operation == "install":
                cmd.append("--backup")
            
            self.logger.info(f"Executing: {' '.join(cmd)}")
            
            # Execute with progress tracking
            return self._run_command_with_progress(cmd, operation)
            
        except Exception as e:
            self.logger.error(f"Firmware operation failed: {e}")
            self._report_error(str(e))
            return False
    
    def _run_command_with_progress(self, cmd: List[str], operation: str) -> bool:
        """Run command with real-time progress parsing."""
        start_time = time.time()
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            output_lines = []
            current_stage = "Initializing"
            progress = 0.0
            
            # Read output line by line
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if not line:
                    continue
                
                output_lines.append(line)
                
                # Parse progress from output
                stage, prog, step = self._parse_progress_line(line)
                if stage:
                    current_stage = stage
                if prog >= 0:
                    progress = prog
                if step:
                    current_step = step
                else:
                    current_step = line
                
                # Report progress
                if self.progress_callback:
                    progress_info = CodexCtlProgress(
                        operation=self.current_operation,
                        stage=current_stage,
                        progress_percentage=progress,
                        current_step=current_step,
                        message=line,
                        output_lines=output_lines.copy()
                    )
                    self.progress_callback(progress_info)
                
                # Report output
                if self.output_callback:
                    self.output_callback(line)
            
            # Wait for completion
            return_code = process.wait(timeout=self.timeout)
            execution_time = time.time() - start_time
            
            success = return_code == 0
            
            if success:
                self.logger.info(f"Operation completed successfully in {execution_time:.1f}s")
            else:
                self.logger.error(f"Operation failed with code {return_code}")
            
            return success
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Operation timed out after {self.timeout}s")
            process.kill()
            return False
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return False
    
    def _parse_progress_line(self, line: str) -> Tuple[Optional[str], float, Optional[str]]:
        """
        Parse progress information from output line.
        
        Returns:
            Tuple of (stage, progress_percentage, step_description)
        """
        stage = None
        progress = -1.0
        step = None
        
        line_lower = line.lower()
        
        # Stage detection
        if "downloading" in line_lower:
            stage = "Downloading firmware"
        elif "backup" in line_lower:
            stage = "Creating backup"
        elif "installing" in line_lower or "flashing" in line_lower:
            stage = "Installing firmware"
        elif "verifying" in line_lower:
            stage = "Verifying installation"
        elif "restoring" in line_lower:
            stage = "Restoring firmware"
        elif "complete" in line_lower:
            stage = "Completed"
            progress = 100.0
        
        # Progress percentage detection
        import re
        progress_match = re.search(r'(\d+)%', line)
        if progress_match:
            progress = float(progress_match.group(1))
        
        # Step description
        if any(keyword in line_lower for keyword in ["downloading", "installing", "verifying", "restoring"]):
            step = line
        
        return stage, progress, step
    
    def _report_error(self, message: str) -> None:
        """Report error through callbacks."""
        if self.progress_callback and self.current_operation:
            error_progress = CodexCtlProgress(
                operation=self.current_operation,
                stage="Error",
                progress_percentage=0.0,
                current_step="Operation failed",
                message=message,
                output_lines=[message]
            )
            self.progress_callback(error_progress)
        
        if self.output_callback:
            self.output_callback(f"ERROR: {message}")
    
    def cancel_operation(self) -> bool:
        """Cancel currently running operation."""
        # Note: This is a simplified implementation
        # In a real scenario, you'd need to track the subprocess and terminate it
        with self._operation_lock:
            if self.is_operation_running:
                self.logger.info("Operation cancellation requested")
                # Implementation would involve process termination
                return True
        return False
    
    def _auto_fetch_binary_on_launch(self) -> None:
        """
        Automatically attempt to fetch codexctl binary on service launch.
        
        Conditions for auto-fetch:
        - System is compatible with CodexCtl requirements
        - Binary is not already present and working
        - Internet connection is available
        - Download attempt is non-blocking (background thread)
        """
        # Check system compatibility first - no point downloading if incompatible
        import sys
        current_version = sys.version_info
        required_version = (3, 12)
        
        if current_version < required_version:
            self.logger.debug("Python version incompatible with CodexCtl, skipping binary auto-fetch")
            return
        
        # Skip if binary already exists and works
        if self.is_binary_available():
            self.logger.debug("CodexCtl binary already available, skipping auto-fetch")
            return
        
        # Check for internet connectivity first
        if not self._check_internet_connectivity():
            self.logger.debug("No internet connectivity detected, skipping binary auto-fetch")
            return
        
        # Attempt download in background thread to avoid blocking startup
        def background_download():
            try:
                self.logger.info("Auto-fetching CodexCtl binary in background...")
                success = self.download_binary()
                if success:
                    self.logger.info("CodexCtl binary auto-fetch completed successfully")
                else:
                    self.logger.debug("CodexCtl binary auto-fetch failed, will retry later when needed")
            except Exception as e:
                self.logger.debug(f"CodexCtl binary auto-fetch encountered error: {e}")
        
        # Submit to background thread pool
        try:
            self.executor.submit(background_download)
        except Exception as e:
            self.logger.debug(f"Failed to submit auto-fetch task: {e}")
    
    def _check_internet_connectivity(self) -> bool:
        """
        Check if internet connectivity is available.
        
        Returns:
            True if internet connection appears to be working
        """
        try:
            # Quick connectivity test to GitHub API
            response = requests.head(
                f"https://api.github.com/repos/{self.github_repo}",
                timeout=5
            )
            return response.status_code < 500
        except Exception:
            # Any network error means no connectivity
            return False
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        self.executor.shutdown(wait=True)
        self.logger.info("CodexCtl service cleaned up")


# Global service instance
_global_codexctl_service: Optional[CodexCtlService] = None


def get_codexctl_service() -> CodexCtlService:
    """
    Get the global CodexCtl service instance.
    
    Returns:
        Global CodexCtlService instance
        
    Raises:
        RuntimeError: If service hasn't been initialized
    """
    global _global_codexctl_service
    if _global_codexctl_service is None:
        raise RuntimeError("CodexCtl service not initialized. Call init_codexctl_service() first.")
    return _global_codexctl_service


def init_codexctl_service(**kwargs) -> CodexCtlService:
    """
    Initialize the global CodexCtl service.
    
    Args:
        **kwargs: CodexCtlService initialization arguments
        
    Returns:
        Initialized CodexCtlService instance
    """
    global _global_codexctl_service
    
    _global_codexctl_service = CodexCtlService(**kwargs)
    return _global_codexctl_service