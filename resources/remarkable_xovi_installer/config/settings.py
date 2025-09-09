"""
Configuration management system for freeMarkable.

This module handles application settings, user preferences, default values,
and configuration file loading/saving with proper error handling.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, TYPE_CHECKING
from dataclasses import dataclass, asdict, field
from enum import Enum

if TYPE_CHECKING:
    from ..models.device import DeviceType


def _get_version_from_file() -> str:
    """Read version from VERSION file in resources directory."""
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
    except Exception:
        pass
    # Fallback to hardcoded version if file doesn't exist
    return "1.0.5"


class LogLevel(Enum):
    """Available log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class NetworkConfig:
    """Network and connection configuration."""
    default_ip: str = "10.11.99.1"
    connection_timeout: int = 10
    ssh_port: int = 22
    max_connection_attempts: int = 3
    retry_delay: int = 2


@dataclass
class DownloadConfig:
    """Download URLs and configuration."""
    # Default URLs (32-bit ARM for RM1/RM2)
    xovi_extensions_url: str = "https://github.com/asivery/rm-xovi-extensions/releases/download/v12-12082025/extensions-arm32-testing.zip"
    appload_url: str = "https://github.com/asivery/rm-appload/releases/download/v0.2.4/appload-arm32.zip"
    xovi_binary_url: str = "https://github.com/asivery/xovi/releases/latest/download/xovi-arm32.so"
    koreader_url: str = "https://github.com/koreader/koreader/releases/download/v2025.08/koreader-remarkable-v2025.08.zip"
    xovi_tripletap_url: str = "https://github.com/rmitchellscott/xovi-tripletap/archive/refs/heads/main.zip"
    
    # Architecture-specific URL mappings
    _url_mappings: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "arm32": {
            "xovi_extensions": "https://github.com/asivery/rm-xovi-extensions/releases/download/v12-12082025/extensions-arm32-testing.zip",
            "appload": "https://github.com/asivery/rm-appload/releases/download/v0.2.4/appload-arm32.zip",
            "xovi_binary": "https://github.com/asivery/xovi/releases/latest/download/xovi-arm32.so",
            "koreader": "https://github.com/koreader/koreader/releases/download/v2025.08/koreader-remarkable-v2025.08.zip"
        },
        "aarch64": {
            "xovi_extensions": "https://github.com/asivery/rm-xovi-extensions/releases/download/v12-12082025/extensions-aarch64.zip",
            "appload": "https://github.com/asivery/rm-appload/releases/download/v0.2.4/appload-aarch64.zip",
            "xovi_binary": "https://github.com/asivery/xovi/releases/download/v0.2.2/xovi-aarch64.so",
            "koreader": "https://build.koreader.rocks/download/stable/v2025.08/koreader-remarkable-aarch64-v2025.08.zip"
        }
    })
    
    # Download settings
    download_timeout: int = 300
    max_retries: int = 3
    chunk_size: int = 8192
    
    def get_url_for_architecture(self, component: str, device_type: Optional[Any] = None) -> str:
        """
        Get the appropriate URL for a component based on device architecture.
        
        Args:
            component: Component name (xovi_extensions, appload, xovi_binary, koreader)
            device_type: Device type to determine architecture
            
        Returns:
            URL for the component matching the device architecture
        """
        if device_type is None:
            # Return default URL if no device type specified
            return getattr(self, f"{component}_url", "")
        
        # Determine architecture key
        if device_type and hasattr(device_type, 'architecture'):
            # Use the architecture property from DeviceType
            arch_key = "aarch64" if device_type.architecture == "aarch64" else "arm32"
        elif device_type and hasattr(device_type, 'value') and device_type.value == "rMPP":
            arch_key = "aarch64"
        else:
            arch_key = "arm32"  # Default to 32-bit ARM for RM1/RM2
        
        # Get URL from mapping or fall back to default
        if arch_key in self._url_mappings and component in self._url_mappings[arch_key]:
            return self._url_mappings[arch_key][component]
        
        # Fallback to default URL
        return getattr(self, f"{component}_url", "")
    
    def get_filename_for_architecture(self, component: str, device_type: Optional[Any] = None) -> str:
        """
        Get the appropriate filename for a component based on device architecture.
        
        Args:
            component: Component name (xovi_extensions, appload, xovi_binary, koreader)
            device_type: Device type to determine architecture
            
        Returns:
            Filename for the component matching the device architecture
        """
        is_paper_pro = False
        if device_type:
            if hasattr(device_type, 'architecture'):
                is_paper_pro = device_type.architecture == "aarch64"
            elif hasattr(device_type, 'value'):
                is_paper_pro = device_type.value == "rMPP"
        
        if not is_paper_pro:
            # Default 32-bit ARM filenames
            filename_map = {
                "xovi_extensions": "extensions-arm32-testing.zip",
                "appload": "appload-arm32.zip",
                "xovi_binary": "xovi-arm32.so",
                "koreader": "koreader-remarkable-v2025.08.zip"
            }
        else:
            # 64-bit aarch64 filenames for Paper Pro
            filename_map = {
                "xovi_extensions": "extensions-aarch64.zip",
                "appload": "appload-aarch64.zip",
                "xovi_binary": "xovi-aarch64.so",
                "koreader": "koreader-remarkable-aarch64-v2025.08.zip"
            }
        
        return filename_map.get(component, f"{component}.zip")


