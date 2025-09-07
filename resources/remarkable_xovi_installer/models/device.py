"""
Device model and data structures for freeMarkable.

This module contains the Device class representing reMarkable tablet state,
architecture detection, connection info, and validation methods.
"""

import re
import subprocess
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from ipaddress import IPv4Address, AddressValueError

# Import network service for SSH operations
try:
    from ..services.network_service import get_network_service, NetworkService
except ImportError:
    # Handle case where network service is not yet initialized
    get_network_service = None
    NetworkService = None


class DeviceType(Enum):
    """Supported reMarkable device types with their architecture mappings."""
    RM1 = ("rM1", "armv6l", "reMarkable 1")
    RM2 = ("rM2", "armv7l", "reMarkable 2") 
    RMPP = ("rMPP", "aarch64", "reMarkable Paper Pro")
    
    def __init__(self, short_name: str, architecture: str, display_name: str):
        self.short_name = short_name
        self.architecture = architecture
        self.display_name = display_name
    
    @classmethod
    def from_architecture(cls, arch: str) -> Optional['DeviceType']:
        """Get device type from architecture string."""
        arch_mapping = {
            "armv6l": cls.RM1,
            "armv7l": cls.RM2,
            "armhf": cls.RM2,  # Alternative name for rM2
            "aarch64": cls.RMPP,
            "arm64": cls.RMPP   # Alternative name for rMPP
        }
        return arch_mapping.get(arch.lower())
    
    @classmethod
    def from_short_name(cls, name: str) -> Optional['DeviceType']:
        """Get device type from short name (rM1, rM2, rMPP)."""
        name_mapping = {
            "rm1": cls.RM1,
            "rm2": cls.RM2,
            "rmpp": cls.RMPP
        }
        return name_mapping.get(name.lower())
    
    @classmethod
    def from_short_name(cls, name: str) -> Optional['DeviceType']:
        """Get device type from short name (rM1, rM2, rMPP)."""
        name_mapping = {
            "rm1": cls.RM1,
            "rm2": cls.RM2,
            "rmpp": cls.RMPP
        }
        return name_mapping.get(name.lower())


