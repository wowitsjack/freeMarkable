# freeMarkable

![freeMarkable Interface](image.png)

**ALPHA VERSION - NOT READY FOR PUBLIC USE**

This is an alpha version of freeMarkable and is currently under development. It is not recommended for general use and may contain bugs or incomplete features. Use at your own risk and only for testing purposes.

---

Modern Python GUI application for installing XOVI+AppLoader on reMarkable 1/2 devices, along with KOReader. This is a complete transformation from the original bash script into a user-friendly graphical interface.

## Features

- **Modern GUI Interface** - Built with CustomTkinter for cross-platform compatibility
- **Complete XOVI Installation** - Full framework with proper tmpfs overlay activation
- **AppLoad Integration** - Application launcher system for reMarkable devices
- **KOReader Installation** - Popular eBook reader with full integration
- **Automatic Backup & Restore** - System backups created before any modifications
- **Connection Management** - Easy device setup with configuration wizard
- **Real-time Progress Tracking** - Live installation progress with detailed logging
- **Cross-Platform Support** - Works on both Linux and Windows systems
- **Error Recovery** - Comprehensive error handling and recovery options

## System Requirements

- **Python 3.6 or higher** installed on your system
- **reMarkable 1 or reMarkable 2** device with SSH access enabled
- **USB or WiFi connection** to your reMarkable device
- **Internet connection** for downloading required components

## Installation & Usage

### Linux Users
```bash
chmod +x launch.sh
./launch.sh
```

### Windows Users
```cmd
launch.bat
```
(or simply double-click the launch.bat file)

The launcher scripts will automatically:
1. Check for Python installation
2. Install required Python dependencies
3. Launch the freeMarkable application

## First Time Setup

1. Run the appropriate launcher script for your operating system
2. Complete the initial setup wizard to configure your reMarkable connection
3. Test the connection to ensure proper communication with your device
4. Choose your installation type (Full installation or Launcher-only)
5. Follow the on-screen instructions to complete the installation

## Project Structure

```
freeMarkable/
├── launch.sh              # Linux launcher script
├── launch.bat             # Windows launcher script  
├── README.md              # Documentation (this file)
├── LICENSE                # Project license
├── image.png              # Application screenshot
└── resources/             # Core application files
    ├── main.py            # Application entry point
    ├── requirements.txt   # Python dependencies
    └── remarkable_xovi_installer/
        ├── gui/           # User interface components
        ├── services/      # Core installation services
        ├── models/        # Data models and state management
        ├── utils/         # Utility functions and helpers
        └── config/        # Application configuration
```

## Development Status

This application is currently in **ALPHA** status. While it contains the complete functionality of the original bash script, it has not undergone extensive real-world testing. Known limitations include:

- Limited testing on various system configurations
- Potential edge cases in error handling
- User interface refinements still in progress
- Documentation may be incomplete

## Contributing

This is an alpha release for testing and feedback purposes. If you encounter issues or have suggestions for improvements, please report them through the project's issue tracker.

## Disclaimer

This software modifies your reMarkable device. While every effort has been made to ensure safety through automatic backups and proper error handling, use this software at your own risk. The developers are not responsible for any damage to your device.

Always ensure you have a recent backup of your reMarkable device before using this software.

## License

This project is licensed under the terms specified in the LICENSE file.

---

**Alpha Version Notice**: This software is in active development. Features may change, and stability is not guaranteed. Use only for testing purposes.
