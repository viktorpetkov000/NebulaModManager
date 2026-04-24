import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
import customtkinter as ctk
import threading
import os
import shutil
import io
import urllib.request
import uuid
import datetime
import webbrowser
import re
import zipfile
import base64
import zlib
from PIL import Image, ImageDraw
try:
    import pystray
except ImportError:
    pystray = None
from database import GAMES_MAP

class NebulaModManager:
    def __init__(self, root, db, engine):
        self.root = root
        self.db = db
        self.engine = engine
        
        # NEBULA THEME SETUP
        ctk.set_appearance_mode("dark")
        self.bg_color = "#0B0F19"      # Deep Space Black
        self.pane_color = "#151A28"    # Interstellar Blue-Grey
        self.accent_color = "#6366F1"  # Indigo Nebula
        self.hover_color = "#4F46E5"
        
        self.root.title("Nebula Mod Manager")
        self.root.geometry("1250x850") 
        self.root.minsize(1000, 700)
        self.root.configure(fg_color=self.bg_color)
        
        self.installed_mods_data = {}
        self.mod_warnings = {} 
        self.missing_dep_names = set()
        self.drag_data = None
        self.current_thumbnail = None
        
        self.download_queue = [] 
        self.is_downloading = False
        self.workshop_ui_updater = None 
        self.available_updates = {}

        self.icon = None
        if pystray:
            self.root.protocol('WM_DELETE_WINDOW', self.hide_window)

        # Global Hotkeys
        self.root.bind("<F5>", lambda e: self.refresh_installed_mods())

        self.apply_treeview_styles()
        self.build_ui()
        self.refresh_installed_mods()
        self.update_collection_dropdown()

        # Initial Auto-Check for Updates
        if self.db.get_setting("auto_update_check") != "False":
            self.root.after(1500, self.check_for_updates)

    def apply_treeview_styles(self):
        style = ttk.Style()
        style.theme_use("default")
        # Nebula styling for the treeviews
        style.configure("Treeview", background=self.pane_color, foreground="#F8FAFC", fieldbackground=self.pane_color, rowheight=30, borderwidth=0, font=("Segoe UI", 10))
        style.map("Treeview", background=[("selected", "#312E81")]) # Deep indigo selection
        style.configure("Treeview.Heading", background="#1E293B", foreground="#F8FAFC", relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Treeview.Heading", background=[("active", self.accent_color)])
        
        self.collection_tree = ttk.Treeview() 
        self.collection_tree.tag_configure("warning", foreground="#F59E0B")
        self.collection_tree.tag_configure("downloading", foreground="#10B981")
        self.collection_tree.tag_configure("update_avail", foreground="#D946EF") # Neon pink/purple for updates

    def build_ui(self):
        # TOP PANE (Header)
        top_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        top_frame.pack(fill="x", pady=15, padx=20)

        title_lbl = ctk.CTkLabel(top_frame, text="NEBULA", font=("Segoe UI", 24, "bold"), text_color=self.accent_color)
        title_lbl.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(top_frame, text="Game:", font=("Segoe UI", 14, "bold")).pack(side="left", padx=(0, 10))
        
        game_list = list(GAMES_MAP.keys())
        last_game = self.db.get_setting("last_game")
        self.game_var = ctk.StringVar(value=last_game if last_game in game_list else game_list[0])
        ctk.CTkOptionMenu(top_frame, variable=self.game_var, values=game_list, command=self.on_game_switch, width=250, fg_color=self.pane_color, button_color=self.accent_color, button_hover_color=self.hover_color).pack(side="left")

        ctk.CTkButton(top_frame, text="⚙ Options", fg_color=self.pane_color, hover_color="#1E293B", command=self.open_options).pack(side="right")
        ctk.CTkButton(top_frame, text="🛠 Mod Tools", fg_color="#9F1239", hover_color="#881337", command=self.open_tools_menu).pack(side="right", padx=10)

        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=5)

        # LEFT PANE (Installed Mods & Inline Downloads)
        left_pane = ctk.CTkFrame(main_frame, fg_color="transparent")
        left_pane.pack(side="left", fill="both", expand=True)
        
        left_header = ctk.CTkFrame(left_pane, fg_color="transparent")
        left_header.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(left_header, text="Vault / Installed", font=("Segoe UI", 16, "bold"), text_color="#E2E8F0").pack(side="left")
        
        self.lbl_installed_count = ctk.CTkLabel(left_header, text="(0)", font=("Segoe UI", 14), text_color="#64748B")
        self.lbl_installed_count.pack(side="left", padx=(5, 0))
        
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self.filter_installed_mods)
        ctk.CTkEntry(left_header, textvariable=self.search_var, placeholder_text="Search mods...", width=200, fg_color=self.pane_color, border_color="#334155").pack(side="right")

        self.installed_tree = ttk.Treeview(left_pane, columns=("Mod Name", "Version", "Status"), show="headings")
        self.installed_tree.heading("Mod Name", text="Mod Name", command=lambda: self.tree_sort(self.installed_tree, "Mod Name", False))
        self.installed_tree.heading("Version", text="Version", command=lambda: self.tree_sort(self.installed_tree, "Version", False))
        self.installed_tree.heading("Status", text="Status", command=lambda: self.tree_sort(self.installed_tree, "Status", False))
        self.installed_tree.column("Mod Name", width=200)
        self.installed_tree.column("Version", width=60, anchor="center")
        self.installed_tree.column("Status", width=90, anchor="center")
        self.installed_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Setup Installed Mods Right-Click Menu
        self.ctx_menu = tk.Menu(self.root, tearoff=0, bg=self.pane_color, fg="#ffffff", activebackground=self.accent_color, relief="flat", borderwidth=0)
        self.ctx_menu.add_command(label="Open Folder in Explorer", command=self.open_mod_folder)
        self.ctx_menu.add_command(label="View in Workshop", command=self.open_selected_mod_page)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Update Mod", command=self.update_selected_mod)
        self.ctx_menu.add_command(label="Delete Mod Permanently", command=self.delete_selected_mod)
        
        def on_installed_right_click(e):
            row = self.installed_tree.identify_row(e.y)
            if row:
                if row not in self.installed_tree.selection():
                    self.installed_tree.selection_set(row)
                self.installed_tree.focus(row)
                # Show/hide Update Mod conditionally
                if row in self.available_updates: self.ctx_menu.entryconfig("Update Mod", state="normal")
                else: self.ctx_menu.entryconfig("Update Mod", state="disabled")
                self.ctx_menu.post(e.x_root, e.y_root)
                
        self.installed_tree.bind("<Button-3>", on_installed_right_click)
        self.installed_tree.bind("<<TreeviewSelect>>", lambda e: self.on_mod_select(self.installed_tree))

        # MID PANE (Transfer Buttons)
        mid_pane = ctk.CTkFrame(main_frame, fg_color="transparent")
        mid_pane.pack(side="left", fill="y", padx=15)
        ctk.CTkFrame(mid_pane, fg_color="transparent", height=150).pack()
        ctk.CTkButton(mid_pane, text="Add >>", width=100, font=("Segoe UI", 13, "bold"), fg_color=self.pane_color, hover_color="#1E293B", command=self.add_to_collection).pack(pady=5)
        ctk.CTkButton(mid_pane, text="<< Remove", width=100, font=("Segoe UI", 13, "bold"), fg_color=self.pane_color, hover_color="#1E293B", command=self.remove_from_collection).pack(pady=5)

        # RIGHT PANE (Collections)
        right_pane = ctk.CTkFrame(main_frame, fg_color="transparent")
        right_pane.pack(side="right", fill="both", expand=True)
        coll_ctrl = ctk.CTkFrame(right_pane, fg_color="transparent")
        coll_ctrl.pack(fill="x", padx=10, pady=10)
        
        self.current_collection_var = ctk.StringVar()
        self.collection_combo = ctk.CTkOptionMenu(coll_ctrl, variable=self.current_collection_var, command=self.on_collection_switch, width=150, fg_color=self.pane_color, button_color=self.accent_color, button_hover_color=self.hover_color)
        self.collection_combo.pack(side="left", padx=(0, 5))
        
        self.lbl_collection_count = ctk.CTkLabel(coll_ctrl, text="(0)", font=("Segoe UI", 14), text_color="#64748B")
        self.lbl_collection_count.pack(side="left", padx=(0, 10))

        ctk.CTkButton(coll_ctrl, text="New", width=40, fg_color=self.accent_color, hover_color=self.hover_color, command=self.create_collection).pack(side="left", padx=2)
        ctk.CTkButton(coll_ctrl, text="Del", width=40, fg_color="#9F1239", hover_color="#881337", command=self.delete_collection).pack(side="left", padx=2)
        ctk.CTkButton(coll_ctrl, text="From Save", width=80, fg_color="#059669", hover_color="#047857", command=self.import_from_save).pack(side="left", padx=2)
        
        ctk.CTkButton(coll_ctrl, text="Share Code", width=80, fg_color=self.accent_color, hover_color=self.hover_color, command=self.share_load_order).pack(side="right", padx=2)
        ctk.CTkButton(coll_ctrl, text="Paste Code", width=80, fg_color=self.pane_color, hover_color="#1E293B", command=self.paste_load_order).pack(side="right", padx=2)
        
        tools_f = ctk.CTkFrame(right_pane, fg_color="transparent")
        tools_f.pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(tools_f, text="⚠️ Double-click mods with yellow warnings for details", font=("Segoe UI", 11, "italic"), text_color="#64748B").pack(side="left")
        ctk.CTkButton(tools_f, text="Auto-Sort", width=80, fg_color=self.pane_color, hover_color="#1E293B", command=self.auto_sort).pack(side="right", padx=2)
        ctk.CTkButton(tools_f, text="Import Zip", width=70, fg_color=self.pane_color, hover_color="#1E293B", command=self.import_collection).pack(side="right", padx=2)
        ctk.CTkButton(tools_f, text="Export Zip", width=70, fg_color=self.pane_color, hover_color="#1E293B", command=self.export_collection).pack(side="right", padx=2)

        self.collection_tree = ttk.Treeview(right_pane, columns=("Order", "Mod Name", "Version"), show="headings")
        self.collection_tree.heading("Order", text="#")
        self.collection_tree.heading("Mod Name", text="Active Collection")
        self.collection_tree.heading("Version", text="Version")
        self.collection_tree.column("Order", width=40, anchor="center")
        self.collection_tree.column("Mod Name", width=220)
        self.collection_tree.column("Version", width=60, anchor="center")
        self.collection_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.collection_tree.bind("<ButtonPress-1>", self.on_drag_start)
        self.collection_tree.bind("<B1-Motion>", self.on_drag_motion)
        self.collection_tree.bind("<ButtonRelease-1>", self.on_drag_release)
        self.collection_tree.bind("<Double-1>", self.show_mod_warnings)
        self.collection_tree.bind("<<TreeviewSelect>>", lambda e: self.on_mod_select(self.collection_tree))

        # MOD DETAILS PANE
        self.details_frame = ctk.CTkFrame(self.root, height=130, cursor="hand2", fg_color=self.pane_color, border_width=1, border_color="#1E293B")
        self.details_frame.pack(fill="x", padx=20, pady=(0, 5))
        self.details_frame.pack_propagate(False)
        
        self.thumb_label = ctk.CTkLabel(self.details_frame, text="Select a Mod", font=("Segoe UI", 12, "italic"), text_color="#64748B", width=110, height=110, fg_color="#0F172A", corner_radius=8, cursor="hand2")
        self.thumb_label.pack(side="left", padx=10, pady=10)
        
        self.info_frame = ctk.CTkFrame(self.details_frame, fg_color="transparent", cursor="hand2")
        self.info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        self.lbl_mod_name = ctk.CTkLabel(self.info_frame, text="No Mod Selected", font=("Segoe UI", 22, "bold"), anchor="w", cursor="hand2", text_color="#F8FAFC")
        self.lbl_mod_name.pack(fill="x")
        self.lbl_mod_path = ctk.CTkLabel(self.info_frame, text="", font=("Segoe UI", 12, "italic"), text_color="#94A3B8", anchor="w", cursor="hand2")
        self.lbl_mod_path.pack(fill="x")
        self.lbl_mod_desc = ctk.CTkLabel(self.info_frame, text="Select a mod from the lists above to view its details, thumbnails, and health status.", font=("Segoe UI", 13), text_color="#E2E8F0", anchor="w", justify="left", cursor="hand2")
        self.lbl_mod_desc.pack(fill="x", pady=(5,0))
        
        self.btn_cancel_dl = ctk.CTkButton(self.info_frame, text="✖ Cancel Action", width=120, height=28, fg_color="#9F1239", hover_color="#881337", command=self.cancel_selected_download)

        for w in [self.details_frame, self.thumb_label, self.info_frame, self.lbl_mod_name, self.lbl_mod_path, self.lbl_mod_desc]:
            w.bind("<Button-1>", self.open_selected_mod_page)

        # BOTTOM PANE (Launch & Sync Controls)
        bottom = ctk.CTkFrame(self.root, fg_color="transparent")
        bottom.pack(fill="x", pady=5, padx=20)
        
        ctk.CTkButton(bottom, text="↻ Refresh Mods", fg_color=self.pane_color, hover_color="#1E293B", command=self.refresh_installed_mods).pack(side="left")
        ctk.CTkButton(bottom, text="🔍 Check Updates", fg_color=self.pane_color, hover_color="#1E293B", text_color="#D946EF", command=self.check_for_updates).pack(side="left", padx=10)
        
        ctk.CTkButton(bottom, text="🚀 Launch Game", font=("Segoe UI", 14, "bold"), height=40, fg_color=self.accent_color, hover_color=self.hover_color, command=self.launch_game).pack(side="right", padx=(15, 0))
        ctk.CTkButton(bottom, text="🌐 Workshop Browser", height=40, fg_color=self.pane_color, hover_color="#1E293B", command=self.open_workshop_browser).pack(side="right", padx=10)
        ctk.CTkButton(bottom, text="⬇ Download Link", height=40, fg_color=self.pane_color, hover_color="#1E293B", command=self.open_download_dialog).pack(side="right")
        ctk.CTkButton(bottom, text="📦 Install Local", height=40, fg_color=self.pane_color, hover_color="#1E293B", command=self.open_install_local_dialog).pack(side="right", padx=10)

        # STATUS BAR & UPDATE PROGRESS (Isolated)
        status_frame = ctk.CTkFrame(self.root, fg_color="#0F172A", height=30, corner_radius=0)
        status_frame.pack(fill="x", side="bottom")
        
        self.status_bar = ctk.CTkLabel(status_frame, text="Ready.", font=("Segoe UI", 12), text_color="#94A3B8", anchor="w", padx=15)
        self.status_bar.pack(side="left")
        
        self.update_prog = ctk.CTkProgressBar(status_frame, width=100, mode="indeterminate", progress_color=self.accent_color)
        self.update_prog.pack(side="right", padx=(0, 15))
        self.update_prog.pack_forget() 
        
        self.update_status_lbl = ctk.CTkLabel(status_frame, text="", font=("Segoe UI", 12, "bold"), text_color="#D946EF", anchor="e", padx=15)
        self.update_status_lbl.pack(side="right")

    def set_status(self, msg, color="#E2E8F0"):
        self.status_bar.configure(text=msg, text_color=color)

    def clear_mod_details(self):
        self.lbl_mod_name.configure(text="No Mod Selected", text_color="#F8FAFC")
        self.lbl_mod_path.configure(text="")
        self.lbl_mod_desc.configure(text="Select a mod from the lists above to view its details, thumbnails, and health status.")
        self.thumb_label.configure(image="", text="Select a Mod")
        self.current_thumbnail = None
        self.btn_cancel_dl.pack_forget()

    # --- UPDATE SYSTEM ---
    def check_for_updates(self):
        self.update_status_lbl.configure(text="Checking Steam Workshop for updates...", text_color="#D946EF")
        self.update_prog.pack(side="right", padx=(0, 15))
        self.update_prog.start()
        
        def task():
            try: cache_hours = float(self.db.get_setting("api_cache_hours") or "4")
            except: cache_hours = 4.0
            
            updates = self.engine.check_mod_updates(self.installed_mods_data, cache_hours=cache_hours)
            self.available_updates = updates
            self.root.after(0, self._apply_updates_ui)
            
        threading.Thread(target=task, daemon=True).start()
        
    def _apply_updates_ui(self):
        self.update_prog.stop()
        self.update_prog.pack_forget()
        
        count = len(self.available_updates)
        if count == 0:
            self.update_status_lbl.configure(text="✅ All mods up to date", text_color="#10B981")
        else:
            self.update_status_lbl.configure(text=f"🚀 {count} update(s) available!", text_color="#D946EF")
        self.refresh_installed_mods()

    def update_selected_mod(self):
        selected = self.installed_tree.selection()
        if not selected: return
        rel_path = selected[0]
        data = self.installed_mods_data.get(rel_path)
        wid = data.get("remote_id")
        if wid and data:
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={wid}"
            self.add_to_download_queue(f"Updating: {data['name']}", url, replace_rel_path=rel_path)
            if rel_path in self.available_updates:
                del self.available_updates[rel_path] # Remove from active updates map

    # --- INLINE DOWNLOAD SYSTEM ---
    def add_to_download_queue(self, title, url, replace_rel_path=None):
        task_id = "dl_" + str(uuid.uuid4())
        self.download_queue.append({
            "id": task_id, "title": title, "url": url, 
            "status": "Queued", "replace_rel_path": replace_rel_path
        })
        self.refresh_installed_mods() 
        self.set_status(f"Queued: {title}")
        self.process_download_queue()
        return task_id

    def cancel_selected_download(self):
        selected = self.installed_tree.selection()
        if not selected: return
        task_id = selected[0]
        
        self.download_queue = [t for t in self.download_queue if t["id"] != task_id]
        self.engine.cancel_download(task_id) 
        
        self.set_status("Action cancelled.", color="#F59E0B")
        self.btn_cancel_dl.pack_forget()
        self.refresh_installed_mods()
        if self.workshop_ui_updater: self.workshop_ui_updater()

    def process_download_queue(self):
        if self.is_downloading: return
        self.is_downloading = True
        
        def worker():
            while True:
                task = next((t for t in self.download_queue if t["status"] == "Queued"), None)
                if not task: break
                    
                task_id = task["id"]
                task["status"] = "0%"
                self.root.after(0, self.refresh_installed_mods)
                self.root.after(0, lambda t=task["title"]: self.set_status(f"Downloading: {t}..."))
                
                def prog_cb(pct):
                    pct_str = f"{pct:.1f}%"
                    task["status"] = pct_str
                    def update_ui(tid=task_id, text=pct_str, ttitle=task["title"]):
                        try:
                            if self.installed_tree.exists(tid):
                                self.installed_tree.item(tid, values=(ttitle, "N/A", text))
                        except Exception: pass
                    self.root.after(0, update_ui)
                
                success, error_msg = self.engine.download_single_mod(self.game_var.get(), task["url"], task_id, prog_cb)
                
                if task_id in self.engine.cancel_flags:
                    pass 
                elif success:
                    self.root.after(0, lambda t=task["title"]: self.set_status(f"Successfully installed: {t}", color="#10B981"))
                    self.root.after(0, lambda t=task: self._post_download_cleanup(t))
                else:
                    self.root.after(0, lambda t=task["title"], e=error_msg: self.set_status(f"Failed to install {t}: {e}", color="#EF4444"))
                
                self.download_queue = [t for t in self.download_queue if t["id"] != task_id]
                self.root.after(0, self.refresh_installed_mods)
                
                if self.workshop_ui_updater: self.root.after(0, self.workshop_ui_updater)
            
            self.is_downloading = False
            self.root.after(0, lambda: self.set_status("All downloads completed.", color="#10B981"))
            
        threading.Thread(target=worker, daemon=True).start()

    def _post_download_cleanup(self, task):
        # 1. Re-scan entirely to find exactly where the downloaded mod ended up
        self.refresh_installed_mods() 
        
        wid_match = re.search(r'id=(\d+)', task["url"])
        if not wid_match: return
        wid = wid_match.group(1)
        
        new_rel_path = next((p for p, d in self.installed_mods_data.items() if str(d.get("remote_id")) == str(wid)), None)
        
        # 2. Globally update any placeholder 'ugc_{wid}' or old mod paths inside ALL collections
        if new_rel_path:
            game = self.game_var.get()
            for coll in self.db.get_collections_list(game):
                mods = self.db.get_collection_mods(game, coll)
                updated = False
                for i, m in enumerate(mods):
                    if m == f"mod/ugc_{wid}.mod" and new_rel_path != m:
                        mods[i] = new_rel_path
                        updated = True
                    elif task.get("replace_rel_path") and m == task["replace_rel_path"] and new_rel_path != task["replace_rel_path"]:
                        mods[i] = new_rel_path
                        updated = True
                if updated:
                    self.db.save_collection_mods(game, coll, mods)
                    
        # 3. Permanently wipe the old mod files from disk if this was an update
        if task.get("replace_rel_path") and new_rel_path and new_rel_path != task["replace_rel_path"]:
            old_rel = task["replace_rel_path"]
            old_data = self.installed_mods_data.get(old_rel)
            if old_data:
                try:
                    if os.path.exists(old_data["file_path"]): os.remove(old_data["file_path"])
                    if old_data.get("content_path") and os.path.exists(old_data["content_path"]):
                        shutil.rmtree(old_data["content_path"]) if os.path.isdir(old_data["content_path"]) else os.remove(old_data["content_path"])
                except Exception as e: print(f"Cleanup Error: {e}")
            self.refresh_installed_mods() 
        else:
            self.refresh_collection_view()

    # --- UI EVENT LOGIC ---
    def open_selected_mod_page(self, event=None):
        if self.btn_cancel_dl.winfo_ismapped(): return
        
        selected = self.installed_tree.selection()
        if not selected: selected = self.collection_tree.selection()
        if not selected: return
        rel_path = selected[0]
        data = self.installed_mods_data.get(rel_path)
        
        if data:
            if data.get("remote_id"):
                webbrowser.open(f"https://steamcommunity.com/sharedfiles/filedetails/?id={data['remote_id']}")
            else:
                app_id = GAMES_MAP.get(self.game_var.get(), {}).get("app_id", "")
                query = urllib.parse.quote(data['name'])
                webbrowser.open(f"https://steamcommunity.com/workshop/browse/?appid={app_id}&searchtext={query}")

    def tree_sort(self, tv, col, reverse):
        l = [(tv.set(k, col), k) for k in tv.get_children('')]
        l.sort(reverse=reverse, key=lambda x: x[0].lower())
        for index, (val, k) in enumerate(l): tv.move(k, '', index)
        tv.heading(col, command=lambda _col=col: self.tree_sort(tv, _col, not reverse))

    def on_drag_start(self, e):
        row = self.collection_tree.identify_row(e.y)
        if row: self.drag_data = {"item": row, "moved": False}

    def on_drag_motion(self, e):
        if not self.drag_data: return
        item = self.drag_data["item"]
        target = self.collection_tree.identify_row(e.y)
        if target and target != item:
            self.collection_tree.move(item, self.collection_tree.parent(target), self.collection_tree.index(target))
            self.drag_data["moved"] = True

    def on_drag_release(self, e):
        if self.drag_data and self.drag_data.get("moved"):
            game, coll = self.game_var.get(), self.current_collection_var.get()
            self.db.save_collection_mods(game, coll, list(self.collection_tree.get_children()))
            self.refresh_collection_view()
        self.drag_data = None

    def on_game_switch(self, choice):
        self.db.set_setting("last_game", choice)
        self.search_var.set("")
        self.clear_mod_details() 
        self.update_collection_dropdown()
        self.refresh_installed_mods()

    def on_collection_switch(self, choice):
        self.db.set_setting(f"last_collection_{self.game_var.get()}", choice)
        self.refresh_collection_view()

    def hide_window(self):
        self.root.withdraw()
        image = Image.new('RGB', (64, 64), color=(31, 83, 141))
        draw = ImageDraw.Draw(image)
        draw.rectangle((16, 16, 48, 48), fill="white")
        draw.rectangle((24, 24, 40, 40), fill=(181, 59, 59))

        def on_show(icon, item):
            icon.stop()
            self.root.after(0, self.root.deiconify)

        def on_quit(icon, item):
            icon.stop()
            self.root.after(0, self.root.destroy)

        def make_launch_callback(g, c):
            return lambda icon, item: self.root.after(0, lambda: self.engine.launch_game(g, c))

        menu_items = [pystray.MenuItem("Show Nebula", on_show, default=True), pystray.Menu.SEPARATOR]

        for g in GAMES_MAP.keys():
            colls = self.db.get_collections_list(g)
            if colls:
                sub_menu = pystray.Menu(*[pystray.MenuItem(c, make_launch_callback(g, c)) for c in colls])
                menu_items.append(pystray.MenuItem(f"Launch {g}", sub_menu))

        menu_items.extend([pystray.Menu.SEPARATOR, pystray.MenuItem("Quit", on_quit)])
        self.icon = pystray.Icon("Nebula", image, "Nebula Mod Manager", menu=pystray.Menu(*menu_items))
        threading.Thread(target=self.icon.run, daemon=True).start()

    def show_mod_warnings(self, event):
        selected = self.collection_tree.selection()
        if not selected: return
        rel_path = selected[0]
        if rel_path in self.mod_warnings:
            msg = "\n\n".join(self.mod_warnings[rel_path])
            messagebox.showwarning("Mod Health Check", f"⚠️ Issues detected for this mod:\n\n{msg}")

    def on_mod_select(self, tree):
        selected = tree.selection()
        if not selected: return
        
        if tree == self.installed_tree:
            if self.collection_tree.selection(): self.collection_tree.selection_remove(self.collection_tree.selection())
        else:
            if self.installed_tree.selection(): self.installed_tree.selection_remove(self.installed_tree.selection())

        rel_path = selected[0]
        
        if str(rel_path).startswith("dl_"):
            task = next((t for t in self.download_queue if t["id"] == rel_path), None)
            if task:
                self.lbl_mod_name.configure(text=task["title"], text_color="#10B981")
                self.lbl_mod_path.configure(text=f"🔗 {task['url']}")
                self.lbl_mod_desc.configure(text=f"Status: {task['status']}")
                self.thumb_label.configure(image="", text="Downloading...")
                self.btn_cancel_dl.pack(side="right", padx=20)
                return
        
        self.btn_cancel_dl.pack_forget()

        data = self.installed_mods_data.get(rel_path)
        if not data: return

        self.lbl_mod_name.configure(text=data["name"])
        path_text = data.get('content_path') or data.get('file_path') or "Unknown Path"
        self.lbl_mod_path.configure(text=f"📂 {path_text}")
        
        desc = f"🏷️ Version: {data.get('version', 'Any')}"
        deps = data.get('dependencies', [])
        if deps: desc += f"   |   🔗 Dependencies: {', '.join(deps)}"
            
        if rel_path in self.available_updates:
            desc += "\n🚀 UPDATE AVAILABLE! Right-click this mod to update."
            self.lbl_mod_name.configure(text_color="#D946EF")
        elif rel_path in self.mod_warnings:
            desc += f"\n⚠️ Warnings: {len(self.mod_warnings[rel_path])} issues detected."
            self.lbl_mod_name.configure(text_color="#F59E0B")
        else:
            self.lbl_mod_name.configure(text_color="#F8FAFC")
            
        desc += "\n🌐 Click anywhere here to view on Steam Workshop"
        self.lbl_mod_desc.configure(text=desc)

        thumb_loaded = False
        if data.get("content_path") and os.path.isdir(data["content_path"]):
            thumb_path = os.path.join(data["content_path"], "thumbnail.png")
            if os.path.exists(thumb_path):
                try:
                    img = Image.open(thumb_path)
                    img.thumbnail((110, 110))
                    self.current_thumbnail = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    self.thumb_label.configure(image=self.current_thumbnail, text="")
                    thumb_loaded = True
                except Exception: pass
                    
        if not thumb_loaded:
            self.thumb_label.configure(image="", text="No Image\nAvailable")

    # --- REFRESH VIEWS ---
    def refresh_installed_mods(self):
        for item in self.installed_tree.get_children(): self.installed_tree.delete(item)
        game = self.game_var.get()
        self.installed_mods_data = self.engine.scan_installed_mods(game)
        
        for task in self.download_queue:
            self.installed_tree.insert("", "end", iid=task["id"], values=(task["title"], "N/A", task["status"]), tags=("downloading",))

        self.filter_installed_mods()
        self.refresh_collection_view()

    def filter_installed_mods(self, *args):
        search_term = self.search_var.get().lower()
        
        for item in self.installed_tree.get_children(): 
            if not str(item).startswith("dl_"):
                self.installed_tree.delete(item)
        
        sorted_mods = sorted(self.installed_mods_data.items(), key=lambda x: x[1]["name"].lower())
        match_count = 0
        for rel_path, data in sorted_mods:
            if search_term in data["name"].lower():
                # Apply conditional tags for updates
                tag = ""
                status_text = "Installed"
                if rel_path in self.available_updates:
                    tag = "update_avail"
                    status_text = "Update!"
                    
                self.installed_tree.insert("", "end", iid=rel_path, values=(data["name"], data["version"], status_text), tags=(tag,))
                match_count += 1
                
        self.lbl_installed_count.configure(text=f"({match_count + len(self.download_queue)})")

    def refresh_collection_view(self):
        for item in self.collection_tree.get_children(): self.collection_tree.delete(item)
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll: 
            self.lbl_collection_count.configure(text="(0)")
            if hasattr(self, 'dep_resolve_btn') and self.dep_resolve_btn.winfo_ismapped():
                self.dep_resolve_btn.pack_forget()
            return
        
        mod_list = self.db.get_collection_mods(game, coll)
        game_ver = self.engine.get_game_version(game)
        self.mod_warnings = {}
        self.missing_dep_names.clear()
        
        self.lbl_collection_count.configure(text=f"({len(mod_list)})")
        
        active_names = {self.installed_mods_data.get(p, {}).get("name", ""): idx for idx, p in enumerate(mod_list)}
        
        for index, rel_path in enumerate(mod_list):
            data = self.installed_mods_data.get(rel_path)
            
            # Identify missing mods or currently downloading placeholders gracefully
            if not data: 
                display_name = f"[Missing] {rel_path}"
                tag = "warning"
                
                wid_match = re.search(r'ugc_(\d+)', rel_path)
                if wid_match:
                    wid = wid_match.group(1)
                    task = next((t for t in self.download_queue if f"id={wid}" in t["url"]), None)
                    if task:
                        display_name = f"⬇ {task['title']} (Downloading...)"
                        tag = "downloading"
                        
                self.collection_tree.insert("", "end", iid=rel_path, values=(str(index+1), display_name, "N/A"), tags=(tag,))
                continue
                
            warnings = []
            mod_ver = data.get("version", "Any")
            if game_ver and mod_ver not in ["*", "Any", ""] and game_ver != "Unknown":
                g_nums = re.findall(r'\d+', game_ver)
                m_nums = re.findall(r'\d+', mod_ver)
                if g_nums and m_nums:
                    if g_nums[:len(m_nums[:2])] != m_nums[:2]:
                        warnings.append(f"Game is {game_ver}, but mod is built for {mod_ver}.")
            
            for dep in data.get("dependencies", []):
                if dep not in active_names:
                    warnings.append(f"Missing dependency: '{dep}' is not in this collection.")
                    self.missing_dep_names.add(dep)
                elif active_names[dep] > index:
                    warnings.append(f"Load Order Error: '{dep}' must be loaded BEFORE this mod.")
                    
            display_name = data["name"]
            tag = ""
            
            if rel_path in self.available_updates:
                tag = "update_avail"
                display_name = f"🚀 {display_name}"
            elif warnings:
                self.mod_warnings[rel_path] = warnings
                display_name = f"⚠️ {display_name}"
                tag = "warning"
                
            self.collection_tree.insert("", "end", iid=rel_path, values=(str(index+1), display_name, mod_ver), tags=(tag,))
            
        if self.collection_tree.selection():
            self.on_mod_select(self.collection_tree)
            
        # UI Toggle for the new Auto-Dependency Resolver
        if self.missing_dep_names:
            if not hasattr(self, 'dep_resolve_btn'):
                self.dep_resolve_btn = ctk.CTkButton(self.collection_tree.master, fg_color="#F59E0B", hover_color="#D97706", text_color="#0F172A", font=("Segoe UI", 12, "bold"), command=self.resolve_dependencies)
            self.dep_resolve_btn.pack(fill="x", padx=10, pady=(0, 10))
            self.dep_resolve_btn.configure(text=f"⬇ Resolve {len(self.missing_dep_names)} Missing Dependencies")
        else:
            if hasattr(self, 'dep_resolve_btn') and self.dep_resolve_btn.winfo_ismapped():
                self.dep_resolve_btn.pack_forget()

    # --- AUTO-DEPENDENCY SYSTEM ---
    def resolve_dependencies(self):
        deps = list(self.missing_dep_names)
        msg = f"Nebula will attempt to search Steam and download the following missing dependencies:\n\n{', '.join(deps[:10])}{'...' if len(deps)>10 else ''}\n\nProceed?"
        if not messagebox.askyesno("Resolve Dependencies", msg): return
            
        self.set_status(f"Resolving {len(deps)} dependencies...", color="#D946EF")
        def task():
            game = self.game_var.get()
            for dep in deps:
                self.root.after(0, lambda d=dep: self.set_status(f"Searching for {d}..."))
                results = self.engine.search_steam_workshop(game, dep)
                if results:
                    best_match = results[0]
                    url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={best_match['id']}"
                    self.root.after(0, lambda t=best_match['title'], u=url: self.add_to_download_queue(t, u))
                else:
                    print(f"Could not find dependency on Steam: {dep}")
        threading.Thread(target=task, daemon=True).start()

    # --- DB COLLECTION INTERACTIONS ---
    def update_collection_dropdown(self):
        game = self.game_var.get()
        colls = self.db.get_collections_list(game)
        self.collection_combo.configure(values=colls if colls else [""])
        
        last_coll = self.db.get_setting(f"last_collection_{game}")
        if last_coll and last_coll in colls: self.current_collection_var.set(last_coll)
        else: self.current_collection_var.set(colls[0] if colls else "")
        self.refresh_collection_view()

    def create_collection(self):
        name = simpledialog.askstring("New", "Collection name:")
        if name:
            game = self.game_var.get()
            self.db.create_collection(game, name)
            self.update_collection_dropdown()
            self.current_collection_var.set(name)
            self.db.set_setting(f"last_collection_{game}", name)
            self.refresh_collection_view()
            self.set_status(f"Collection '{name}' created.", color="#10B981")

    def delete_collection(self):
        name = self.current_collection_var.get()
        if name and messagebox.askyesno("Delete", f"Delete collection '{name}'?"):
            self.db.delete_collection(self.game_var.get(), name)
            self.update_collection_dropdown()
            self.set_status(f"Collection '{name}' deleted.", color="#10B981")

    def add_to_collection(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll: return
        mods = self.db.get_collection_mods(game, coll)
        for rel_path in self.installed_tree.selection():
            if str(rel_path).startswith("dl_"): continue 
            if rel_path not in mods: mods.append(rel_path)
        self.db.save_collection_mods(game, coll, mods)
        self.refresh_collection_view()

    def remove_from_collection(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll: return
        mods = self.db.get_collection_mods(game, coll)
        for rel_path in self.collection_tree.selection():
            if rel_path in mods: mods.remove(rel_path)
        self.db.save_collection_mods(game, coll, mods)
        self.refresh_collection_view()

    # --- ENGINE WRAPPERS ---
    def auto_sort(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll: return
        mod_list = self.db.get_collection_mods(game, coll)
        def get_weight(rel_path):
            data = self.installed_mods_data.get(rel_path)
            if not data: return 50
            try:
                with open(data["file_path"], 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                    if "total conversion" in content: return 10
                    if "ui" in content: return 20
                    if "patch" in content or "fix" in content: return 90
            except Exception: pass
            return 50
        mod_list.sort(key=get_weight)
        self.db.save_collection_mods(game, coll, mod_list)
        self.refresh_collection_view()
        self.set_status("Collection auto-sorted based on simple heuristics.", color="#10B981")

    def import_from_save(self):
        save_path = filedialog.askopenfilename(title="Select Save File", filetypes=[("Save Files", "*.sav")])
        if not save_path: return
        try:
            with zipfile.ZipFile(save_path, 'r') as z:
                mods_found = re.findall(r'"(mod/[^"]+\.mod)"', z.read('meta').decode('utf-8', errors='ignore')) if 'meta' in z.namelist() else []
            if mods_found:
                missing_mods = [m for m in mods_found if m not in self.installed_mods_data]
                if missing_mods:
                    msg = "⚠️ Missing required mods for this save:\n\n"
                    msg += "\n".join(missing_mods[:10])
                    if len(missing_mods) > 10: msg += f"\n...and {len(missing_mods)-10} more."
                    msg += "\n\nImport anyway?"
                    if not messagebox.askyesno("Missing Mods", msg):
                        return
                        
                coll_name = simpledialog.askstring("Import", "Enter new collection name:")
                if coll_name:
                    self.db.create_collection(self.game_var.get(), coll_name)
                    self.db.save_collection_mods(self.game_var.get(), coll_name, mods_found)
                    self.update_collection_dropdown()
                    self.current_collection_var.set(coll_name)
                    self.set_status(f"Imported save game load order into '{coll_name}'.", color="#10B981")
            else: self.set_status("No mods found inside save game.", color="#F59E0B")
        except Exception as e: self.set_status(f"Error parsing save: {e}", color="#EF4444")

    def launch_game(self):
        try: 
            self.engine.launch_game(self.game_var.get(), self.current_collection_var.get())
            self.set_status("Game launched successfully!", color="#10B981")
        except Exception as e: 
            self.set_status(f"Launch Error: {e}", color="#EF4444")

    def open_mod_folder(self):
        selected = self.installed_tree.selection()
        if selected and not str(selected[0]).startswith("dl_") and self.installed_mods_data.get(selected[0]):
            os.startfile(self.installed_mods_data[selected[0]]["content_path"])

    def delete_selected_mod(self):
        selected = self.installed_tree.selection()
        if not selected: return
        rel_path = selected[0]
        if str(rel_path).startswith("dl_"): return
        
        data = self.installed_mods_data.get(rel_path)
        if data and messagebox.askyesno("Delete", f"Permanently delete '{data['name']}'?"):
            if os.path.exists(data["file_path"]): os.remove(data["file_path"])
            if os.path.exists(data["content_path"]): shutil.rmtree(data["content_path"]) if os.path.isdir(data["content_path"]) else os.remove(data["content_path"])
            self.set_status(f"Deleted mod: {data['name']}")
            self.refresh_installed_mods()

    # --- MOD TOOLS & OPTIONS ---
    def open_tools_menu(self):
        tools_win = ctk.CTkToplevel(self.root)
        tools_win.title("Mod Toolkit")
        tools_win.geometry("450x380")
        tools_win.configure(fg_color=self.bg_color)
        tools_win.focus_force() 
        
        ctk.CTkButton(tools_win, text="🧹 Clean Orphaned Files", height=45, fg_color=self.pane_color, command=self.tool_clean).pack(fill="x", padx=40, pady=10)
        ctk.CTkButton(tools_win, text="⚠️ Detect Conflicts", height=45, fg_color=self.pane_color, command=self.tool_conflicts).pack(fill="x", padx=40, pady=10)
        ctk.CTkButton(tools_win, text="📦 Merge into Mega-Mod", fg_color=self.accent_color, hover_color=self.hover_color, height=45, command=self.tool_merge).pack(fill="x", padx=40, pady=10)
        ctk.CTkButton(tools_win, text="💾 Backup Save Games", fg_color="#059669", hover_color="#047857", height=45, command=self.tool_backup_saves).pack(fill="x", padx=40, pady=10)

    def tool_backup_saves(self):
        game = self.game_var.get()
        save_path = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=f"{game}_Saves_Backup.zip", filetypes=[("Zip", "*.zip")])
        if not save_path: return
        self.set_status("Backing up save games...", color="#F59E0B")
        
        def task():
            try:
                self.engine.backup_saves_zip(game, save_path)
                self.root.after(0, lambda: self.set_status("Save games backed up successfully!", color="#10B981"))
            except Exception as e:
                self.root.after(0, lambda: self.set_status(f"Backup failed: {e}", color="#EF4444"))
        threading.Thread(target=task, daemon=True).start()

    def tool_clean(self):
        orphans = self.engine.clean_junk(self.game_var.get())
        self.refresh_installed_mods()
        self.set_status(f"Cleaned {orphans} orphaned mod files.", color="#10B981")

    def tool_conflicts(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        active_data = [self.installed_mods_data.get(p) for p in self.db.get_collection_mods(game, coll)]
        conflicts = self.engine.find_conflicts(active_data)
        
        c_win = ctk.CTkToplevel(self.root)
        c_win.geometry("800x500")
        c_win.title("Conflicts")
        c_win.configure(fg_color=self.bg_color)
        c_win.focus_force()
        if not conflicts:
            ctk.CTkLabel(c_win, text="✅ No conflicts!", text_color="#10B981", font=("Segoe UI", 18)).pack(pady=50)
            return
        
        tree = ttk.Treeview(c_win, columns=("File", "Mods"), show="headings")
        tree.heading("File", text="File Path")
        tree.heading("Mods", text="Overwritten By")
        tree.column("File", width=300)
        tree.pack(fill="both", expand=True, padx=20, pady=20)
        for f, m in conflicts.items(): tree.insert("", "end", values=(f, " -> ".join(m)))

    def tool_merge(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll or not self.db.get_collection_mods(game, coll): return
        merged_name = simpledialog.askstring("Merge Collection", "Enter Mega-Mod Name (No spaces):")
        if not merged_name: return
        merged_name = merged_name.replace(" ", "_")

        self.set_status("Merging Mega-Mod in background. This may take a while...", color="#F59E0B")

        def task():
            try:
                self.engine.merge_mega_mod(game, coll, merged_name, self.installed_mods_data)
                self.root.after(0, lambda: self.set_status(f"Mega-Mod '{merged_name}' created successfully!", color="#10B981"))
                self.root.after(0, self.refresh_installed_mods)
            except Exception as e: 
                self.root.after(0, lambda: self.set_status(f"Merge error: {e}", color="#EF4444"))

        threading.Thread(target=task, daemon=True).start()

    def open_options(self):
        opt_win = ctk.CTkToplevel(self.root)
        opt_win.geometry("750x550")
        opt_win.title(f"Settings - {self.game_var.get()}")
        opt_win.configure(fg_color=self.bg_color)
        opt_win.focus_force()
        
        ctk.CTkLabel(opt_win, text=f"Options for {self.game_var.get()}", font=("Segoe UI", 20, "bold"), text_color=self.accent_color).pack(pady=(20, 15))

        container = ctk.CTkFrame(opt_win, fg_color=self.pane_color, corner_radius=10)
        container.pack(fill="both", expand=True, padx=20, pady=10)

        # General Options
        ctk.CTkLabel(container, text="General Options", font=("Segoe UI", 16, "bold"), text_color="#F8FAFC").pack(anchor="w", pady=(15, 10), padx=20)
        
        f_auto = ctk.CTkFrame(container, fg_color="transparent")
        f_auto.pack(fill="x", pady=5, padx=20)
        ctk.CTkLabel(f_auto, text="Check Workshop Updates on Startup:", width=250, anchor="w", font=("Segoe UI", 13)).pack(side="left")
        
        # Safely fetches without throwing TypeErrors (1 Arg Only)
        auto_update_var = ctk.StringVar(value=self.db.get_setting("auto_update_check") or "True")
        def toggle_auto_update(choice):
            self.db.set_setting("auto_update_check", choice)
        ctk.CTkOptionMenu(f_auto, values=["True", "False"], variable=auto_update_var, command=toggle_auto_update, fg_color="#0F172A", button_color=self.accent_color).pack(side="left")

        # API Cache Setting
        f_cache = ctk.CTkFrame(container, fg_color="transparent")
        f_cache.pack(fill="x", pady=5, padx=20)
        ctk.CTkLabel(f_cache, text="API Cache Expiry (Hours, 0 to always check):", width=300, anchor="w", font=("Segoe UI", 13)).pack(side="left")
        
        # Safely fetches without throwing TypeErrors
        cache_var = ctk.StringVar(value=self.db.get_setting("api_cache_hours") or "4")
        def set_cache(*args):
            self.db.set_setting("api_cache_hours", cache_var.get())
        cache_var.trace_add("write", set_cache)
        ctk.CTkEntry(f_cache, textvariable=cache_var, width=60, fg_color="#0F172A", border_color="#334155", text_color="#F8FAFC").pack(side="left")

        # Active Game Paths Only
        ctk.CTkLabel(container, text="Game Paths", font=("Segoe UI", 16, "bold"), text_color="#F8FAFC").pack(anchor="w", pady=(25, 10), padx=20)

        current_game = self.game_var.get()
        game_data = GAMES_MAP.get(current_game)
        game_id = game_data["id"] if game_data else ""

        def create_row(parent, label, key, is_dir=True):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(fill="x", pady=5, padx=20)
            ctk.CTkLabel(f, text=label, width=120, anchor="w", font=("Segoe UI", 13)).pack(side="left")
            e = ctk.CTkEntry(f, width=400, fg_color="#0F172A", border_color="#334155", text_color="#F8FAFC")
            e.insert(0, self.db.get_setting(key) or "")
            e.configure(state="readonly")
            e.pack(side="left", padx=(10, 10))
            def browse():
                path = filedialog.askdirectory() if is_dir else filedialog.askopenfilename(filetypes=[("Executable", "*.exe")])
                if path:
                    self.db.set_setting(key, path)
                    opt_win.destroy()
                    self.open_options()
            ctk.CTkButton(f, text="Browse", width=80, fg_color=self.accent_color, hover_color=self.hover_color, command=browse).pack(side="left")

        if game_id:
            create_row(container, "Mod Folder:", f"{game_id}_mod_path", True)
            create_row(container, "Executable:", f"{game_id}_exe_path", False)

        def restore():
            if game_id:
                self.db.set_setting(f"{game_id}_mod_path", game_data["default_mod"])
                self.db.set_setting(f"{game_id}_exe_path", game_data["default_exe"])
            opt_win.destroy()
            self.open_options()

        btn_f = ctk.CTkFrame(opt_win, fg_color="transparent")
        btn_f.pack(fill="x", pady=15, padx=20)
        ctk.CTkButton(btn_f, text="Restore Defaults", fg_color=self.pane_color, hover_color="#1E293B", command=restore).pack(side="left")
        ctk.CTkButton(btn_f, text="Close", fg_color=self.accent_color, command=opt_win.destroy).pack(side="right")

    # --- SHARE / LOAD ORDER CODES ---
    def share_load_order(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll: return
        mods = self.db.get_collection_mods(game, coll)
        wids = []
        for rel in mods:
            data = self.installed_mods_data.get(rel)
            if data and data.get("remote_id"): wids.append(str(data["remote_id"]))
        
        if not wids:
            messagebox.showinfo("Share Code", "No Steam Workshop mods found in this collection.")
            return
            
        code_str = "NEB-" + base64.b64encode(zlib.compress(",".join(wids).encode())).decode()
        
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Share Load Order")
        dlg.geometry("500x150")
        dlg.focus_force()
        dlg.configure(fg_color=self.bg_color)
        ctk.CTkLabel(dlg, text="Copy this Code to share your collection online:", text_color=self.accent_color, font=("Segoe UI", 14, "bold")).pack(pady=10)
        entry = ctk.CTkEntry(dlg, width=450, fg_color=self.pane_color)
        entry.insert(0, code_str)
        entry.configure(state="readonly")
        entry.pack(pady=5)
        ctk.CTkButton(dlg, text="Close", command=dlg.destroy, width=100, fg_color=self.pane_color, hover_color="#1E293B").pack(pady=10)

    def paste_load_order(self):
        code_str = simpledialog.askstring("Import Code", "Paste the NEB- share code here:")
        if not code_str: return
        try:
            raw = code_str.strip()
            if raw.startswith("NEB-"): raw = raw[4:]
            wids = zlib.decompress(base64.b64decode(raw)).decode().split(",")
            
            coll_name = simpledialog.askstring("Import Code", "Enter a name for this new collection:")
            if not coll_name: return
            
            game = self.game_var.get()
            new_mods = []
            missing_wids = []
            
            # Smart Placement Logic: Ensures we don't blindly ask for mods you already have under different folder names!
            for w in wids:
                existing_rel = next((p for p, d in self.installed_mods_data.items() if str(d.get("remote_id")) == str(w)), None)
                if existing_rel:
                    new_mods.append(existing_rel)
                else:
                    new_mods.append(f"mod/ugc_{w}.mod")
                    missing_wids.append(w)
            
            self.db.create_collection(game, coll_name)
            self.db.save_collection_mods(game, coll_name, new_mods)
            
            self.update_collection_dropdown()
            self.current_collection_var.set(coll_name)
            self.db.set_setting(f"last_collection_{game}", coll_name)
            
            if missing_wids:
                self.set_status(f"Fetching titles for {len(missing_wids)} missing mods...", color="#F59E0B")
                def fetch_and_queue():
                    cache_hours_str = self.db.get_setting("api_cache_hours") or "4"
                    try: cache_hours = float(cache_hours_str)
                    except: cache_hours = 4.0
                    api_data = self.engine.fetch_api_details(missing_wids, cache_hours=cache_hours)
                    for w in missing_wids:
                        title = api_data.get(str(w), {}).get("title", f"Mod {w}")
                        url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={w}"
                        self.root.after(0, lambda t=title, u=url: self.add_to_download_queue(t, u))
                threading.Thread(target=fetch_and_queue, daemon=True).start()
                
            self.refresh_collection_view()
            self.set_status("Collection imported via Code!", color="#10B981")
        except Exception as e:
            messagebox.showerror("Import Error", f"Invalid code format: {e}")

    # --- EXPORT / IMPORT (ZIP) ---
    def export_collection(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll: return
        save_path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("Zip", "*.zip")])
        if not save_path: return
        
        self.set_status("Exporting collection... please wait.", color="#F59E0B")
        def task():
            try:
                self.engine.export_collection_zip(game, coll, self.installed_mods_data, save_path)
                self.root.after(0, lambda: self.set_status("Collection exported successfully!", color="#10B981"))
            except Exception as e: 
                self.root.after(0, lambda: self.set_status(f"Export Failed: {e}", color="#EF4444"))
        threading.Thread(target=task, daemon=True).start()

    def import_collection(self):
        zip_path = filedialog.askopenfilename(filetypes=[("Zip", "*.zip")])
        if not zip_path: return
        coll_name = simpledialog.askstring("Import", "New collection name:")
        if not coll_name: return
        game = self.game_var.get()
        
        self.set_status("Importing collection... please wait.", color="#F59E0B")
        def task():
            try:
                new_mods = self.engine.import_collection_zip(game, zip_path)
                self.root.after(0, lambda: self.finish_import(game, coll_name, new_mods))
            except Exception as e: 
                self.root.after(0, lambda: self.set_status(f"Import Failed: {e}", color="#EF4444"))
        threading.Thread(target=task, daemon=True).start()

    def finish_import(self, game, coll_name, new_mods):
        self.db.create_collection(game, coll_name)
        self.db.save_collection_mods(game, coll_name, new_mods)
        self.refresh_installed_mods()
        self.update_collection_dropdown()
        self.current_collection_var.set(coll_name)
        self.db.set_setting(f"last_collection_{game}", coll_name)
        self.refresh_collection_view()
        self.set_status("Collection imported successfully!", color="#10B981")

    # --- LOCAL INSTALL & DIRECT URL ---
    def open_install_local_dialog(self):
        dl_win = ctk.CTkToplevel(self.root)
        dl_win.geometry("400x200")
        dl_win.title("Install Local Mod")
        dl_win.configure(fg_color=self.bg_color)
        dl_win.focus_force()
        
        ctk.CTkLabel(dl_win, text="Install a Mod from your PC", font=("Segoe UI", 16, "bold"), text_color=self.accent_color).pack(pady=(20, 10))
        
        def install_zip():
            file_path = filedialog.askopenfilename(title="Select Mod Archive", filetypes=[("Zip Files", "*.zip"), ("All Files", "*.*")])
            if file_path:
                self.install_local_archive(file_path)
                dl_win.destroy()
                
        def install_folder():
            folder_path = filedialog.askdirectory(title="Select Mod Folder")
            if folder_path:
                self.install_local_folder(folder_path)
                dl_win.destroy()

        btn_f = ctk.CTkFrame(dl_win, fg_color="transparent")
        btn_f.pack(pady=10)
        ctk.CTkButton(btn_f, text="📦 Install from .ZIP", height=40, fg_color=self.pane_color, hover_color="#1E293B", command=install_zip).pack(side="left", padx=10)
        ctk.CTkButton(btn_f, text="📁 Install from Folder", height=40, fg_color=self.pane_color, hover_color="#1E293B", command=install_folder).pack(side="left", padx=10)

    def install_local_archive(self, file_path):
        target_path = self.engine.get_mod_path(self.game_var.get())
        self.set_status(f"Installing {os.path.basename(file_path)}...", color="#F59E0B")
        def task():
            try:
                with zipfile.ZipFile(file_path, 'r') as z:
                    z.extractall(target_path)
                self.root.after(0, lambda: self.set_status("Local mod installed successfully!", color="#10B981"))
                self.root.after(0, self.refresh_installed_mods)
            except Exception as e:
                self.root.after(0, lambda: self.set_status(f"Installation failed: {e}", color="#EF4444"))
        threading.Thread(target=task, daemon=True).start()
        
    def install_local_folder(self, folder_path):
        target_path = self.engine.get_mod_path(self.game_var.get())
        folder_name = os.path.basename(os.path.normpath(folder_path))
        dest_path = os.path.join(target_path, folder_name)
        
        self.set_status(f"Copying {folder_name}...", color="#F59E0B")
        def task():
            try:
                if os.path.exists(dest_path):
                    shutil.rmtree(dest_path)
                shutil.copytree(folder_path, dest_path)
                self.root.after(0, lambda: self.set_status("Local mod folder copied successfully!", color="#10B981"))
                self.root.after(0, self.refresh_installed_mods)
            except Exception as e:
                self.root.after(0, lambda: self.set_status(f"Copy failed: {e}", color="#EF4444"))
        threading.Thread(target=task, daemon=True).start()

    def open_download_dialog(self):
        dl_win = ctk.CTkToplevel(self.root)
        dl_win.geometry("550x300")
        dl_win.title("Direct Download")
        dl_win.configure(fg_color=self.bg_color)
        dl_win.focus_force() 
        
        ctk.CTkLabel(dl_win, text="Paste Steam Workshop URLs or Direct .ZIP links:", font=("Segoe UI", 16, "bold"), text_color=self.accent_color).pack(pady=(15, 0))
        ctk.CTkLabel(dl_win, text="(One link per line, Ctrl+V works here)", font=("Segoe UI", 12, "italic"), text_color="#94A3B8").pack(pady=(0, 10))
        
        url_text = ctk.CTkTextbox(dl_win, height=120, width=500, fg_color=self.pane_color, text_color="#F8FAFC")
        url_text.pack(pady=5)
        btn = ctk.CTkButton(dl_win, text="Queue Downloads", height=40, fg_color=self.accent_color, hover_color=self.hover_color)
        btn.pack(pady=15)

        def run():
            urls = [u.strip() for u in url_text.get("1.0", tk.END).split("\n") if u.strip()]
            for url in urls:
                self.add_to_download_queue("Link Download", url)
            dl_win.destroy()
        btn.configure(command=run)

    # --- WORKSHOP BROWSER UI ---
    def open_workshop_browser(self):
        # Guarantee singleton window! Prevents opening multiple instances.
        if hasattr(self, 'wb_win') and self.wb_win is not None and self.wb_win.winfo_exists():
            self.wb_win.deiconify()
            self.wb_win.focus_force()
            return
            
        self.wb_win = ctk.CTkToplevel(self.root)
        self.wb_win.geometry("950x750")
        self.wb_win.title(f"Steam Workshop Browser - {self.game_var.get()}")
        self.wb_win.configure(fg_color=self.bg_color)
        self.wb_win.focus_force()
        
        def fast_close():
            self.wb_win.withdraw()
            self.root.after(50, self.wb_win.destroy)
        self.wb_win.protocol("WM_DELETE_WINDOW", fast_close)
        
        # Context Menu for Workshop Browser
        self.ws_ctx_menu = tk.Menu(self.wb_win, tearoff=0, bg=self.pane_color, fg="#ffffff", activebackground=self.accent_color, relief="flat", borderwidth=0)
        self.ws_ctx_menu.add_command(label="View in Workshop")
        
        top_ctrl = ctk.CTkFrame(self.wb_win, fg_color="transparent")
        top_ctrl.pack(fill="x", padx=20, pady=15)
        
        search_var = ctk.StringVar()
        sort_var = ctk.StringVar(value="Trending")
        page_var = tk.IntVar(value=1)
        
        sort_map = {"Trending": "trend", "Top Rated": "toprated", "Most Recent": "mostrecent"}
        time_options = {"All Time": "all", "1 Day": "1", "1 Week": "7", "1 Month": "30", "3 Months": "90", "6 Months": "180", "1 Year": "365", "Custom Date": "custom"}
        time_display_var = ctk.StringVar(value="3 Months")
        
        ctk.CTkEntry(top_ctrl, textvariable=search_var, placeholder_text="Search mods...", width=200, fg_color=self.pane_color).pack(side="left", padx=(10, 5))
        ctk.CTkOptionMenu(top_ctrl, variable=sort_var, values=list(sort_map.keys()), width=130, fg_color=self.pane_color, button_color=self.accent_color).pack(side="left", padx=5)
        
        ctk.CTkLabel(top_ctrl, text="Updated Since:", text_color="#E2E8F0").pack(side="left", padx=(10, 5))
        time_dropdown = ctk.CTkOptionMenu(top_ctrl, variable=time_display_var, values=list(time_options.keys()), width=110, fg_color=self.pane_color, button_color=self.accent_color)
        time_dropdown.pack(side="left", padx=5)
        
        custom_date_entry = ctk.CTkEntry(top_ctrl, placeholder_text="YYYY-MM-DD", width=110, fg_color=self.pane_color)
        
        def handle_time_dropdown(choice):
            if choice == "Custom Date": custom_date_entry.pack(side="left", padx=5)
            else: custom_date_entry.pack_forget()
        time_dropdown.configure(command=handle_time_dropdown)
        
        results_frame = ctk.CTkScrollableFrame(self.wb_win, fg_color="transparent")
        results_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        
        bot_ctrl = ctk.CTkFrame(self.wb_win, fg_color="transparent")
        bot_ctrl.pack(fill="x", padx=20, pady=10)
        
        lbl_page = ctk.CTkLabel(bot_ctrl, text="Page 1", font=("Segoe UI", 14, "bold"), text_color=self.accent_color)
        lbl_page.pack(side="left", expand=True)
        
        loaded_images = {}
        
        button_updaters = []
        def update_all_btns():
            for fn in button_updaters: fn()
            
        self.workshop_ui_updater = update_all_btns
        self.wb_win.bind("<Destroy>", lambda e: setattr(self, 'workshop_ui_updater', None) if e.widget == self.wb_win else None)
        
        selected_card = [None]
        def select_card(card):
            if selected_card[0]: selected_card[0].configure(fg_color=self.pane_color, border_color=self.pane_color)
            card.configure(fg_color="#1E293B", border_width=1, border_color=self.accent_color)
            selected_card[0] = card
        
        def open_browser_link(wid):
            webbrowser.open(f"https://steamcommunity.com/sharedfiles/filedetails/?id={wid}")
            
        def on_ws_right_click(event, card, wid):
            select_card(card)
            self.ws_ctx_menu.entryconfig("View in Workshop", command=lambda: open_browser_link(wid))
            self.ws_ctx_menu.post(event.x_root, event.y_root)
            
        def delete_mod_from_workshop(rel_path):
            if messagebox.askyesno("Delete", "Permanently delete this installed mod?", parent=self.wb_win):
                data = self.installed_mods_data.get(rel_path)
                if data:
                    if os.path.exists(data["file_path"]): os.remove(data["file_path"])
                    if os.path.exists(data["content_path"]): shutil.rmtree(data["content_path"]) if os.path.isdir(data["content_path"]) else os.remove(data["content_path"])
                self.set_status("Mod deleted.", color="#10B981")
                self.refresh_installed_mods()
                update_all_btns()

        def cancel_queue_from_workshop(wid):
            task = next((t for t in self.download_queue if t["url"].endswith(wid)), None)
            if task:
                self.download_queue = [t for t in self.download_queue if t["id"] != task["id"]]
                self.engine.cancel_download(task["id"])
                self.set_status("Download cancelled.", color="#F59E0B")
                self.refresh_installed_mods()
                update_all_btns()
        
        def toggle_download(wid, title):
            url = f"https://steamcommunity.com/sharedfiles/filedetails/?id={wid}"
            self.add_to_download_queue(title, url)
            update_all_btns()

        def load_results():
            for widget in results_frame.winfo_children(): widget.destroy()
            button_updaters.clear()
            lbl_loading = ctk.CTkLabel(results_frame, text="Intercepting Comms... (Querying Steam API)", font=("Segoe UI", 18), text_color=self.accent_color)
            lbl_loading.pack(pady=50)
            
            def fetch():
                game = self.game_var.get()
                query = search_var.get()
                sort = sort_map[sort_var.get()]
                page = page_var.get()
                
                days = time_options[time_display_var.get()]
                if days == "custom":
                    try:
                        date_obj = datetime.datetime.strptime(custom_date_entry.get().strip(), "%Y-%m-%d")
                        delta = datetime.datetime.now() - date_obj
                        days = str(max(1, delta.days))
                    except: days = "all" 
                
                results = self.engine.search_steam_workshop(game, query, page, sort, days)
                self.root.after(0, lambda: render_results(results, lbl_loading))
            
            threading.Thread(target=fetch, daemon=True).start()
        
        def render_results(results, loader_lbl):
            loader_lbl.destroy()
            if not results:
                ctk.CTkLabel(results_frame, text="No results found matching those filters.", font=("Segoe UI", 16), text_color="#94A3B8").pack(pady=50)
                return
                
            for item in results:
                card = ctk.CTkFrame(results_frame, height=120, fg_color=self.pane_color, border_color=self.pane_color)
                card.pack(fill="x", pady=5, padx=10)
                card.pack_propagate(False)
                
                img_lbl = ctk.CTkLabel(card, text="...", width=100, height=100, fg_color="#0F172A")
                img_lbl.pack(side="left", padx=10, pady=10)
                
                info_f = ctk.CTkFrame(card, fg_color="transparent")
                info_f.pack(side="left", fill="both", expand=True, padx=10, pady=10)
                
                lbl_title = ctk.CTkLabel(info_f, text=item["title"], font=("Segoe UI", 16, "bold"), text_color="#F8FAFC", anchor="w")
                lbl_title.pack(fill="x")
                lbl_updated = ctk.CTkLabel(info_f, text=f"Last Updated: {item.get('last_updated', 'Unknown')}", font=("Segoe UI", 12), text_color="#94A3B8", anchor="w")
                lbl_updated.pack(fill="x")
                lbl_id = ctk.CTkLabel(info_f, text=f"ID: {item['id']}", font=("Segoe UI", 10), text_color="#475569", anchor="w")
                lbl_id.pack(fill="x")
                
                # Binds for Left/Right/Double Click
                for widget in [card, img_lbl, info_f, lbl_title, lbl_updated, lbl_id]:
                    widget.bind("<Button-1>", lambda e, c=card: select_card(c))
                    widget.bind("<Button-3>", lambda e, c=card, w=item["id"]: on_ws_right_click(e, c, w))
                    widget.bind("<Double-1>", lambda e, w=item["id"]: open_browser_link(w))
                
                btn_dl = ctk.CTkButton(card, width=120)
                btn_dl.pack(side="right", padx=20)
                
                def update_btn(b=btn_dl, wid=item["id"], title=item["title"]):
                    is_installed = False
                    installed_rel_path = None
                    for rel, data in self.installed_mods_data.items():
                        if f"{wid}" in str(rel) or f"{wid}" in str(data.get("content_path", "")) or f"{wid}" in str(data.get("file_path", "")):
                            is_installed = True
                            installed_rel_path = rel
                            break
                            
                    if is_installed:
                        b.configure(text="🗑 Delete Mod", fg_color="#9F1239", hover_color="#881337")
                        b.configure(command=lambda r=installed_rel_path: delete_mod_from_workshop(r))
                    elif any(t["url"].endswith(wid) for t in self.download_queue):
                        b.configure(text="✖ Cancel Queue", fg_color="#F59E0B", hover_color="#D97706")
                        b.configure(command=lambda w=wid: cancel_queue_from_workshop(w))
                    else:
                        b.configure(text="⬇ Download", fg_color="#059669", hover_color="#047857")
                        b.configure(command=lambda w=wid, t=title: toggle_download(w, t))
                
                button_updaters.append(update_btn)
                update_btn() 
                
                def load_img(url, label, wid):
                    try:
                        if wid in loaded_images:
                            self.root.after(0, lambda: label.configure(image=loaded_images[wid], text=""))
                            return
                        if not url: return
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req) as response: img_data = response.read()
                        img = Image.open(io.BytesIO(img_data))
                        
                        if img.mode not in ("RGB", "RGBA"):
                            img = img.convert("RGBA")
                            
                        img.thumbnail((100, 100))
                        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                        loaded_images[wid] = ctk_img
                        self.root.after(0, lambda: label.configure(image=ctk_img, text=""))
                    except Exception as e:
                        pass
                        
                threading.Thread(target=load_img, args=(item["image_url"], img_lbl, item["id"]), daemon=True).start()
                
        def do_search():
            page_var.set(1)
            lbl_page.configure(text="Page 1")
            load_results()
            
        def next_page():
            page_var.set(page_var.get() + 1)
            lbl_page.configure(text=f"Page {page_var.get()}")
            load_results()
            
        def prev_page():
            if page_var.get() > 1:
                page_var.set(page_var.get() - 1)
                lbl_page.configure(text=f"Page {page_var.get()}")
                load_results()
                
        ctk.CTkButton(top_ctrl, text="🔍 Search", fg_color=self.accent_color, hover_color=self.hover_color, command=do_search).pack(side="left", padx=(10, 0))
        ctk.CTkButton(bot_ctrl, text="<< Prev", width=80, fg_color=self.pane_color, hover_color="#1E293B", command=prev_page).pack(side="left", padx=10)
        ctk.CTkButton(bot_ctrl, text="Next >>", width=80, fg_color=self.pane_color, hover_color="#1E293B", command=next_page).pack(side="right", padx=10)
        
        load_results()