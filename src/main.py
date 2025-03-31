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
                           QMessageBox, QFileDialog, QGroupBox, QHBoxLayout, QGridLayout,
                           QDialog, QSpinBox, QSlider, QTabWidget, QInputDialog,
                           QFrame, QLineEdit, QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QByteArray
from PyQt5.QtGui import QIcon, QPixmap, QFont, QPainter, QColor, QPainterPath

from .config import *

def create_icon_from_base64(base64_str):
    base64_str = base64_str.strip()
    icon_data = base64.b64decode(base64_str)
    pixmap = QPixmap()
    pixmap.loadFromData(icon_data)
    return QIcon(pixmap)

def generate_uuid_from_username(username):
    namespace = uuid.NAMESPACE_OID
    username_uuid = uuid.uuid5(namespace, username)
    return str(username_uuid)

class MinecraftVersionThread(QThread):
    version_signal = pyqtSignal(list)
    
    def run(self):
        try:
            versions = mclib.utils.get_version_list()
            self.version_signal.emit(versions)
        except Exception as e:
            self.version_signal.emit([])

class MinecraftInstallThread(QThread):
    progress_signal = pyqtSignal(int, str)
    complete_signal = pyqtSignal(bool, str)
    
    def __init__(self, minecraft_dir, version, version_type, forge_version_string=None):
        super().__init__()
        self.minecraft_directory = minecraft_dir
        self.version = version
        self.version_type = version_type
        self.forge_version_string = forge_version_string
        self._current_status = "Starting installation..."
        self._current_progress = 0
        
    def set_status(self, status):
        self._current_status = status
        self.progress_signal.emit(self._current_progress, self._current_status)

    def set_progress(self, value, max_value=None):
        if max_value is not None and max_value > 0: 
            self._current_progress = int((value / max_value) * 100)
        
        self.progress_signal.emit(self._current_progress, self._current_status)
        
    def run(self):
        callback_dict = {
            "setStatus": self.set_status,
            "setProgress": self.set_progress
        }
        
        base_vanilla_id = self.version
        if self.version_type == "fabric":
            try:
                base_vanilla_id = self.version.split('-')[-1]
            except IndexError:
                 self.complete_signal.emit(False, f"Invalid Fabric version ID format: {self.version}")
                 return

        try:
            self.set_status(f"Installing Vanilla {base_vanilla_id}...")
            if not os.path.exists(self.minecraft_directory):
                os.makedirs(self.minecraft_directory)
                
            mclib.install.install_minecraft_version(
                base_vanilla_id, 
                self.minecraft_directory, 
                callback=callback_dict
            )
            self.set_status(f"Vanilla {base_vanilla_id} installed.")

            if self.version_type == "fabric":
                self.set_status(f"Installing Fabric for {base_vanilla_id}...")
                try:
                    mclib.fabric.install_fabric(
                        base_vanilla_id,
                        self.minecraft_directory,
                        callback=callback_dict,
                    )
                    self.set_status(f"Fabric for {base_vanilla_id} installed.")
                except Exception as fabric_exc:
                    error_message = f"Vanilla {base_vanilla_id} installed, but Fabric failed: {str(fabric_exc)}"
                    self.complete_signal.emit(False, error_message)
                    return

            elif self.version_type == "forge":
                if not self.forge_version_string:
                    self.complete_signal.emit(False, f"Missing Forge version info for {base_vanilla_id}")
                    return

                self.set_status(f"Installing Forge for {base_vanilla_id} ({self.forge_version_string})...")
                try:
                    if not forge.supports_automatic_install(self.forge_version_string):
                        raise Exception(f"Automatic installation not supported for Forge {self.forge_version_string}. Please install manually.")

                    forge.install_forge_version(
                        self.forge_version_string, 
                        self.minecraft_directory,
                        callback=callback_dict
                    )
                    self.set_status(f"Forge for {base_vanilla_id} installed.")
                except Exception as forge_exc:
                    error_message = f"Vanilla {base_vanilla_id} installed, but Forge failed: {str(forge_exc)}"
                    self.complete_signal.emit(False, error_message)
                    return

            success_message = f"Minecraft {self.version} installed successfully."
            if self.version_type == "fabric":
                 success_message = f"Fabric {base_vanilla_id} ({self.version}) installed successfully."
            elif self.version_type == "forge":
                 success_message = f"Forge {base_vanilla_id} installed successfully."
                 
            self.complete_signal.emit(True, success_message)

        except Exception as e:
            error_message = f"Error installing {self.version}: {str(e)}"
            self.complete_signal.emit(False, error_message)

