#!/bin/bash

# reMarkable SSH Helper Script
# Usage: ./rm_ssh.sh "command to run on device"
# Example: ./rm_ssh.sh "ls -la /usr/bin/xochitl"

REMARKABLE_IP="10.11.99.1"
REMARKABLE_USER="root"
REMARKABLE_PASSWORD="dyovaamsE"

if [ $# -eq 0 ]; then
    echo "Usage: $0 \"command\""
    echo "Example: $0 \"ls -la /usr/bin/xochitl\""
    echo "Example: $0 \"cat /sys/version\""
    echo "Available functions:"
    echo "  - Copy file from device: $0 \"cat /path/to/file\" > local_file"
    echo "  - Check xochitl binary: $0 \"ls -la /usr/bin/xochitl\""
    exit 1
fi

# Execute command on reMarkable device using sshpass for automated authentication
sshpass -p "$REMARKABLE_PASSWORD" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q "$REMARKABLE_USER@$REMARKABLE_IP" "$1"