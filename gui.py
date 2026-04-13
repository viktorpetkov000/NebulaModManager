import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import customtkinter as ctk
import threading
import os
import shutil
from database import GAMES_MAP

class NebulaModManager:
    def __init__(self, root, db, engine):
        self.root = root
        self.db = db
        self.engine = engine
        
        self.root.title("Nebula Mod Manager")
        self.root.geometry("1250x750")
        self.root.minsize(1000, 600)
        
        self.installed_mods_data = {}
        self.drag_data = None

        self.apply_treeview_styles()
        self.build_ui()
        self.refresh_installed_mods()
        self.update_collection_dropdown()

    def apply_treeview_styles(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2b2b2b", foreground="#ffffff", fieldbackground="#2b2b2b", rowheight=28, borderwidth=0, font=("Segoe UI", 10))
        style.map("Treeview", background=[("selected", "#1f538d")])
        style.configure("Treeview.Heading", background="#3b3b3b", foreground="#ffffff", relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Treeview.Heading", background=[("active", "#1f538d")])

    def build_ui(self):
        top_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        top_frame.pack(fill="x", pady=15, padx=20)

        ctk.CTkLabel(top_frame, text="Game:", font=("Segoe UI", 14, "bold")).pack(side="left", padx=(0, 10))
        
        game_list = list(GAMES_MAP.keys())
        self.game_var = ctk.StringVar(value=game_list[0])
        ctk.CTkOptionMenu(top_frame, variable=self.game_var, values=game_list, command=self.on_game_switch, width=250).pack(side="left")

        ctk.CTkButton(top_frame, text="⚙ Options", fg_color="#3b3b3b", hover_color="#555555", command=self.open_options).pack(side="right")
        ctk.CTkButton(top_frame, text="🛠 Mod Tools", fg_color="#b53b3b", hover_color="#8c2e2e", command=self.open_tools_menu).pack(side="right", padx=10)

        main_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=5)

        # LEFT PANE
        left_pane = ctk.CTkFrame(main_frame)
        left_pane.pack(side="left", fill="both", expand=True)
        left_header = ctk.CTkFrame(left_pane, fg_color="transparent")
        left_header.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(left_header, text="Installed Mods", font=("Segoe UI", 16, "bold")).pack(side="left")
        
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self.filter_installed_mods)
        ctk.CTkEntry(left_header, textvariable=self.search_var, placeholder_text="Search mods...", width=200).pack(side="right")

        self.installed_tree = ttk.Treeview(left_pane, columns=("Mod Name", "Version"), show="headings")
        self.installed_tree.column("Mod Name", width=250)
        self.installed_tree.column("Version", width=80, anchor="center")
        for col in ("Mod Name", "Version"):
            self.installed_tree.heading(col, text=col, command=lambda c=col: self.tree_sort(self.installed_tree, c, False))
        self.installed_tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.ctx_menu = tk.Menu(self.root, tearoff=0, bg="#2b2b2b", fg="#ffffff", activebackground="#1f538d", relief="flat")
        self.ctx_menu.add_command(label="Open Folder in Explorer", command=self.open_mod_folder)
        self.ctx_menu.add_command(label="Delete Mod Permanently", command=self.delete_selected_mod)
        self.installed_tree.bind("<Button-3>", lambda e: self.ctx_menu.post(e.x_root, e.y_root) if self.installed_tree.identify_row(e.y) else None)

        # MID PANE
        mid_pane = ctk.CTkFrame(main_frame, fg_color="transparent")
        mid_pane.pack(side="left", fill="y", padx=15)
        ctk.CTkFrame(mid_pane, fg_color="transparent", height=150).pack()
        ctk.CTkButton(mid_pane, text="Add >>", width=100, command=self.add_to_collection).pack(pady=5)
        ctk.CTkButton(mid_pane, text="<< Remove", width=100, fg_color="#3b3b3b", hover_color="#555555", command=self.remove_from_collection).pack(pady=5)

        # RIGHT PANE
        right_pane = ctk.CTkFrame(main_frame)
        right_pane.pack(side="right", fill="both", expand=True)
        coll_ctrl = ctk.CTkFrame(right_pane, fg_color="transparent")
        coll_ctrl.pack(fill="x", padx=10, pady=10)
        
        self.current_collection_var = ctk.StringVar()
        self.collection_combo = ctk.CTkOptionMenu(coll_ctrl, variable=self.current_collection_var, command=self.on_collection_switch, width=150)
        self.collection_combo.pack(side="left", padx=(0, 5))

        ctk.CTkButton(coll_ctrl, text="New", width=50, command=self.create_collection).pack(side="left", padx=2)
        ctk.CTkButton(coll_ctrl, text="Del", width=50, fg_color="#b53b3b", hover_color="#8c2e2e", command=self.delete_collection).pack(side="left", padx=2)
        ctk.CTkButton(coll_ctrl, text="From Save", width=80, fg_color="#2b8256", hover_color="#1c593a", command=self.import_from_save).pack(side="left", padx=2)
        ctk.CTkButton(coll_ctrl, text="Auto-Sort", width=80, command=self.auto_sort).pack(side="left", padx=2)
        
        ctk.CTkButton(coll_ctrl, text="Import", width=60, fg_color="#3b3b3b", hover_color="#555555", command=self.import_collection).pack(side="right", padx=2)
        ctk.CTkButton(coll_ctrl, text="Export", width=60, fg_color="#3b3b3b", hover_color="#555555", command=self.export_collection).pack(side="right", padx=2)

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

        # BOTTOM PANE
        bottom = ctk.CTkFrame(self.root, fg_color="transparent")
        bottom.pack(fill="x", pady=15, padx=20)
        ctk.CTkButton(bottom, text="↻ Refresh Mods", fg_color="#3b3b3b", hover_color="#555555", command=self.refresh_installed_mods).pack(side="left")
        ctk.CTkButton(bottom, text="🚀 Launch Game", font=("Segoe UI", 14, "bold"), height=40, command=self.launch_game).pack(side="right", padx=(15, 0))
        ctk.CTkButton(bottom, text="⬇ Download New Mod(s)", height=40, fg_color="#3b3b3b", hover_color="#555555", command=self.open_download_dialog).pack(side="right")

    # --- UI EVENT LOGIC ---
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
        self.search_var.set("")
        self.update_collection_dropdown()
        self.refresh_installed_mods()

    def on_collection_switch(self, choice):
        self.refresh_collection_view()

    # --- REFRESH VIEWS ---
    def refresh_installed_mods(self):
        for item in self.installed_tree.get_children(): self.installed_tree.delete(item)
        game = self.game_var.get()
        self.installed_mods_data = self.engine.scan_installed_mods(game)
        self.filter_installed_mods()
        self.refresh_collection_view()

    def filter_installed_mods(self, *args):
        search_term = self.search_var.get().lower()
        for item in self.installed_tree.get_children(): self.installed_tree.delete(item)
        sorted_mods = sorted(self.installed_mods_data.items(), key=lambda x: x[1]["name"].lower())
        for rel_path, data in sorted_mods:
            if search_term in data["name"].lower():
                self.installed_tree.insert("", "end", iid=rel_path, values=(data["name"], data["version"]))

    def refresh_collection_view(self):
        for item in self.collection_tree.get_children(): self.collection_tree.delete(item)
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll: return
        
        for index, rel_path in enumerate(self.db.get_collection_mods(game, coll)):
            data = self.installed_mods_data.get(rel_path)
            if data: self.collection_tree.insert("", "end", iid=rel_path, values=(str(index+1), data["name"], data["version"]))

    # --- DB COLLECTION INTERACTIONS ---
    def update_collection_dropdown(self):
        colls = self.db.get_collections_list(self.game_var.get())
        self.collection_combo.configure(values=colls if colls else [""])
        self.current_collection_var.set(colls[0] if colls else "")
        self.refresh_collection_view()

    def create_collection(self):
        name = simpledialog.askstring("New", "Collection name:")
        if name:
            self.db.create_collection(self.game_var.get(), name)
            self.update_collection_dropdown()
            self.current_collection_var.set(name)
            self.refresh_collection_view()

    def delete_collection(self):
        name = self.current_collection_var.get()
        if name and messagebox.askyesno("Delete", f"Delete '{name}'?"):
            self.db.delete_collection(self.game_var.get(), name)
            self.update_collection_dropdown()

    def add_to_collection(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll: return
        mods = self.db.get_collection_mods(game, coll)
        for rel_path in self.installed_tree.selection():
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

    def import_from_save(self):
        save_path = filedialog.askopenfilename(title="Select Save File", filetypes=[("Save Files", "*.sav")])
        if not save_path: return
        try:
            import zipfile, re
            with zipfile.ZipFile(save_path, 'r') as z:
                mods_found = re.findall(r'"(mod/[^"]+\.mod)"', z.read('meta').decode('utf-8', errors='ignore')) if 'meta' in z.namelist() else []
            if mods_found:
                coll_name = simpledialog.askstring("Import", "Enter new collection name:")
                if coll_name:
                    self.db.create_collection(self.game_var.get(), coll_name)
                    self.db.save_collection_mods(self.game_var.get(), coll_name, mods_found)
                    self.update_collection_dropdown()
                    self.current_collection_var.set(coll_name)
            else: messagebox.showinfo("Info", "No mods found in save.")
        except Exception as e: messagebox.showerror("Error", str(e))

    def launch_game(self):
        try: self.engine.launch_game(self.game_var.get(), self.current_collection_var.get())
        except Exception as e: messagebox.showerror("Error", str(e))

    def open_mod_folder(self):
        selected = self.installed_tree.selection()
        if selected and self.installed_mods_data.get(selected[0]):
            os.startfile(self.installed_mods_data[selected[0]]["content_path"])

    def delete_selected_mod(self):
        selected = self.installed_tree.selection()
        if not selected: return
        rel_path = selected[0]
        data = self.installed_mods_data.get(rel_path)
        if data and messagebox.askyesno("Delete", f"Permanently delete '{data['name']}'?"):
            if os.path.exists(data["file_path"]): os.remove(data["file_path"])
            if os.path.exists(data["content_path"]): shutil.rmtree(data["content_path"]) if os.path.isdir(data["content_path"]) else os.remove(data["content_path"])
            self.refresh_installed_mods()

    # --- MOD TOOLS & OPTIONS ---
    def open_tools_menu(self):
        tools_win = ctk.CTkToplevel(self.root)
        tools_win.title("Mod Toolkit")
        tools_win.geometry("450x300")
        tools_win.attributes("-topmost", True)
        ctk.CTkButton(tools_win, text="🧹 Clean Orphaned Files", height=45, command=self.tool_clean).pack(fill="x", padx=40, pady=10)
        ctk.CTkButton(tools_win, text="⚠️ Detect Conflicts", height=45, command=self.tool_conflicts).pack(fill="x", padx=40, pady=10)
        ctk.CTkButton(tools_win, text="📦 Merge into Mega-Mod", fg_color="#1f538d", hover_color="#14375e", height=45, command=self.tool_merge).pack(fill="x", padx=40, pady=10)

    def tool_clean(self):
        orphans = self.engine.clean_junk(self.game_var.get())
        self.refresh_installed_mods()
        messagebox.showinfo("Clean", f"Deleted {orphans} orphaned files." if orphans > 0 else "Already clean!")

    def tool_conflicts(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        active_data = [self.installed_mods_data.get(p) for p in self.db.get_collection_mods(game, coll)]
        conflicts = self.engine.find_conflicts(active_data)
        
        c_win = ctk.CTkToplevel(self.root)
        c_win.geometry("800x500")
        c_win.title("Conflicts")
        if not conflicts:
            ctk.CTkLabel(c_win, text="✅ No conflicts!", text_color="#5cb85c", font=("Segoe UI", 18)).pack(pady=50)
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

        def task():
            try:
                self.engine.merge_mega_mod(game, coll, merged_name, self.installed_mods_data)
                self.root.after(0, lambda: messagebox.showinfo("Success", f"Created Mega-Mod: '{merged_name}'!"))
                self.root.after(0, self.refresh_installed_mods)
            except Exception as e: self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

        messagebox.showinfo("Merging", "Merge started. This may take a while.")
        threading.Thread(target=task, daemon=True).start()

    def open_options(self):
        opt_win = ctk.CTkToplevel(self.root)
        opt_win.geometry("850x650")
        opt_win.title("Settings")
        opt_win.attributes("-topmost", True)

        ctk.CTkLabel(opt_win, text="Application Paths", font=("Segoe UI", 18, "bold")).pack(pady=(15, 10))

        # Replaced static list with dynamic ScrollableFrame to support all games
        scroll_frame = ctk.CTkScrollableFrame(opt_win, width=800, height=500)
        scroll_frame.pack(pady=10, padx=20, fill="both", expand=True)

        def create_row(parent, label, key, is_dir=True):
            f = ctk.CTkFrame(parent, fg_color="transparent")
            f.pack(fill="x", pady=5, padx=10)
            ctk.CTkLabel(f, text=label, width=100, anchor="w").pack(side="left")
            e = ctk.CTkEntry(f, width=500)
            e.insert(0, self.db.get_setting(key))
            e.configure(state="readonly")
            e.pack(side="left", padx=(10, 10))
            def browse():
                path = filedialog.askdirectory() if is_dir else filedialog.askopenfilename(filetypes=[("Executable", "*.exe")])
                if path:
                    self.db.set_setting(key, path)
                    opt_win.destroy()
                    self.open_options()
            ctk.CTkButton(f, text="Browse", width=80, command=browse).pack(side="left")

        # Generate paths for every game mapped in the database
        for game_name, game_data in GAMES_MAP.items():
            game_id = game_data["id"]
            lbl = ctk.CTkLabel(scroll_frame, text=game_name, font=("Segoe UI", 14, "bold"), text_color="#1f538d")
            lbl.pack(anchor="w", pady=(15, 5), padx=10)
            create_row(scroll_frame, "Mod Folder:", f"{game_id}_mod_path", True)
            create_row(scroll_frame, "Executable:", f"{game_id}_exe_path", False)

        def restore():
            for game_name, game_data in GAMES_MAP.items():
                game_id = game_data["id"]
                self.db.set_setting(f"{game_id}_mod_path", game_data["default_mod"])
                self.db.set_setting(f"{game_id}_exe_path", game_data["default_exe"])
            opt_win.destroy()
            self.open_options()

        btn_f = ctk.CTkFrame(opt_win, fg_color="transparent")
        btn_f.pack(fill="x", pady=10, padx=20)
        ctk.CTkButton(btn_f, text="Restore All Defaults", fg_color="#3b3b3b", hover_color="#555555", command=restore).pack(side="left")
        ctk.CTkButton(btn_f, text="Close", command=opt_win.destroy).pack(side="right")

    # --- EXPORT / IMPORT / DOWNLOADS ---
    def export_collection(self):
        game, coll = self.game_var.get(), self.current_collection_var.get()
        if not coll: return
        save_path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("Zip", "*.zip")])
        if not save_path: return
        def task():
            try:
                self.engine.export_collection_zip(game, coll, self.installed_mods_data, save_path)
                self.root.after(0, lambda: messagebox.showinfo("Export", "Success!"))
            except Exception as e: self.root.after(0, lambda: messagebox.showerror("Export Failed", str(e)))
        messagebox.showinfo("Exporting", "Started in background...")
        threading.Thread(target=task, daemon=True).start()

    def import_collection(self):
        zip_path = filedialog.askopenfilename(filetypes=[("Zip", "*.zip")])
        if not zip_path: return
        coll_name = simpledialog.askstring("Import", "New collection name:")
        if not coll_name: return
        game = self.game_var.get()
        def task():
            try:
                new_mods = self.engine.import_collection_zip(game, zip_path)
                self.root.after(0, lambda: self.finish_import(game, coll_name, new_mods))
            except Exception as e: self.root.after(0, lambda: messagebox.showerror("Import Failed", str(e)))
        messagebox.showinfo("Importing", "Started...")
        threading.Thread(target=task, daemon=True).start()

    def finish_import(self, game, coll_name, new_mods):
        self.db.create_collection(game, coll_name)
        self.db.save_collection_mods(game, coll_name, new_mods)
        self.refresh_installed_mods()
        self.update_collection_dropdown()
        self.current_collection_var.set(coll_name)
        self.refresh_collection_view()

    def open_download_dialog(self):
        dl_win = ctk.CTkToplevel(self.root)
        dl_win.geometry("550x380")
        dl_win.title("Download Mods")
        dl_win.attributes("-topmost", True)
        ctk.CTkLabel(dl_win, text="Paste Direct .ZIP URLs (One per line):", font=("Segoe UI", 14)).pack(pady=(15, 5))
        url_text = ctk.CTkTextbox(dl_win, height=200, width=500)
        url_text.pack(pady=5)
        btn = ctk.CTkButton(dl_win, text="Download & Install", height=40)
        btn.pack(pady=15)

        def run():
            urls = [u.strip() for u in url_text.get("1.0", tk.END).split("\n") if u.strip()]
            if not urls: return
            btn.configure(state="disabled", text="Downloading...")
            def task():
                success_count, failed_urls = self.engine.batch_download_mods(self.game_var.get(), urls)
                self.root.after(0, lambda: dl_win.destroy())
                self.root.after(0, self.refresh_installed_mods)
                
                def show_result():
                    if failed_urls:
                        if success_count == 0:
                            messagebox.showerror("Download Failed", "Failed to download any mods. Check your links and internet connection.")
                        else:
                            error_msg = f"Successfully downloaded {success_count} mods.\n\nFailed to download {len(failed_urls)} mods:\n" + "\n".join(failed_urls)
                            messagebox.showwarning("Partial Success", error_msg)
                    else:
                        messagebox.showinfo("Done", f"Successfully downloaded {success_count} mods!")
                
                self.root.after(0, show_result)
                
            threading.Thread(target=task, daemon=True).start()
        btn.configure(command=run)