class MinecraftLauncherThread(QThread):
    launch_signal = pyqtSignal(bool, str)
    
    def __init__(self, minecraft_dir, version, username, ram, java_path=None):
        super().__init__()
        self.minecraft_directory = minecraft_dir
        self.version = version
        self.username = username
        self.ram = ram
        self.java_path = java_path
    
    def run(self):
        try:
            if self.java_path and os.path.exists(self.java_path):
                java_path = self.java_path
            else:
                java_path = None
                
            player_uuid = generate_uuid_from_username(self.username)
                
            options = {
                "username": self.username,
                "uuid": player_uuid,
                "token": "",
                "jvmArguments": [f"-Xmx{self.ram}m"],
                "quickPlayPath": None
            }
            
            if java_path:
                options["executablePath"] = java_path
            
            command = mclib.command.get_minecraft_command(
                self.version, 
                self.minecraft_directory, 
                options
            )
            
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
            
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
            
            try:
                process = subprocess.Popen(
                    filtered_command, 
                    cwd=self.minecraft_directory,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                self.launch_signal.emit(True, "Minecraft launch command sent successfully.")
            except Exception as e:
                raise Exception(f"Failed to execute Minecraft: {str(e)}")
            
        except Exception as e:
            error_message = f"Error launching Minecraft: {str(e)}"
            self.launch_signal.emit(False, error_message)

class UserInfoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.username = ""
        self.setWindowTitle("Welcome to Nova Launcher")
        self.setMinimumSize(460, 260)
        self.setMaximumSize(460, 260)
        self.setup_ui()
        
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
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        welcome_label = QLabel("Welcome to Nova Launcher!")
        welcome_label.setFont(QFont("Segoe UI", 16, QFont.Bold))
        welcome_label.setAlignment(Qt.AlignCenter)
        
        input_label = QLabel("Please enter your Minecraft username:")
        input_label.setFont(QFont("Segoe UI", 12))
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Your Minecraft username")
        self.username_input.setMinimumHeight(40)
        
        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Continue")
        self.ok_button.setMinimumHeight(40)
        self.ok_button.clicked.connect(self.accept_username)
        
        button_layout.addStretch()
        button_layout.addWidget(self.ok_button)
        
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 400)
        self.setMaximumSize(600, 400)
        
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
        
        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))
    
    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        tab_widget = QTabWidget()
        
        general_tab = QWidget()
        general_layout = QVBoxLayout()
        general_layout.setSpacing(15)
        
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

        general_layout.addWidget(dir_widget)
        general_layout.addWidget(username_widget)
        general_layout.addWidget(version_options_group)
        general_layout.addStretch()
        general_tab.setLayout(general_layout)
        
        java_tab = QWidget()
        java_layout = QVBoxLayout()
        java_layout.setSpacing(15)
        
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
        
        java_reset_button = QPushButton("Reset")
        java_reset_button.setMaximumWidth(80)
        java_reset_button.clicked.connect(self.reset_java_path)
        
        java_layout_row.addWidget(java_label)
        java_layout_row.addWidget(self.java_path_label, 1)
        java_layout_row.addWidget(java_reset_button)
        java_layout_row.addWidget(java_path_button)
        
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
        
        self.ram_slider.valueChanged.connect(self.ram_spin.setValue)
        self.ram_spin.valueChanged.connect(self.ram_slider.setValue)
        
        ram_layout.addWidget(ram_label)
        ram_layout.addWidget(self.ram_slider)
        ram_layout.addWidget(self.ram_spin)
        
        java_layout.addWidget(java_widget)
        java_layout.addWidget(ram_widget)
        java_layout.addStretch()
        java_tab.setLayout(java_layout)
        
        tab_widget.addTab(general_tab, "General")
        tab_widget.addTab(java_tab, "Java Settings")
        
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
        self.java_path_label.setText("System default")
    
    def save_settings(self):
        self.parent.minecraft_directory = self.directory_label.text()
        self.parent.username = self.username_combo.currentText()
        
        java_path_text = self.java_path_label.text()
        if java_path_text == "System default":
            self.parent.java_path = ""
        else:
            self.parent.java_path = java_path_text
            
        self.parent.ram_allocation = self.ram_spin.value() * 1024
        self.parent.show_fabric = self.fabric_checkbox.isChecked()
        self.parent.show_forge = self.forge_checkbox.isChecked()
        self.parent.show_snapshots = self.snapshot_checkbox.isChecked()
        
        self.parent.user_label.setText(self.parent.username)
        
        self.parent.save_settings()
        
        self.parent.load_versions()
        
        self.accept()

