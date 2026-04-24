# Nebula Mod Manager 🌌

A modern, lightning-fast, and advanced Mod Manager built with Python and CustomTkinter. Tailored for Paradox Interactive games (Stellaris, Hearts of Iron IV) to bypass the slow official launcher and give power-users total control over their playsets, complete with **full in-app Steam Workshop integration**.

## ✨ Features

### 🌐 Workshop & Sharing
* **In-App Steam Workshop Browser:** Search, filter (Trending, Top Rated, Most Recent, Custom Dates), and download mods directly inside Nebula without ever opening your browser.
* **Load Order "Share Codes":** Instantly compress your entire active load order into a short, encrypted string (e.g., `NEB-eJzz...`). Paste a friend's code into Nebula to instantly rebuild their playset and auto-queue any missing mods for download!
* **Auto-Dependency Resolver:** Nebula cross-references your load order and alerts you if required mods are missing. Click a single button to automatically find and queue them from the Steam Workshop.
* **Smart Mod Updating:** Cross-references your installed mods with Steam to detect updates. When updating, Nebula intelligently deletes the old version to save space and automatically swaps the new version into *all* of your saved collections.
* **Direct Links & Local Installs:** Paste direct Steam Workshop URLs or `.zip` links for bulk downloading, or natively install mods directly from local `.zip` archives and folders on your PC.

### 🛠️ Advanced Mod Tools
* **Advanced Load Order:** Physically drag and drop mods to define exact load orders.
* **Auto-Sorting Algorithm:** Automatically organizes your collection based on smart heuristics (Core overhauls at the top, UI in the middle, compatibility patches at the bottom).
* **Save Game Integration:** Reads your raw Paradox `.sav` files to detect and instantly rebuild the exact mod collection used in that specific playthrough.
* **The Conflict Detector:** Deep-scans every `.zip` and folder in your active collection to show you exactly which vanilla files are being overwritten by multiple mods simultaneously.
* **Mega-Mod Merger:** Merges a 50+ mod collection into a single, highly optimized "Mega-Mod" folder to drastically improve game boot times.
* **Orphan File Cleanup:** One-click junk removal for broken or orphaned `.mod` files.

### ⚡ Performance
* **Lightning Fast Engine:** Uses a local SQLite database and asynchronous concurrent thread pooling to parse and load hundreds of mods instantly.
* **Steam API Caching:** Built-in localized JSON caching for the Steam API ensures large mod setups load instantly on startup without rate-limiting your connection to Steam's servers.

## 🚀 Installation & Usage

### Option 1: Download the Executable (Easiest)
1. Go to the [Releases](../../releases) tab on the right side of this GitHub page.
2. Download the latest `NebulaModManager.exe`.
3. Place it anywhere on your PC and run it. No installation is required!

### Option 2: Run from Source
If you want to run the raw Python code or modify the manager:

1. Clone this repository:
   ```bash
   git clone [https://github.com/viktorpetkov000/NebulaModManager.git](https://github.com/viktorpetkov000/NebulaModManager.git)
   ```
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```

## 🛠️ Architecture
This project uses a clean **MVC (Model-View-Controller)** architecture to ensure easy maintenance, modularity, and community contributions:
* `main.py` - Application entry point.
* `database.py` - Local SQLite storage for instant load times and configuration saving.
* `mod_engine.py` - Concurrent file parsing, auto-repair logic, Steam API, and file merging.
* `gui.py` - Modern, dark-themed UI powered by CustomTkinter.

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! If you'd like to add support for a new game, feel free to fork the repository and submit a pull request.
