import sys
import os
import json
import requests
import minecraft_launcher_lib as mclib
import minecraft_launcher_lib.fabric as fabric
import minecraft_launcher_lib.forge as forge
import subprocess
import uuid
import hashlib
import time
import base64
import math
import traceback
import glob
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QLabel, QPushButton, QComboBox, QProgressBar, 
                           QMessageBox, QFileDialog, QGroupBox, QHBoxLayout,
                           QDialog, QSpinBox, QSlider, QTabWidget, QInputDialog,
                           QFrame, QLineEdit, QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QByteArray
from PyQt5.QtGui import QIcon, QPixmap, QFont, QPainter, QColor, QPainterPath

# Import configuration file
from .config import *

# Base64 ikondan QIcon oluşturma
def create_icon_from_base64(base64_str):
    # Base64 kodunu temizle
    base64_str = base64_str.strip()
    # Base64'ten binary veriye dönüştür
    icon_data = base64.b64decode(base64_str)
    # QPixmap oluştur
    pixmap = QPixmap()
    pixmap.loadFromData(icon_data)
    return QIcon(pixmap)

def generate_uuid_from_username(username):
    """Generates a consistent UUID based on the username"""
    # Generate a hash from the username (produces the same UUID for the same username every time)
    namespace = uuid.NAMESPACE_OID  # Use a constant namespace
    username_uuid = uuid.uuid5(namespace, username)
    return str(username_uuid)

class MinecraftVersionThread(QThread):
    version_signal = pyqtSignal(list)
    
    def run(self):
        try:
            # get_version_list API'sini kullan
            versions = mclib.utils.get_version_list()
            self.version_signal.emit(versions)
        except Exception as e:
            self.version_signal.emit([])
            print(f"Error getting version list: {str(e)}")

class MinecraftInstallThread(QThread):
    progress_signal = pyqtSignal(int, str)
    complete_signal = pyqtSignal(bool, str)
    
    def __init__(self, minecraft_dir, version, version_type, forge_version_string=None):
        super().__init__()
        self.minecraft_directory = minecraft_dir
        self.version = version
        self.version_type = version_type
        self.forge_version_string = forge_version_string
        # Initialize status and progress trackers
        self._current_status = "Starting installation..."
        self._current_progress = 0
        
    def set_status(self, status):
        """Callback for status updates"""
        self._current_status = status
        # Emit the combined signal
        self.progress_signal.emit(self._current_progress, self._current_status)

    def set_progress(self, value, max_value=None):
        """Callback for progress updates"""
        # Only calculate percentage if max_value is provided and greater than 0
        if max_value is not None and max_value > 0: 
            self._current_progress = int((value / max_value) * 100)
        # If max_value is not provided or zero, we don't update the percentage
        # but we still emit the signal to potentially update the status text
        
        # Emit the combined signal
        self.progress_signal.emit(self._current_progress, self._current_status)
        
    def run(self):
        """Install Minecraft version (Vanilla or Fabric)"""
        callback_dict = {
            "setStatus": self.set_status,
            "setProgress": self.set_progress
        }
        
        base_vanilla_id = self.version # Default to self.version for vanilla
        if self.version_type == "fabric":
            try:
                # Extract base vanilla ID like "1.20.1" from fabric ID "fabric-loader-x.y.z-1.20.1"
                base_vanilla_id = self.version.split('-')[-1]
            except IndexError:
                 self.complete_signal.emit(False, f"Invalid Fabric version ID format: {self.version}")
                 return

        try:
            # === Step 1: Install Vanilla Version (Always required) ===
            self.set_status(f"Installing Vanilla {base_vanilla_id}...")
            if not os.path.exists(self.minecraft_directory):
                os.makedirs(self.minecraft_directory)
                
            mclib.install.install_minecraft_version(
                base_vanilla_id, 
                self.minecraft_directory, 
                callback=callback_dict
            )
            self.set_status(f"Vanilla {base_vanilla_id} installed.")

            # === Step 2: Install Fabric (If requested) ===
            if self.version_type == "fabric":
                self.set_status(f"Installing Fabric for {base_vanilla_id}...")
                try:
                    mclib.fabric.install_fabric(
                        base_vanilla_id, # Use base vanilla ID here
                        self.minecraft_directory,
                        callback=callback_dict,
                        # Optional: Specify loader version if needed, otherwise uses latest
                        # loader_version=self.version.split('-')[2] # Extract loader from ID if needed
                    )
                    self.set_status(f"Fabric for {base_vanilla_id} installed.")
                except Exception as fabric_exc:
                    # Provide a more specific error if Fabric install fails after Vanilla success
                    error_message = f"Vanilla {base_vanilla_id} installed, but Fabric failed: {str(fabric_exc)}"
                    print("--- FABRIC INSTALLATION ERROR ---")
                    print(error_message)
                    print("Traceback:")
                    traceback.print_exc()
                    print("---------------------------------")
                    self.complete_signal.emit(False, error_message)
                    return # Stop here if fabric install failed

            # === Step 3: Install Forge (If requested) ===
            elif self.version_type == "forge":
                if not self.forge_version_string:
                    self.complete_signal.emit(False, f"Missing Forge version info for {base_vanilla_id}")
                    return

                self.set_status(f"Installing Forge for {base_vanilla_id} ({self.forge_version_string})...")
                try:
                    # Check if this specific forge version is supported for auto-install
                    if not forge.supports_automatic_install(self.forge_version_string):
                        raise Exception(f"Automatic installation not supported for Forge {self.forge_version_string}. Please install manually.")

                    forge.install_forge_version(
                        self.forge_version_string, 
                        self.minecraft_directory,
                        callback=callback_dict
                    )
                    self.set_status(f"Forge for {base_vanilla_id} installed.")
                except Exception as forge_exc:
                    # Provide a more specific error if Forge install fails
                    error_message = f"Vanilla {base_vanilla_id} installed, but Forge failed: {str(forge_exc)}"
                    print("--- FORGE INSTALLATION ERROR ---")
                    print(error_message)
                    print("Traceback:")
                    traceback.print_exc()
                    print("--------------------------------")
                    self.complete_signal.emit(False, error_message)
                    return # Stop here if forge install failed

            # === Completion ===
            success_message = f"Minecraft {self.version} installed successfully."
            if self.version_type == "fabric":
                 success_message = f"Fabric {base_vanilla_id} ({self.version}) installed successfully."
            elif self.version_type == "forge":
                 # Note: self.version is base ID here, actual launch ID determined later
                 success_message = f"Forge {base_vanilla_id} installed successfully."
                 
            self.complete_signal.emit(True, success_message)

        except Exception as e:
            # General installation error (likely during Vanilla install)
            error_message = f"Error installing {self.version}: {str(e)}"
            print("--- MINECRAFT INSTALLATION ERROR ---")
            print(error_message)
            print("Traceback:")
            traceback.print_exc()
            print("------------------------------------")
            self.complete_signal.emit(False, error_message)

