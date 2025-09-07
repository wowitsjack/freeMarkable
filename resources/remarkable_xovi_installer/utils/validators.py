"""
Input validation utilities for freeMarkable.

This module provides validation functions for IP addresses, passwords,
file paths, network connectivity, and other user inputs.
"""

import re
import os
import socket
import subprocess
import logging
from pathlib import Path
from typing import Union, Optional, List, Tuple, Dict, Any
from ipaddress import IPv4Address, AddressValueError
from urllib.parse import urlparse

# Import Windows compatibility utilities
try:
    from .windows_compat import is_windows, check_windows_ssh_support, get_windows_ssh_client_path
except ImportError:
    # Fallback if windows_compat is not available
    def is_windows():
        return os.name == 'nt'
    def check_windows_ssh_support():
        return {"paramiko_available": False}
    def get_windows_ssh_client_path():
        return None


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


class ValidationResult:
    """Result of a validation operation."""
    
    def __init__(self, is_valid: bool, message: str = "", details: Optional[Dict[str, Any]] = None):
        self.is_valid = is_valid
        self.message = message
        self.details = details or {}
    
    def __bool__(self) -> bool:
        return self.is_valid
    
    def __str__(self) -> str:
        return f"ValidationResult(valid={self.is_valid}, message='{self.message}')"


