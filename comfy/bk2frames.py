"""Stills from the game's Bink 2 videos (.bk2) through its own bink2w64.dll: vanilla event pictures are videos
(gfx/event_pictures/*.bk2, ffmpeg does not read Bink 2), and a still is what a sample for generation needs.

    py comfy/bk2frames.py OUTDIR FILE.bk2... [--at 0.6]     # one PNG per video, the frame at that share of it

The first frames are often black (a fade-in): take one from the middle. 64-bit Python with Pillow.
"""
import ctypes, os, sys
from PIL import Image
GAME = r"C:\games\steam\steamapps\common\Victoria 3\binaries"
os.add_dll_directory(GAME)
dll = ctypes.WinDLL(os.path.join(GAME, "bink2w64.dll"))
dll.BinkOpen.restype = ctypes.c_void_p
dll.BinkOpen.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
for f in ("BinkDoFrame", "BinkNextFrame", "BinkClose"):
    getattr(dll, f).argtypes = [ctypes.c_void_p]
dll.BinkCopyToBuffer.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32]
dll.BinkGoto.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32]
dll.BinkGetError.restype = ctypes.c_char_p
args = sys.argv[1:]
if "--at" in args:
    del args[args.index("--at"):args.index("--at") + 2]
out, files = args[0], args[1:]
at = float(sys.argv[sys.argv.index("--at") + 1]) if "--at" in sys.argv else 0.6
fmt = 5  # BINKSURFACE32BGRA
for f in files:
    h = dll.BinkOpen(f.encode(), 0)
    if not h:
        print("FAIL", f, dll.BinkGetError()); continue
    w, hh, frames = (ctypes.c_uint32 * 3).from_address(h)
    target = int(frames * at)
    if target:
        dll.BinkGoto(h, target + 1, 0)
    dll.BinkDoFrame(h)
    buf = ctypes.create_string_buffer(w * hh * 4)
    dll.BinkCopyToBuffer(h, buf, w * 4, hh, 0, 0, fmt | 0x80000000)
    im = Image.frombuffer("RGBA", (w, hh), buf.raw, "raw", "BGRA", 0, 1).convert("RGB")
    name = os.path.splitext(os.path.basename(f))[0] + ".png"
    im.save(os.path.join(out, name)); print(name, w, hh, frames)
    dll.BinkClose(h)
