#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Builds the Nova Launcher application using PyInstaller and then compiles
the Inno Setup installer script.

Requirements:
- PyInstaller must be installed (`pip install pyinstaller`).
- Inno Setup 6 must be installed (https://jrsoftware.org/isinfo.php).
  The script attempts to find ISCC.exe in default locations or PATH.
- A valid `nova_launcher.spec` file must exist in the same directory.
- A valid `novalauncher_setup.iss` file must exist in the same directory.
"""

import subprocess
import os
import sys
import shutil

SPEC_FILE = "nova_launcher.spec"
ISS_FILE = "novalauncher_setup.iss"

INNO_SETUP_PATHS = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe"
]

def find_iscc():
    for path in INNO_SETUP_PATHS:
        if os.path.exists(path):
            return path

    if shutil.which("iscc"):
        return "iscc"

    return None

def run_command(command_list, step_name="Command"):
    try:
        process = subprocess.run(command_list, check=True, capture_output=True, text=True, encoding='utf-8')
        if process.stderr:
            pass
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        return False
    except Exception:
        return False

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    if not os.path.exists(SPEC_FILE):
        sys.exit(1)
    if not os.path.exists(ISS_FILE):
        sys.exit(1)

    iscc_exe = find_iscc()
    if not iscc_exe:
        sys.exit(1)

    pyinstaller_command = ["pyinstaller", SPEC_FILE, "--clean"]
    if not run_command(pyinstaller_command, "PyInstaller Build"):
        sys.exit(1)

    inno_setup_command = [iscc_exe, ISS_FILE]
    if not run_command(inno_setup_command, "Inno Setup Compilation"):
        sys.exit(1)

if __name__ == "__main__":
    main()