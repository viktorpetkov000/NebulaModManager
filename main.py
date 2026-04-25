import customtkinter as ctk
from database import DatabaseManager
from mod_engine import ModEngine
from gui import NebulaModManager
import socket
import sys
import threading

def enforce_single_instance(root):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 33999))
        s.listen(1)
        
        def listen_for_wakeup():
            while True:
                try:
                    conn, addr = s.accept()
                    data = conn.recv(1024)
                    if b"WAKEUP" in data:
                        root.after(0, root.deiconify)
                        root.after(0, root.lift)
                        root.after(0, root.focus_force)
                    conn.close()
                except: pass
                
        threading.Thread(target=listen_for_wakeup, daemon=True).start()
        return s  # Keep socket alive
    except OSError:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", 33999))
            s.sendall(b"WAKEUP")
            s.close()
        except: pass
        sys.exit(0)

if __name__ == "__main__":
    # Initialize the App Theme
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    
    # Enforce Single Instance
    _sock = enforce_single_instance(root)
    
    # Initialize Architecture Layers
    db = DatabaseManager()
    engine = ModEngine(db)
    
    # Inject Model and Controller into the View
    app = NebulaModManager(root, db, engine)
    
    # Start Program
    root.mainloop()