class ConnectionStatus(Enum):
    """Device connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATION_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    ERROR = "error"


class InstallationStatus(Enum):
    """Installation status on device."""
    NOT_INSTALLED = "not_installed"
    XOVI_ONLY = "xovi_only"
    PARTIAL_INSTALL = "partial_install"
    FULLY_INSTALLED = "fully_installed"
    CORRUPTED = "corrupted"


@dataclass
class DeviceInfo:
    """Device system information."""
    hostname: Optional[str] = None
    kernel_version: Optional[str] = None
    remarkable_version: Optional[str] = None
    uptime: Optional[str] = None
    free_space: Optional[int] = None  # bytes
    total_space: Optional[int] = None  # bytes
    
    def get_free_space_mb(self) -> Optional[float]:
        """Get free space in MB."""
        return self.free_space / (1024 * 1024) if self.free_space else None
    
    def get_total_space_mb(self) -> Optional[float]:
        """Get total space in MB."""
        return self.total_space / (1024 * 1024) if self.total_space else None


@dataclass
class NetworkInfo:
    """Device network configuration."""
    usb_ip: Optional[str] = None
    wifi_ip: Optional[str] = None
    wifi_enabled: bool = False
    ethernet_enabled: bool = False
    
    def get_primary_ip(self) -> Optional[str]:
        """Get the primary IP address (USB preferred)."""
        return self.usb_ip or self.wifi_ip
    
    def has_connectivity(self) -> bool:
        """Check if device has any network connectivity."""
        return bool(self.usb_ip or self.wifi_ip)


@dataclass
class InstallationInfo:
    """Information about installed components."""
    xovi_installed: bool = False
    xovi_version: Optional[str] = None
    appload_installed: bool = False
    koreader_installed: bool = False
    tripletap_installed: bool = False
    extensions_count: int = 0
    backup_count: int = 0
    
    installed_extensions: List[str] = field(default_factory=list)
    available_backups: List[str] = field(default_factory=list)
    
    def get_status(self) -> InstallationStatus:
        """Get overall installation status."""
        if not self.xovi_installed:
            return InstallationStatus.NOT_INSTALLED
        elif self.xovi_installed and self.appload_installed and self.koreader_installed:
            return InstallationStatus.FULLY_INSTALLED
        elif self.xovi_installed and self.appload_installed:
            return InstallationStatus.XOVI_ONLY
        elif self.xovi_installed:
            return InstallationStatus.PARTIAL_INSTALL
        else:
            return InstallationStatus.CORRUPTED


class Device:
    """
    Represents a reMarkable device with connection and state management.
    
    This class encapsulates all device-related functionality including
    connection management, architecture detection, and installation status.
    """
    
    def __init__(self, ip_address: Optional[str] = None, 
                 ssh_password: Optional[str] = None,
                 device_type: Optional[DeviceType] = None):
        """
        Initialize a Device instance.
        
        Args:
            ip_address: Device IP address
            ssh_password: SSH password for authentication
            device_type: Device type (will be auto-detected if None)
        """
        self.ip_address = ip_address
        self.ssh_password = ssh_password
        self.device_type = device_type
        
        # State information
        self.connection_status = ConnectionStatus.DISCONNECTED
        self.last_connection_attempt: Optional[datetime] = None
        self.last_error: Optional[str] = None
        
        # Device information (populated on connection)
        self.device_info: Optional[DeviceInfo] = None
        self.network_info: Optional[NetworkInfo] = None
        self.installation_info: Optional[InstallationInfo] = None
        
        # Connection settings
        self.connection_timeout = 10
        self.max_retries = 3
        self.ssh_port = 22
        
        self._logger = logging.getLogger(__name__)
    
    def __str__(self) -> str:
        """String representation of the device."""
        device_type_str = self.device_type.display_name if self.device_type else "Unknown"
        status_str = self.connection_status.value.replace('_', ' ').title()
        return f"{device_type_str} at {self.ip_address or 'Unknown IP'} ({status_str})"
    
    def __repr__(self) -> str:
        """Developer representation of the device."""
        return (f"Device(ip_address='{self.ip_address}', "
                f"device_type={self.device_type}, "
                f"status={self.connection_status})")
    
    def is_configured(self) -> bool:
        """Check if device has minimum required configuration."""
        return bool(self.ip_address and self.ssh_password)
    
    def is_connected(self) -> bool:
        """Check if device is currently connected."""
        return self.connection_status == ConnectionStatus.CONNECTED
    
    def validate_ip_address(self) -> bool:
        """
        Validate the IP address format.
        
        Returns:
            True if IP address is valid, False otherwise
        """
        if not self.ip_address:
            return False
        
        try:
            IPv4Address(self.ip_address)
            return True
        except AddressValueError:
            return False
    
    def validate_ssh_password(self) -> bool:
        """
        Validate SSH password format.
        
        Returns:
            True if password appears valid, False otherwise
        """
        if not self.ssh_password:
            return False
        
        # Basic validation - password should be non-empty and reasonable length
        return 1 <= len(self.ssh_password) <= 256
    
    def update_connection_info(self, ip_address: Optional[str] = None,
                             ssh_password: Optional[str] = None) -> None:
        """
        Update device connection information.
        
        Args:
            ip_address: New IP address
            ssh_password: New SSH password
        """
        if ip_address is not None:
            self.ip_address = ip_address
            self.connection_status = ConnectionStatus.DISCONNECTED
            
        if ssh_password is not None:
            self.ssh_password = ssh_password
            self.connection_status = ConnectionStatus.DISCONNECTED
    
    def detect_device_type(self, force: bool = False) -> Optional[DeviceType]:
        """
        Detect device type by querying architecture.
        
        Args:
            force: Force re-detection even if type is already known
            
        Returns:
            Detected device type or None if detection failed
        """
        if self.device_type and not force:
            return self.device_type
        
        if not self.is_configured():
            self._logger.warning("Cannot detect device type: device not configured")
            return None
        
        try:
            # Use network service for SSH-based architecture detection
            if get_network_service is None:
                self._logger.warning("Network service not available for device type detection")
                return None
            
            network_service = get_network_service()
            network_service.set_connection_details(
                hostname=self.ip_address,
                password=self.ssh_password
            )
            
            if not network_service.connect():
                self._logger.error("Failed to connect for device type detection")
                return None
            
            # Get device architecture
            arch = network_service.get_device_architecture()
            if arch:
                self.device_type = DeviceType.from_architecture(arch)
                if self.device_type:
                    self._logger.info(f"Detected device type: {self.device_type.display_name}")
                else:
                    self._logger.warning(f"Unknown architecture: {arch}")
            
            return self.device_type
            
        except Exception as e:
            self._logger.error(f"Failed to detect device type: {e}")
            self.last_error = str(e)
            return None
    
    def test_connection(self) -> bool:
        """
        Test SSH connection to the device.
        
        Returns:
            True if connection successful, False otherwise
        """
        if not self.is_configured():
            self.connection_status = ConnectionStatus.ERROR
            self.last_error = "Device not configured (missing IP or password)"
            return False
        
        if not self.validate_ip_address():
            self.connection_status = ConnectionStatus.ERROR
            self.last_error = "Invalid IP address format"
            return False
        
        self.connection_status = ConnectionStatus.CONNECTING
        self.last_connection_attempt = datetime.now()
        
        try:
            # Use network service for actual SSH connection testing
            if get_network_service is None:
                self.connection_status = ConnectionStatus.ERROR
                self.last_error = "Network service not available"
                return False
            
            network_service = get_network_service()
            network_service.set_connection_details(
                hostname=self.ip_address,
                password=self.ssh_password
            )
            
            success = network_service.test_connection()
            
            if success:
                self.connection_status = ConnectionStatus.CONNECTED
                self.last_error = None
                self._logger.info(f"Successfully connected to device at {self.ip_address}")
                return True
            else:
                self.connection_status = ConnectionStatus.AUTHENTICATION_FAILED
                self.last_error = network_service.last_error or "Connection test failed"
                self._logger.error(f"Connection test failed: {self.last_error}")
                return False
                
        except Exception as e:
            self._logger.error(f"Connection test failed: {e}")
            self.connection_status = ConnectionStatus.ERROR
            self.last_error = str(e)
            return False
    
    def refresh_device_info(self) -> bool:
        """
        Refresh device system information.
        
        Returns:
            True if information was refreshed successfully
        """
        if not self.is_connected():
            self._logger.warning("Cannot refresh device info: not connected")
            return False
        
        try:
            if get_network_service is None:
                self._logger.warning("Network service not available for device info refresh")
                return False
            
            network_service = get_network_service()
            device_info_dict = network_service.get_device_info()
            
            if device_info_dict:
                # Parse disk space information
                free_space = None
                total_space = None
                if 'disk_space' in device_info_dict:
                    disk_info = device_info_dict['disk_space']
                    # Parse df output to extract space info
                    # Example: "/dev/mmcblk2p7  7.3G  2.1G  4.9G  30% /"
                    import re
                    disk_match = re.search(r'(\d+(?:\.\d+)?[KMGT]?)\s+(\d+(?:\.\d+)?[KMGT]?)\s+(\d+(?:\.\d+)?[KMGT]?)', disk_info)
                    if disk_match:
                        def parse_size(size_str):
                            """Convert human readable sizes to bytes"""
                            units = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
                            if size_str[-1] in units:
                                return int(float(size_str[:-1]) * units[size_str[-1]])
                            return int(size_str)
                        
                        try:
                            total_space = parse_size(disk_match.group(1))
                            free_space = parse_size(disk_match.group(3))
                        except (ValueError, IndexError):
                            pass
                
                self.device_info = DeviceInfo(
                    hostname="remarkable",
                    kernel_version=device_info_dict.get('kernel_version', 'Unknown'),
                    remarkable_version=device_info_dict.get('remarkable_version', 'Unknown'),
                    uptime=device_info_dict.get('uptime', 'Unknown'),
                    free_space=free_space,
                    total_space=total_space
                )
                
                self._logger.info("Device information refreshed successfully")
                return True
            else:
                self._logger.warning("No device info returned from network service")
                return False
            
        except Exception as e:
            self._logger.error(f"Failed to refresh device info: {e}")
            self.last_error = str(e)
            return False
    
    def refresh_network_info(self) -> bool:
        """
        Refresh device network configuration.
        
        Returns:
            True if network info was refreshed successfully
        """
        if not self.is_connected():
            self._logger.warning("Cannot refresh network info: not connected")
            return False
        
        try:
            if get_network_service is None:
                self._logger.warning("Network service not available for network info refresh")
                return False
            
            network_service = get_network_service()
            
            # Get network interface information
            ip_result = network_service.execute_command("ip addr show")
            route_result = network_service.execute_command("ip route show")
            
            wifi_enabled = False
            ethernet_enabled = False
            usb_ip = None
            wifi_ip = None
            
            if ip_result.success:
                # Parse IP addresses from interfaces
                import re
                
                # Look for USB ethernet (typically usb0)
                usb_match = re.search(r'usb0:.*?inet (\d+\.\d+\.\d+\.\d+)', ip_result.stdout, re.DOTALL)
                if usb_match:
                    usb_ip = usb_match.group(1)
                    ethernet_enabled = True
                
                # Look for WiFi (typically wlan0)
                wifi_match = re.search(r'wlan0:.*?inet (\d+\.\d+\.\d+\.\d+)', ip_result.stdout, re.DOTALL)
                if wifi_match:
                    wifi_ip = wifi_match.group(1)
                    wifi_enabled = True
                
                # If we don't find specific interfaces, use the current connection IP
                if not usb_ip and not wifi_ip:
                    # Assume current connection is the primary interface
                    if self.ip_address.startswith('10.11.99'):
                        usb_ip = self.ip_address
                        ethernet_enabled = True
                    else:
                        wifi_ip = self.ip_address
                        wifi_enabled = True
            
            self.network_info = NetworkInfo(
                usb_ip=usb_ip,
                wifi_ip=wifi_ip,
                wifi_enabled=wifi_enabled,
                ethernet_enabled=ethernet_enabled
            )
            
            self._logger.info("Network information refreshed successfully")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to refresh network info: {e}")
            self.last_error = str(e)
            return False
    
    def refresh_installation_info(self) -> bool:
        """
        Refresh installation status information.
        
        Returns:
            True if installation info was refreshed successfully
        """
        if not self.is_connected():
            self._logger.warning("Cannot refresh installation info: not connected")
            return False
        
        try:
            if get_network_service is None:
                self._logger.warning("Network service not available for installation info refresh")
                return False
            
            network_service = get_network_service()
            
            # Check for XOVI installation
            xovi_check = network_service.execute_command("test -d /home/root/xovi && echo 'exists' || echo 'missing'")
            xovi_installed = xovi_check.success and 'exists' in xovi_check.stdout
            
            # Check for AppLoad installation
            appload_check = network_service.execute_command("test -d /home/root/xovi/exthome/appload && echo 'exists' || echo 'missing'")
            appload_installed = appload_check.success and 'exists' in appload_check.stdout
            
            # Check for KOReader installation
            koreader_check = network_service.execute_command("test -f /home/root/xovi/exthome/appload/koreader.so && echo 'exists' || echo 'missing'")
            koreader_installed = koreader_check.success and 'exists' in koreader_check.stdout
            
            # Check for xovi-tripletap
            tripletap_check = network_service.execute_command("test -d /home/root/xovi-tripletap && echo 'exists' || echo 'missing'")
            tripletap_installed = tripletap_check.success and 'exists' in tripletap_check.stdout
            
            # Count extensions
            extensions_count = 0
            if xovi_installed:
                ext_check = network_service.execute_command("find /home/root/xovi/extensions.d -name '*.so' 2>/dev/null | wc -l")
                if ext_check.success:
                    try:
                        extensions_count = int(ext_check.stdout.strip())
                    except ValueError:
                        extensions_count = 0
            
            # List available backups
            backup_check = network_service.execute_command("ls -1d /home/root/koreader_backup_* 2>/dev/null | wc -l")
            backup_count = 0
            if backup_check.success:
                try:
                    backup_count = int(backup_check.stdout.strip())
                except ValueError:
                    backup_count = 0
            
            # Get XOVI version if available
            xovi_version = None
            if xovi_installed:
                version_check = network_service.execute_command("cat /home/root/xovi/VERSION 2>/dev/null || echo 'unknown'")
                if version_check.success and version_check.stdout.strip() != 'unknown':
                    xovi_version = version_check.stdout.strip()
            
            self.installation_info = InstallationInfo(
                xovi_installed=xovi_installed,
                xovi_version=xovi_version,
                appload_installed=appload_installed,
                koreader_installed=koreader_installed,
                tripletap_installed=tripletap_installed,
                extensions_count=extensions_count,
                backup_count=backup_count
            )
            
            self._logger.info("Installation information refreshed successfully")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to refresh installation info: {e}")
            self.last_error = str(e)
            return False
    
    def refresh_all_info(self) -> bool:
        """
        Refresh all device information.
        
        Returns:
            True if all information was refreshed successfully
        """
        success = True
        success &= self.refresh_device_info()
        success &= self.refresh_network_info()  
        success &= self.refresh_installation_info()
        return success
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get a comprehensive status summary.
        
        Returns:
            Dictionary containing device status information
        """
        return {
            "device_type": self.device_type.display_name if self.device_type else "Unknown",
            "ip_address": self.ip_address,
            "connection_status": self.connection_status.value,
            "last_connection_attempt": self.last_connection_attempt.isoformat() if self.last_connection_attempt else None,
            "last_error": self.last_error,
            "is_configured": self.is_configured(),
            "is_connected": self.is_connected(),
            "installation_status": self.installation_info.get_status().value if self.installation_info else "unknown",
            "has_network": self.network_info.has_connectivity() if self.network_info else False
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert device to dictionary representation.
        
        Returns:
            Dictionary representation of the device
        """
        return {
            "ip_address": self.ip_address,
            "device_type": self.device_type.short_name if self.device_type else None,
            "connection_status": self.connection_status.value,
            "last_connection_attempt": self.last_connection_attempt.isoformat() if self.last_connection_attempt else None,
            "last_error": self.last_error,
            "device_info": {
                "hostname": self.device_info.hostname if self.device_info else None,
                "kernel_version": self.device_info.kernel_version if self.device_info else None,
                "remarkable_version": self.device_info.remarkable_version if self.device_info else None,
                "free_space_mb": self.device_info.get_free_space_mb() if self.device_info else None,
                "total_space_mb": self.device_info.get_total_space_mb() if self.device_info else None
            },
            "network_info": {
                "primary_ip": self.network_info.get_primary_ip() if self.network_info else None,
                "wifi_enabled": self.network_info.wifi_enabled if self.network_info else False,
                "ethernet_enabled": self.network_info.ethernet_enabled if self.network_info else False
            },
            "installation_info": {
                "status": self.installation_info.get_status().value if self.installation_info else "unknown",
                "xovi_installed": self.installation_info.xovi_installed if self.installation_info else False,
                "koreader_installed": self.installation_info.koreader_installed if self.installation_info else False,
                "extensions_count": self.installation_info.extensions_count if self.installation_info else 0
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Device':
        """
        Create Device instance from dictionary.
        
        Args:
            data: Dictionary representation of device
            
        Returns:
            Device instance
        """
        device_type = None
        if data.get("device_type"):
            device_type = DeviceType.from_short_name(data["device_type"])
        
        device = cls(
            ip_address=data.get("ip_address"),
            device_type=device_type
        )
        
        # Restore connection status
        if connection_status := data.get("connection_status"):
            try:
                device.connection_status = ConnectionStatus(connection_status)
            except ValueError:
                pass
        
        # Restore timestamps and errors
        if last_attempt := data.get("last_connection_attempt"):
            try:
                device.last_connection_attempt = datetime.fromisoformat(last_attempt)
            except ValueError:
                pass
                
        device.last_error = data.get("last_error")
        
        return device


# Utility functions for device management

def get_default_device_ip() -> str:
    """Get the default reMarkable device IP address."""
    return "10.11.99.1"


def is_valid_remarkable_ip(ip_address: str) -> bool:
    """
    Check if an IP address is likely a reMarkable device.
    
    Args:
        ip_address: IP address to validate
        
    Returns:
        True if IP appears to be a reMarkable device
    """
    if not ip_address:
        return False
    
    try:
        ip = IPv4Address(ip_address)
        
        # Common reMarkable IP ranges
        remarkable_networks = [
            "10.11.99.0/24",    # USB ethernet
            "192.168.0.0/16",   # Common WiFi networks
            "172.16.0.0/12",    # Private networks
            "10.0.0.0/8"        # Private networks
        ]
        
        # Check if IP is in any of the common ranges
        for network in remarkable_networks:
            try:
                from ipaddress import ip_network
                if ip in ip_network(network):
                    return True
            except ValueError:
                continue
        
        return False
        
    except AddressValueError:
        return False


def detect_local_remarkable_devices() -> List[str]:
    """
    Attempt to detect reMarkable devices on the local network.
    
    Returns:
        List of potential reMarkable IP addresses
        
    Network scanning functionality could be implemented here in the future.
    """
    # This would implement network scanning to find reMarkable devices
    # For now, return common IP addresses
    return ["10.11.99.1"]  # USB ethernet default