@dataclass
class PathConfig:
    """File and directory path configuration."""
    downloads_dir: str = "downloads"
    backup_prefix: str = "koreader_backup"
    stage_file: str = ".koreader_install_stage"
    
    # Device paths
    device_home: str = "/home/root"
    device_xovi_dir: str = "/home/root/xovi"
    device_extensions_dir: str = "/home/root/xovi/extensions.d"
    device_appload_dir: str = "/home/root/xovi/exthome/appload"
    device_shims_dir: str = "/home/root/shims"
    device_tripletap_dir: str = "/home/root/xovi-tripletap"
    device_config_file: str = "/home/root/.config/remarkable/xochitl.conf"


@dataclass
class InstallationConfig:
    """Installation behavior configuration."""
    create_backup: bool = True
    skip_confirmation: bool = False
    enable_tripletap: bool = False  # Disabled by default as per script
    cleanup_downloads: bool = True
    verify_installation: bool = True
    
    # Stage management
    auto_continue_stages: bool = False
    stage_wait_timeout: int = 60
    device_ready_timeout: int = 30


@dataclass
class UIConfig:
    """User interface configuration."""
    show_progress: bool = True
    colored_output: bool = True
    verbose_logging: bool = False
    
    # Color codes (matching bash script)
    colors: Dict[str, str] = field(default_factory=lambda: {
        "RED": "\033[0;31m",
        "GREEN": "\033[0;32m", 
        "YELLOW": "\033[1;33m",
        "BLUE": "\033[0;34m",
        "PURPLE": "\033[0;35m",
        "NC": "\033[0m"  # No Color
    })


@dataclass
class DeviceConfig:
    """Device-specific configuration."""
    ip_address: Optional[str] = None
    ssh_password: Optional[str] = None
    device_type: Optional[Any] = None
    
    # Auto-detection settings
    auto_detect_device: bool = True
    validate_connection: bool = True


