"""
freeMarkable - Main Application Entry Point

A complete Python implementation of the freeMarkable installer with GUI and CLI interfaces.
Provides two-stage installation of XOVI framework, AppLoad launcher, and KOReader.
"""

import sys
import argparse
import logging
import traceback
from pathlib import Path
from typing import Optional, List

# Import core modules
from remarkable_xovi_installer.config.settings import (
    init_config, get_config, AppConfig
)
from remarkable_xovi_installer.models.device import Device, DeviceType
from remarkable_xovi_installer.models.installation_state import InstallationState, InstallationStage
from remarkable_xovi_installer.utils.logger import setup_logging, get_logger
from remarkable_xovi_installer.utils.validators import get_validator
from remarkable_xovi_installer.services.network_service import init_network_service, get_network_service
from remarkable_xovi_installer.services.file_service import init_file_service, get_file_service
from remarkable_xovi_installer.services.backup_service import init_backup_service, get_backup_service
from remarkable_xovi_installer.services.installation_service import (
    init_installation_service, get_installation_service, InstallationType
)


class XOVIInstallerApp:
    """Main application class for freeMarkable."""
    
    def __init__(self):
        self.config: Optional[AppConfig] = None
        self.device: Optional[Device] = None
        self.logger = None
        self.gui_mode = False
        
    def initialize(self, config_file: Optional[str] = None) -> None:
        """Initialize the application with configuration and services."""
        try:
            # Initialize configuration
            self.config = init_config(config_file)
            
            # Setup logging
            log_file = self.config.get_config_dir() / 'installer.log'
            self.logger = setup_logging(
                colored=self.config.ui.colored_output,
                log_file=log_file,
                level=self.config.log_level
            )
            
            self.logger.info(f"Starting {self.config.app_name} v{self.config.version}")
            
            # Initialize device model
            self.device = Device(
                ip_address=self.config.device.ip_address,
                ssh_password=self.config.device.ssh_password,
                device_type=self.config.device.device_type
            )
            
            # Initialize services
            init_network_service(
                connection_timeout=self.config.network.connection_timeout,
                max_retries=self.config.network.max_connection_attempts,
                retry_delay=self.config.network.retry_delay
            )
            
            init_file_service(
                downloads_dir=self.config.get_downloads_directory(),
                chunk_size=self.config.downloads.chunk_size,
                timeout=self.config.downloads.download_timeout,
                max_retries=self.config.downloads.max_retries
            )
            
            init_backup_service(get_network_service(), get_file_service())
            
            init_installation_service(
                self.config, 
                get_network_service(), 
                get_file_service(), 
                self.device
            )
            
            self.logger.info("Application initialization completed")
            
        except Exception as e:
            print(f"Failed to initialize application: {e}")
            if self.logger:
                self.logger.error(f"Initialization failed: {e}")
                self.logger.debug(traceback.format_exc())
            sys.exit(1)
    
    def check_dependencies(self) -> bool:
        """Check if required dependencies are available."""
        try:
            validator = get_validator()
            
            # Check SSH requirements (paramiko handles this, but check if available)
            try:
                import paramiko
                self.logger.debug("paramiko available for SSH operations")
            except ImportError:
                self.logger.error("paramiko not available - SSH operations will fail")
                return False
            
            # Check GUI dependencies
            try:
                import customtkinter
                self.logger.debug("customtkinter available for GUI")
            except ImportError:
                self.logger.warning("customtkinter not available - GUI mode disabled")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Dependency check failed: {e}")
            return False
    
    def update_device_config(self, ip_address: Optional[str] = None, 
                           password: Optional[str] = None,
                           device_type: Optional[str] = None) -> None:
        """Update device configuration from command line arguments."""
        if ip_address:
            self.device.ip_address = ip_address
            self.config.device.ip_address = ip_address
        
        if password:
            self.device.ssh_password = password
            self.config.device.ssh_password = password
        
        if device_type:
            try:
                dtype = DeviceType.from_short_name(device_type)
                if dtype:
                    self.device.device_type = dtype
                    self.config.device.device_type = dtype
                else:
                    self.logger.warning(f"Unknown device type: {device_type}")
            except Exception as e:
                self.logger.warn(f"Invalid device type '{device_type}': {e}")
    
    def run_cli_installation(self, installation_type: InstallationType,
                           continue_from_stage: Optional[InstallationStage] = None) -> bool:
        """Run installation in CLI mode."""
        try:
            self.logger.info(f"Starting {installation_type.value} installation")
            
            # Set up network service with device details
            network_service = get_network_service()
            if self.device.ip_address and self.device.ssh_password:
                network_service.set_connection_details(
                    hostname=self.device.ip_address,
                    password=self.device.ssh_password
                )
            
            # Set up progress callbacks for CLI output
            installation_service = get_installation_service()
            
            def progress_callback(progress):
                self.logger.info(f"[{progress.progress_percentage:.1f}%] {progress.message}")
            
            def output_callback(message):
                self.logger.info(message)
            
            installation_service.set_progress_callback(progress_callback)
            installation_service.set_output_callback(output_callback)
            
            # Start installation
            return installation_service.start_installation(
                installation_type=installation_type,
                continue_from_stage=continue_from_stage
            )
            
        except Exception as e:
            self.logger.error(f"CLI installation failed: {e}")
            self.logger.debug(traceback.format_exc())
            return False
    
    def run_cli_backup_operations(self, operation: str, backup_name: Optional[str] = None) -> bool:
        """Run backup operations in CLI mode."""
        try:
            backup_service = get_backup_service()
            
            # Set up output callback
            def output_callback(message):
                self.logger.info(message)
            
            backup_service.set_output_callback(output_callback)
            
            if operation == "create":
                self.logger.info("Creating backup...")
                backup_info = backup_service.create_backup(include_local_copy=True)
                self.logger.info(f"Backup created: {backup_info.name}")
                return True
            
            elif operation == "list":
                self.logger.info("Listing available backups...")
                backups = backup_service.list_backups()
                if backups:
                    self.logger.info("Available backups:")
                    for backup in backups:
                        size_str = f" ({backup.size_mb:.1f} MB)" if backup.size_mb else ""
                        self.logger.info(f"  • {backup.name}{size_str}")
                else:
                    self.logger.info("No backups found on device")
                return True
            
            elif operation == "restore" and backup_name:
                self.logger.info(f"Restoring from backup: {backup_name}")
                return backup_service.restore_from_backup(backup_name)
            
            elif operation == "delete" and backup_name:
                self.logger.info(f"Deleting backup: {backup_name}")
                return backup_service.delete_backup(backup_name)
            
            else:
                self.logger.error(f"Invalid backup operation: {operation}")
                return False
                
        except Exception as e:
            self.logger.error(f"Backup operation failed: {e}")
            self.logger.debug(traceback.format_exc())
            return False
    
    def run_gui_mode(self) -> bool:
        """Run the application in GUI mode."""
        try:
            # Import GUI components
            from remarkable_xovi_installer.gui.main_window import MainWindow
            
            self.logger.info("Starting GUI mode")
            self.gui_mode = True
            
            # Create and run GUI
            app = MainWindow(
                config=self.config,
                device=self.device,
                network_service=get_network_service(),
                file_service=get_file_service(),
                backup_service=get_backup_service(),
                installation_service=get_installation_service()
            )
            
            app.run()
            return True
            
        except ImportError as e:
            self.logger.error(f"GUI dependencies not available: {e}")
            self.logger.info("Please install GUI dependencies: pip install customtkinter")
            return False
        except Exception as e:
            self.logger.error(f"GUI mode failed: {e}")
            self.logger.debug(traceback.format_exc())
            return False
    
    def cleanup(self) -> None:
        """Clean up resources and save configuration."""
        try:
            if self.config:
                self.config.save_to_file()
            
            # Clean up services
            if get_network_service():
                get_network_service().disconnect()
            
            if get_file_service():
                get_file_service().cleanup_temp_files()
            
            if self.logger:
                self.logger.info("Application shutdown completed")
                
        except Exception as e:
            if self.logger:
                self.logger.error(f"Cleanup failed: {e}")


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the command line argument parser."""
    parser = argparse.ArgumentParser(
        description="freeMarkable - Install XOVI framework, AppLoad launcher, and KOReader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Start GUI mode
  %(prog)s --cli --full-install               # Full installation in CLI mode
  %(prog)s --cli --launcher-only              # Launcher-only installation
  %(prog)s --cli --continue                   # Continue interrupted installation
  %(prog)s --ip 192.168.1.100 --gui          # Set IP and start GUI
  %(prog)s --backup-only                      # Create backup only
  %(prog)s --restore backup_name              # Restore from backup
  
Installation Types:
  Full Install: XOVI + AppLoad + KOReader (default)
  Launcher Only: XOVI + AppLoad framework without apps
  Stage 1: Setup, backup, XOVI installation, hashtable rebuild
  Stage 2: KOReader installation and final configuration
        """)
    
    # Connection options
    connection_group = parser.add_argument_group('Device Connection')
    connection_group.add_argument(
        '-i', '--ip', 
        help='reMarkable device IP address (default: 10.11.99.1)'
    )
    connection_group.add_argument(
        '-p', '--password',
        help='SSH password (found in Settings > Help > Copyrights and licenses)'
    )
    connection_group.add_argument(
        '--device-type',
        choices=['rM1', 'rM2', 'rMPP'],
        help='Device type (auto-detected if not specified)'
    )
    
    # Interface options
    interface_group = parser.add_argument_group('Interface Mode')
    interface_mode = interface_group.add_mutually_exclusive_group()
    interface_mode.add_argument(
        '--gui',
        action='store_true',
        help='Force GUI mode (default if no other options specified)'
    )
    interface_mode.add_argument(
        '--cli',
        action='store_true', 
        help='Force CLI mode'
    )
    
    # Installation options
    install_group = parser.add_argument_group('Installation Options')
    install_type = install_group.add_mutually_exclusive_group()
    install_type.add_argument(
        '--full-install',
        action='store_true',
        help='Full installation: XOVI + AppLoad + KOReader (default)'
    )
    install_type.add_argument(
        '--launcher-only',
        action='store_true',
        help='Install launcher framework only (XOVI + AppLoad)'
    )
    install_type.add_argument(
        '--stage1',
        action='store_true',
        help='Run Stage 1 only (setup through hashtable rebuild)'
    )
    install_type.add_argument(
        '--stage2', 
        action='store_true',
        help='Run Stage 2 only (KOReader installation)'
    )
    install_type.add_argument(
        '--continue',
        action='store_true',
        help='Continue from interrupted installation'
    )
    
    # Backup options
    backup_group = parser.add_argument_group('Backup Operations')
    backup_type = backup_group.add_mutually_exclusive_group()
    backup_type.add_argument(
        '--backup-only',
        action='store_true',
        help='Create backup only, do not install'
    )
    backup_type.add_argument(
        '--list-backups',
        action='store_true',
        help='List available backups on device'
    )
    backup_type.add_argument(
        '--restore',
        metavar='BACKUP_NAME',
        help='Restore from specified backup'
    )
    backup_type.add_argument(
        '--delete-backup',
        metavar='BACKUP_NAME', 
        help='Delete specified backup'
    )
    
    # Configuration options
    config_group = parser.add_argument_group('Configuration')
    config_group.add_argument(
        '--config',
        metavar='CONFIG_FILE',
        help='Path to configuration file'
    )
    config_group.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompts'
    )
    config_group.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    config_group.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    
    return parser


