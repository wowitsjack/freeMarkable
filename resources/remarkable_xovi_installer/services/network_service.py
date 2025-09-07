"""
Network service for freeMarkable.

This module provides SSH/SCP operations with paramiko, connection management,
remote command execution, and file transfer with progress tracking.
"""

import os
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Union, Tuple
from dataclasses import dataclass
from enum import Enum
import paramiko
from paramiko import SSHClient, SFTPClient
from paramiko.ssh_exception import (
    SSHException, 
    AuthenticationException, 
    NoValidConnectionsError,
    BadHostKeyException
)
import socket
from concurrent.futures import ThreadPoolExecutor, Future


class ConnectionStatus(Enum):
    """SSH connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATION_FAILED = "auth_failed"
    HOST_KEY_ERROR = "host_key_error"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    ERROR = "error"


class CommandResult:
    """Result of SSH command execution."""
    
    def __init__(self, command: str, exit_code: int, stdout: str, stderr: str, 
                 execution_time: float = 0.0):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.execution_time = execution_time
        
    @property
    def success(self) -> bool:
        """Check if command executed successfully."""
        return self.exit_code == 0
    
    @property
    def output(self) -> str:
        """Get combined stdout/stderr output."""
        return f"{self.stdout}\n{self.stderr}".strip()
    
    def __str__(self) -> str:
        return f"Command: {self.command}\nExit Code: {self.exit_code}\nOutput: {self.output}"


@dataclass
class TransferProgress:
    """Progress information for file transfers."""
    filename: str
    bytes_transferred: int
    total_bytes: int
    start_time: float
    is_upload: bool = True
    
    @property
    def progress_percentage(self) -> float:
        """Get transfer progress as percentage."""
        if self.total_bytes > 0:
            return (self.bytes_transferred / self.total_bytes) * 100.0
        return 0.0
    
    @property
    def speed_bytes_per_second(self) -> float:
        """Get transfer speed in bytes per second."""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            return self.bytes_transferred / elapsed
        return 0.0
    
    @property
    def eta_seconds(self) -> Optional[float]:
        """Get estimated time to completion."""
        speed = self.speed_bytes_per_second
        if speed > 0:
            remaining = self.total_bytes - self.bytes_transferred
            return remaining / speed
        return None


class NetworkService:
    """
    Network service for SSH/SCP operations with the reMarkable device.
    
    Provides secure SSH connections, remote command execution, and file transfers
    with progress tracking and comprehensive error handling.
    """
    
    def __init__(self, connection_timeout: int = 10, 
                 max_retries: int = 3,
                 retry_delay: int = 2,
                 keepalive_interval: int = 30):
        """
        Initialize network service.
        
        Args:
            connection_timeout: SSH connection timeout in seconds
            max_retries: Maximum connection retry attempts
            retry_delay: Delay between retry attempts in seconds
            keepalive_interval: SSH keepalive interval in seconds
        """
        self.connection_timeout = connection_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.keepalive_interval = keepalive_interval
        
        # Connection state
        self.ssh_client: Optional[SSHClient] = None
        self.sftp_client: Optional[SFTPClient] = None
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.last_error: Optional[str] = None
        
        # Connection details
        self.hostname: Optional[str] = None
        self.username: str = "root"  # reMarkable always uses root
        self.password: Optional[str] = None
        self.port: int = 22
        
        # Progress callbacks
        self.command_output_callback: Optional[Callable[[str], None]] = None
        self.transfer_progress_callback: Optional[Callable[[TransferProgress], None]] = None
        
        # Thread management
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._connection_lock = threading.Lock()
        
        self._logger = logging.getLogger(__name__)
    
    def set_connection_details(self, hostname: str, password: str, 
                             username: str = "root", port: int = 22) -> None:
        """
        Set connection details for SSH operations.
        
        Args:
            hostname: Device IP address or hostname
            password: SSH password
            username: SSH username (default: root)
            port: SSH port (default: 22)
        """
        self.hostname = hostname
        self.password = password
        self.username = username
        self.port = port
        
        # Reset connection if details changed
        if self.is_connected():
            self._logger.info("Connection details changed, disconnecting...")
            self.disconnect()
    
    def set_command_output_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for real-time command output."""
        self.command_output_callback = callback
    
    def set_transfer_progress_callback(self, callback: Callable[[TransferProgress], None]) -> None:
        """Set callback for file transfer progress."""
        self.transfer_progress_callback = callback
    
    def is_connected(self) -> bool:
        """Check if SSH connection is active."""
        return (self.connection_status == ConnectionStatus.CONNECTED and 
                self.ssh_client is not None and 
                self.ssh_client.get_transport() is not None and
                self.ssh_client.get_transport().is_active())
    
    def connect(self, force_reconnect: bool = False) -> bool:
        """
        Establish SSH connection to the device.
        
        Args:
            force_reconnect: Force reconnection even if already connected
            
        Returns:
            True if connection successful, False otherwise
        """
        with self._connection_lock:
            if self.is_connected() and not force_reconnect:
                return True
            
            if not self.hostname or not self.password:
                self.last_error = "Hostname and password are required"
                self.connection_status = ConnectionStatus.ERROR
                return False
            
            self._logger.info(f"Connecting to {self.hostname}:{self.port} as {self.username}")
            
            # Disconnect existing connection
            if self.ssh_client:
                self.disconnect()
            
            # Clear any existing host keys for this hostname BEFORE attempting connection
            # This prevents Paramiko from loading conflicting keys that cause verification failures
            known_hosts_path = os.path.expanduser('~/.ssh/known_hosts')
            if os.path.exists(known_hosts_path):
                try:
                    # Remove existing entries for this hostname
                    with open(known_hosts_path, 'r') as f:
                        lines = f.readlines()
                    
                    filtered_lines = []
                    for line in lines:
                        if not line.startswith(self.hostname + ' ') and not line.startswith(self.hostname + ','):
                            filtered_lines.append(line)
                    
                    # Only rewrite if we found entries to remove
                    if len(filtered_lines) < len(lines):
                        with open(known_hosts_path, 'w') as f:
                            f.writelines(filtered_lines)
                        self._logger.debug(f"Cleared conflicting host key entries for {self.hostname}")
                except Exception as e:
                    self._logger.debug(f"Could not clear host key entries: {e}")
            
            # Attempt connection with retries
            for attempt in range(self.max_retries):
                self.connection_status = ConnectionStatus.CONNECTING
                
                try:
                    # Create SSH client with proper configuration for reMarkable devices
                    self.ssh_client = SSHClient()
                    
                    # Use AutoAddPolicy to automatically accept unknown host keys
                    # This is necessary because reMarkable devices often have changing host keys
                    self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    
                    # Connect with timeout and reMarkable-specific settings
                    self.ssh_client.connect(
                        hostname=self.hostname,
                        port=self.port,
                        username=self.username,
                        password=self.password,
                        timeout=self.connection_timeout,
                        banner_timeout=self.connection_timeout,
                        auth_timeout=self.connection_timeout,
                        look_for_keys=False,          # Don't use SSH keys
                        allow_agent=False             # Don't use SSH agent
                    )
                    
                    # Set keepalive to prevent connection drops
                    transport = self.ssh_client.get_transport()
                    if transport:
                        transport.set_keepalive(self.keepalive_interval)
                    
                    # Create SFTP client for file operations
                    self.sftp_client = self.ssh_client.open_sftp()
                    
                    self.connection_status = ConnectionStatus.CONNECTED
                    self.last_error = None
                    self._logger.info(f"Successfully connected to {self.hostname}")
                    
                    return True
                    
                except AuthenticationException as e:
                    self.last_error = f"Authentication failed: {e}"
                    self.connection_status = ConnectionStatus.AUTHENTICATION_FAILED
                    self._logger.error(self.last_error)
                    break  # Don't retry auth failures
                    
                except BadHostKeyException as e:
                    self.last_error = f"Host key verification failed: {e}"
                    self.connection_status = ConnectionStatus.HOST_KEY_ERROR
                    self._logger.error(self.last_error)
                    break  # Don't retry host key issues
                    
                except (NoValidConnectionsError, socket.timeout, socket.error) as e:
                    self.last_error = f"Network connection failed: {e}"
                    self.connection_status = ConnectionStatus.NETWORK_ERROR
                    
                    if attempt < self.max_retries - 1:
                        self._logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                        self._logger.info(f"Retrying in {self.retry_delay} seconds...")
                        time.sleep(self.retry_delay)
                    else:
                        self._logger.error(f"All connection attempts failed: {e}")
                        
                except SSHException as e:
                    self.last_error = f"SSH error: {e}"
                    self.connection_status = ConnectionStatus.ERROR
                    
                    if attempt < self.max_retries - 1:
                        self._logger.warning(f"SSH error on attempt {attempt + 1}: {e}")
                        time.sleep(self.retry_delay)
                    else:
                        self._logger.error(f"SSH connection failed after {self.max_retries} attempts: {e}")
                        
                except Exception as e:
                    self.last_error = f"Unexpected error: {e}"
                    self.connection_status = ConnectionStatus.ERROR
                    self._logger.error(f"Unexpected connection error: {e}")
                    break
            
            # Clean up on failure
            if self.ssh_client:
                self.disconnect()
            
            return False
    
    def disconnect(self) -> None:
        """Close SSH and SFTP connections."""
        with self._connection_lock:
            if self.sftp_client:
                try:
                    self.sftp_client.close()
                except Exception:
                    pass
                self.sftp_client = None
            
            if self.ssh_client:
                try:
                    self.ssh_client.close()
                except Exception:
                    pass
                self.ssh_client = None
            
            self.connection_status = ConnectionStatus.DISCONNECTED
            self._logger.debug("SSH connection closed")
    
    def test_connection(self) -> bool:
        """
        Test SSH connection without maintaining it.
        
        Returns:
            True if connection test successful
        """
        if not self.hostname or not self.password:
            return False
        
        original_connected = self.is_connected()
        
        try:
            if self.connect():
                # Test with a simple command
                result = self.execute_command("echo 'connection_test'", timeout=5)
                return result.success and "connection_test" in result.stdout
            return False
        finally:
            # Restore original connection state
            if not original_connected:
                self.disconnect()
    
    def execute_command(self, command: str, timeout: Optional[int] = None,
                       capture_output: bool = True,
                       real_time_output: bool = False) -> CommandResult:
        """
        Execute a command on the remote device.
        
        Args:
            command: Command to execute
            timeout: Command timeout in seconds
            capture_output: Whether to capture stdout/stderr
            real_time_output: Whether to stream output in real-time
            
        Returns:
            CommandResult with execution details
        """
        if not self.is_connected():
            if not self.connect():
                return CommandResult(
                    command=command,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Not connected to device: {self.last_error}",
                    execution_time=0.0
                )
        
        self._logger.debug(f"Executing command: {command}")
        start_time = time.time()
        
        try:
            # Handle None timeout by not setting any timeout at all
            if timeout is None:
                stdin, stdout, stderr = self.ssh_client.exec_command(command)
            else:
                stdin, stdout, stderr = self.ssh_client.exec_command(
                    command,
                    timeout=timeout or self.connection_timeout
                )
            
            if real_time_output and self.command_output_callback:
                # Stream output in real-time
                stdout_data = []
                stderr_data = []
                
                def read_output(stream, data_list, is_stderr=False):
                    for line in iter(stream.readline, ""):
                        if line:
                            data_list.append(line)
                            if self.command_output_callback:
                                self.command_output_callback(line.rstrip())
                
                # Start threads to read both streams
                import threading
                stdout_thread = threading.Thread(target=read_output, args=(stdout, stdout_data))
                stderr_thread = threading.Thread(target=read_output, args=(stderr, stderr_data, True))
                
                stdout_thread.start()
                stderr_thread.start()
                
                # Wait for command completion
                exit_code = stdout.channel.recv_exit_status()
                
                stdout_thread.join()
                stderr_thread.join()
                
                stdout_text = "".join(stdout_data)
                stderr_text = "".join(stderr_data)
            else:
                # Read all output at once
                stdout_text = stdout.read().decode('utf-8', errors='replace') if capture_output else ""
                stderr_text = stderr.read().decode('utf-8', errors='replace') if capture_output else ""
                exit_code = stdout.channel.recv_exit_status()
            
            execution_time = time.time() - start_time
            
            result = CommandResult(
                command=command,
                exit_code=exit_code,
                stdout=stdout_text,
                stderr=stderr_text,
                execution_time=execution_time
            )
            
            if result.success:
                self._logger.debug(f"Command completed successfully in {execution_time:.2f}s")
            else:
                self._logger.warning(f"Command failed with exit code {exit_code}: {stderr_text}")
            
            return result
            
        except socket.timeout:
            execution_time = time.time() - start_time
            error_msg = f"Command timed out after {timeout or self.connection_timeout} seconds"
            self._logger.error(error_msg)
            return CommandResult(command, -1, "", error_msg, execution_time)
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Command execution failed: {e}"
            self._logger.error(error_msg)
            return CommandResult(command, -1, "", error_msg, execution_time)
    
    def upload_file(self, local_path: Union[str, Path], remote_path: str,
                   create_dirs: bool = True) -> bool:
        """
        Upload a file to the remote device.
        
        Args:
            local_path: Local file path
            remote_path: Remote file path
            create_dirs: Whether to create remote directories
            
        Returns:
            True if upload successful
        """
        if not self.is_connected():
            if not self.connect():
                self._logger.error("Cannot upload file: not connected")
                return False
        
        local_path = Path(local_path)
        if not local_path.exists():
            self._logger.error(f"Local file does not exist: {local_path}")
            return False
        
        try:
            # Create remote directories if needed
            if create_dirs:
                remote_dir = str(Path(remote_path).parent)
                if remote_dir != "/":
                    self.execute_command(f"mkdir -p '{remote_dir}'")
            
            # Get file size for progress tracking
            file_size = local_path.stat().st_size
            transferred = 0
            start_time = time.time()
            
            def progress_callback(bytes_transferred: int, total_bytes: int) -> None:
                nonlocal transferred
                transferred = bytes_transferred
                
                if self.transfer_progress_callback:
                    progress = TransferProgress(
                        filename=local_path.name,
                        bytes_transferred=bytes_transferred,
                        total_bytes=total_bytes,
                        start_time=start_time,
                        is_upload=True
                    )
                    self.transfer_progress_callback(progress)
            
            self._logger.info(f"Uploading {local_path} to {remote_path}")
            
            # Use SFTP for file transfer with progress callback
            self.sftp_client.put(
                str(local_path), 
                remote_path, 
                callback=progress_callback
            )
            
            elapsed = time.time() - start_time
            speed = file_size / elapsed if elapsed > 0 else 0
            self._logger.info(f"Upload completed: {file_size} bytes in {elapsed:.2f}s ({speed:.0f} B/s)")
            
            return True
            
        except Exception as e:
            self._logger.error(f"Upload failed: {e}")
            return False
    
    def download_file(self, remote_path: str, local_path: Union[str, Path],
                     create_dirs: bool = True) -> bool:
        """
        Download a file from the remote device.
        
        Args:
            remote_path: Remote file path
            local_path: Local file path
            create_dirs: Whether to create local directories
            
        Returns:
            True if download successful
        """
        if not self.is_connected():
            if not self.connect():
                self._logger.error("Cannot download file: not connected")
                return False
        
        local_path = Path(local_path)
        
        try:
            # Create local directories if needed
            if create_dirs:
                local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Get remote file size for progress tracking
            try:
                file_attrs = self.sftp_client.stat(remote_path)
                file_size = file_attrs.st_size
            except Exception:
                file_size = 0
            
            transferred = 0
            start_time = time.time()
            
            def progress_callback(bytes_transferred: int, total_bytes: int) -> None:
                nonlocal transferred
                transferred = bytes_transferred
                
                if self.transfer_progress_callback:
                    progress = TransferProgress(
                        filename=Path(remote_path).name,
                        bytes_transferred=bytes_transferred,
                        total_bytes=total_bytes or file_size,
                        start_time=start_time,
                        is_upload=False
                    )
                    self.transfer_progress_callback(progress)
            
            self._logger.info(f"Downloading {remote_path} to {local_path}")
            
            # Use SFTP for file transfer with progress callback
            self.sftp_client.get(
                remote_path,
                str(local_path),
                callback=progress_callback
            )
            
            elapsed = time.time() - start_time
            actual_size = local_path.stat().st_size if local_path.exists() else 0
            speed = actual_size / elapsed if elapsed > 0 else 0
            self._logger.info(f"Download completed: {actual_size} bytes in {elapsed:.2f}s ({speed:.0f} B/s)")
            
            return True
            
        except Exception as e:
            self._logger.error(f"Download failed: {e}")
            return False
    
    def upload_directory(self, local_dir: Union[str, Path], remote_dir: str,
                        recursive: bool = True) -> bool:
        """
        Upload a directory to the remote device.
        
        Args:
            local_dir: Local directory path
            remote_dir: Remote directory path
            recursive: Whether to upload recursively
            
        Returns:
            True if upload successful
        """
        if not self.is_connected():
            if not self.connect():
                return False
        
        local_dir = Path(local_dir)
        if not local_dir.is_dir():
            self._logger.error(f"Local directory does not exist: {local_dir}")
            return False
        
        try:
            # Create remote directory
            self.execute_command(f"mkdir -p '{remote_dir}'")
            
            # Upload files
            success = True
            for item in local_dir.iterdir():
                if item.is_file():
                    remote_file = f"{remote_dir}/{item.name}"
                    if not self.upload_file(item, remote_file):
                        success = False
                elif item.is_dir() and recursive:
                    remote_subdir = f"{remote_dir}/{item.name}"
                    if not self.upload_directory(item, remote_subdir, recursive):
                        success = False
            
            return success
            
        except Exception as e:
            self._logger.error(f"Directory upload failed: {e}")
            return False
    
    def file_exists(self, remote_path: str) -> bool:
        """Check if a file exists on the remote device."""
        if not self.is_connected():
            return False
        
        try:
            self.sftp_client.stat(remote_path)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False
    
    def get_device_architecture(self) -> Optional[str]:
        """Get device architecture via uname command."""
        result = self.execute_command("uname -m")
        if result.success:
            return result.stdout.strip()
        return None
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get comprehensive device information."""
        info = {}
        
        # Architecture
        arch_result = self.execute_command("uname -m")
        if arch_result.success:
            info["architecture"] = arch_result.stdout.strip()
        
        # Kernel version
        kernel_result = self.execute_command("uname -r")
        if kernel_result.success:
            info["kernel_version"] = kernel_result.stdout.strip()
        
        # Uptime
        uptime_result = self.execute_command("uptime")
        if uptime_result.success:
            info["uptime"] = uptime_result.stdout.strip()
        
        # Disk space
        df_result = self.execute_command("df -h /")
        if df_result.success:
            info["disk_space"] = df_result.stdout.strip()
        
        # reMarkable version (if available)
        version_result = self.execute_command("cat /etc/version 2>/dev/null || echo 'unknown'")
        if version_result.success:
            info["remarkable_version"] = version_result.stdout.strip()
        
        return info
    
    def install_ethernet_fix(self) -> bool:
        """
        Install USB ethernet fix on the reMarkable device.
        
        This fixes USB ethernet adapter connectivity by loading the g_ether module
        and configuring the usb0 interface with the standard IP address.
        
        Returns:
            True if ethernet fix was successfully applied
        """
        if not self.is_connected():
            if not self.connect():
                self._logger.error("Cannot install ethernet fix: not connected")
                return False
        
        self._logger.info("Installing USB ethernet fix...")
        
        try:
            # Execute the ethernet fix commands from the original script
            commands = [
                "echo 'Loading g_ether module...'",
                "modprobe g_ether",
                "echo 'Bringing up usb0 interface...'",
                "ip link set usb0 up",
                "echo 'Configuring IP address...'",
                "ip addr add 10.11.99.1/27 dev usb0 2>/dev/null || echo 'IP already configured'",
                "echo 'USB Ethernet Fix completed successfully!'",
                "echo 'You can now connect via USB at 10.11.99.1'"
            ]
            
            # Execute all commands in sequence
            for command in commands:
                result = self.execute_command(command, timeout=10)
                if not result.success and "IP already configured" not in result.stderr:
                    self._logger.warning(f"Ethernet fix command had issues: {command}")
                    self._logger.warning(f"Output: {result.output}")
                    # Continue with other commands even if one fails
            
            self._logger.info("USB ethernet fix installation completed")
            return True
            
        except Exception as e:
            self._logger.error(f"Ethernet fix installation failed: {e}")
            return False

    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status information."""
        return {
            "status": self.connection_status.value,
            "hostname": self.hostname,
            "port": self.port,
            "username": self.username,
            "connected": self.is_connected(),
            "last_error": self.last_error
        }
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.disconnect()
        self.executor.shutdown(wait=True)