@dataclass
class AppConfig:
    """Main application configuration container."""
    
    # Core configuration sections
    network: NetworkConfig = field(default_factory=NetworkConfig)
    downloads: DownloadConfig = field(default_factory=DownloadConfig)
    paths: PathConfig = field(default_factory=PathConfig)
    installation: InstallationConfig = field(default_factory=InstallationConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    device: DeviceConfig = field(default_factory=DeviceConfig)
    
    # Application metadata
    version: str = field(default_factory=_get_version_from_file)
    app_name: str = "freeMarkable"
    config_version: str = "1.0"
    
    # Runtime settings
    debug_mode: bool = False
    log_level: LogLevel = LogLevel.INFO
    
    def __post_init__(self):
        """Post-initialization processing."""
        self._load_environment_variables()
        self._validate_config()
    
    def _load_environment_variables(self) -> None:
        """Load configuration from environment variables."""
        # Device connection from environment
        if env_ip := os.getenv("REMARKABLE_IP"):
            self.device.ip_address = env_ip
            
        if env_password := os.getenv("REMARKABLE_PASSWORD"):
            self.device.ssh_password = env_password
            
        if env_device_type := os.getenv("REMARKABLE_DEVICE_TYPE"):
            try:
                # Import DeviceType here to avoid circular imports
                from ..models.device import DeviceType
                self.device.device_type = DeviceType(env_device_type.upper())
            except (ValueError, ImportError):
                logging.warning(f"Invalid device type in environment: {env_device_type}")
        
        # Application settings from environment  
        if env_debug := os.getenv("XOVI_DEBUG"):
            self.debug_mode = env_debug.lower() in ("true", "1", "yes", "on")
            
        if env_log_level := os.getenv("XOVI_LOG_LEVEL"):
            try:
                self.log_level = LogLevel(env_log_level.upper())
            except ValueError:
                logging.warning(f"Invalid log level in environment: {env_log_level}")
        
        # Installation options from environment
        if env_skip_confirm := os.getenv("XOVI_SKIP_CONFIRMATION"):
            self.installation.skip_confirmation = env_skip_confirm.lower() in ("true", "1", "yes", "on")
            
        if env_no_backup := os.getenv("XOVI_NO_BACKUP"):
            self.installation.create_backup = not (env_no_backup.lower() in ("true", "1", "yes", "on"))
    
    def _validate_config(self) -> None:
        """Validate configuration values."""
        # Validate network timeouts
        if self.network.connection_timeout <= 0:
            raise ValueError("Connection timeout must be positive")
            
        if self.network.max_connection_attempts <= 0:
            raise ValueError("Max connection attempts must be positive")
        
        # Validate download settings
        if self.downloads.download_timeout <= 0:
            raise ValueError("Download timeout must be positive")
            
        if self.downloads.max_retries < 0:
            raise ValueError("Max retries cannot be negative")
        
        # Validate paths
        if not self.paths.downloads_dir:
            raise ValueError("Downloads directory cannot be empty")
    
    def get_config_dir(self) -> Path:
        """Get the application configuration directory."""
        # Use the new platform-agnostic utility to get the config directory
        from ..utils.platform_utils import get_platform_config_dir
        return get_platform_config_dir('remarkable-xovi-installer')
    
    def get_config_file_path(self) -> Path:
        """Get the path to the configuration file."""
        return self.get_config_dir() / 'config.json'
    
    def save_to_file(self, file_path: Optional[Union[str, Path]] = None) -> None:
        """
        Save configuration to a JSON file.
        
        Args:
            file_path: Path to save the config file. If None, uses default location.
            
        Raises:
            IOError: If the file cannot be written
            ValueError: If the configuration is invalid
        """
        if file_path is None:
            file_path = self.get_config_file_path()
        else:
            file_path = Path(file_path)
        
        try:
            # Convert to dictionary, handling enums
            config_dict = self._to_serializable_dict()
            
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
                
            logging.info(f"Configuration saved to {file_path}")
            
        except Exception as e:
            raise IOError(f"Failed to save configuration to {file_path}: {e}")
    
    def _to_serializable_dict(self) -> Dict[str, Any]:
        """Convert configuration to a JSON-serializable dictionary."""
        config_dict = asdict(self)
        
        # Convert enums to their values
        if config_dict.get('device', {}).get('device_type'):
            config_dict['device']['device_type'] = config_dict['device']['device_type'].value
            
        if config_dict.get('log_level'):
            config_dict['log_level'] = config_dict['log_level'].value
            
        return config_dict
    
    @classmethod
    def load_from_file(cls, file_path: Optional[Union[str, Path]] = None) -> 'AppConfig':
        """
        Load configuration from a JSON file.
        
        Args:
            file_path: Path to load the config file from. If None, uses default location.
            
        Returns:
            AppConfig instance loaded from file
            
        Raises:
            FileNotFoundError: If the config file doesn't exist
            ValueError: If the config file is invalid
        """
        if file_path is None:
            file_path = cls._get_default_config_path()
        else:
            file_path = Path(file_path)
            
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
            
            return cls._from_dict(config_dict)
            
        except Exception as e:
            raise ValueError(f"Failed to load configuration from {file_path}: {e}")
    
    @classmethod
    def _get_default_config_path(cls) -> Path:
        """Get the default configuration file path."""
        # Create a temporary instance to get the config directory
        temp_config = cls()
        return temp_config.get_config_file_path()
    
    @classmethod
    def _from_dict(cls, config_dict: Dict[str, Any]) -> 'AppConfig':
        """Create AppConfig instance from dictionary."""
        # Handle enum conversions
        if device_type_str := config_dict.get('device', {}).get('device_type'):
            try:
                # Import DeviceType here to avoid circular imports
                from ..models.device import DeviceType
                config_dict['device']['device_type'] = DeviceType(device_type_str)
            except (ValueError, ImportError):
                logging.warning(f"Invalid device type in config: {device_type_str}")
                config_dict['device']['device_type'] = None
        
        if log_level_str := config_dict.get('log_level'):
            try:
                config_dict['log_level'] = LogLevel(log_level_str)
            except ValueError:
                logging.warning(f"Invalid log level in config: {log_level_str}")
                config_dict['log_level'] = LogLevel.INFO
        
        # Create nested configurations
        network_config = NetworkConfig(**config_dict.get('network', {}))
        downloads_config = DownloadConfig(**config_dict.get('downloads', {}))
        paths_config = PathConfig(**config_dict.get('paths', {}))
        installation_config = InstallationConfig(**config_dict.get('installation', {}))
        ui_config = UIConfig(**config_dict.get('ui', {}))
        device_config = DeviceConfig(**config_dict.get('device', {}))
        
        # Create main config
        return cls(
            network=network_config,
            downloads=downloads_config,
            paths=paths_config,
            installation=installation_config,
            ui=ui_config,
            device=device_config,
            version=config_dict.get('version', _get_version_from_file()),
            app_name=config_dict.get('app_name', 'freeMarkable'),
            config_version=config_dict.get('config_version', '1.0'),
            debug_mode=config_dict.get('debug_mode', False),
            log_level=config_dict.get('log_level', LogLevel.INFO)
        )
    
    def update_device_info(self, ip_address: Optional[str] = None,
                          ssh_password: Optional[str] = None,
                          device_type: Optional[Any] = None) -> None:
        """
        Update device configuration information.
        
        Args:
            ip_address: Device IP address
            ssh_password: SSH password
            device_type: Device type
        """
        if ip_address is not None:
            self.device.ip_address = ip_address
            
        if ssh_password is not None:
            self.device.ssh_password = ssh_password
            
        if device_type is not None:
            self.device.device_type = device_type
    
    def get_downloads_directory(self) -> Path:
        """Get the downloads directory path, creating it if necessary."""
        downloads_path = Path(self.paths.downloads_dir)
        downloads_path.mkdir(parents=True, exist_ok=True)
        return downloads_path
    
    def get_stage_file_path(self) -> Path:
        """Get the path to the installation stage file."""
        return Path(self.paths.stage_file)
    
    def is_valid_device_config(self) -> bool:
        """Check if device configuration is valid for connection."""
        return (
            self.device.ip_address is not None and 
            self.device.ssh_password is not None and
            self.device.device_type is not None
        )
    
    def get_color_code(self, color_name: str) -> str:
        """
        Get ANSI color code by name.
        
        Args:
            color_name: Name of the color (RED, GREEN, etc.)
            
        Returns:
            ANSI color code string, or empty string if colors disabled
        """
        if not self.ui.colored_output:
            return ""
        return self.ui.colors.get(color_name.upper(), "")
    
    def reset_to_defaults(self) -> None:
        """Reset all configuration to default values."""
        default_config = AppConfig()
        
        self.network = default_config.network
        self.downloads = default_config.downloads
        self.paths = default_config.paths
        self.installation = default_config.installation
        self.ui = default_config.ui
        self.device = DeviceConfig()  # Keep device info separate
        self.debug_mode = default_config.debug_mode
        self.log_level = default_config.log_level


# Global configuration instance
_global_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """
    Get the global configuration instance.
    
    Returns:
        Global AppConfig instance
        
    Raises:
        RuntimeError: If configuration hasn't been initialized
    """
    global _global_config
    if _global_config is None:
        raise RuntimeError("Configuration not initialized. Call init_config() first.")
    return _global_config


def init_config(config_file: Optional[Union[str, Path]] = None) -> AppConfig:
    """
    Initialize the global configuration.
    
    Args:
        config_file: Optional path to config file. If None, uses default or creates new.
        
    Returns:
        Initialized AppConfig instance
    """
    global _global_config
    
    try:
        if config_file:
            _global_config = AppConfig.load_from_file(config_file)
        else:
            # Try to load from default location
            try:
                _global_config = AppConfig.load_from_file()
            except FileNotFoundError:
                # Create new config with defaults
                _global_config = AppConfig()
                logging.info("Created new configuration with default values")
    except Exception as e:
        logging.warning(f"Failed to load configuration: {e}. Using defaults.")
        _global_config = AppConfig()
    
    return _global_config


def save_config() -> None:
    """Save the current global configuration to file."""
    config = get_config()
    config.save_to_file()