class NovaLauncher(QMainWindow):
    def __init__(self):
        super().__init__()
        if getattr(sys, 'frozen', False):
            self._install_dir = os.path.dirname(sys.executable)
        else:
            self._install_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
        self.settings_file_path = os.path.join(self._install_dir, "nova_launcher_settings.json") 
        
        self.settings = self.load_settings()
        
        self.minecraft_directory = self.settings.get("minecraft_directory", DEFAULT_MINECRAFT_DIR)
        self.username = self.settings.get("username", "")
        self.selected_version = self.settings.get("last_used_version")
        self.ram_allocation = self.settings.get("ram_allocation", DEFAULT_SETTINGS["ram_allocation"])
        self.java_path = self.settings.get("java_path", DEFAULT_SETTINGS["java_path"])
        self.show_fabric = self.settings.get("show_fabric", DEFAULT_SETTINGS["show_fabric"])
        self.show_forge = self.settings.get("show_forge", DEFAULT_SETTINGS["show_forge"])
        self.show_snapshots = self.settings.get("show_snapshots", DEFAULT_SETTINGS["show_snapshots"])
        
        if not self.username:
            dialog = UserInfoDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                self.username = dialog.username
                self.save_settings()
            else:
                self.username = "Player"
        
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(800, 250)
        
        if os.path.exists(LOGO_PATH):
            self.setWindowIcon(QIcon(LOGO_PATH))
        
        self.setup_dark_theme()
        
        self.setup_ui()
        
        self.version_retries = 0
        self.max_retries = 5
        
        self.load_versions()
        
        if not os.path.exists(self.minecraft_directory):
            try:
                os.makedirs(self.minecraft_directory)
            except Exception as e:
                print(f"Could not create Minecraft directory: {str(e)}")
    
    def setup_dark_theme(self):
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
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 10, 20, 10)
        main_layout.setSpacing(8)
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        top_bar = QWidget()
        top_layout = QGridLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        top_bar.setLayout(top_layout)
        
        user_widget = QWidget()
        user_widget.setObjectName("userWidget")
        user_widget.setMaximumWidth(200)
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
        
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(26, 26)
        
        creeper_path = os.path.join(RESOURCES_DIR, "creeper.jpg")
        if os.path.exists(creeper_path):
            avatar_pixmap = QPixmap(creeper_path)
            self.avatar_label.setPixmap(avatar_pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
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
        
        self.user_label = QLabel(self.username)
        self.user_label.setStyleSheet("""
            color: #e0e0e0;
            font-size: 13px;
        """)
        
        user_layout.addWidget(self.avatar_label)
        user_layout.addWidget(self.user_label)
        top_layout.addWidget(user_widget, 0, 0, Qt.AlignLeft)
        
        self.header_label = QLabel()
        self.header_label.setAlignment(Qt.AlignCenter)
        header_path = os.path.join(RESOURCES_DIR, "header.png")
        if os.path.exists(header_path):
            header_pixmap = QPixmap(header_path)
            header_pixmap = header_pixmap.scaledToHeight(40, Qt.SmoothTransformation)
            self.header_label.setPixmap(header_pixmap)
        else:
            self.header_label.setText(APP_NAME)
            self.header_label.setObjectName("titleLabel")
            self.header_label.setFont(QFont("Segoe UI", 28, QFont.Bold))
        top_layout.addWidget(self.header_label, 0, 1, Qt.AlignCenter)
        
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
        
        top_layout.addWidget(settings_button, 0, 2, Qt.AlignRight)
        
        top_layout.setColumnStretch(0, 1)
        top_layout.setColumnStretch(1, 0)
        top_layout.setColumnStretch(2, 1)
        
        main_layout.addWidget(top_bar)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("background-color: #3d3d3d;")
        main_layout.addWidget(separator)
        
        version_group = QGroupBox("Minecraft Version")
        version_layout = QVBoxLayout()
        version_layout.setSpacing(6)
        version_group.setLayout(version_layout)
        
        self.version_combo = QComboBox()
        self.version_combo.setMinimumHeight(35)
        self.version_combo.setPlaceholderText("Select Minecraft version")
        version_layout.addWidget(QLabel("Select the Minecraft version you want to play:"))
        version_layout.addWidget(self.version_combo)
        
        main_layout.addWidget(version_group)
        
        self.play_button = QPushButton("PLAY")
        self.play_button.setObjectName("playButton")
        self.play_button.clicked.connect(self.play_minecraft)
        self.play_button.setMinimumHeight(50)
        self.play_button.setMinimumWidth(250)
        self.play_button.setFont(QFont("Segoe UI", 16, QFont.Bold))
        
        main_layout.addWidget(self.play_button, 0, Qt.AlignCenter)
        
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
        
        self.spinner_label = QLabel()
        self.spinner_label.setFixedSize(30, 30)
        self.spinner_label.setAlignment(Qt.AlignCenter)
        
        self.status_label = QLabel()
        self.status_label.setFont(QFont("Segoe UI", 8, QFont.Bold))
        self.status_label.setStyleSheet("color: #5ba042;")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        loading_layout.addWidget(self.spinner_label)
        loading_layout.addWidget(self.status_label, 1)
        
        self.loading_container.setLayout(loading_layout)
        self.loading_container.hide()
        
        main_layout.addWidget(self.loading_container, 0, Qt.AlignCenter)
        
        self.spinner_angle = 0
        self.spinner_timer = QTimer()
        self.spinner_timer.timeout.connect(self.update_spinner)
        
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        
        self.version_combo.currentIndexChanged.connect(self.update_selected_version)

    def open_settings(self):
        settings_dialog = SettingsDialog(self)
        settings_dialog.exec_()
    
    def load_versions(self):
        self.progress_label.setText("Loading versions...")
        self.version_thread = MinecraftVersionThread()
        self.version_thread.version_signal.connect(self.update_versions)
        self.version_thread.start()
    
    def update_versions(self, versions):
        current_selection = self.version_combo.currentText()
        self.version_combo.clear()
        
        if not versions:
            if self.version_retries < self.max_retries:
                self.version_retries += 1
                print(f"Retrying version load ({self.version_retries}/{self.max_retries})...")
                QTimer.singleShot(3000, self.load_versions)
            return
        
        self.version_retries = 0
        release_versions = []
        snapshot_versions = []
        processed_versions = []
        
        for version in versions:
            version_type = version.get("type")
            if version_type == "release":
                release_versions.append(version)
            elif version_type == "snapshot" and self.show_snapshots:
                snapshot_versions.append(version)
        
        release_versions.sort(key=lambda x: x.get("releaseTime", ""), reverse=True)
        snapshot_versions.sort(key=lambda x: x.get("releaseTime", ""), reverse=True)

        combined_versions = snapshot_versions + release_versions

        for version in combined_versions:
            vanilla_id = version.get("id")
            if not vanilla_id: continue
            
            display_name_prefix = "[S] " if version.get("type") == "snapshot" else ""

            processed_versions.append((f"{display_name_prefix}{vanilla_id}", vanilla_id, "vanilla"))

            if self.show_fabric and version.get("type") == "release": 
                fabric_display_name = f"Fabric {vanilla_id}"
                processed_versions.append((fabric_display_name, vanilla_id, "fabric"))

            if self.show_forge and version.get("type") == "release":
                try:
                    forge_version_str = forge.find_forge_version(vanilla_id)
                    if forge_version_str:
                        forge_display_name = f"Forge {vanilla_id}"
                        processed_versions.append((forge_display_name, vanilla_id, "forge", forge_version_str))
                except Exception as e:
                    pass

        for item_tuple in processed_versions:
            display_name = item_tuple[0]
            version_id_or_base_id = item_tuple[1]
            version_type = item_tuple[2]
            user_data = {"id": version_id_or_base_id, "type": version_type}
            if version_type == "forge" and len(item_tuple) > 3:
                user_data["forge_version"] = item_tuple[3]
            
            self.version_combo.addItem(display_name, userData=user_data)
        
        index = self.version_combo.findText(current_selection)
        if index >= 0:
            self.version_combo.setCurrentIndex(index)
        elif not self.selected_version and self.version_combo.count() > 0:
             self.version_combo.setCurrentIndex(0)
             self.update_selected_version(0)
        elif self.selected_version:
            found_index = -1
            for i in range(self.version_combo.count()):
                item_data = self.version_combo.itemData(i)
                stored_id_in_settings = self.settings.get("last_used_version")
                current_item_id = item_data.get("id")
                current_item_type = item_data.get("type")
                
                if stored_id_in_settings == current_item_id:
                     found_index = i
                     break
                elif stored_id_in_settings and (current_item_type == "fabric" or current_item_type == "forge"):
                     try:
                         base_from_saved = stored_id_in_settings.split('-')[-1]
                         if base_from_saved == current_item_id:
                             found_index = i
                             break
                     except:
                         pass

            if found_index >= 0:
                self.version_combo.setCurrentIndex(found_index)
            elif self.version_combo.count() > 0:
                 self.version_combo.setCurrentIndex(0)
                 self.update_selected_version(0)

    def update_selected_version(self, index):
        if index >= 0:
            item_data = self.version_combo.itemData(index)
            if item_data:
                self.selected_version = item_data.get("id")
                self.save_settings()
    
    def open_minecraft_directory(self):
        if not os.path.exists(self.minecraft_directory):
            QMessageBox.warning(self, "Warning", "Minecraft directory does not exist!")
            return
            
        try:
            if sys.platform == 'win32':
                os.startfile(self.minecraft_directory)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.minecraft_directory])
            else:
                subprocess.Popen(['xdg-open', self.minecraft_directory])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open directory: {str(e)}")
    
    def check_and_install_minecraft(self, version_data):
        if not version_data:
            return False

        version_id = version_data.get("id")
        version_type = version_data.get("type")
        display_name = self.version_combo.currentText()

        is_installed = False
        if version_type == "fabric":
            base_vanilla_id = version_id
            vanilla_version_dir = os.path.join(self.minecraft_directory, "versions", base_vanilla_id)
            vanilla_jar_file = os.path.join(vanilla_version_dir, f"{base_vanilla_id}.jar")
            
            if os.path.exists(vanilla_jar_file):
                fabric_pattern = os.path.join(self.minecraft_directory, "versions", f"fabric-loader*-{base_vanilla_id}")
                matching_fabric_dirs = glob.glob(fabric_pattern)
                is_installed = bool(matching_fabric_dirs)
            else:
                 is_installed = False

        elif version_type == "forge":
            base_vanilla_id = version_id
            vanilla_version_dir = os.path.join(self.minecraft_directory, "versions", base_vanilla_id)
            vanilla_jar_file = os.path.join(vanilla_version_dir, f"{base_vanilla_id}.jar")

            if os.path.exists(vanilla_jar_file):
                forge_pattern = os.path.join(self.minecraft_directory, "versions", f"*{base_vanilla_id}*forge*")
                matching_forge_dirs = glob.glob(forge_pattern)
                is_installed = bool(matching_forge_dirs)
            else:
                is_installed = False

        else:
            version_dir = os.path.join(self.minecraft_directory, "versions", version_id)
            jar_file = os.path.join(version_dir, f"{version_id}.jar")
            is_installed = os.path.exists(jar_file)
        
        if is_installed:
            return True
        
        reply = QMessageBox.question(
            self, 
            "Minecraft Installation",
            f"{display_name} is not installed. Do you want to install it now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.show_loading(is_launching=False, percentage=0)
            self.install_minecraft(version_data)
            return False
        else:
            return False
    
    def install_minecraft(self, version_data):
        if not version_data:
            QMessageBox.warning(self, "Warning", "Invalid version selected!")
            return
            
        version_id = version_data.get("id")
        version_type = version_data.get("type")
        display_name = self.version_combo.currentText()

        if not version_id or not version_type:
            QMessageBox.warning(self, "Warning", "Version information incomplete!")
            return
        
        self.play_button.setText(f"INSTALLING {display_name}...")
        self.play_button.setEnabled(False)
        self.play_button.setStyleSheet("""
            #playButton {
                background-color: #6c6c6c;
                color: white;
                border: none;
                font-weight: bold;
                font-size: 16px;
                text-align: center;
            }
        """)
        
        forge_version_string = version_data.get("forge_version")
        self.install_thread = MinecraftInstallThread(self.minecraft_directory, version_id, version_type, forge_version_string)
        self.install_thread.progress_signal.connect(self.update_progress)
        self.install_thread.complete_signal.connect(self.installation_complete)
        self.install_thread.start()
    
    def update_play_button_text(self):
        if not self.play_button.isEnabled():
            version = self.selected_version
            
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
        self.progress_label.setText(status)
        
        if self.loading_container.isVisible() and self.status_label.text().startswith("DOWNLOADING"):
            self.status_label.setText(f"DOWNLOADING {percentage}%")
            
            if percentage >= 100:
                QTimer.singleShot(2000, self.hide_loading)
    
    def installation_complete(self, success, message):
        self.progress_label.setText(message)
        
        if hasattr(self, 'play_spinner_timer') and self.play_spinner_timer.isActive():
            self.play_spinner_timer.stop()
        
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
        
        self.hide_loading()
        
        if success:
            self.show_loading(is_launching=True)
            self.launch_minecraft()
        else:
            QMessageBox.critical(self, "Installation Error", message)
    
    def show_loading(self, is_launching=True, percentage=0):
        self.play_button.hide()
        
        if is_launching:
            self.status_label.setText("LAUNCHING")
        else:
            self.status_label.setText(f"DOWNLOADING {percentage}%")
        
        self.loading_container.show()
        
        self.spinner_timer.start(50)
        
        if is_launching:
            QTimer.singleShot(10000, self.hide_loading)
    
    def hide_loading(self):
        self.spinner_timer.stop()
        
        self.loading_container.hide()
        
        self.play_button.show()

    def update_spinner(self):
        self.spinner_angle = (self.spinner_angle + 15) % 360
        
        spinner_pixmap = QPixmap(30, 30)
        spinner_pixmap.fill(Qt.transparent)
        
        painter = QPainter(spinner_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(80, 80, 80, 80))
        painter.drawEllipse(3, 3, 24, 24)
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(PRIMARY_COLOR))
        
        path = QPainterPath()
        path.moveTo(15, 15)
        path.arcTo(3, 3, 24, 24, self.spinner_angle, 120)
        path.lineTo(15, 15)
        painter.drawPath(path)
        
        painter.end()
        
        self.spinner_label.setPixmap(spinner_pixmap)

    def play_minecraft(self):
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
        
        self.save_settings()
        
        if self.check_and_install_minecraft(version_data):
            self.show_loading(is_launching=True)
            self.launch_minecraft()
    
    def launch_minecraft(self):
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

        version_id_to_launch = version_data.get("id")
        version_type = version_data.get("type")

        if version_type == "fabric":
            base_vanilla_id = version_id_to_launch
            try:
                installed_versions = mclib.utils.get_installed_versions(self.minecraft_directory)
                found_fabric_id = None
                pattern = f"fabric-loader-"
                for installed_ver in installed_versions:
                    ver_id = installed_ver.get("id")
                    if ver_id and ver_id.startswith(pattern) and ver_id.endswith(base_vanilla_id):
                        found_fabric_id = ver_id
                        break
                
                if not found_fabric_id:
                    QMessageBox.critical(self, "Launch Error", f"Could not find installed Fabric for {base_vanilla_id}. Please try installing it again.")
                    self.hide_loading()
                    return
                
                version_id_to_launch = found_fabric_id

            except Exception as e:
                 QMessageBox.critical(self, "Launch Error", f"Error finding installed Fabric version: {e}")
                 self.hide_loading()
                 return
        elif version_type == "forge":
            base_vanilla_id = version_id_to_launch
            try:
                installed_versions = mclib.utils.get_installed_versions(self.minecraft_directory)
                found_forge_id = None
                for installed_ver in installed_versions:
                    ver_id = installed_ver.get("id")
                    if ver_id and base_vanilla_id in ver_id and "forge" in ver_id.lower():
                        found_forge_id = ver_id
                        break 
                
                if not found_forge_id:
                    QMessageBox.critical(self, "Launch Error", f"Could not find installed Forge for {base_vanilla_id}. Please try installing it again.")
                    self.hide_loading()
                    return
                
                version_id_to_launch = found_forge_id

            except Exception as e:
                 QMessageBox.critical(self, "Launch Error", f"Error finding installed Forge version: {e}")
                 self.hide_loading()
                 return

        if not version_id_to_launch:
             QMessageBox.critical(self, "Launch Error", "Could not determine version to launch.")
             self.hide_loading()
             return

        self.launch_thread = MinecraftLauncherThread(
            self.minecraft_directory,
            version_id_to_launch,
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
        self.save_settings()
        super().closeEvent(event)

    def load_settings(self):
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
            if os.path.exists(self.settings_file_path):
                with open(self.settings_file_path, 'r') as f:
                    loaded_settings = json.load(f)
                    settings.update(loaded_settings)
        except Exception as e:
            pass
        
        return settings
    
    def save_settings(self):
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
            if not os.path.exists(self.minecraft_directory):
                os.makedirs(self.minecraft_directory)
            
            with open(self.settings_file_path, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            pass

def main():
    app = QApplication(sys.argv)
    launcher = NovaLauncher()
    launcher.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()