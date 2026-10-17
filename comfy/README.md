# comfy — Victoria 3 graphics in ComfyUI

## Install (once, ComfyUI Desktop)

```
mklink /J "<ComfyUI>\custom_nodes\v3_nodes" "<vic3_tools>\comfy\v3_nodes"
```

`v3_nodes/v3_nodes.json` (not in git) — roots for paths: `{"game": ".../Victoria 3/game", "fork": "<mod>",
"workshop": ".../workshop/content/529340"}`; without it the usual Steam folders are tried. Restart ComfyUI after
installing or changing the nodes (Desktop: menu → Restart; the server has no restart endpoint).

## Nodes (category `vic3`)

| node | what |
| --- | --- |
| V3 Load Game Image | .dds / .png by its path in the game's tree (`root` game / fork / workshop / absolute); alpha → mask |
| V3 Roll, V3 Seam Mask, V3 Tile | seamless piece: shift by half with wrap, the band to repaint, check by repeating |
| V3 Mirror, V3 Sprite Border | the piece as the game draws it: `mirror = horizontal`, `spriteborder` + Corneredtiled / stretched |
| V3 Blend, V3 Fill, V3 Gray | layers: overlay, multiply, alphamultiply, add, screen …; flat colour; grey layer |
| V3 Text | a caption in a font of `game/fonts` |
| V3 Sheet | a labelled contact sheet |

Masks follow ComfyUI: 1 = transparent / to repaint. Images with alpha (Qwen Image 2.1 decodes RGBA) are taken
as RGB + mask.

## Workflows

`workflows.py` describes the workflows once; sockets and widget order come from the running ComfyUI's
`/object_info`. Run it with ComfyUI's Python (it has torch, needed for the vic3 node specs before a restart):

```
<ComfyUI>\.venv\Scripts\python.exe comfy\workflows.py save [--model qwen21|zimage|klein4b|krea2] [--only ld_1]
<ComfyUI>\.venv\Scripts\python.exe comfy\workflows.py run ld_10 --set "Промпт (Qwen 2.1).prompt=..." --out DIR [--previews]
```

| workflow | for |
| --- | --- |
| ld_00 | memo: sizes, how the game builds a picture, layers, themes, the nodes |
| ld_01 | four models on one prompt and the same samples → a labelled sheet |
| ld_10 | a layer by samples (in its own form: grey ornament, no frame); a piece, not a stretched band |
| ld_11 | seamless piece: roll by half, repaint the seam band, roll back, 3×1 check |
| ld_12 | end + repeat for `spriteborder` and the mirror: outpaint the end, then the whole header as the game draws it |
| ld_20 | icon: plain background → Qwen 2.1 background removal (real alpha) → vanilla size, light / dark preview |
| ld_30 | illustration in the game's proportions |
| ld_40 | refine: RealESRGAN ×4 → img2img at low denoise; repaint a part by a MaskEditor mask |
| ld_50 | the fullscreen header's layers as the game stacks them (colour, cloth, velvet, shading, shape mask, ornament, frame, caption) |

`save` overwrites the workflow in ComfyUI: hand edits made there are lost when it is rebuilt.
