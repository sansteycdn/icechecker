#!/bin/bash
# Streamlit Cloud setup script to install Chromium and ChromeDriver

# Update package lists
apt-get update

# Install Chromium browser and driver
apt-get install -y chromium chromium-driver

# Optional: confirm installation
chromium --version
chromedriver --version
