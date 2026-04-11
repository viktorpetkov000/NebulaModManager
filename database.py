import sqlite3
import os
import json

class DatabaseManager:
    def __init__(self, db_file="mod_manager.db"):
        self.db_conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.db_conn.cursor()
        self.cursor.execute("PRAGMA foreign_keys = ON")
        self.setup_db()

    def setup_db(self):
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS collections (id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, name TEXT, UNIQUE(game, name));
            CREATE TABLE IF NOT EXISTS collection_mods (
                collection_id INTEGER, rel_path TEXT, load_order INTEGER, 
                FOREIGN KEY(collection_id) REFERENCES collections(id) ON DELETE CASCADE
            );
        ''')
        
        user_home = os.path.expanduser('~')
        defaults = {
            "stellaris_mod_path": os.path.join(user_home, "Documents", "Paradox Interactive", "Stellaris", "mod"),
            "hoi4_mod_path": os.path.join(user_home, "Documents", "Paradox Interactive", "Hearts of Iron IV", "mod"),
            "stellaris_exe_path": r"C:\Program Files (x86)\Steam\steamapps\common\Stellaris\stellaris.exe",
            "hoi4_exe_path": r"C:\Program Files (x86)\Steam\steamapps\common\Hearts of Iron IV\hoi4.exe"
        }
        for k, v in defaults.items():
            self.cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
            
        self.cursor.execute("INSERT OR IGNORE INTO collections (game, name) VALUES ('Stellaris', 'Default')")
        self.cursor.execute("INSERT OR IGNORE INTO collections (game, name) VALUES ('Hearts of Iron IV', 'Default')")
        self.db_conn.commit()
        self.migrate_old_json()

    def migrate_old_json(self):
        old_json = "mod_manager_config.json"
        if os.path.exists(old_json):
            try:
                with open(old_json, 'r') as f: data = json.load(f)
                for key in ["stellaris_mod_path", "hoi4_mod_path", "stellaris_exe_path", "hoi4_exe_path"]:
                    if key in data: self.set_setting(key, data[key])
                if "collections" in data:
                    for game, colls in data["collections"].items():
                        for coll_name, mods in colls.items():
                            self.create_collection(game, coll_name)
                            self.save_collection_mods(game, coll_name, mods)
                os.rename(old_json, old_json + ".bak")
            except Exception: pass

    def get_setting(self, key):
        self.cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
        res = self.cursor.fetchone()
        return res[0] if res else ""

    def set_setting(self, key, value):
        self.cursor.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        self.db_conn.commit()

    def get_collections_list(self, game):
        self.cursor.execute("SELECT name FROM collections WHERE game=?", (game,))
        return [r[0] for r in self.cursor.fetchall()]

    def create_collection(self, game, name):
        self.cursor.execute("INSERT OR IGNORE INTO collections (game, name) VALUES (?, ?)", (game, name))
        self.db_conn.commit()

    def delete_collection(self, game, name):
        self.cursor.execute("DELETE FROM collections WHERE game=? AND name=?", (game, name))
        self.db_conn.commit()

    def get_collection_mods(self, game, coll_name):
        self.cursor.execute('''SELECT rel_path FROM collection_mods
                               JOIN collections ON collections.id = collection_mods.collection_id
                               WHERE collections.game=? AND collections.name=? ORDER BY load_order''', (game, coll_name))
        return [r[0] for r in self.cursor.fetchall()]

    def save_collection_mods(self, game, coll_name, mod_list):
        self.cursor.execute("SELECT id FROM collections WHERE game=? AND name=?", (game, coll_name))
        res = self.cursor.fetchone()
        if not res: return
        cid = res[0]
        self.cursor.execute("DELETE FROM collection_mods WHERE collection_id=?", (cid,))
        data = [(cid, rel_path, i) for i, rel_path in enumerate(mod_list)]
        self.cursor.executemany("INSERT INTO collection_mods (collection_id, rel_path, load_order) VALUES (?, ?, ?)", data)
        self.db_conn.commit()