class MinecraftLauncherThread(QThread):
    """Thread for launching Minecraft"""
    launch_signal = pyqtSignal(bool, str)
    
    def __init__(self, minecraft_dir, version, username, ram, java_path=None):
        super().__init__()
        self.minecraft_directory = minecraft_dir
        self.version = version
        self.username = username
        self.ram = ram
        self.java_path = java_path
    
    def run(self):
        """Launch Minecraft with options"""
        try:
            # Check if Java path is provided and exists
            if self.java_path and os.path.exists(self.java_path):
                java_path = self.java_path
            else:
                # Use system default Java
                java_path = None
                
            # Generate UUID from username
            player_uuid = generate_uuid_from_username(self.username)
                
            # Get launch command
            options = {
                "username": self.username,
                "uuid": player_uuid,  # Stabil bir UUID kullan
                "token": "",
                "jvmArguments": [f"-Xmx{self.ram}m"],
                "quickPlayPath": None  # QuickPlay'i devre dışı bırak
            }
            
            # Java yolunu ayarla (eğer belirtilmişse)
            if java_path:
                options["executablePath"] = java_path
            
            command = mclib.command.get_minecraft_command(
                self.version, 
                self.minecraft_directory, 
                options
            )
            
            # QuickPlay ile ilgili parametreleri kaldır
            filtered_command = []
            skip_next = False
            for i, arg in enumerate(command):
                if skip_next:
                    skip_next = False
                    continue
                    
                if arg == "--quickPlayPath" or arg.startswith("--quickPlay"):
                    skip_next = True
                    continue
                    
                filtered_command.append(arg)
            
            print(f"Launching Minecraft (offline mode) (Custom Java: {java_path or 'System default'}): {filtered_command}")
            
            # Konsol penceresi göstermeden başlat
            startupinfo = None
            if os.name == 'nt':  # Windows işletim sistemi
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
            
            # Minecraft'ı başlat ve hemen devam et
            try:
                process = subprocess.Popen(
                    filtered_command, 
                    cwd=self.minecraft_directory,
                    startupinfo=startupinfo,  # Konsol penceresini gizle
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                # Başlatma hatasını kontrol etmek için kısa bir süre bekleyin
                time.sleep(1)
                if process.poll() is not None:  # İşlem sonlandıysa
                    returncode = process.returncode
                    if returncode != 0:  # Hata var
                        raise Exception(f"Process exited with code {returncode}")
                
                self.launch_signal.emit(True, "Minecraft launched successfully.")
            except Exception as e:
                raise Exception(f"Failed to execute Minecraft: {str(e)}")
            
        except Exception as e:
            error_message = f"Error launching Minecraft: {str(e)}"
            print(error_message)
            self.launch_signal.emit(False, error_message)

class UserInfoDialog(QDialog):
    """Kullanıcı adı soran diyalog"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.username = ""
        self.setWindowTitle("Welcome to Nova Launcher")
        self.setMinimumSize(460, 260)  # 30 pixel büyütüldü
        self.setMaximumSize(460, 260)  # 30 pixel büyütüldü
        self.setup_ui()
        
        # Set dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLineEdit {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: 1px solid #5d5d5d;
                padding: 8px;
                border-radius: 4px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #5ba042;
            }
            QPushButton {
                background-color: #5ba042;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4e8a38;
            }
            QPushButton:pressed {
                background-color: #3d6b2c;
            }
        """)
    
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 40, 40, 40)  # 30 pixel artırıldı
        layout.setSpacing(20)
        
        # Welcome message
        welcome_label = QLabel("Welcome to Nova Launcher!")
        welcome_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        welcome_label.setAlignment(Qt.AlignCenter)
        
        # Username input
        input_label = QLabel("Please enter your Minecraft username:")
        input_label.setFont(QFont("Segoe UI", 12))
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Your Minecraft username")
        self.username_input.setMinimumHeight(40)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Continue")
        self.ok_button.setMinimumHeight(40)
        self.ok_button.clicked.connect(self.accept_username)
        
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        
        # Add widgets to layout
        layout.addWidget(welcome_label)
        layout.addWidget(input_label)
        layout.addWidget(self.username_input)
        layout.addStretch()
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def accept_username(self):
        username = self.username_input.text().strip()
        if not username:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid username.")
            return
        
        self.username = username
        self.accept()

