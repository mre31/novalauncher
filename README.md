# Nova Launcher

A simple and user-friendly Minecraft launcher built with Python and PyQt5.

## Features

- Select and start playing any version you want.
- Support for **Fabric** and **Forge** mod loaders (installs latest compatible version).

## Installation

1. Download the `NovaLauncherSetup.exe` file from the latest [Releases](https://github.com/mre31/novalauncher/releases) page.
2. Run the `NovaLauncherSetup.exe` installer.
3. Follow the on-screen instructions:
    - A desktop shortcut can be created (optional, enabled by default).
    - **Clean Install (Optional):** You can choose to perform a clean install, which will **delete your existing `.minecraft` folder** (`%APPDATA%\.minecraft`). **Use this option with extreme caution, as it will delete all your worlds, mods, resource packs, and settings within that folder.** This option is disabled by default.
4. The launcher will be installed to `%APPDATA%\.novalauncher`.
5. Launch the application from the desktop shortcut (if created) or by finding it in your user's AppData\Roaming\.novalauncher directory.

## Requirements

- Windows 10 or later.
- [Java Runtime Environment (JRE) 8 or later](https://www.java.com/en/download/) installed and accessible in the system PATH, or a specific Java executable path set in the launcher settings.
- Internet connection (for downloading Minecraft versions, libraries, Fabric, Forge).

## Usage

- The first time you launch, you might be prompted for a username.
- Select the desired Minecraft version (Vanilla, Fabric, or Forge) from the dropdown menu.
- Use the Settings (⚙️ icon) to:
  - Change your username.
  - Select the `.minecraft` directory (defaults to `%APPDATA%\.minecraft`).
  - Configure Java path and RAM allocation.
  - Toggle the visibility of Fabric, Forge, and Snapshot versions in the list.
- Click "PLAY". If the selected version (or its dependencies like Vanilla base, Fabric/Forge) is not installed, you will be prompted to install it.

## Settings File Location

User settings (username, paths, version visibility, etc.) are stored in:
`%APPDATA%\.novalauncher\nova_launcher_settings.json`

## Building from Source (Development)

1. Clone the repository: `git clone https://github.com/mre31/novalauncher.git`
2. Navigate to the project directory: `cd novalauncher`
3. Install requirements: `pip install -r requirements.txt`
4. Run to build: `pyinstaller nova_launcher.spec --clean`
5. Create an Installer using novalauncher_setup.iss.