class Validator:
    """
    Comprehensive validator class for freeMarkable.
    
    Provides validation methods for various input types including
    IP addresses, passwords, file paths, and network connectivity.
    """
    
    def __init__(self):
        self._logger = logging.getLogger(__name__)
        
        # Regex patterns matching the bash script
        self.ip_pattern = re.compile(r'^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$')
        self.hostname_pattern = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$')
        
        # Common reMarkable IP ranges
        self.remarkable_networks = [
            "10.11.99.0/24",    # USB ethernet default
            "192.168.0.0/16",   # Common WiFi networks
            "172.16.0.0/12",    # Private networks
            "10.0.0.0/8"        # Private networks
        ]
    
    def validate_ip_address(self, ip_address: str, allow_hostnames: bool = False) -> ValidationResult:
        """
        Validate IP address format and optionally resolve hostnames.
        
        Args:
            ip_address: IP address or hostname to validate
            allow_hostnames: Whether to allow and resolve hostnames
            
        Returns:
            ValidationResult with validation status and details
        """
        if not ip_address or not isinstance(ip_address, str):
            return ValidationResult(False, "IP address cannot be empty")
        
        ip_address = ip_address.strip()
        
        # Check basic format with regex (matching bash script)
        if self.ip_pattern.match(ip_address):
            try:
                # Validate with ipaddress module for proper validation
                ip_obj = IPv4Address(ip_address)
                
                # Additional checks for reMarkable devices
                is_remarkable_range = self._is_remarkable_ip_range(ip_address)
                is_private = ip_obj.is_private
                
                details = {
                    "ip_object": ip_obj,
                    "is_private": is_private,
                    "is_remarkable_range": is_remarkable_range,
                    "ip_type": "ipv4"
                }
                
                if ip_obj.is_loopback:
                    return ValidationResult(False, "Loopback addresses are not valid for reMarkable devices", details)
                
                if ip_obj.is_multicast:
                    return ValidationResult(False, "Multicast addresses are not valid for reMarkable devices", details)
                
                return ValidationResult(True, "Valid IP address", details)
                
            except AddressValueError as e:
                return ValidationResult(False, f"Invalid IP address format: {e}")
        
        # If not a valid IP, check if it's a hostname (if allowed)
        if allow_hostnames:
            if self.hostname_pattern.match(ip_address):
                try:
                    # Try to resolve hostname
                    resolved_ip = socket.gethostbyname(ip_address)
                    recursive_result = self.validate_ip_address(resolved_ip, allow_hostnames=False)
                    
                    if recursive_result.is_valid:
                        details = recursive_result.details.copy()
                        details.update({
                            "original_hostname": ip_address,
                            "resolved_ip": resolved_ip,
                            "ip_type": "hostname"
                        })
                        return ValidationResult(True, f"Valid hostname resolves to {resolved_ip}", details)
                    else:
                        return ValidationResult(False, f"Hostname resolves to invalid IP: {recursive_result.message}")
                        
                except socket.gaierror as e:
                    return ValidationResult(False, f"Cannot resolve hostname: {e}")
            else:
                return ValidationResult(False, "Invalid hostname format")
        
        return ValidationResult(False, "Invalid IP address format. Expected format: xxx.xxx.xxx.xxx")
    
    def _is_remarkable_ip_range(self, ip_address: str) -> bool:
        """Check if IP address is in a typical reMarkable device range."""
        try:
            ip = IPv4Address(ip_address)
            from ipaddress import ip_network
            
            for network_str in self.remarkable_networks:
                network = ip_network(network_str)
                if ip in network:
                    return True
            return False
        except (AddressValueError, ValueError):
            return False
    
    def validate_ssh_password(self, password: str, min_length: int = 1, max_length: int = 256) -> ValidationResult:
        """
        Validate SSH password.
        
        Args:
            password: Password to validate
            min_length: Minimum password length
            max_length: Maximum password length
            
        Returns:
            ValidationResult with validation status
        """
        if not password:
            return ValidationResult(False, "Password cannot be empty")
        
        if not isinstance(password, str):
            return ValidationResult(False, "Password must be a string")
        
        if len(password) < min_length:
            return ValidationResult(False, f"Password too short (minimum {min_length} characters)")
        
        if len(password) > max_length:
            return ValidationResult(False, f"Password too long (maximum {max_length} characters)")
        
        # Check for problematic characters that might cause SSH issues
        problematic_chars = ['\n', '\r', '\0']
        for char in problematic_chars:
            if char in password:
                return ValidationResult(False, f"Password contains invalid character: {repr(char)}")
        
        # Basic strength indicators
        details = {
            "length": len(password),
            "has_uppercase": any(c.isupper() for c in password),
            "has_lowercase": any(c.islower() for c in password),
            "has_digits": any(c.isdigit() for c in password),
            "has_special": any(not c.isalnum() for c in password)
        }
        
        return ValidationResult(True, "Valid password", details)
    
    def validate_file_path(self, file_path: Union[str, Path], 
                          must_exist: bool = False,
                          must_be_file: bool = False,
                          must_be_dir: bool = False,
                          must_be_readable: bool = False,
                          must_be_writable: bool = False) -> ValidationResult:
        """
        Validate file path and check various conditions.
        
        Args:
            file_path: Path to validate
            must_exist: Whether the path must exist
            must_be_file: Whether the path must be a file
            must_be_dir: Whether the path must be a directory
            must_be_readable: Whether the path must be readable
            must_be_writable: Whether the path must be writable
            
        Returns:
            ValidationResult with validation status and path details
        """
        if not file_path:
            return ValidationResult(False, "File path cannot be empty")
        
        try:
            path_obj = Path(file_path)
            
            # Basic path validation
            if not path_obj.is_absolute() and '..' in str(path_obj):
                # Allow relative paths but warn about potential security issues with ..
                self._logger.warning(f"Path contains '..' which may be a security risk: {file_path}")
            
            # Check existence
            exists = path_obj.exists()
            if must_exist and not exists:
                return ValidationResult(False, f"Path does not exist: {file_path}")
            
            details = {
                "path_object": path_obj,
                "exists": exists,
                "is_absolute": path_obj.is_absolute(),
                "parent_exists": path_obj.parent.exists() if path_obj.parent != path_obj else True
            }
            
            if exists:
                is_file = path_obj.is_file()
                is_dir = path_obj.is_dir()
                
                details.update({
                    "is_file": is_file,
                    "is_dir": is_dir,
                    "is_symlink": path_obj.is_symlink(),
                    "size_bytes": path_obj.stat().st_size if is_file else None
                })
                
                # Type checks
                if must_be_file and not is_file:
                    return ValidationResult(False, f"Path is not a file: {file_path}")
                
                if must_be_dir and not is_dir:
                    return ValidationResult(False, f"Path is not a directory: {file_path}")
                
                # Permission checks
                if must_be_readable and not os.access(path_obj, os.R_OK):
                    return ValidationResult(False, f"Path is not readable: {file_path}")
                
                if must_be_writable and not os.access(path_obj, os.W_OK):
                    return ValidationResult(False, f"Path is not writable: {file_path}")
                
                details.update({
                    "readable": os.access(path_obj, os.R_OK),
                    "writable": os.access(path_obj, os.W_OK),
                    "executable": os.access(path_obj, os.X_OK)
                })
            
            return ValidationResult(True, "Valid file path", details)
            
        except Exception as e:
            return ValidationResult(False, f"Invalid file path: {e}")
    
    def validate_url(self, url: str, allowed_schemes: Optional[List[str]] = None) -> ValidationResult:
        """
        Validate URL format and scheme.
        
        Args:
            url: URL to validate
            allowed_schemes: List of allowed schemes (default: ['http', 'https'])
            
        Returns:
            ValidationResult with URL validation status
        """
        if not url:
            return ValidationResult(False, "URL cannot be empty")
        
        if allowed_schemes is None:
            allowed_schemes = ['http', 'https']
        
        try:
            parsed = urlparse(url)
            
            if not parsed.scheme:
                return ValidationResult(False, "URL missing scheme (http/https)")
            
            if parsed.scheme.lower() not in allowed_schemes:
                return ValidationResult(False, f"Invalid URL scheme. Allowed: {allowed_schemes}")
            
            if not parsed.netloc:
                return ValidationResult(False, "URL missing network location (domain)")
            
            details = {
                "scheme": parsed.scheme,
                "netloc": parsed.netloc,
                "path": parsed.path,
                "params": parsed.params,
                "query": parsed.query,
                "fragment": parsed.fragment
            }
            
            return ValidationResult(True, "Valid URL", details)
            
        except Exception as e:
            return ValidationResult(False, f"Invalid URL format: {e}")
    
    def validate_device_type(self, device_type: str) -> ValidationResult:
        """
        Validate reMarkable device type.
        
        Args:
            device_type: Device type string to validate
            
        Returns:
            ValidationResult with device type validation
        """
        if not device_type:
            return ValidationResult(False, "Device type cannot be empty")
        
        valid_types = ['rM1', 'rM2', 'rMPP', 'rm1', 'rm2', 'rmpp']
        normalized = device_type.strip()
        
        if normalized not in valid_types:
            return ValidationResult(False, f"Invalid device type. Must be one of: {valid_types}")
        
        # Normalize to standard format
        normalized_upper = normalized.upper()
        if normalized_upper in ['RM1', 'RM2', 'RMPP']:
            canonical = 'r' + normalized_upper[1:]  # Convert RM1 -> rM1
        else:
            canonical = normalized
        
        details = {
            "original": device_type,
            "normalized": canonical,
            "is_supported": canonical in ['rM1', 'rM2']  # rMPP is future support
        }
        
        return ValidationResult(True, "Valid device type", details)
    
    def check_network_connectivity(self, host: str, port: int = 22, timeout: int = 5) -> ValidationResult:
        """
        Check network connectivity to a host and port.
        
        Args:
            host: Hostname or IP address
            port: Port number (default: 22 for SSH)
            timeout: Connection timeout in seconds
            
        Returns:
            ValidationResult with connectivity status
        """
        try:
            # First validate the host as an IP or hostname
            ip_result = self.validate_ip_address(host, allow_hostnames=True)
            if not ip_result.is_valid:
                return ValidationResult(False, f"Invalid host: {ip_result.message}")
            
            # Attempt socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            try:
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    details = {
                        "host": host,
                        "port": port,
                        "timeout": timeout,
                        "connection_successful": True
                    }
                    return ValidationResult(True, f"Successfully connected to {host}:{port}", details)
                else:
                    details = {
                        "host": host,
                        "port": port,
                        "timeout": timeout,
                        "connection_successful": False,
                        "error_code": result
                    }
                    return ValidationResult(False, f"Cannot connect to {host}:{port} (error {result})", details)
                    
            except socket.timeout:
                return ValidationResult(False, f"Connection to {host}:{port} timed out after {timeout} seconds")
            except Exception as e:
                return ValidationResult(False, f"Connection error: {e}")
                
        except Exception as e:
            return ValidationResult(False, f"Network connectivity check failed: {e}")
    
    def check_ssh_requirements(self) -> ValidationResult:
        """
        Check if SSH client requirements are met.
        
        Returns:
            ValidationResult with SSH requirements status
        """
        if is_windows():
            # Use Windows-specific SSH checking
            ssh_support = check_windows_ssh_support()
            
            # On Windows, paramiko is our primary SSH client
            if ssh_support.get("paramiko_available", False):
                details = {
                    "platform": "windows",
                    "primary_client": "paramiko",
                    "ssh_support": ssh_support,
                    "all_requirements_met": True
                }
                return ValidationResult(True, "SSH support available via paramiko", details)
            
            # Check for OpenSSH as fallback
            elif ssh_support.get("openssh_available", False):
                details = {
                    "platform": "windows", 
                    "primary_client": "openssh",
                    "ssh_support": ssh_support,
                    "all_requirements_met": True,
                    "warning": "Using OpenSSH - paramiko recommended for better integration"
                }
                return ValidationResult(True, "SSH support available via OpenSSH", details)
            
            else:
                details = {
                    "platform": "windows",
                    "ssh_support": ssh_support,
                    "all_requirements_met": False,
                    "recommendation": "Install paramiko: pip install paramiko"
                }
                return ValidationResult(False, "No SSH client available. Please install paramiko.", details)
        
        else:
            # Unix-like systems - use original logic
            required_commands = ['ssh']  # sshpass and scp are not required since we use paramiko
            missing_commands = []
            available_commands = {}
            
            for cmd in required_commands:
                try:
                    # Check if command exists
                    result = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        available_commands[cmd] = result.stdout.strip()
                    else:
                        missing_commands.append(cmd)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    missing_commands.append(cmd)
            
            # Check for paramiko as primary SSH client
            paramiko_available = False
            try:
                import paramiko
                paramiko_available = True
            except ImportError:
                pass
            
            if paramiko_available:
                available_commands['paramiko'] = 'python module'
            
            # SSH is available if either system SSH or paramiko is available
            ssh_available = 'ssh' in available_commands or paramiko_available
            
            if not ssh_available:
                return ValidationResult(
                    False,
                    "No SSH client available. Please install OpenSSH or paramiko.",
                    {"missing": ["ssh", "paramiko"], "available": available_commands}
                )
            
            # Check SSH version if available
            version_info = "paramiko module"
            if 'ssh' in available_commands:
                try:
                    ssh_version = subprocess.run(['ssh', '-V'], capture_output=True, text=True, timeout=5)
                    version_info = ssh_version.stderr.strip()  # SSH version goes to stderr
                except Exception:
                    version_info = "Unknown SSH version"
            
            details = {
                "platform": "unix",
                "available_commands": available_commands,
                "ssh_version": version_info,
                "paramiko_available": paramiko_available,
                "all_requirements_met": True
            }
            
            return ValidationResult(True, "SSH requirements met", details)
    
    def sanitize_filename(self, filename: str, replacement: str = "_") -> str:
        """
        Sanitize filename by removing/replacing problematic characters.
        
        Args:
            filename: Original filename
            replacement: Character to replace problematic characters with
            
        Returns:
            Sanitized filename
        """
        if not filename:
            return "unnamed"
        
        # Remove problematic characters
        problematic_chars = r'[<>:"/\\|?*\x00-\x1f]'
        sanitized = re.sub(problematic_chars, replacement, filename)
        
        # Remove leading/trailing dots and spaces
        sanitized = sanitized.strip('. ')
        
        # Ensure not empty
        if not sanitized:
            sanitized = "unnamed"
        
        # Limit length
        if len(sanitized) > 255:
            sanitized = sanitized[:255]
        
        return sanitized
    
    def validate_backup_name(self, backup_name: str) -> ValidationResult:
        """
        Validate backup name format.
        
        Args:
            backup_name: Backup name to validate
            
        Returns:
            ValidationResult with backup name validation
        """
        if not backup_name:
            return ValidationResult(False, "Backup name cannot be empty")
        
        # Check for valid characters (alphanumeric, underscore, hyphen, dot)
        if not re.match(r'^[a-zA-Z0-9._-]+$', backup_name):
            return ValidationResult(False, "Backup name contains invalid characters")
        
        # Check length
        if len(backup_name) > 100:
            return ValidationResult(False, "Backup name too long (max 100 characters)")
        
        # Check for reserved names
        reserved_names = ['con', 'prn', 'aux', 'nul'] + [f'com{i}' for i in range(1, 10)] + [f'lpt{i}' for i in range(1, 10)]
        if backup_name.lower() in reserved_names:
            return ValidationResult(False, f"Backup name '{backup_name}' is reserved")
        
        details = {
            "sanitized_name": self.sanitize_filename(backup_name),
            "length": len(backup_name),
            "valid_chars_only": True
        }
        
        return ValidationResult(True, "Valid backup name", details)
    
    def validate_installation_stage(self, stage: str) -> ValidationResult:
        """
        Validate installation stage value.
        
        Args:
            stage: Stage value to validate
            
        Returns:
            ValidationResult with stage validation
        """
        valid_stages = ['not_started', '1', '2', 'completed', 'failed', 'launcher_only']
        
        if stage not in valid_stages:
            return ValidationResult(False, f"Invalid stage. Must be one of: {valid_stages}")
        
        details = {
            "stage": stage,
            "is_numeric": stage.isdigit(),
            "valid_stages": valid_stages
        }
        
        return ValidationResult(True, "Valid installation stage", details)


