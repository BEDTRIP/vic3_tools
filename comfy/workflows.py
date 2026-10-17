"""Shim: the workflows live in vic3tools.gfx.workflows (`v3 gfx workflows ...`); this runs them with ComfyUI's own
Python (which has torch for the vic3 node specs): <ComfyUI>/.venv/Scripts/python.exe comfy/workflows.py save|run|list"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vic3tools.gfx.workflows import main  # noqa: E402

if __name__ == "__main__":
    main()
