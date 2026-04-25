# Nebula Mod Manager

A modern, lightning-fast, and advanced Mod Manager built with Python and CustomTkinter. Currently, Nebula is tailored for Paradox Interactive games (Stellaris, Hearts of Iron IV) to bypass the slow official launcher and give power-users total control over their playsets. However, its modular architecture is designed with the potential to easily expand support to other games and publishers in the future.

## ✨ Features

* **Advanced Load Order:** Physically drag and drop mods to define exact load orders.
* **Auto-Sorting Algorithm:** Automatically organizes your collection (Core overhauls at the top, UI in the middle, compatibility patches at the bottom).
* **Missing Dependencies Resolution:** Instantly identifies missing required dependencies and offers to copy them to clipboard or directly download them via SteamCMD.
* **Save Game Integration:** Reads your raw Paradox `.sav` files to detect and instantly rebuild the exact mod collection used in that playthrough.
* **The Conflict Detector:** Deep-scans every `.zip` and folder in your active collection to show you exactly which vanilla files are being overwritten by multiple mods simultaneously.
* **Mega-Mod Merger:** Merges a 50+ mod collection into a single, highly optimized "Mega-Mod" folder to drastically improve game boot times.
* **Smart Collection Cleanup:** One-click tools to purge deleted/orphaned mods and gracefully remove mods with broken dependencies from your load order.
* **Visual Load Order Feedback:** Dynamic UI highlighting for active mods and intuitive double-click bindings to rapidly build your playsets.
* **Lightning Fast:** Uses an SQLite database (with metadata caching) and a centralized asynchronous concurrent thread pool to parse hundreds of mods without dropping a frame.

## 🚀 Installation & Usage

### Option 1: Download the Executable (Easiest)
1. Go to the [Releases](../../releases) tab on the right side of this GitHub page.
2. Download the latest `NebulaModManager.exe`.
3. Place it anywhere on your PC and run it. No installation required.

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
* `mod_engine.py` - Concurrent file parsing, auto-repair logic, and file merging.
* `gui.py` - Modern, dark-themed UI powered by CustomTkinter.

## 🤝 Contributing
Contributions, issues, and feature requests are welcome! If you'd like to add support for a new game, feel free to fork the repository and submit a pull request.