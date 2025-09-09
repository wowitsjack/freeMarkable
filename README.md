# freeMarkable

![freeMarkable Interface](image.png)

**ALPHA VERSION - NOT READY FOR PUBLIC USE**

This is an alpha version of freeMarkable and is currently under development. It is not recommended for general use and may contain bugs or incomplete features. Use at your own risk and only for testing purposes.

---

Modern Python GUI application for installing XOVI+AppLoader on **all reMarkable devices**, including the new **reMarkable Paper Pro**. This is a complete transformation from the original bash script into a user-friendly graphical interface with automatic architecture detection.

## NEW: reMarkable Paper Pro Support

**freeMarkable now supports the new reMarkable Paper Pro with full 64-bit architecture detection!**

- **Automatic Device Detection** - Detects reMarkable 1, 2, and Paper Pro automatically
- **Architecture-Aware Installation** - Uses correct 32-bit or 64-bit binaries based on device
- **Seamless Experience** - Same interface works for all reMarkable generations
- **Future-Ready** - Built to support new reMarkable devices as they're released

## Supported Devices

| Device | Architecture | Binary Type | Status |
|--------|-------------|-------------|---------|
| **reMarkable 1** | armv6l | 32-bit ARM | ✅ Fully Supported |
| **reMarkable 2** | armv7l/armhf | 32-bit ARM | ✅ Fully Supported |
| **reMarkable Paper Pro** | aarch64/arm64 | 64-bit ARM | ✅ Fully Supported |

## Features

- **Universal Device Support** - Works with reMarkable 1, 2, and Paper Pro
- **Smart Architecture Detection** - Automatically detects device type and uses appropriate binaries
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
- **reMarkable device** (any generation: 1, 2, or Paper Pro) with SSH access enabled
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
4. **Device Auto-Detection** - The app will automatically detect your device type (RM1/RM2/Paper Pro)
5. Choose your installation type (Full installation or Launcher-only)
6. Follow the on-screen instructions to complete the installation

## Technical Details

### Architecture Detection

freeMarkable uses hardware-level architecture detection to identify your reMarkable device:

- **SSH-Based Detection** - Connects to device and runs `uname -m` to get CPU architecture
- **Automatic Binary Selection** - Downloads correct binaries based on detected architecture
- **No Manual Configuration** - Device type detection is completely automatic

### Binary Compatibility

The application automatically selects the correct binaries for your device:

**reMarkable 1/2 (32-bit ARM):**
- XOVI Extensions: `extensions-arm32-testing.zip`
- AppLoad: `appload-arm32.zip`
- XOVI Binary: `xovi-arm32.so`
- KOReader: Standard reMarkable build

**reMarkable Paper Pro (64-bit ARM):**
- XOVI Extensions: `extensions-aarch64.zip`
- AppLoad: `appload-aarch64.zip` 
- XOVI Binary: `xovi-aarch64.so`
- KOReader: Architecture-specific aarch64 build

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
        ├── models/        # Data models and device detection
        ├── utils/         # Utility functions and helpers
        └── config/        # Application configuration
```

## Development Status

This application is currently in **ALPHA** status. While it contains the complete functionality of the original bash script plus new Paper Pro support, it has not undergone extensive real-world testing. Known limitations include:

- Limited testing on various system configurations
- Paper Pro support is newly implemented and needs real-world validation
- Potential edge cases in error handling
- User interface refinements still in progress
- Documentation may be incomplete

## Recent Bug Fixes

**v1.0.5**: Fixed critical bug where AppLoad menu wouldn't appear after full installation
- **Issue**: XOVI framework was installed but not activated in Stage 1 and Stage 2 installations
- **Root Cause**: Missing systemd service override creation during installation process
- **Fix**: Added automatic XOVI activation step to all installation stages
- **Impact**: AppLoad launcher menu now appears properly after all installation types

## Contributing

This is an alpha release for testing and feedback purposes. If you encounter issues or have suggestions for improvements, please report them through the project's issue tracker.

**Paper Pro Testing Needed:** If you have access to a reMarkable Paper Pro, your testing and feedback would be especially valuable!

## Disclaimer

This software modifies your reMarkable device. While every effort has been made to ensure safety through automatic backups and proper error handling, use this software at your own risk. The developers are not responsible for any damage to your device.

Always ensure you have a recent backup of your reMarkable device before using this software.

## License

This project is licensed under the terms specified in the LICENSE file.

---

**Alpha Version Notice**: This software is in active development. Features may change, and stability is not guaranteed. Use only for testing purposes.
