"""
Windows compatibility utilities for freeMarkable.

This module provides Windows-specific functionality and compatibility layers
for operations that may differ between Windows and Unix-like systems.
"""

import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
import platform

# Windows-specific imports
if os.name == 'nt':
    try:
        import winreg
        import ctypes
        from ctypes import wintypes
        import win32api
        import win32con
        import win32security
        WINDOWS_MODULES_AVAILABLE = True
    except ImportError:
        WINDOWS_MODULES_AVAILABLE = False
        winreg = None
        ctypes = None
        win32api = None
else:
    WINDOWS_MODULES_AVAILABLE = False
    winreg = None
    ctypes = None
    win32api = None


def is_windows() -> bool:
    """Check if running on Windows."""
    return os.name == 'nt'


def is_admin() -> bool:
    """Check if running with administrator privileges on Windows."""
    if not is_windows():
        return os.geteuid() == 0 if hasattr(os, 'geteuid') else False
    
    if not WINDOWS_MODULES_AVAILABLE:
        return False
    
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def get_windows_version() -> Optional[str]:
    """Get Windows version information."""
    if not is_windows():
        return None
    
    try:
        return platform.platform()
    except Exception:
        return "Unknown Windows Version"


def check_windows_ssh_support() -> Dict[str, Any]:
    """Check Windows SSH support capabilities."""
    result = {
        "openssh_available": False,
        "putty_available": False,
        "paramiko_available": False,
        "windows_ssh_service": False,
        "recommended_client": "paramiko"
    }
    
    if not is_windows():
        return result
    
    # Check for paramiko (our primary SSH client)
    try:
        import paramiko
        result["paramiko_available"] = True
        result["recommended_client"] = "paramiko"
    except ImportError:
        pass
    
    # Check for OpenSSH (Windows 10/11 includes this)
    try:
        ssh_result = subprocess.run(
            ["ssh", "-V"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        if ssh_result.returncode == 0 or "OpenSSH" in ssh_result.stderr:
            result["openssh_available"] = True
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Check for PuTTY
    try:
        putty_result = subprocess.run(
            ["putty", "-V"], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        if putty_result.returncode == 0:
            result["putty_available"] = True
    except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Check Windows SSH service
    if WINDOWS_MODULES_AVAILABLE:
        try:
            import win32service
            services = win32service.EnumServicesStatus(
                win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ENUMERATE_SERVICE),
                win32service.SERVICE_TYPE_WIN32,
                win32service.SERVICE_STATE_ALL
            )
            for service in services:
                if 'ssh' in service[0].lower():
                    result["windows_ssh_service"] = True
                    break
        except Exception:
            pass
    
    return result


def get_windows_temp_directory() -> Path:
    """Get Windows-appropriate temporary directory."""
    if is_windows():
        # Use Windows temp directory
        temp_dir = Path(os.environ.get('TEMP', os.environ.get('TMP', r'C:\Temp')))
    else:
        temp_dir = Path('/tmp')
    
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def get_windows_downloads_directory() -> Path:
    """Get Windows-appropriate downloads directory."""
    if is_windows():
        # Try to get user's Downloads folder
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                              r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
                downloads_dir = Path(winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")[0])
                if downloads_dir.exists():
                    return downloads_dir
        except Exception:
            pass
        
        # Fallback to user profile Downloads
        user_profile = Path(os.environ.get('USERPROFILE', ''))
        if user_profile.exists():
            downloads_dir = user_profile / 'Downloads'
            if downloads_dir.exists():
                return downloads_dir
        
        # Last resort fallback
        return Path.home() / 'Downloads'
    else:
        return Path.home() / 'Downloads'


def normalize_path_for_platform(path_str: str) -> str:
    """Normalize path string for the current platform."""
    # Convert to Path and back to string for platform normalization
    return str(Path(path_str))


def get_executable_extension() -> str:
    """Get executable file extension for the current platform."""
    return '.exe' if is_windows() else ''


def check_windows_firewall_ssh() -> bool:
    """Check if SSH port is blocked by Windows Firewall."""
    if not is_windows() or not WINDOWS_MODULES_AVAILABLE:
        return True  # Assume OK on non-Windows
    
    try:
        # Simple check - try to create a socket on SSH port
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', 22))
        sock.close()
        
        # If we can connect to localhost:22, firewall likely allows SSH
        return result == 0
    except Exception:
        return True  # Assume OK if we can't check


def get_windows_network_interfaces() -> List[Dict[str, str]]:
    """Get network interface information on Windows."""
    interfaces = []
    
    if not is_windows():
        return interfaces
    
    try:
        # Use ipconfig to get interface information
        result = subprocess.run(
            ["ipconfig", "/all"], 
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        if result.returncode == 0:
            # Parse ipconfig output for interface information
            current_interface = {}
            for line in result.stdout.split('\n'):
                line = line.strip()
                if 'adapter' in line.lower() and ':' in line:
                    if current_interface:
                        interfaces.append(current_interface)
                    current_interface = {'name': line, 'ip': None, 'type': 'unknown'}
                elif 'IPv4 Address' in line:
                    ip_match = line.split(':')[-1].strip()
                    if ip_match:
                        current_interface['ip'] = ip_match.split('(')[0].strip()
                elif 'ethernet' in line.lower():
                    current_interface['type'] = 'ethernet'
                elif 'wireless' in line.lower() or 'wi-fi' in line.lower():
                    current_interface['type'] = 'wifi'
            
            if current_interface:
                interfaces.append(current_interface)
                
    except Exception as e:
        logging.debug(f"Failed to get Windows network interfaces: {e}")
    
    return interfaces


def setup_windows_console() -> None:
    """Setup Windows console for better display."""
    if not is_windows():
        return
    
    try:
        # Enable ANSI color codes on Windows 10+
        if WINDOWS_MODULES_AVAILABLE:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


def check_windows_dependencies() -> Dict[str, bool]:
    """Check Windows-specific dependencies."""
    dependencies = {
        "pywin32": False,
        "paramiko": False,
        "customtkinter": False,
        "requests": False
    }
    
    # Check each dependency
    for dep in dependencies:
        try:
            __import__(dep)
            dependencies[dep] = True
        except ImportError:
            dependencies[dep] = False
    
    return dependencies


def get_windows_ssh_client_path() -> Optional[str]:
    """Get path to Windows SSH client if available."""
    if not is_windows():
        return None
    
    # Check for OpenSSH in Windows
    possible_paths = [
        r"C:\Windows\System32\OpenSSH\ssh.exe",
        r"C:\Program Files\OpenSSH\ssh.exe",
        r"C:\Program Files (x86)\OpenSSH\ssh.exe"
    ]
    
    for path in possible_paths:
        if Path(path).exists():
            return path
    
    # Check PATH
    try:
        result = subprocess.run(["where", "ssh"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')[0]
    except Exception:
        pass
    
    return None


def create_windows_shortcut(target_path: str, shortcut_path: str, 
                           description: str = "", icon_path: str = "") -> bool:
    """Create a Windows shortcut."""
    if not is_windows() or not WINDOWS_MODULES_AVAILABLE:
        return False
    
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = target_path
        shortcut.WorkingDirectory = str(Path(target_path).parent)
        if description:
            shortcut.Description = description
        if icon_path:
            shortcut.IconLocation = icon_path
        shortcut.save()
        return True
    except Exception as e:
        logging.debug(f"Failed to create Windows shortcut: {e}")
        return False


# Utility functions for cross-platform compatibility

# Testing function
def test_windows_compatibility() -> Dict[str, Any]:
    """Test Windows compatibility and return results."""
    results = {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "is_windows": is_windows(),
        "is_admin": is_admin(),
        "windows_modules": WINDOWS_MODULES_AVAILABLE,
        "ssh_support": check_windows_ssh_support(),
        "dependencies": check_windows_dependencies(),
        "ssh_client_path": get_windows_ssh_client_path(),
        "config_dir": str(get_platform_config_dir("remarkable-xovi-installer")),
        "temp_dir": str(get_windows_temp_directory()),
        "downloads_dir": str(get_windows_downloads_directory())
    }
    
    return results


if __name__ == "__main__":
    # Test Windows compatibility
    results = test_windows_compatibility()
    print("Windows Compatibility Test Results:")
    print("=" * 40)
    for key, value in results.items():
        print(f"{key}: {value}")