def main() -> int:
    """Main application entry point."""
    app = XOVIInstallerApp()
    exit_code = 0
    
    try:
        # Parse command line arguments
        parser = create_argument_parser()
        args = parser.parse_args()
        
        # Initialize application
        app.initialize(args.config)
        
        # Update configuration from command line arguments
        if args.debug:
            app.config.debug_mode = True
            app.config.log_level = app.config.log_level.__class__.DEBUG
        
        if args.no_color:
            app.config.ui.colored_output = False
        
        if args.force:
            app.config.installation.skip_confirmation = True
        
        # Update device configuration
        app.update_device_config(args.ip, args.password, args.device_type)
        
        # Check dependencies
        if not app.check_dependencies():
            app.logger.error("Required dependencies not available")
            return 1
        
        # Determine operation mode
        if args.backup_only:
            success = app.run_cli_backup_operations("create")
            exit_code = 0 if success else 1
            
        elif args.list_backups:
            success = app.run_cli_backup_operations("list")
            exit_code = 0 if success else 1
            
        elif args.restore:
            success = app.run_cli_backup_operations("restore", args.restore)
            exit_code = 0 if success else 1
            
        elif args.delete_backup:
            success = app.run_cli_backup_operations("delete", args.delete_backup)
            exit_code = 0 if success else 1
            
        elif args.cli or any([args.full_install, args.launcher_only, args.stage1, args.stage2, getattr(args, 'continue', False)]):
            # Determine installation type
            if args.launcher_only:
                install_type = InstallationType.LAUNCHER_ONLY
            elif args.stage1:
                install_type = InstallationType.STAGE_1_ONLY
            elif args.stage2:
                install_type = InstallationType.STAGE_2_ONLY
            else:
                install_type = InstallationType.FULL
            
            # Determine continue stage
            continue_stage = None
            if getattr(args, 'continue', False):
                # Load existing state to determine stage
                state = InstallationState.load_from_file(app.config.get_stage_file_path())
                if state:
                    continue_stage = state.current_stage
                    app.logger.info(f"Continuing from {continue_stage.value}")
                else:
                    app.logger.warning("No saved installation state found, starting from beginning")
            
            success = app.run_cli_installation(install_type, continue_stage)
            exit_code = 0 if success else 1
            
        elif args.gui or not any([args.cli, args.backup_only, args.list_backups, args.restore, args.delete_backup]):
            # Default to GUI mode
            success = app.run_gui_mode()
            exit_code = 0 if success else 1
            
        else:
            parser.print_help()
            exit_code = 1
    
    except KeyboardInterrupt:
        if app.logger:
            app.logger.info("Installation interrupted by user")
        else:
            print("\nInstallation interrupted by user")
        exit_code = 130
        
    except Exception as e:
        if app.logger:
            app.logger.error(f"Unexpected error: {e}")
            app.logger.debug(traceback.format_exc())
        else:
            print(f"Unexpected error: {e}")
        exit_code = 1
        
    finally:
        app.cleanup()
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())