# Global network service instance
_global_network_service: Optional[NetworkService] = None


def get_network_service() -> NetworkService:
    """
    Get the global network service instance.
    
    Returns:
        Global NetworkService instance
        
    Raises:
        RuntimeError: If network service hasn't been initialized
    """
    global _global_network_service
    if _global_network_service is None:
        raise RuntimeError("Network service not initialized. Call init_network_service() first.")
    return _global_network_service


def init_network_service(**kwargs) -> NetworkService:
    """
    Initialize the global network service.
    
    Args:
        **kwargs: NetworkService initialization arguments
        
    Returns:
        Initialized NetworkService instance
    """
    global _global_network_service
    
    _global_network_service = NetworkService(**kwargs)
    return _global_network_service


def configure_from_config(config: Any) -> NetworkService:
    """
    Configure network service from application config.
    
    Args:
        config: Application configuration object
        
    Returns:
        Configured network service
    """
    kwargs = {}
    if hasattr(config, 'network'):
        if hasattr(config.network, 'connection_timeout'):
            kwargs['connection_timeout'] = config.network.connection_timeout
        if hasattr(config.network, 'max_connection_attempts'):
            kwargs['max_retries'] = config.network.max_connection_attempts
        if hasattr(config.network, 'retry_delay'):
            kwargs['retry_delay'] = config.network.retry_delay
    
    return init_network_service(**kwargs)


# Convenience functions

def execute_command(command: str, **kwargs) -> CommandResult:
    """Execute a command (convenience function)."""
    return get_network_service().execute_command(command, **kwargs)


def upload_file(local_path: Union[str, Path], remote_path: str, **kwargs) -> bool:
    """Upload a file (convenience function)."""
    return get_network_service().upload_file(local_path, remote_path, **kwargs)


def download_file(remote_path: str, local_path: Union[str, Path], **kwargs) -> bool:
    """Download a file (convenience function)."""
    return get_network_service().download_file(remote_path, local_path, **kwargs)


def test_connection() -> bool:
    """Test connection (convenience function)."""
    return get_network_service().test_connection()