class SettingsDialog(QDialog):
    """Settings dialog for configuring launcher options"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 400)
        self.setMaximumSize(600, 400)
        
        # Apply stylesheet to dialog (dark theme)
        self.setStyleSheet("""
            QDialog {
                background-color: #2d2d2d;
                color: #e0e0e0;
            }
            QTabWidget::pane { 
                border: 1px solid #3d3d3d;
                background-color: #2d2d2d;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #3d3d3d;
                color: #e0e0e0;
                padding: 8px 16px;
                border: 1px solid #4d4d4d;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4d4d4d;
                color: #ffffff;
            }
            QLabel {
                color: #e0e0e0;
            }
            QComboBox, QSpinBox {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: 1px solid #5d5d5d;
                padding: 4px;
                border-radius: 4px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QSlider::groove:horizontal {
                border: 1px solid #5d5d5d;
                height: 8px;
                background: #3d3d3d;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #5ba042;
                border: 1px solid #5ba042;
                width: 18px;
                margin: -8px 0;
                border-radius: 9px;
            }
            QPushButton {
                background-color: #5ba042;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #4e8a38;
            }
            QPushButton:pressed {
                background-color: #3d6b2c;
            }
            QPushButton#cancelButton {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: 1px solid #5d5d5d;
            }
            QPushButton#cancelButton:hover {
                background-color: #4d4d4d;
            }
        """)
        
        self.setup_ui()
        
        # Set window icon if available
        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))
    
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Create tab widget
        tab_widget = QTabWidget()
        
        # General tab
        general_tab = QWidget()
        general_layout = QVBoxLayout()
        general_layout.setSpacing(15)
        
        # Minecraft directory selector
        dir_widget = QWidget()
        dir_layout = QHBoxLayout()
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_widget.setLayout(dir_layout)
        
        dir_label = QLabel("Minecraft Directory:")
        dir_label.setMinimumWidth(120)
        self.directory_label = QLabel(self.parent.minecraft_directory)
        self.directory_label.setStyleSheet("font-size: 13px; color: #666666; background-color: #f9f9f9; padding: 5px; border-radius: 3px;")
        directory_button = QPushButton("Select")
        directory_button.setMaximumWidth(80)
        directory_button.clicked.connect(self.select_directory)
        
        view_button = QPushButton("View")
        view_button.setMaximumWidth(80)
        view_button.clicked.connect(self.parent.open_minecraft_directory)
        
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.directory_label, 1)
        dir_layout.addWidget(view_button)
        dir_layout.addWidget(directory_button)
        
        # Username field
        username_widget = QWidget()
        username_layout = QHBoxLayout()
        username_layout.setContentsMargins(0, 0, 0, 0)
        username_widget.setLayout(username_layout)
        
        username_label = QLabel("Username:")
        username_label.setMinimumWidth(120)
        
        self.username_combo = QComboBox()
        self.username_combo.setEditable(True)
        self.username_combo.setMinimumHeight(40)
        self.username_combo.setCurrentText(self.parent.username)
        self.username_combo.setStyleSheet("padding: 2px 5px;")
        
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_combo)
        
        # Version Display Options
        version_options_group = QGroupBox("Version Display")
        version_options_layout = QVBoxLayout()
        self.fabric_checkbox = QCheckBox("Show Fabric Versions")
        self.fabric_checkbox.setChecked(self.parent.show_fabric)
        self.forge_checkbox = QCheckBox("Show Forge Versions")
        self.forge_checkbox.setChecked(self.parent.show_forge)
        self.snapshot_checkbox = QCheckBox("Show Snapshot Versions")
        self.snapshot_checkbox.setChecked(self.parent.show_snapshots)
        version_options_layout.addWidget(self.fabric_checkbox)
        version_options_layout.addWidget(self.forge_checkbox)
        version_options_layout.addWidget(self.snapshot_checkbox)
        version_options_group.setLayout(version_options_layout)

        # Add widgets to general tab
        general_layout.addWidget(dir_widget)
        general_layout.addWidget(username_widget)
        general_layout.addWidget(version_options_group) # Add the group box
        general_layout.addStretch()
        general_tab.setLayout(general_layout)
        
        # Java tab
        java_tab = QWidget()
        java_layout = QVBoxLayout()
        java_layout.setSpacing(15)
        
        # Java path selector
        java_widget = QWidget()
        java_layout_row = QHBoxLayout()
        java_layout_row.setContentsMargins(0, 0, 0, 0)
        java_widget.setLayout(java_layout_row)
        
        java_label = QLabel("Java Path:")
        java_label.setMinimumWidth(120)
        self.java_path_label = QLabel(self.parent.java_path if self.parent.java_path else "System default")
        self.java_path_label.setStyleSheet("font-size: 13px; color: #666666; background-color: #f9f9f9; padding: 5px; border-radius: 3px;")
        java_path_button = QPushButton("Select")
        java_path_button.setMaximumWidth(80)
        java_path_button.clicked.connect(self.select_java_path)
        
        # Add Reset button
        java_reset_button = QPushButton("Reset")
        java_reset_button.setMaximumWidth(80)
        java_reset_button.clicked.connect(self.reset_java_path)
        
        java_layout_row.addWidget(java_label)
        java_layout_row.addWidget(self.java_path_label, 1)
        java_layout_row.addWidget(java_reset_button)
        java_layout_row.addWidget(java_path_button)
        
        # RAM allocation
        ram_widget = QWidget()
        ram_layout = QHBoxLayout()
        ram_layout.setContentsMargins(0, 0, 0, 0)
        ram_widget.setLayout(ram_layout)
        
        ram_label = QLabel("RAM Allocation:")
        ram_label.setMinimumWidth(120)
        
        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setMinimum(1)
        self.ram_slider.setMaximum(16)
        self.ram_slider.setValue(self.parent.ram_allocation // 1024)
        self.ram_slider.setTickPosition(QSlider.TicksBelow)
        self.ram_slider.setTickInterval(1)
        
        self.ram_spin = QSpinBox()
        self.ram_spin.setMinimum(1)
        self.ram_spin.setMaximum(16)
        self.ram_spin.setValue(self.parent.ram_allocation // 1024)
        self.ram_spin.setSuffix(" GB")
        
        # Connect the slider and spin box to update each other
        self.ram_slider.valueChanged.connect(self.ram_spin.setValue)
        self.ram_spin.valueChanged.connect(self.ram_slider.setValue)
        
        ram_layout.addWidget(ram_label)
        ram_layout.addWidget(self.ram_slider)
        ram_layout.addWidget(self.ram_spin)
        
        # Add widgets to Java tab
        java_layout.addWidget(java_widget)
        java_layout.addWidget(ram_widget)
        java_layout.addStretch()
        java_tab.setLayout(java_layout)
        
        # Add tabs to the tab widget
        tab_widget.addTab(general_tab, "General")
        tab_widget.addTab(java_tab, "Java Settings")
        
        # Buttons at the bottom
        button_widget = QWidget()
        button_layout = QHBoxLayout()
        button_widget.setLayout(button_layout)
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_settings)
        self.save_button.setMinimumHeight(40)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancelButton")
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setMinimumHeight(40)
        
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.save_button)
        
        # Add widgets to main layout
        main_layout.addWidget(tab_widget)
        main_layout.addWidget(button_widget)
        
        self.setLayout(main_layout)
    
    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self, 
            "Select Minecraft Directory",
            self.parent.minecraft_directory
        )
        
        if directory:
            self.directory_label.setText(directory)
    
    def select_java_path(self):
        file_filter = "Executable files (*.exe);;All files (*.*)" if os.name == 'nt' else "All files (*.*)"
        java_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Java Executable",
            os.path.dirname(self.parent.java_path) if self.parent.java_path else os.path.expanduser("~"),
            file_filter
        )
        
        if java_path:
            self.java_path_label.setText(java_path)
    
    def reset_java_path(self):
        """Reset Java path to system default"""
        self.java_path_label.setText("System default")
    
    def save_settings(self):
        # Update parent settings
        self.parent.minecraft_directory = self.directory_label.text()
        self.parent.username = self.username_combo.currentText()
        
        # Set java_path to empty string if label is "System default"
        java_path_text = self.java_path_label.text()
        if java_path_text == "System default":
            self.parent.java_path = ""
        else:
            self.parent.java_path = java_path_text
            
        self.parent.ram_allocation = self.ram_spin.value() * 1024
        self.parent.show_fabric = self.fabric_checkbox.isChecked()
        self.parent.show_forge = self.forge_checkbox.isChecked()
        self.parent.show_snapshots = self.snapshot_checkbox.isChecked()
        
        # Update UI elements in the main window
        self.parent.user_label.setText(self.parent.username)
        
        # Save settings to file
        self.parent.save_settings()
        
        # Reload versions in the main window to reflect changes
        self.parent.load_versions()
        
        self.accept()

class NovaLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Load user settings
        self.settings = self.load_settings()
        
        # Application settings
        self.minecraft_directory = self.settings.get("minecraft_directory", DEFAULT_MINECRAFT_DIR)
        self.username = self.settings.get("username", "")
        self.selected_version = self.settings.get("last_used_version")
        self.ram_allocation = self.settings.get("ram_allocation", DEFAULT_SETTINGS["ram_allocation"])
        self.java_path = self.settings.get("java_path", DEFAULT_SETTINGS["java_path"])
        self.show_fabric = self.settings.get("show_fabric", DEFAULT_SETTINGS["show_fabric"])
        self.show_forge = self.settings.get("show_forge", DEFAULT_SETTINGS["show_forge"])
        self.show_snapshots = self.settings.get("show_snapshots", DEFAULT_SETTINGS["show_snapshots"])
        
        # Request username if not set
        if not self.username:
            dialog = UserInfoDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                self.username = dialog.username
                self.save_settings()
            else:
                # Default username if user cancels
                self.username = "Player"
        
        # UI setup
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(800, 250)
        
        # Set logo (if available)
        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))
        
        # Setup dark theme
        self.setup_dark_theme()
        
        self.setup_ui()
        
        # Retry counters for version loading
        self.version_retries = 0
        self.max_retries = 5
        
        # Load versions
        self.load_versions()
        
        # Create Minecraft directory (if it doesn't exist)
        if not os.path.exists(self.minecraft_directory):
            try:
                os.makedirs(self.minecraft_directory)
            except Exception as e:
                print(f"Could not create Minecraft directory: {str(e)}")
    
    def setup_dark_theme(self):
        """Apply dark theme styles to the application"""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #2d2d2d;
                color: #e0e0e0;
            }
            QGroupBox {
                border: 1px solid #3d3d3d;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                color: #e0e0e0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLabel#titleLabel {
                color: #5ba042;
                font-weight: bold;
            }
            QComboBox {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: 1px solid #5d5d5d;
                padding: 4px;
                border-radius: 4px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QLineEdit {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: 1px solid #5d5d5d;
                padding: 4px;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: 1px solid #5d5d5d;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QPushButton#playButton {
                background-color: #5ba042;
                color: white;
                border: none;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton#playButton:hover {
                background-color: #4e8a38;
            }
            QPushButton#playButton:pressed {
                background-color: #3d6b2c;
            }
            QProgressBar {
                border: 1px solid #5d5d5d;
                border-radius: 4px;
                text-align: center;
                background-color: #3d3d3d;
            }
            QProgressBar::chunk {
                background-color: #5ba042;
                width: 20px;
            }
        """)

    def setup_ui(self):
        # Ana widget ve düzen
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 10, 20, 10)
        main_layout.setSpacing(8)
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # ===== ÜST BAR (NOVA LAUNCHER, KULLANICI VE AYARLAR) =====
        top_bar = QWidget()
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_bar.setLayout(top_layout)
        
        # -- Kullanıcı bilgisi (sol taraf) --
        user_widget = QWidget()
        user_widget.setObjectName("userWidget")
        user_widget.setStyleSheet("""
            #userWidget {
                background-color: #2d2d2d;
                border-radius: 4px;
                padding: 0px;
            }
        """)
        user_layout = QHBoxLayout()
        user_layout.setContentsMargins(8, 4, 10, 4)
        user_layout.setSpacing(8)
        user_widget.setLayout(user_layout)
        
        # Avatar
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(26, 26)
        
        # Load creeper avatar
        creeper_path = os.path.join(RESOURCES_DIR, "creeper.jpg")
        if os.path.exists(creeper_path):
            avatar_pixmap = QPixmap(creeper_path)
            # Scale pixmap smoothly keeping aspect ratio
            self.avatar_label.setPixmap(avatar_pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            print(f"Warning: Avatar image not found at {creeper_path}. Drawing default.")
            # Fallback to drawing default avatar if image is missing
            avatar_pixmap = QPixmap(26, 26)
            avatar_pixmap.fill(Qt.transparent)
            painter = QPainter(avatar_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(PRIMARY_COLOR))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(0, 0, 26, 26)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(9, 4, 8, 8)
            path = QPainterPath()
            path.moveTo(13, 12)
            path.lineTo(17, 22)
            path.lineTo(9, 22)
            path.lineTo(13, 12)
            painter.drawPath(path)
            painter.end()
            self.avatar_label.setPixmap(avatar_pixmap)
        
        # Kullanıcı adı
        self.user_label = QLabel(self.username)
        self.user_label.setStyleSheet("""
            color: #e0e0e0;
            font-size: 13px;
        """)
        
        user_layout.addWidget(self.avatar_label)
        user_layout.addWidget(self.user_label)
        
        # -- Header Image (orta) --
        self.header_label = QLabel()
        self.header_label.setAlignment(Qt.AlignCenter)
        header_path = os.path.join(RESOURCES_DIR, "header.png")
        if os.path.exists(header_path):
            header_pixmap = QPixmap(header_path)
            # Optionally scale header if needed, e.g., to height 40
            header_pixmap = header_pixmap.scaledToHeight(40, Qt.SmoothTransformation)
            self.header_label.setPixmap(header_pixmap)
        else:
            # Fallback to text if image is missing
            print(f"Warning: Header image not found at {header_path}. Using text title.")
            self.header_label.setText(APP_NAME)
            self.header_label.setObjectName("titleLabel")
            self.header_label.setFont(QFont("Segoe UI", 28, QFont.Bold))
        
        # -- Ayarlar butonu (sağ taraf) --
        settings_button = QPushButton("⚙️")
        settings_button.setObjectName("settingsButton")
        settings_button.setFixedSize(36, 36)
        settings_button.setFont(QFont("Segoe UI", 16))
        settings_button.setStyleSheet("""
            #settingsButton {
                background-color: transparent;
                border: none;
                border-radius: 18px;
                padding: 0px;
                color: #e0e0e0;
            }
            #settingsButton:hover {
                background-color: #3d3d3d;
            }
            #settingsButton:pressed {
                background-color: #2d2d2d;
            }
        """)
        
        settings_button.setToolTip("Settings")
        settings_button.clicked.connect(self.open_settings)
        
        # Tüm öğeleri üst bara ekle
        top_layout.addWidget(user_widget)
        top_layout.addStretch(1)
        top_layout.addWidget(self.header_label) # Use header label here
        top_layout.addStretch(1)
        top_layout.addWidget(settings_button)
        
        main_layout.addWidget(top_bar)
        
        # ===== AYIRICI ÇİZGİ =====
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #3d3d3d;")
        main_layout.addWidget(separator)
        
        # ===== SÜRÜM SEÇİCİ =====
        version_group = QGroupBox("Minecraft Version")
        version_layout = QVBoxLayout()
        version_layout.setSpacing(6)
        version_group.setLayout(version_layout)
        
        # Sürüm seçici
        self.version_combo = QComboBox()
        self.version_combo.setMinimumHeight(35)
        self.version_combo.setPlaceholderText("Select Minecraft version")
        version_layout.addWidget(QLabel("Select the Minecraft version you want to play:"))
        version_layout.addWidget(self.version_combo)
        
        main_layout.addWidget(version_group)
        
        # ===== OYNA BUTONU =====
        self.play_button = QPushButton("PLAY")
        self.play_button.setObjectName("playButton")
        self.play_button.clicked.connect(self.play_minecraft)
        self.play_button.setMinimumHeight(50)
        self.play_button.setMinimumWidth(250)
        self.play_button.setFont(QFont("Segoe UI", 16, QFont.Bold))
        
        main_layout.addWidget(self.play_button, 0, Qt.AlignCenter)
        
        # Yükleme durumu gösterimi için bir container
        self.loading_container = QFrame()
        self.loading_container.setObjectName("loadingContainer")
        self.loading_container.setStyleSheet("""
            #loadingContainer {
                background-color: #2d2d2d;
                border-radius: 6px;
                border: 1px solid #5ba042;
            }
        """)
        self.loading_container.setFixedHeight(50)
        self.loading_container.setFixedWidth(250)
        
        loading_layout = QHBoxLayout()
        loading_layout.setContentsMargins(15, 5, 15, 5)
        loading_layout.setSpacing(15)
        
        # Spinner (Animasyonlu dönen daire)
        self.spinner_label = QLabel()
        self.spinner_label.setFixedSize(30, 30)
        self.spinner_label.setAlignment(Qt.AlignCenter)
        
        # Durum metni
        self.status_label = QLabel()
        self.status_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.status_label.setStyleSheet("color: #5ba042;")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        loading_layout.addWidget(self.spinner_label)
        loading_layout.addWidget(self.status_label, 1)
        
        self.loading_container.setLayout(loading_layout)
        self.loading_container.hide()  # Başlangıçta gizli
        
        main_layout.addWidget(self.loading_container, 0, Qt.AlignCenter)
        
        # Spinner animasyonu için timer
        self.spinner_angle = 0
        self.spinner_timer = QTimer()
        self.spinner_timer.timeout.connect(self.update_spinner)
        
        # Gizli durum etiketi
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        
        # Sürüm değişikliği dinleyicisi
        self.version_combo.currentIndexChanged.connect(self.update_selected_version)

    def open_settings(self):
        """Open the settings dialog"""
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec_()
    
    def load_versions(self):
        """Load Minecraft versions"""
        self.progress_label.setText("Loading versions...")
        self.version_thread = MinecraftVersionThread()
        self.version_thread.version_signal.connect(self.update_versions)
        self.version_thread.start()
    
    def update_versions(self, versions):
        current_selection = self.version_combo.currentText() # Keep track of current selection
        self.version_combo.clear()
        
        if not versions:
            # Only retry if we haven't exceeded the maximum number of retries
            if self.version_retries < self.max_retries:
                self.version_retries += 1
                print(f"Retrying version load ({self.version_retries}/{self.max_retries})...")
                # Wait 3 seconds before trying again
                QTimer.singleShot(3000, self.load_versions)
            return
        
        self.version_retries = 0  # Reset retry counter on success
        release_versions = []
        snapshot_versions = []
        processed_versions = [] # Store tuples of (display_name, version_id, type)
        
        # Separate releases and snapshots (if shown)
        for version in versions:
            version_type = version.get("type")
            if version_type == "release":
                release_versions.append(version)
            elif version_type == "snapshot" and self.show_snapshots: # Check setting here
                snapshot_versions.append(version)
        
        # Sort releases and snapshots separately by release time, newest first
        release_versions.sort(key=lambda x: x.get("releaseTime", ""), reverse=True)
        snapshot_versions.sort(key=lambda x: x.get("releaseTime", ""), reverse=True)

        # Combine lists (snapshots first if shown)
        combined_versions = snapshot_versions + release_versions

        # Add Vanilla, Fabric and Forge versions based on combined list
        for version in combined_versions:
            vanilla_id = version.get("id")
            if not vanilla_id: continue
            
            # Determine display name prefix for snapshots
            display_name_prefix = "[S] " if version.get("type") == "snapshot" else ""

            # Add Vanilla entry
            processed_versions.append((f"{display_name_prefix}{vanilla_id}", vanilla_id, "vanilla"))

            # Add Fabric entry only if show_fabric is enabled AND it's a release version
            if self.show_fabric and version.get("type") == "release": 
                fabric_display_name = f"Fabric {vanilla_id}" # No prefix for Fabric/Forge releases
                # Store BASE vanilla ID and type "fabric" for later use
                processed_versions.append((fabric_display_name, vanilla_id, "fabric"))

            # Try to get and add Forge entry only if show_forge is enabled AND it's a release version
            if self.show_forge and version.get("type") == "release":
                try:
                    forge_version_str = forge.find_forge_version(vanilla_id)
                    if forge_version_str:
                        forge_display_name = f"Forge {vanilla_id}" # No prefix for Fabric/Forge releases
                        # Store base vanilla ID, type 'forge', and the specific forge version string
                        processed_versions.append((forge_display_name, vanilla_id, "forge", forge_version_str))
                except Exception as e:
                    pass

        # Populate the combo box
        for item_tuple in processed_versions:
            display_name = item_tuple[0]
            version_id_or_base_id = item_tuple[1]
            version_type = item_tuple[2]
            user_data = {"id": version_id_or_base_id, "type": version_type}
            # Add forge_version if it exists (for forge types)
            if version_type == "forge" and len(item_tuple) > 3:
                user_data["forge_version"] = item_tuple[3]
            
            self.version_combo.addItem(display_name, userData=user_data)
        
        # Restore previous selection if possible
        # Find based on DISPLAY NAME first
        index = self.version_combo.findText(current_selection)
        if index >= 0:
            self.version_combo.setCurrentIndex(index)
        # Select latest version if no previous selection or previous selection is gone
        elif not self.selected_version and self.version_combo.count() > 0:
             self.version_combo.setCurrentIndex(0)
             self.update_selected_version(0) # Trigger update
        # If there was a selected version saved, try to find it by ID
        elif self.selected_version:
            found_index = -1
            for i in range(self.version_combo.count()):
                item_data = self.version_combo.itemData(i)
                # Check against base ID for Fabric/Forge, full ID for Vanilla
                stored_id_in_settings = self.settings.get("last_used_version") # This might be base or full
                current_item_id = item_data.get("id") # Base for Fabric/Forge, Full for Vanilla
                current_item_type = item_data.get("type")
                
                # Attempt to match based on what was saved
                # If saved ID matches current item ID directly (works for Vanilla, or if base ID was saved for F/F)
                if stored_id_in_settings == current_item_id:
                     found_index = i
                     break
                # If saved ID might be a full Fabric/Forge launch ID, check if its base matches current item's base ID
                elif stored_id_in_settings and (current_item_type == "fabric" or current_item_type == "forge"):
                     try:
                         # Attempt to extract base ID from potentially full saved ID
                         base_from_saved = stored_id_in_settings.split('-')[-1]
                         if base_from_saved == current_item_id:
                             found_index = i
                             break
                     except:
                         pass # Ignore potential errors splitting non-standard IDs

            if found_index >= 0:
                self.version_combo.setCurrentIndex(found_index)
            elif self.version_combo.count() > 0: # Fallback to first item
                 self.version_combo.setCurrentIndex(0)
                 self.update_selected_version(0) # Trigger update

    def update_selected_version(self, index):
        if index >= 0:
            item_data = self.version_combo.itemData(index)
            if item_data:
                # Save the BASE ID for Fabric/Forge, or the full ID for Vanilla
                # This might cause issues if multiple Fabric/Forge loaders exist for the same base
                # but simplifies restoring selection for now.
                # Launch logic will find the specific installed version anyway.
                self.selected_version = item_data.get("id")
                # Save settings
                self.save_settings()
    
    def open_minecraft_directory(self):
        if not os.path.exists(self.minecraft_directory):
            QMessageBox.warning(self, "Warning", "Minecraft directory does not exist!")
            return
            
        try:
            if sys.platform == 'win32':
                os.startfile(self.minecraft_directory)
            elif sys.platform == 'darwin':  # macOS
                subprocess.Popen(['open', self.minecraft_directory])
            else:  # Linux ve diğer işletim sistemleri
                subprocess.Popen(['xdg-open', self.minecraft_directory])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open directory: {str(e)}")
    
    def check_and_install_minecraft(self, version_data):
        """Check if version is installed and install if needed. version_data is a dict {'id': '...', 'type': '...'}"""
        if not version_data:
            return False # Should not happen

        version_id = version_data.get("id") # This is BASE ID for Fabric
        version_type = version_data.get("type")
        display_name = self.version_combo.currentText() # For messages

        is_installed = False
        if version_type == "fabric":
            # For Fabric, check if base vanilla is installed AND *any* fabric loader exists for it
            base_vanilla_id = version_id # It's already the base ID
            vanilla_version_dir = os.path.join(self.minecraft_directory, "versions", base_vanilla_id)
            vanilla_jar_file = os.path.join(vanilla_version_dir, f"{base_vanilla_id}.jar")
            
            # Check if base vanilla jar exists
            if os.path.exists(vanilla_jar_file):
                # Check if *any* directory matching "fabric-loader-*-(base_vanilla_id)" exists
                fabric_pattern = os.path.join(self.minecraft_directory, "versions", f"fabric-loader*-{base_vanilla_id}")
                matching_fabric_dirs = glob.glob(fabric_pattern)
                is_installed = bool(matching_fabric_dirs) # True if any matching directory found
            else:
                 is_installed = False # Vanilla base not even installed

        elif version_type == "forge":
            # For Forge, check if base vanilla is installed AND *any* forge version exists for it
            base_vanilla_id = version_id # It's already the base ID
            vanilla_version_dir = os.path.join(self.minecraft_directory, "versions", base_vanilla_id)
            vanilla_jar_file = os.path.join(vanilla_version_dir, f"{base_vanilla_id}.jar")

            if os.path.exists(vanilla_jar_file):
                # Check if *any* directory matching pattern like "*forge*-(base_vanilla_id)" exists
                # Forge naming can be inconsistent (e.g., 1.12.2-forge-14..., 1.16.5-forge-...)
                forge_pattern = os.path.join(self.minecraft_directory, "versions", f"*{base_vanilla_id}*forge*") # More flexible pattern
                matching_forge_dirs = glob.glob(forge_pattern)
                is_installed = bool(matching_forge_dirs)
            else:
                is_installed = False

        else: # Vanilla
            version_dir = os.path.join(self.minecraft_directory, "versions", version_id)
            jar_file = os.path.join(version_dir, f"{version_id}.jar")
            is_installed = os.path.exists(jar_file)
        
        if is_installed:
            return True  # Already installed
        
        # Need to install
        reply = QMessageBox.question(
            self, 
            "Minecraft Installation",
            f"{display_name} is not installed. Do you want to install it now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.show_loading(is_launching=False, percentage=0)  # Show loading screen
            self.install_minecraft(version_data) # Pass the whole data dict
            return False  # Installation in progress
        else:
            return False  # User declined installation
    
    def install_minecraft(self, version_data):
        # version_data is the dict like {'id': '...', 'type': '...'}
        if not version_data:
            QMessageBox.warning(self, "Warning", "Invalid version selected!")
            return
            
        version_id = version_data.get("id")
        version_type = version_data.get("type")
        display_name = self.version_combo.currentText() # For display

        if not version_id or not version_type:
            QMessageBox.warning(self, "Warning", "Version information incomplete!")
            return
        
        # Update button text for installation
        self.play_button.setText(f"INSTALLING {display_name}...")
        self.play_button.setEnabled(False)
        self.play_button.setStyleSheet("""
            #playButton {
                background-color: #6c6c6c; /* Grey out */
                color: white;
                border: none;
                font-weight: bold;
                font-size: 16px;
                text-align: center;
            }
        """)
        
        # Start installation thread with version id and type
        forge_version_string = version_data.get("forge_version") # Get forge version if exists
        self.install_thread = MinecraftInstallThread(self.minecraft_directory, version_id, version_type, forge_version_string)
        self.install_thread.progress_signal.connect(self.update_progress)
        self.install_thread.complete_signal.connect(self.installation_complete)
        self.install_thread.start()
    
    def update_play_button_text(self):
        """Text-based spinner için dönen noktaları güncelle"""
        if not self.play_button.isEnabled():
            version = self.selected_version
            
            # Mevcut dönen nokta sayısını bul
            current_text = self.play_button.text()
            base_text = f"INSTALLING {version}"
            
            if current_text == base_text:
                new_text = f"{base_text} ."
            elif current_text == f"{base_text} .":
                new_text = f"{base_text} .."
            elif current_text == f"{base_text} ..":
                new_text = f"{base_text} ..."
            else:
                new_text = base_text
                
            self.play_button.setText(new_text)
    
    def update_progress(self, percentage, status):
        """İlerleme durumunu günceller ve loading ekranındaki yüzdeyi de günceller"""
        self.progress_label.setText(status)
        
        # Loading ekranı gösteriliyorsa yüzdeyi güncelle
        if self.loading_container.isVisible() and self.status_label.text().startswith("DOWNLOADING"):
            self.status_label.setText(f"DOWNLOADING {percentage}%")
            
            # İndirme tamamlandıysa (100%) 2 saniye sonra loading ekranını kapat
            if percentage >= 100:
                QTimer.singleShot(2000, self.hide_loading)
    
    def installation_complete(self, success, message):
        self.progress_label.setText(message)
        
        # Play spinner'ı durdur
        if hasattr(self, 'play_spinner_timer') and self.play_spinner_timer.isActive():
            self.play_spinner_timer.stop()
        
        # Play butonunu normal haline getir
        self.play_button.setText("PLAY")
        self.play_button.setEnabled(True)
        self.play_button.setStyleSheet("""
            #playButton {
                background-color: #5ba042;
                color: white;
                border: none;
                font-weight: bold;
                font-size: 16px;
                text-align: center;
                padding: 0px;
            }
            #playButton:hover {
                background-color: #4e8a38;
            }
            #playButton:pressed {
                background-color: #3d6b2c;
            }
        """)
        
        # Loading ekranını kapat
        self.hide_loading()
        
        if success:
            # Launch minecraft after successful installation
            self.show_loading(is_launching=True)  # LAUNCHING göster
            self.launch_minecraft()
        else:
            QMessageBox.critical(self, "Installation Error", message)
    
    def show_loading(self, is_launching=True, percentage=0):
        """Yükleme/başlatma animasyonunu gösterir"""
        # Play butonunu gizle
        self.play_button.hide()
        
        # Duruma göre metni ayarla
        if is_launching:
            self.status_label.setText("LAUNCHING")
        else:
            # İndirme durumunda yüzdeyi göster
            self.status_label.setText(f"DOWNLOADING {percentage}%")
        
        # Loading container'ı göster
        self.loading_container.show()
        
        # Spinner animasyonunu başlat
        self.spinner_timer.start(50)  # Her 50 ms'de bir güncelle
        
        # Başlatma durumunda 10 saniye sonra loading'i kapat
        if is_launching:
            QTimer.singleShot(10000, self.hide_loading)
    
    def hide_loading(self):
        """Yükleme/başlatma animasyonunu gizler"""
        # Spinner'ı durdur
        self.spinner_timer.stop()
        
        # Loading container'ı gizle
        self.loading_container.hide()
        
        # Play butonunu tekrar göster
        self.play_button.show()

    def update_spinner(self):
        """Spinner animasyonunu günceller"""
        self.spinner_angle = (self.spinner_angle + 15) % 360
        
        # Spinner çizimi
        spinner_pixmap = QPixmap(30, 30)
        spinner_pixmap.fill(Qt.transparent)
        
        painter = QPainter(spinner_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Spinner arka planı (grilik)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(80, 80, 80, 80))
        painter.drawEllipse(3, 3, 24, 24)
        
        # Dönen parça (yeşil)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(PRIMARY_COLOR))
        
        # Sadece bir kısmını çiz (120 derece)
        path = QPainterPath()
        path.moveTo(15, 15)  # Merkez
        path.arcTo(3, 3, 24, 24, self.spinner_angle, 120)
        path.lineTo(15, 15)  # Merkeze geri dön
        painter.drawPath(path)
        
        painter.end()
        
        self.spinner_label.setPixmap(spinner_pixmap)

    def play_minecraft(self):
        """Unified method to play or install Minecraft"""
        current_index = self.version_combo.currentIndex()
        if current_index < 0:
            QMessageBox.warning(self, "Warning", "Please select a Minecraft version!")
            return
            
        version_data = self.version_combo.itemData(current_index)
        if not version_data or not version_data.get("id"):
            QMessageBox.warning(self, "Warning", "Invalid version data selected!")
            return
        
        if not self.username:
            QMessageBox.warning(self, "Warning", "Please enter your username!")
            return
        
        # Ayarları kaydet (selected_version ID'sini zaten güncelledik)
        self.save_settings()
        
        # Sürüm kurulu değilse kur (version_data'yı ilet)
        if self.check_and_install_minecraft(version_data):
            # Kuruluysa doğrudan başlat
            self.show_loading(is_launching=True)  # LAUNCHING göster
            self.launch_minecraft()
    
    def launch_minecraft(self):
        """Launch Minecraft with current settings"""
        current_index = self.version_combo.currentIndex()
        if current_index < 0:
            QMessageBox.critical(self, "Launch Error", "No version selected.")
            self.hide_loading()
            return
            
        version_data = self.version_combo.itemData(current_index)
        if not version_data:
             QMessageBox.critical(self, "Launch Error", "Invalid version data.")
             self.hide_loading()
             return

        version_id_to_launch = version_data.get("id") # Base ID for Fabric, Full ID for Vanilla
        version_type = version_data.get("type")

        # If Fabric, find the exact installed version ID
        if version_type == "fabric":
            base_vanilla_id = version_id_to_launch # It's the base ID here
            try:
                installed_versions = mclib.utils.get_installed_versions(self.minecraft_directory)
                found_fabric_id = None
                # Look for an ID like "fabric-loader-<loader_version>-(base_vanilla_id)"
                pattern = f"fabric-loader-"
                for installed_ver in installed_versions:
                    ver_id = installed_ver.get("id")
                    if ver_id and ver_id.startswith(pattern) and ver_id.endswith(base_vanilla_id):
                        found_fabric_id = ver_id
                        break # Found the first match
                
                if not found_fabric_id:
                    # This might happen if check_and_install failed silently or something is wrong
                    QMessageBox.critical(self, "Launch Error", f"Could not find installed Fabric for {base_vanilla_id}. Please try installing it again.")
                    self.hide_loading()
                    return
                
                version_id_to_launch = found_fabric_id # Update to the full Fabric ID

            except Exception as e:
                 QMessageBox.critical(self, "Launch Error", f"Error finding installed Fabric version: {e}")
                 self.hide_loading()
                 return

        # If Forge, find the exact installed launch ID
        elif version_type == "forge":
            base_vanilla_id = version_id_to_launch # It's the base ID here
            try:
                installed_versions = mclib.utils.get_installed_versions(self.minecraft_directory)
                found_forge_id = None
                # Look for an ID that contains both the base_vanilla_id and "forge"
                # Order might vary (e.g., 1.12.2-forge-..., 1.16.5-forge-...)
                for installed_ver in installed_versions:
                    ver_id = installed_ver.get("id")
                    if ver_id and base_vanilla_id in ver_id and "forge" in ver_id.lower():
                        found_forge_id = ver_id
                        # Maybe add preference for specific forge version if multiple found?
                        # For now, take the first one found.
                        break 
                
                if not found_forge_id:
                    QMessageBox.critical(self, "Launch Error", f"Could not find installed Forge for {base_vanilla_id}. Please try installing it again.")
                    self.hide_loading()
                    return
                
                version_id_to_launch = found_forge_id # Update to the full Forge launch ID

            except Exception as e:
                 QMessageBox.critical(self, "Launch Error", f"Error finding installed Forge version: {e}")
                 self.hide_loading()
                 return

        # Ensure we have a final version ID to launch
        if not version_id_to_launch:
             QMessageBox.critical(self, "Launch Error", "Could not determine version to launch.")
             self.hide_loading()
             return

        # Launch Minecraft using the final determined version ID
        self.launch_thread = MinecraftLauncherThread(
            self.minecraft_directory,
            version_id_to_launch, # Use the determined ID
            self.username,  
            self.ram_allocation,
            self.java_path
        )
        self.launch_thread.launch_signal.connect(self.launch_complete)
        self.launch_thread.start()
    
    def launch_complete(self, success, message):
        if not success:
            QMessageBox.critical(self, "Launch Error", message)
    
    def closeEvent(self, event):
        # Save settings when application closes
        self.save_settings()
        super().closeEvent(event)

    def load_settings(self):
        """Load user settings from the settings file"""
        settings = {
            "minecraft_directory": DEFAULT_MINECRAFT_DIR,
            "username": "",
            "last_used_version": None,
            "ram_allocation": DEFAULT_SETTINGS["ram_allocation"],
            "java_path": DEFAULT_SETTINGS["java_path"],
            "show_fabric": DEFAULT_SETTINGS["show_fabric"],
            "show_forge": DEFAULT_SETTINGS["show_forge"],
            "show_snapshots": DEFAULT_SETTINGS["show_snapshots"]
        }
        
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
        except Exception as e:
            print(f"Error loading settings: {str(e)}")
        
        return settings
    
    def save_settings(self):
        """Save user settings to the settings file"""
        settings = {
            "minecraft_directory": self.minecraft_directory,
            "username": self.username,
            "last_used_version": self.selected_version,
            "ram_allocation": self.ram_allocation,
            "java_path": self.java_path,
            "show_fabric": self.show_fabric,
            "show_forge": self.show_forge,
            "show_snapshots": self.show_snapshots
        }
        
        try:
            # Minecraft klasörünü oluştur (eğer yoksa)
            if not os.path.exists(self.minecraft_directory):
                os.makedirs(self.minecraft_directory)
            
            # Ayarlar dosyasını doğrudan Minecraft klasörüne kaydet
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {str(e)}")

def main():
    app = QApplication(sys.argv)
    launcher = NovaLauncher()
    launcher.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 