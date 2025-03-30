#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Nova Launcher - Minecraft Launcher
Basit ve kullanışlı Minecraft başlatıcısı
"""

import sys
import os

# Çalıştırılabilir dosya dizinini PATH'e ekle
if getattr(sys, 'frozen', False):
    # PyInstaller ile paketlenmiş durumda
    application_path = os.path.dirname(sys.executable)
    sys.path.insert(0, application_path)

# src.main modülünden main fonksiyonunu içe aktar
from src.main import main

if __name__ == "__main__":
    main() 