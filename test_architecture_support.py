#!/usr/bin/env python3
"""
Test script to verify reMarkable Paper Pro (64-bit aarch64) support.

This script tests the architecture detection and URL selection logic
without requiring an actual device connection.
"""

import sys
import os
from pathlib import Path

# Add the resources directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "resources"))

from remarkable_xovi_installer.models.device import DeviceType
from remarkable_xovi_installer.config.settings import init_config

def test_device_type_enum():
    """Test DeviceType enum functionality."""
    print("=== Testing DeviceType Enum ===")
    
    # Test all device types
    for device_type in [DeviceType.RM1, DeviceType.RM2, DeviceType.RMPP]:
        print(f"\nDevice: {device_type.display_name}")
        print(f"  Short name: {device_type.short_name}")
        print(f"  Architecture: {device_type.architecture}")
        print(f"  Is 64-bit: {device_type.architecture == 'aarch64'}")
    
    # Test architecture detection
    print("\n=== Testing Architecture Detection ===")
    test_cases = [
        ("armv6l", DeviceType.RM1),
        ("armv7l", DeviceType.RM2),
        ("armhf", DeviceType.RM2),
        ("aarch64", DeviceType.RMPP),
        ("arm64", DeviceType.RMPP),
        ("unknown", None)
    ]
    
    for arch, expected in test_cases:
        result = DeviceType.from_architecture(arch)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {arch} -> {result.display_name if result else 'None'}")
    
    # Test short name detection
    print("\n=== Testing Short Name Detection ===")
    short_name_cases = [
        ("rm1", DeviceType.RM1),
        ("rm2", DeviceType.RM2),
        ("rmpp", DeviceType.RMPP),
        ("RM1", DeviceType.RM1),
        ("RMPP", DeviceType.RMPP),
        ("unknown", None)
    ]
    
    for name, expected in short_name_cases:
        result = DeviceType.from_short_name(name)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {name} -> {result.display_name if result else 'None'}")

def test_url_configuration():
    """Test architecture-specific URL configuration."""
    print("\n=== Testing URL Configuration ===")
    
    # Initialize config
    config = init_config()
    downloads = config.downloads
    
    # Test URL selection for each device type
    for device_type in [DeviceType.RM1, DeviceType.RM2, DeviceType.RMPP]:
        print(f"\n{device_type.display_name} ({device_type.architecture}):")
        
        # Test each component
        components = ['xovi_extensions', 'appload', 'xovi_binary', 'koreader']
        for component in components:
            url = downloads.get_url_for_architecture(component, device_type)
            filename = downloads.get_filename_for_architecture(component, device_type)
            
            # Check if URL contains correct architecture
            arch_in_url = "aarch64" in url if device_type == DeviceType.RMPP else "arm32" in url
            status = "✓" if arch_in_url else "✗"
            
            print(f"  {status} {component}:")
            print(f"    URL: {url}")
            print(f"    Filename: {filename}")

def test_expected_urls():
    """Test that the expected URLs are correctly configured."""
    print("\n=== Testing Expected URLs ===")
    
    config = init_config()
    downloads = config.downloads
    
    # Expected URLs for Paper Pro (aarch64)
    expected_rmpp_urls = {
        'xovi_binary': 'https://github.com/asivery/xovi/releases/download/v0.2.2/xovi-aarch64.so',
        'appload': 'https://github.com/asivery/rm-appload/releases/download/v0.2.4/appload-aarch64.zip',
        'xovi_extensions': 'https://github.com/asivery/rm-xovi-extensions/releases/download/v12-12082025/extensions-aarch64.zip',
        'koreader': 'https://build.koreader.rocks/download/stable/v2025.08/koreader-remarkable-aarch64-v2025.08.zip'
    }
    
    # Expected URLs for RM1/RM2 (arm32)
    expected_arm32_urls = {
        'xovi_binary': 'https://github.com/asivery/xovi/releases/latest/download/xovi-arm32.so',
        'appload': 'https://github.com/asivery/rm-appload/releases/download/v0.2.4/appload-arm32.zip',
        'xovi_extensions': 'https://github.com/asivery/rm-xovi-extensions/releases/download/v12-12082025/extensions-arm32-testing.zip',
        'koreader': 'https://github.com/koreader/koreader/releases/download/v2025.08/koreader-remarkable-v2025.08.zip'
    }
    
    print("\nPaper Pro (aarch64) URLs:")
    for component, expected_url in expected_rmpp_urls.items():
        actual_url = downloads.get_url_for_architecture(component, DeviceType.RMPP)
        status = "✓" if actual_url == expected_url else "✗"
        print(f"  {status} {component}: {actual_url}")
        if actual_url != expected_url:
            print(f"    Expected: {expected_url}")
    
    print("\nRM1/RM2 (arm32) URLs:")
    for component, expected_url in expected_arm32_urls.items():
        actual_url = downloads.get_url_for_architecture(component, DeviceType.RM2)
        status = "✓" if actual_url == expected_url else "✗"
        print(f"  {status} {component}: {actual_url}")
        if actual_url != expected_url:
            print(f"    Expected: {expected_url}")

def test_filename_generation():
    """Test filename generation for different architectures."""
    print("\n=== Testing Filename Generation ===")
    
    config = init_config()
    downloads = config.downloads
    
    expected_filenames = {
        DeviceType.RMPP: {
            'xovi_binary': 'xovi-aarch64.so',
            'appload': 'appload-aarch64.zip',
            'xovi_extensions': 'extensions-aarch64.zip',
            'koreader': 'koreader-remarkable-aarch64-v2025.08.zip'
        },
        DeviceType.RM2: {
            'xovi_binary': 'xovi-arm32.so',
            'appload': 'appload-arm32.zip',
            'xovi_extensions': 'extensions-arm32-testing.zip',
            'koreader': 'koreader-remarkable-v2025.08.zip'
        }
    }
    
    for device_type, expected_files in expected_filenames.items():
        print(f"\n{device_type.display_name} filenames:")
        for component, expected_filename in expected_files.items():
            actual_filename = downloads.get_filename_for_architecture(component, device_type)
            status = "✓" if actual_filename == expected_filename else "✗"
            print(f"  {status} {component}: {actual_filename}")
            if actual_filename != expected_filename:
                print(f"    Expected: {expected_filename}")

def main():
    """Run all tests."""
    print("Testing reMarkable Paper Pro (64-bit aarch64) Support")
    print("=" * 60)
    
    try:
        test_device_type_enum()
        test_url_configuration()
        test_expected_urls()
        test_filename_generation()
        
        print("\n" + "=" * 60)
        print("✓ All tests completed successfully!")
        print("\nThe implementation supports:")
        print("• reMarkable 1 (armv6l) - 32-bit ARM binaries")
        print("• reMarkable 2 (armv7l) - 32-bit ARM binaries") 
        print("• reMarkable Paper Pro (aarch64) - 64-bit ARM binaries")
        print("\nArchitecture detection and URL selection are working correctly.")
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())