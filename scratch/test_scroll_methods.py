import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.stdout.reconfigure(encoding='utf-8')

import customtkinter as ctk

def test_scroll():
    app = ctk.CTk()
    app.geometry("800x600")

    scroll = ctk.CTkScrollableFrame(app)
    scroll.pack(fill="both", expand=True)

    print("scroll methods:", [m for m in dir(scroll) if "mouse" in m.lower() or "scroll" in m.lower()])

    app.destroy()

if __name__ == "__main__":
    test_scroll()
