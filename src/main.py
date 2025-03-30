import sys
import os
import json
import requests
import minecraft_launcher_lib as mclib
import subprocess
import uuid
import hashlib
import time
import base64
import math
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QLabel, QPushButton, QComboBox, QProgressBar, 
                           QMessageBox, QFileDialog, QGroupBox, QHBoxLayout,
                           QDialog, QSpinBox, QSlider, QTabWidget, QInputDialog,
                           QFrame, QLineEdit)
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
    
    def __init__(self, minecraft_dir, version):
        super().__init__()
        self.minecraft_directory = minecraft_dir
        self.version = version
        
    def callback(self, value, max_value, status):
        """Callback for download progress"""
        if max_value > 0:
            percentage = int((value / max_value) * 100)
        else:
            percentage = 0
        self.progress_signal.emit(percentage, status)
        
    def run(self):
        """Install Minecraft version"""
        try:
            if not os.path.exists(self.minecraft_directory):
                os.makedirs(self.minecraft_directory)
                
            mclib.install.install_minecraft_version(
                self.version, 
                self.minecraft_directory, 
                callback=self.callback
            )
            
            self.complete_signal.emit(True, f"Minecraft {self.version} installed successfully.")
        except Exception as e:
            error_message = f"Error installing Minecraft: {str(e)}"
            print(error_message)
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
        
        # Add widgets to general tab
        general_layout.addWidget(dir_widget)
        general_layout.addWidget(username_widget)
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
        
        java_layout_row.addWidget(java_label)
        java_layout_row.addWidget(self.java_path_label, 1)
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
    
    def save_settings(self):
        # Update parent settings
        self.parent.minecraft_directory = self.directory_label.text()
        self.parent.username = self.username_combo.currentText()
        self.parent.java_path = self.java_path_label.text()
        self.parent.ram_allocation = self.ram_spin.value() * 1024
        
        # Update UI elements in the main window
        self.parent.user_label.setText(self.parent.username)
        
        # Save settings to file
        self.parent.save_settings()
        
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
        self.ram_allocation = self.settings.get("ram_allocation", 2048)
        self.java_path = self.settings.get("java_path", "")  # Java path setting
        
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
        
        # Avatar çizimi
        avatar_pixmap = QPixmap(26, 26)
        avatar_pixmap.fill(Qt.transparent)
        
        painter = QPainter(avatar_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Yeşil daire
        painter.setBrush(QColor(PRIMARY_COLOR))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, 26, 26)
        
        # Kullanıcı silüeti
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        
        # Baş
        painter.drawEllipse(9, 4, 8, 8)
        
        # Gövde
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
        
        # -- Nova Launcher başlık (orta) --
        title_label = QLabel(APP_NAME)
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Segoe UI", 28, QFont.Bold))
        
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
        top_layout.addWidget(title_label)
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
        
        for version in versions:
            if version.get("type") == "release":
                release_versions.append(version)
        
        # En son sürüm en başta olacak şekilde sırala
        release_versions.sort(key=lambda x: x.get("releaseTime", ""), reverse=True)
        
        for version in release_versions:
            self.version_combo.addItem(version.get("id"))
        
        # İlk sürümü (en son sürümü) seç, eğer daha önce seçilmiş bir sürüm yoksa
        if not self.selected_version and self.version_combo.count() > 0:
            self.selected_version = self.version_combo.itemText(0)
            self.version_combo.setCurrentIndex(0)
        # Eğer daha önce seçilmiş bir sürüm varsa, onu seç
        elif self.selected_version:
            index = self.version_combo.findText(self.selected_version)
            if index >= 0:
                self.version_combo.setCurrentIndex(index)

    def update_selected_version(self, index):
        if index >= 0:
            self.selected_version = self.version_combo.currentText()
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
    
    def check_and_install_minecraft(self, version):
        """Check if version is installed and install if needed"""
        version_dir = os.path.join(self.minecraft_directory, "versions", version)
        jar_file = os.path.join(version_dir, f"{version}.jar")
        
        if os.path.exists(jar_file):
            return True  # Already installed
        
        # Need to install
        reply = QMessageBox.question(
            self, 
            "Minecraft Installation",
            f"Minecraft {version} is not installed. Do you want to install it now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.show_loading(is_launching=False, percentage=0)  # DOWNLOADING %0 göster
            self.install_minecraft(version)
            return False  # Installation in progress
        else:
            return False  # User declined installation
    
    def install_minecraft(self, version=None):
        if not version:
            version = self.selected_version
            
        if not version:
            QMessageBox.warning(self, "Warning", "Please select a Minecraft version!")
            return
        
        # Buton içeriği için basit metin ve spinner
        self.play_button.setText("")  # Metni temizle
        self.play_button.setEnabled(False)
        
        # QHBoxLayout kullanımını kaldırıp, doğrudan buton içine metin yazmayı kullanacağız
        install_label = QLabel(f"INSTALLING {version}")
        install_label.setAlignment(Qt.AlignCenter)
        install_label.setStyleSheet("""
            color: white;
            font-weight: bold;
            font-size: 16px;
        """)
        
        # Basit bir şekilde metni ayarla, spinner kullanmadan
        self.play_button.setText(f"INSTALLING {version}")
        
        # Spinner animasyonu için timer
        self.play_spinner_angle = 0
        self.play_spinner_timer = QTimer()
        self.play_spinner_timer.timeout.connect(self.update_play_button_text)
        self.play_spinner_timer.start(300)
        
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
        
        # Installation process
        self.progress_label.setText("Installing Minecraft...")
        
        self.install_thread = MinecraftInstallThread(self.minecraft_directory, version)
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
        if not self.selected_version:
            QMessageBox.warning(self, "Warning", "Please select a Minecraft version!")
            return
        
        if not self.username:
            QMessageBox.warning(self, "Warning", "Please enter your username!")
            return
        
        # Ayarları kaydet
        self.save_settings()
        
        # Sürüm kurulu değilse kur
        if self.check_and_install_minecraft(self.selected_version):
            # Kuruluysa doğrudan başlat
            self.show_loading(is_launching=True)  # LAUNCHING göster
            self.launch_minecraft()
    
    def launch_minecraft(self):
        """Launch Minecraft with current settings"""
        # username = self.username_combo.currentText()  # Bu satırı kaldır
        
        # Launch Minecraft
        self.launch_thread = MinecraftLauncherThread(
            self.minecraft_directory,
            self.selected_version,
            self.username,  # Doğrudan self.username kullan
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
            "ram_allocation": 2048,
            "java_path": ""
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
            "java_path": self.java_path
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