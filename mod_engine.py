import os
import re
import json
import zipfile
import shutil
import subprocess
import urllib.request
import concurrent.futures
from collections import defaultdict
from database import GAMES_MAP

class ModEngine:
    def __init__(self, db):
        self.db = db

    def get_mod_path(self, game):
        game_id = GAMES_MAP.get(game, {}).get("id", "")
        return self.db.get_setting(f"{game_id}_mod_path")

    def get_exe_path(self, game):
        game_id = GAMES_MAP.get(game, {}).get("id", "")
        return self.db.get_setting(f"{game_id}_exe_path")

    def get_game_version(self, game):
        """Scans the game's directory to determine the exact version installed."""
        exe_path = self.get_exe_path(game)
        if not exe_path or not os.path.exists(exe_path): return None
        
        base_dir = os.path.dirname(exe_path)
        settings_path = os.path.join(base_dir, "launcher-settings.json")
        
        # Some games (like CK3) keep the exe in a /binaries/ folder, so we check one level up
        if not os.path.exists(settings_path):
            settings_path = os.path.join(os.path.dirname(base_dir), "launcher-settings.json")
            
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get("version")
            except Exception: pass
        return None

    # --- AUTO-REPAIR ---
    def auto_generate_root_mods(self, target_path):
        if not os.path.exists(target_path): return
        for item in os.listdir(target_path):
            item_path = os.path.join(target_path, item)
            if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "descriptor.mod")):
                root_mod = os.path.join(target_path, f"{item}.mod")
                if not os.path.exists(root_mod):
                    try:
                        with open(os.path.join(item_path, "descriptor.mod"), 'r', encoding='utf-8', errors='ignore') as src: lines = src.readlines()
                        new_lines, has_path = [], False
                        for line in lines:
                            if line.strip().startswith('archive='): continue
                            elif line.strip().startswith('path='):
                                new_lines.append(f'path="mod/{item}"\n')
                                has_path = True
                            else: new_lines.append(line)
                        if not has_path: new_lines.append(f'path="mod/{item}"\n')
                        with open(root_mod, 'w', encoding='utf-8') as dst: dst.writelines(new_lines)
                    except Exception: pass

    def repair_mod_paths(self, target_path):
        if not os.path.exists(target_path): return
        game_base_dir = os.path.dirname(target_path)
        for file in os.listdir(target_path):
            if file.endswith(".mod"):
                mod_file = os.path.join(target_path, file)
                try:
                    with open(mod_file, 'r', encoding='utf-8', errors='ignore') as f: lines = f.readlines()
                    current_path = next((line.split('=', 1)[1].strip().strip('\"') for line in lines if line.strip().startswith('path=') or line.strip().startswith('archive=')), None)
                    needs_repair = not (current_path and os.path.exists(os.path.join(game_base_dir, current_path.replace('/', os.sep))))
                    if needs_repair:
                        base_name = file[:-4]
                        expected_line = None
                        if os.path.isdir(os.path.join(target_path, base_name)): expected_line = f'path="mod/{base_name}"\n'
                        elif base_name.startswith("ugc_") and os.path.isdir(os.path.join(target_path, base_name[4:])): expected_line = f'path="mod/{base_name[4:]}"\n'
                        if expected_line:
                            new_lines, has_path = [], False
                            for line in lines:
                                if line.strip().startswith('path=') or line.strip().startswith('archive='):
                                    new_lines.append(expected_line)
                                    has_path = True
                                else: new_lines.append(line)
                            if not has_path: new_lines.append(expected_line)
                            with open(mod_file, 'w', encoding='utf-8') as f: f.writelines(new_lines)
                except Exception: pass

    # --- PARSING & SCANNING ---
    def parse_mod_file(self, mod_file_path, rel_path, game_base_dir):
        name, version, content_relative_path, dependencies = "Unknown Mod", "Any", "", []
        try:
            with open(mod_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
                # Extract basic data
                for line in content.split('\n'):
                    if line.strip().startswith('name='): name = line.split('=', 1)[1].strip().strip('\"')
                    elif line.strip().startswith('supported_version='): version = line.split('=', 1)[1].strip().strip('\"')
                    elif line.strip().startswith('path=') or line.strip().startswith('archive='): content_relative_path = line.split('=', 1)[1].strip().strip('\"')
                
                # Extract dependencies robustly
                dep_match = re.search(r'dependencies\s*=\s*\{\s*([^}]+)\s*\}', content)
                if dep_match:
                    dependencies = re.findall(r'"([^"]*)"', dep_match.group(1))

            mod_content_path = os.path.join(game_base_dir, content_relative_path.replace('/', os.sep)) if content_relative_path else None
            return rel_path, {"name": name, "version": version, "file_path": mod_file_path, "content_path": mod_content_path, "dependencies": dependencies}
        except Exception: return rel_path, None

    def scan_installed_mods(self, game):
        target_path = self.get_mod_path(game)
        if not os.path.exists(target_path): return {}
        
        self.auto_generate_root_mods(target_path)
        self.repair_mod_paths(target_path)
        
        game_base_dir = os.path.dirname(target_path)
        mod_files = [(os.path.join(target_path, f), f"mod/{f}", game_base_dir) for f in os.listdir(target_path) if f.endswith(".mod")]
        
        installed_data = {}
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [executor.submit(self.parse_mod_file, *args) for args in mod_files]
            for future in concurrent.futures.as_completed(futures):
                rel_path, data = future.result()
                if data: installed_data[rel_path] = data
        return installed_data

    # --- GAME LAUNCH ---
    def apply_collection(self, game, coll_name):
        mod_paths = self.db.get_collection_mods(game, coll_name)
        target_path = self.get_mod_path(game)
        dlc_load_path = os.path.join(os.path.dirname(target_path), "dlc_load.json")
        try:
            with open(dlc_load_path, 'w') as f: json.dump({"disabled_dlcs": [], "enabled_mods": mod_paths}, f, indent=4)
        except Exception as e: print(f"Failed to apply mods: {e}")

    def launch_game(self, game, coll_name):
        self.apply_collection(game, coll_name)
        exe_path = self.get_exe_path(game)
        if os.path.exists(exe_path) and exe_path.endswith(".exe"): subprocess.Popen([exe_path])
        else: raise Exception("Game executable not found.")

    # --- MOD TOOLS (WITH SMART MERGE) ---
    def find_conflicts(self, active_mods_data):
        file_map = defaultdict(list)
        for data in active_mods_data:
            if not data or not data["content_path"] or not os.path.exists(data["content_path"]): continue
            mod_name, content_path = data["name"], data["content_path"]
            
            if os.path.isdir(content_path):
                for root_dir, _, files in os.walk(content_path):
                    for file in files:
                        if file in ["descriptor.mod", "thumbnail.png"]: continue
                        internal_path = os.path.relpath(os.path.join(root_dir, file), content_path).replace("\\", "/")
                        file_map[internal_path].append(mod_name)
            elif zipfile.is_zipfile(content_path):
                try:
                    with zipfile.ZipFile(content_path, 'r') as z:
                        for internal_path in z.namelist():
                            if not internal_path.endswith('/') and internal_path not in ["descriptor.mod", "thumbnail.png"]: file_map[internal_path].append(mod_name)
                except Exception: pass
        return {k: v for k, v in file_map.items() if len(v) > 1}

    def clean_junk(self, game):
        target_path = self.get_mod_path(game)
        if not os.path.exists(target_path): return 0
        orphans = 0
        for file in os.listdir(target_path):
            if file.endswith(".mod"):
                mod_file = os.path.join(target_path, file)
                content_path = None
                try:
                    with open(mod_file, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if line.strip().startswith('path=') or line.strip().startswith('archive='):
                                rel_path = line.split('=', 1)[1].strip().strip('\"').replace('/', os.sep)
                                content_path = os.path.join(os.path.dirname(target_path), rel_path)
                except Exception: continue
                if content_path and not os.path.exists(content_path):
                    os.remove(mod_file)
                    orphans += 1
        return orphans

    def merge_mega_mod(self, game, coll_name, merged_name, installed_data):
        mod_list = self.db.get_collection_mods(game, coll_name)
        target_path = self.get_mod_path(game)
        merged_folder = os.path.join(target_path, merged_name)
        merged_mod_file = os.path.join(target_path, f"{merged_name}.mod")

        if os.path.exists(merged_folder): raise Exception(f"A mod folder named '{merged_name}' already exists.")

        os.makedirs(merged_folder, exist_ok=True)
        temp_dir = os.path.join(target_path, f"{merged_name}_temp")
        
        try:
            for rel_path in mod_list:
                data = installed_data.get(rel_path)
                if not data or not data["content_path"] or not os.path.exists(data["content_path"]): continue
                
                content_path = data["content_path"]
                mod_name = data["name"]
                
                if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
                os.makedirs(temp_dir, exist_ok=True)
                
                try:
                    if os.path.isdir(content_path): shutil.copytree(content_path, temp_dir, dirs_exist_ok=True)
                    elif zipfile.is_zipfile(content_path):
                        with zipfile.ZipFile(content_path, 'r') as z: z.extractall(temp_dir)
                    
                    for root_dir, _, files in os.walk(temp_dir):
                        for file in files:
                            if file in ["descriptor.mod", "thumbnail.png"]: continue
                            
                            src_file = os.path.join(root_dir, file)
                            rel_file = os.path.relpath(src_file, temp_dir)
                            dst_file = os.path.join(merged_folder, rel_file)
                            
                            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                            
                            # THE HOLY GRAIL: Smart Text Merging Algorithm
                            if os.path.exists(dst_file) and file.endswith(('.txt', '.yml', '.gui', '.csv')):
                                with open(dst_file, 'a', encoding='utf-8', errors='ignore') as df:
                                    df.write(f"\n\n# --- NEBULA SMART MERGE: Appended from {mod_name} ---\n")
                                    with open(src_file, 'r', encoding='utf-8', errors='ignore') as sf:
                                        df.write(sf.read())
                            else:
                                shutil.copy2(src_file, dst_file)
                except Exception as e: print(f"Error merging {mod_name}: {e}")
                
            mod_content = f'version="1.0"\ntags={{\n\t"MegaMod"\n}}\nname="{merged_name}"\nsupported_version="*"\npath="mod/{merged_name}"\n'
            with open(merged_mod_file, "w") as f: f.write(mod_content)
        finally:
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

    # --- IMPORT / EXPORT / DOWNLOAD ---
    def export_collection_zip(self, game, coll_name, installed_data, save_path):
        mod_list = self.db.get_collection_mods(game, coll_name)
        with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for rel_path in mod_list:
                data = installed_data.get(rel_path)
                if not data: continue
                if os.path.exists(data["file_path"]): zipf.write(data["file_path"], os.path.basename(data["file_path"]))
                content_path = data["content_path"]
                if content_path and os.path.exists(content_path):
                    if os.path.isdir(content_path):
                        for root, _, files in os.walk(content_path):
                            for file in files:
                                abs_file = os.path.join(root, file)
                                zipf.write(abs_file, os.path.relpath(abs_file, os.path.dirname(content_path)))
                    else: zipf.write(content_path, os.path.basename(content_path))

    def import_collection_zip(self, game, zip_path):
        target_path = self.get_mod_path(game)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_path)
            return [f"mod/{name}" for name in zip_ref.namelist() if name.endswith(".mod") and "/" not in name]

    def backup_saves_zip(self, game, save_path):
        """Finds the save games folder for the current game and archives it."""
        target_path = self.get_mod_path(game)
        save_dir = os.path.join(os.path.dirname(target_path), "save games")
        if not os.path.exists(save_dir):
            raise Exception("Save games folder not found.")
            
        with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(save_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, save_dir)
                    zipf.write(abs_path, rel_path)

    def batch_download_mods(self, game, urls):
        target_path = self.get_mod_path(game)
        os.makedirs(target_path, exist_ok=True)
        success_count = 0
        failed_urls = []
        
        for i, url in enumerate(urls):
            zip_path = os.path.join(target_path, f"temp_{i}.zip")
            try:
                urllib.request.urlretrieve(url, zip_path)
                with zipfile.ZipFile(zip_path, 'r') as z: z.extractall(target_path)
                os.remove(zip_path)
                success_count += 1
            except Exception as e:
                failed_urls.append(url)
                if os.path.exists(zip_path):
                    try: os.remove(zip_path)
                    except: pass
        return success_count, failed_urls