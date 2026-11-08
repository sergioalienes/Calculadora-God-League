import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import main app
import main
import customtkinter as ctk

print("Testing Main App Headless Initialization...")
root = main.CalculadoraApp()
root.withdraw()

# Select module charts
root.navigate_to("charts")
root.update_idletasks()

print("[OK] Main App initialized and navigated to 'charts' tab successfully without errors!")
root.destroy()