# Global validator instance
_global_validator: Optional[Validator] = None


def get_validator() -> Validator:
    """
    Get the global validator instance.
    
    Returns:
        Global Validator instance
    """
    global _global_validator
    if _global_validator is None:
        _global_validator = Validator()
    return _global_validator


# Convenience functions for common validations

def validate_ip(ip_address: str) -> ValidationResult:
    """Validate IP address (convenience function)."""
    return get_validator().validate_ip_address(ip_address)


def validate_password(password: str) -> ValidationResult:
    """Validate password (convenience function)."""
    return get_validator().validate_ssh_password(password)


def validate_path(file_path: Union[str, Path], **kwargs) -> ValidationResult:
    """Validate file path (convenience function)."""
    return get_validator().validate_file_path(file_path, **kwargs)


def check_connectivity(host: str, port: int = 22) -> ValidationResult:
    """Check network connectivity (convenience function)."""
    return get_validator().check_network_connectivity(host, port)


def check_ssh_available() -> ValidationResult:
    """Check SSH requirements (convenience function)."""
    return get_validator().check_ssh_requirements()


# Testing function
def test_validators() -> None:
    """Test all validator functions with sample inputs."""
    validator = get_validator()
    
    print("Testing Validator Functions:")
    print()
    
    # Test IP validation
    test_ips = ["10.11.99.1", "192.168.1.100", "invalid.ip", "256.256.256.256", "localhost"]
    for ip in test_ips:
        result = validator.validate_ip_address(ip, allow_hostnames=True)
        print(f"IP '{ip}': {result.is_valid} - {result.message}")
    
    print()
    
    # Test password validation
    test_passwords = ["", "weak", "StrongPassword123!", "a" * 300]
    for pwd in test_passwords:
        result = validator.validate_ssh_password(pwd)
        print(f"Password: {result.is_valid} - {result.message}")
    
    print()
    
    # Test file path validation
    test_paths = ["/tmp", "/nonexistent", ".", ".."]
    for path in test_paths:
        result = validator.validate_file_path(path)
        print(f"Path '{path}': {result.is_valid} - {result.message}")
    
    print()
    
    # Test SSH requirements
    ssh_result = validator.check_ssh_requirements()
    print(f"SSH Requirements: {ssh_result.is_valid} - {ssh_result.message}")


if __name__ == "__main__":
    test_validators()