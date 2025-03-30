"""
Nova Launcher konfigürasyon dosyası
"""

import os
import platform

# Uygulama bilgileri
APP_NAME = "Nova Launcher"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Nova Team"

# Dosya yolları
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = os.path.join(ROOT_DIR, "resources")

# Minecraft varsayılan klasörü - işletim sistemine göre ayarlanır
if platform.system() == "Windows":
    DEFAULT_MINECRAFT_DIR = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", ".minecraft")
else:
    DEFAULT_MINECRAFT_DIR = os.path.join(os.path.expanduser("~"), ".minecraft")

# Kullanıcı ayarları dosya yolu
USER_CONFIG_FILE = os.path.join(ROOT_DIR, "user_config.json")

# Varsayılan ayarlar
DEFAULT_SETTINGS = {
    "minecraft_directory": DEFAULT_MINECRAFT_DIR,
    "username": "Player",
    "last_used_version": None,
    "ram_allocation": 2048,
    "java_path": ""
}

# Simgelerin konumu
LOGO_PATH = os.path.join(RESOURCES_DIR, "logo.png")

# Settings file path - Minecraft klasörü içinde
SETTINGS_FILE = os.path.join(DEFAULT_MINECRAFT_DIR, "novasettings.json")

# Default Java path (leave empty to auto-detect)
DEFAULT_JAVA_PATH = ""

# Default RAM allocation in MB
DEFAULT_RAM_ALLOCATION = 2048

# Colors
PRIMARY_COLOR = "#5ba042"
SECONDARY_COLOR = "#3d6b2c"
BACKGROUND_COLOR = "#2d2d2d"
TEXT_COLOR = "#e0e0e0"
HOVER_COLOR = "#4e8a38"
PRESSED_COLOR = "#3d6b2c" 