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

`vic3tools/gfx/workflows.py` describes the workflows once; sockets and widget order come from the running ComfyUI's
`/object_info`. `v3 gfx workflows ...` (or `comfy/workflows.py` with ComfyUI's own Python, which has torch for the
vic3 node specs before ComfyUI has loaded them):

```
v3 gfx workflows save [--model qwen21|zimage|klein4b|krea2] [--only ld_1]
v3 gfx workflows run ld_10 --set "Промпт (Qwen 2.1).prompt=..." --out DIR [--previews] [--repeat N]
```

| workflow | for |
| --- | --- |
| ld_00 | memo: sizes, how the game builds a picture, layers, themes, the nodes |
| ld_01 | four models on one prompt and the same samples → a labelled sheet |
| ld_02 | variants of one picture: Qwen 2.1 and FLUX.2 klein, one per run (Run ×N) — what `v3 gfx gen` runs |
| ld_10 | a layer by samples (in its own form: grey ornament, no frame); a piece, not a stretched band |
| ld_11 | seamless piece: roll by half, repaint the seam band, roll back, 3×1 check |
| ld_12 | end + repeat for `spriteborder` and the mirror: outpaint the end, then the whole header as the game draws it |
| ld_20 | icon: plain background → Qwen 2.1 background removal (real alpha) → vanilla size, light / dark preview |
| ld_30 | illustration in the game's proportions |
| ld_40 | refine: RealESRGAN ×4 → img2img at low denoise; repaint a part by a MaskEditor mask |
| ld_50 | the fullscreen header's layers as the game stacks them (colour, cloth, velvet, shading, shape mask, ornament, frame, caption) |

`save` overwrites the workflow in ComfyUI: hand edits made there are lost when it is rebuilt.

## Vanilla samples that are not pictures

Vanilla event pictures are Bink 2 videos (`gfx/event_pictures/*.bk2`, DLC — `dlc/<dlc>/gfx/event_pictures/`); ffmpeg
does not read Bink 2. `bk2frames.py` takes a still from each through the game's own `bink2w64.dll` (64-bit Python
with Pillow): `py comfy/bk2frames.py <ComfyUI input>/vanilla_events <...>.bk2 ...` — then Load Image, or V3 Load Game
Image with `root = absolute`.

## Cards: `v3 gfx`

A picture of a mod is a card `<mod>/gfx_src/<kind>/<name>.toml` (target DDS, kind, prompt, vanilla samples, sizes,
models, steps) next to the chosen source `<name>.png`; variants go to `<name>.variants/` (keep it out of git).

```
v3 gfx new  <mod>/gfx_src/goods/x.toml --kind goods --target gfx/interface/icons/goods_icons/x.dds --prompt "..."
v3 gfx gen  <card> --repeat 4      # Q1..Q4, K1..K4 + variants.png
v3 gfx pick <card> Q3              # cut out (Qwen 2.1 second pass) when the kind needs it -> x.png
v3 gfx build <card> | --mod <mod>  # x.png -> size / tint / grey -> the DDS (BGRA8 + mips, as vanilla)
v3 gfx check <file.dds>...         # format, mips, size against vanilla of the same folder
```

Kinds (`vic3tools/gfx/cards.py`, from the survey of vanilla's interface): goods, invention, event_icon, building,
law (grey relief, tinted bronze), production_method and timed_modifier (grey relief, tinted), logo, event,
illustration, layer.
