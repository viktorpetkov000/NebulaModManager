import os
import re
import json
import zipfile
import shutil
import subprocess
import urllib.request
import concurrent.futures
from collections import defaultdict

class ModEngine:
    def __init__(self, db):
        self.db = db

    def get_mod_path(self, game):
        return self.db.get_setting("stellaris_mod_path") if game == "Stellaris" else self.db.get_setting("hoi4_mod_path")

    def get_exe_path(self, game):
        return self.db.get_setting("stellaris_exe_path") if game == "Stellaris" else self.db.get_setting("hoi4_exe_path")

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
        name, version, content_relative_path = "Unknown Mod", "Any", ""
        try:
            with open(mod_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.strip().startswith('name='): name = line.split('=', 1)[1].strip().strip('\"')
                    elif line.strip().startswith('supported_version='): version = line.split('=', 1)[1].strip().strip('\"')
                    elif line.strip().startswith('path=') or line.strip().startswith('archive='): content_relative_path = line.split('=', 1)[1].strip().strip('\"')
            mod_content_path = os.path.join(game_base_dir, content_relative_path.replace('/', os.sep)) if content_relative_path else None
            return rel_path, {"name": name, "version": version, "file_path": mod_file_path, "content_path": mod_content_path}
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

    # --- MOD TOOLS ---
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
        for rel_path in mod_list:
            data = installed_data.get(rel_path)
            if not data or not data["content_path"] or not os.path.exists(data["content_path"]): continue
            content_path = data["content_path"]
            try:
                if os.path.isdir(content_path): shutil.copytree(content_path, merged_folder, dirs_exist_ok=True)
                elif zipfile.is_zipfile(content_path):
                    with zipfile.ZipFile(content_path, 'r') as z: z.extractall(merged_folder)
            except Exception as e: print(f"Error merging: {e}")

        mod_content = f'version="1.0"\ntags={{\n\t"MegaMod"\n}}\nname="{merged_name}"\nsupported_version="*"\npath="mod/{merged_name}"\n'
        with open(merged_mod_file, "w") as f: f.write(mod_content)

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

    def batch_download_mods(self, game, urls):
        """Downloads mods and tracks success/failure rates."""
        target_path = self.get_mod_path(game)
        os.makedirs(target_path, exist_ok=True)
        
        success_count = 0
        failed_urls = []
        
        for i, url in enumerate(urls):
            zip_path = os.path.join(target_path, f"temp_{i}.zip")
            try:
                urllib.request.urlretrieve(url, zip_path)
                with zipfile.ZipFile(zip_path, 'r') as z: 
                    z.extractall(target_path)
                os.remove(zip_path)
                success_count += 1
            except Exception as e:
                failed_urls.append(url)
                # Cleanup broken partial zip if the link failed halfway
                if os.path.exists(zip_path):
                    try: os.remove(zip_path)
                    except: pass
                    
        return success_count, failed_urls