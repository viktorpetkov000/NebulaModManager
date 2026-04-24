import os
import re
import json
import zipfile
import shutil
import subprocess
import urllib.request
import urllib.parse
import concurrent.futures
import datetime
from collections import defaultdict
from database import GAMES_MAP, USER_HOME

class ModEngine:
    def __init__(self, db):
        self.db = db
        self.active_processes = {}
        self.cancel_flags = set()

    def get_mod_path(self, game):
        game_id = GAMES_MAP.get(game, {}).get("id", "")
        return self.db.get_setting(f"{game_id}_mod_path")

    def get_exe_path(self, game):
        game_id = GAMES_MAP.get(game, {}).get("id", "")
        return self.db.get_setting(f"{game_id}_exe_path")

    def get_game_version(self, game):
        exe_path = self.get_exe_path(game)
        if not exe_path or not os.path.exists(exe_path): return None
        base_dir = os.path.dirname(exe_path)
        settings_path = os.path.join(base_dir, "launcher-settings.json")
        if not os.path.exists(settings_path):
            settings_path = os.path.join(os.path.dirname(base_dir), "launcher-settings.json")
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get("version")
            except Exception: pass
        return None

    # --- AUTO-REPAIR & SCANNING ---
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

    def parse_mod_file(self, mod_file_path, rel_path, game_base_dir):
        name, version, content_relative_path, dependencies, remote_id = "Unknown Mod", "Any", "", [], None
        try:
            with open(mod_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                for line in content.split('\n'):
                    if line.strip().startswith('name='): name = line.split('=', 1)[1].strip().strip('\"')
                    elif line.strip().startswith('supported_version='): version = line.split('=', 1)[1].strip().strip('\"')
                    elif line.strip().startswith('path=') or line.strip().startswith('archive='): content_relative_path = line.split('=', 1)[1].strip().strip('\"')
                    elif line.strip().startswith('remote_file_id='): remote_id = line.split('=', 1)[1].strip().strip('\"')
                
                dep_match = re.search(r'dependencies\s*=\s*\{\s*([^}]+)\s*\}', content)
                if dep_match: dependencies = re.findall(r'"([^"]*)"', dep_match.group(1))

            mod_content_path = os.path.join(game_base_dir, content_relative_path.replace('/', os.sep)) if content_relative_path else None
            return rel_path, {"name": name, "version": version, "file_path": mod_file_path, "content_path": mod_content_path, "dependencies": dependencies, "remote_id": remote_id}
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

    # --- GAME LAUNCH & MOD TOOLS ---
    def launch_game(self, game, coll_name):
        mod_paths = self.db.get_collection_mods(game, coll_name)
        target_path = self.get_mod_path(game)
        dlc_load_path = os.path.join(os.path.dirname(target_path), "dlc_load.json")
        try:
            with open(dlc_load_path, 'w') as f: json.dump({"disabled_dlcs": [], "enabled_mods": mod_paths}, f, indent=4)
        except Exception as e: print(f"Failed to apply mods: {e}")
        
        exe_path = self.get_exe_path(game)
        if os.path.exists(exe_path) and exe_path.endswith(".exe"): subprocess.Popen([exe_path])
        else: raise Exception("Game executable not found.")

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
                            
                            if os.path.exists(dst_file) and file.endswith(('.txt', '.yml', '.gui', '.csv')):
                                with open(dst_file, 'a', encoding='utf-8', errors='ignore') as df:
                                    df.write(f"\n\n# --- NEBULA SMART MERGE: Appended from {mod_name} ---\n")
                                    with open(src_file, 'r', encoding='utf-8', errors='ignore') as sf: df.write(sf.read())
                            else: shutil.copy2(src_file, dst_file)
                except Exception as e: print(f"Error merging {mod_name}: {e}")
                
            mod_content = f'version="1.0"\ntags={{\n\t"MegaMod"\n}}\nname="{merged_name}"\nsupported_version="*"\npath="mod/{merged_name}"\n'
            with open(merged_mod_file, "w") as f: f.write(mod_content)
        finally:
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

    def backup_saves_zip(self, game, save_path):
        target_path = self.get_mod_path(game)
        save_dir = os.path.join(os.path.dirname(target_path), "save games")
        if not os.path.exists(save_dir): raise Exception("Save games folder not found.")
            
        with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(save_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, save_dir)
                    zipf.write(abs_path, rel_path)

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

    # --- STEAM API WITH CACHING ---
    def fetch_api_details(self, wids, cache_hours=4.0):
        """Fetches metadata with an integrated local JSON caching layer."""
        if not wids: return {}
        
        cache = {}
        cache_file = os.path.join(USER_HOME, ".nebula_mod_manager", "api_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cache = json.load(f)
            except: pass

        now = datetime.datetime.now().timestamp()
        results = {}
        missing_wids = []
        
        for wid in wids:
            wid_str = str(wid)
            if cache_hours > 0 and wid_str in cache:
                cached_time = cache[wid_str].get('_cache_timestamp', 0)
                if now - cached_time < cache_hours * 3600:
                    results[wid_str] = cache[wid_str]
                    continue
            missing_wids.append(wid_str)
            
        if missing_wids:
            for i in range(0, len(missing_wids), 100):
                chunk = missing_wids[i:i+100]
                url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
                data = {"itemcount": len(chunk)}
                for idx, cw in enumerate(chunk):
                    data[f"publishedfileids[{idx}]"] = cw
                    
                encoded_data = urllib.parse.urlencode(data).encode('utf-8')
                try:
                    req = urllib.request.Request(url, data=encoded_data)
                    with urllib.request.urlopen(req) as resp:
                        resp_data = json.loads(resp.read().decode('utf-8'))
                        for item in resp_data.get('response', {}).get('publishedfiledetails', []):
                            if item.get('result') == 1:
                                wid_str = str(item['publishedfileid'])
                                item['_cache_timestamp'] = now
                                results[wid_str] = item
                                cache[wid_str] = item
                except Exception as e:
                    print(f"Steam API Error: {e}")
            
            try:
                os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                with open(cache_file, 'w') as f:
                    json.dump(cache, f)
            except: pass
            
        return results

    def check_mod_updates(self, installed_data, cache_hours=4.0):
        wids_to_rel = {}
        for rel_path, data in installed_data.items():
            wid = data.get("remote_id")
            if wid: wids_to_rel[str(wid)] = rel_path
            
        if not wids_to_rel: return {}
        
        api_data = self.fetch_api_details(list(wids_to_rel.keys()), cache_hours=cache_hours)
        updates_found = {}
        
        for wid_str, details in api_data.items():
            rel_path = wids_to_rel.get(wid_str)
            if not rel_path: continue 
                
            local_data = installed_data[rel_path]
            content_path = local_data.get("content_path")
            
            remote_time = details.get("time_updated", 0)
            needs_update = False
            
            if content_path and os.path.exists(content_path):
                meta_path = os.path.join(content_path, "nebula_update.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r') as f:
                            local_time = json.load(f).get("time_updated", 0)
                            if remote_time > local_time:
                                needs_update = True
                    except: needs_update = True
                else:
                    mtime = os.path.getmtime(content_path)
                    if remote_time > mtime + 86400: 
                        needs_update = True
                        
            if needs_update:
                updates_found[rel_path] = {"wid": wid_str, "title": details.get("title", local_data["name"])}
                
        return updates_found

    def search_steam_workshop(self, game, search_text="", page=1, sort="trend", days="all"):
        game_data = GAMES_MAP.get(game)
        if not game_data or "app_id" not in game_data: return []
        app_id = game_data["app_id"]
        
        url = f"https://steamcommunity.com/workshop/browse/?appid={app_id}&searchtext={urllib.parse.quote(search_text)}&browsesort={sort}&section=readytouseitems&p={page}&days={days}"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req) as response:
                html_data = response.read().decode('utf-8', errors='ignore')
                
            wids = []
            for match in re.finditer(r'filedetails/\?id=(\d+)', html_data):
                wid = match.group(1)
                if wid not in wids: wids.append(wid)
                
            if not wids: return []
            
            try: cache_hours = float(self.db.get_setting("api_cache_hours") or "4")
            except: cache_hours = 4.0
            
            api_results = self.fetch_api_details(wids, cache_hours=cache_hours)
            items = []
            
            for wid in wids:
                details = api_results.get(str(wid))
                if details:
                    title = details.get('title', 'Unknown Title')
                    img_url = details.get('preview_url', '')
                    updated_ts = details.get('time_updated', 0)
                    
                    if updated_ts:
                        updated_str = datetime.datetime.fromtimestamp(updated_ts).strftime('%d %b %Y, %H:%M')
                    else:
                        updated_str = "Unknown"
                        
                    items.append({
                        "id": wid, 
                        "title": title, 
                        "image_url": img_url, 
                        "last_updated": updated_str
                    })
            return items
        except Exception as e:
            print(f"Workshop Scraper Error: {e}")
            return []

    def _ensure_steamcmd(self):
        nebula_dir = os.path.join(USER_HOME, ".nebula_mod_manager")
        steamcmd_dir = os.path.join(nebula_dir, "steamcmd")
        steamcmd_exe = os.path.join(steamcmd_dir, "steamcmd.exe")
        
        if not os.path.exists(steamcmd_exe):
            os.makedirs(steamcmd_dir, exist_ok=True)
            zip_path = os.path.join(steamcmd_dir, "steamcmd.zip")
            url = "https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip"
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path, 'r') as z: z.extractall(steamcmd_dir)
            os.remove(zip_path)
            
        return steamcmd_exe, steamcmd_dir

    def cancel_download(self, task_id):
        self.cancel_flags.add(task_id)
        if task_id in self.active_processes:
            try: self.active_processes[task_id].kill()
            except Exception: pass

    def download_single_mod(self, game, url, task_id, progress_callback):
        target_path = self.get_mod_path(game)
        os.makedirs(target_path, exist_ok=True)
        
        if "steamcommunity.com" not in url:
            zip_path = os.path.join(target_path, f"temp_{task_id}.zip")
            try:
                def reporthook(blocknum, blocksize, totalsize):
                    if task_id in self.cancel_flags: raise Exception("Cancelled by user")
                    if totalsize > 0 and progress_callback:
                        percent = (blocknum * blocksize * 100) / totalsize
                        progress_callback(min(percent, 100))
                        
                urllib.request.urlretrieve(url, zip_path, reporthook)
                if task_id in self.cancel_flags: raise Exception("Cancelled")
                
                with zipfile.ZipFile(zip_path, 'r') as z: z.extractall(target_path)
                os.remove(zip_path)
                return True, ""
            except Exception as e:
                if os.path.exists(zip_path): 
                    try: os.remove(zip_path) 
                    except: pass
                return False, str(e)
                
        match = re.search(r'id=(\d+)', url)
        if not match: return False, "Invalid Workshop URL"
        wid = match.group(1)
        
        game_data = GAMES_MAP.get(game)
        app_id = game_data.get("app_id") if game_data else None
        if not app_id: return False, "Game not supported by SteamCMD"
        
        try:
            steamcmd_exe, steamcmd_dir = self._ensure_steamcmd()
            script_path = os.path.join(steamcmd_dir, f"runscript_{task_id}.txt")
            
            script_content = f"@ShutdownOnFailedCommand 1\n@NoPromptForPassword 1\nlogin anonymous\nworkshop_download_item {app_id} {wid}\nquit\n"
            with open(script_path, 'w') as f: f.write(script_content)
            
            # Use bufsize=1 and text=True to force real-time line buffering for the progress output
            process = subprocess.Popen([steamcmd_exe, "+runscript", script_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
            self.active_processes[task_id] = process
            
            for line in process.stdout:
                if task_id in self.cancel_flags:
                    process.kill()
                    break
                match = re.search(r'progress:\s*([0-9.]+)', line.lower())
                if match and progress_callback:
                    progress_callback(float(match.group(1)))

            process.wait()
            del self.active_processes[task_id]
            if os.path.exists(script_path): os.remove(script_path)
            
            if task_id in self.cancel_flags: return False, "Cancelled by user"
            if process.returncode != 0: return False, "SteamCMD execution failed"
            
            item_folder = os.path.join(steamcmd_dir, "steamapps", "workshop", "content", str(app_id), str(wid))
            dest_folder = os.path.join(target_path, f"ugc_{wid}")
            
            if os.path.exists(item_folder):
                if os.path.exists(dest_folder): shutil.rmtree(dest_folder)
                archives = [f for f in os.listdir(item_folder) if f.endswith(('.zip', '.bin'))]
                if archives:
                    os.makedirs(dest_folder, exist_ok=True)
                    with zipfile.ZipFile(os.path.join(item_folder, archives[0]), 'r') as z: z.extractall(dest_folder)
                else:
                    shutil.copytree(item_folder, dest_folder)
                shutil.rmtree(item_folder)
                
            if os.path.exists(dest_folder):
                api_res = self.fetch_api_details([wid], cache_hours=0) 
                remote_time = api_res.get(str(wid), {}).get("time_updated", int(datetime.datetime.now().timestamp()))
                with open(os.path.join(dest_folder, "nebula_update.json"), "w") as f:
                    json.dump({"time_updated": remote_time}, f)
                
            return True, ""
        except Exception as e:
            return False, str(e)