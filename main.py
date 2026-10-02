"""
Main entry point for ZeroMeta.
- Double-clicking or running without args opens the Modern Desktop GUI.
- Passing command line arguments runs the CLI processor.
"""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] not in ("--gui", "-g"):
        from cli import main as cli_main
        cli_main()
    else:
        from gui.main_window import launch_gui
        launch_gui()
