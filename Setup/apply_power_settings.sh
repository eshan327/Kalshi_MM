#!/bin/bash

# Power Management Configuration Script (Non-interactive)
# Configures macOS to run scripts reliably when lid is closed (on AC power)

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
echo "Your background scripts should now run more reliably when the lid is closed (if plugged in)."


