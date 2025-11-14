#!/bin/bash

# Power Management Configuration Script
# Configures macOS to run scripts reliably when lid is closed (on AC power)

echo "Power Management Configuration for Background Scripts"
echo "======================================================"
echo ""
echo "This script will configure your Mac to:"
echo "  - Prevent sleep when lid is closed (AC power only)"
echo "  - Keep disk active"
echo "  - Maintain network connectivity"
echo ""
echo "These settings only apply when your Mac is PLUGGED IN (AC power)."
echo "On battery, macOS will still throttle to save power."
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo "Error: Please run this script without sudo. It will prompt for password when needed."
    exit 1
fi

# Show current settings
echo "Current AC Power Settings:"
echo "---------------------------"
pmset -g custom | grep -A 15 "AC Power"
echo ""

# Ask for confirmation
read -p "Do you want to apply these settings? (y/n): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Applying power management settings..."
echo ""

# Apply settings for AC power (when plugged in)
sudo pmset -c sleep 0                      # Never sleep on AC power
sudo pmset -c disksleep 0                  # Never spin down disk on AC power
sudo pmset -c networkoversleep 0           # Keep network active on AC power
sudo pmset -c tcpkeepalive 1               # Keep TCP connections alive

echo "✓ Settings applied!"
echo ""
echo "New AC Power Settings:"
echo "---------------------------"
pmset -g custom | grep -A 15 "AC Power"
echo ""
echo "Note: These settings only apply when your Mac is plugged in."
echo "      When on battery, macOS will still use power-saving modes."
echo ""
echo "Your background scripts should now run more reliably when the lid is closed (if plugged in)."


