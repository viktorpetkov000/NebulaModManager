import customtkinter as ctk
from database import DatabaseManager
from mod_engine import ModEngine
from gui import NebulaModManager

if __name__ == "__main__":
    # Initialize the App Theme
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    
    # Initialize Architecture Layers
    db = DatabaseManager()
    engine = ModEngine(db)
    
    # Inject Model and Controller into the View
    app = NebulaModManager(root, db, engine)
    
    # Start Program
    root.mainloop()