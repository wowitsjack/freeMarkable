# freeMarkable

Toolkit for installing XOVI+AppLoader on reMarkable 1/2 devices, along with KOReader.

## Features

- **GUI** built with CustomTkinter
- **Complete XOVI Installation** - Full framework with proper tmpfs overlay
- **AppLoad Integration** - Application launcher for reMarkable
- **KOReader Installation** - Popular eBook reader for reMarkable
- **Backup & Restore** - Automatic system backups before installation
- **Connection Management** - Easy device setup and connection
- **Real-time Progress** - Live installation progress and logging

## Quick Start

### Linux Users
```bash
./launch.sh
```

### Windows Users
```cmd
launch.bat
```
(or simply double-click the file)

## Requirements

- **Python 3.6+** installed on your system
- **reMarkable 1/2** device with SSH access enabled
- **USB or WiFi connection** to your reMarkable device

## Directory Structure

```
freeMarkable/
├── launch.sh          # Linux launcher
├── launch.bat         # Windows launcher
├── README.md          # This file
└── resources/         # Application files
    ├── main.py
    ├── requirements.txt
    └── remarkable_xovi_installer/
        ├── gui/           # GUI components
        ├── services/      # Core functionality
        ├── models/        # Data models
        ├── utils/         # Utilities
        └── config/        # Configuration
```

## First Run

1. Run the appropriate launcher script for your platform
2. The application will automatically install Python dependencies
3. Follow the setup wizard to configure your reMarkable connection
4. Begin installation

---

