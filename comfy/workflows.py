"""Build ComfyUI workflows (the UI format the user opens and edits) for Victoria 3 graphics, and run them.

    py comfy/workflows.py save [--model qwen21] [--only ld_11]   # -> ComfyUI's Workflows list (user/default/workflows)
    py comfy/workflows.py run ld_01 --set prompt="..." [--out DIR] # queue one through the API, wait, fetch the images
    py comfy/workflows.py list

A workflow is described here once (nodes by name, links by output name); the node's sockets and the order of its
widget values come from the running ComfyUI's /object_info, so the file the user gets is what the editor itself writes.
The generator part is a "model" block (qwen21, zimage, klein4b, krea2): after the comparison (ld_01) the chosen one is
put into all workflows by `save --model X`. Notes inside each workflow (MarkdownNote) say what it is for and how the
game uses the result; ld_00 is the memo. The vic3 nodes come from comfy/v3_nodes (a junction in custom_nodes).
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

URL = "http://127.0.0.1:8188"
HERE = Path(__file__).parent
LINKABLE = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}  # widget types; anything else is a socket


def http(path, data=None, timeout=60):
    req = urllib.request.Request(URL + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"} if data is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body[:1] in (b"{", b"[") else body


_INFO = None


def info():
    global _INFO
    if _INFO is None:
        _INFO = http("/object_info")
        if "V3Roll" not in _INFO:  # the server has not loaded the vic3 nodes yet: take their specs from the module
            sys.path.insert(0, str(HERE))
            try:
                import v3_nodes
                for name, cls in v3_nodes.NODE_CLASS_MAPPINGS.items():
                    _INFO[name] = {"input": cls.INPUT_TYPES(), "output": list(cls.RETURN_TYPES),
                                   "output_name": list(getattr(cls, "RETURN_NAMES", cls.RETURN_TYPES))}
            except ImportError as e:  # torch is missing outside ComfyUI's venv
                print(f"note: vic3 node specs unavailable ({e}); run with ComfyUI's python", file=sys.stderr)
    return _INFO


def _is_widget(spec):
    t = spec[0]
    return isinstance(t, list) or t in LINKABLE


def _default(spec):
    t, opt = spec[0], (spec[1] if len(spec) > 1 else {}) or {}
    if "default" in opt:
        return opt["default"]
    if isinstance(t, list):
        return t[0] if t else ""
    if t == "COMBO":
        return (opt.get("options") or [""])[0]
    return {"INT": 0, "FLOAT": 0.0, "STRING": "", "BOOLEAN": False}.get(t)


class Node:
    def __init__(self, g, nid, type_, values, pos, title, size):
        self.g, self.id, self.type, self.values, self.pos, self.title, self.size = g, nid, type_, values, pos, title, size
        self.links_in = {}  # input name -> (src node, src slot)

    def __getitem__(self, out):  # node["IMAGE"] / node[0] -> (node, slot)
        if isinstance(out, int):
            return (self, out)
        names = self.g.out_names(self.type)
        if out not in names:
            raise KeyError(f"{self.type} has no output {out}: {names}")
        return (self, names.index(out))


class Graph:
    def __init__(self, name):
        self.name, self.nodes, self.groups, self._id = name, [], [], 0

    def out_names(self, type_):
        n = info()[type_]
        return list(n.get("output_name") or n["output"])

    def add(self, type_, pos, title=None, size=None, **kw):
        """kw: widget values by name, or (node, slot) for sockets."""
        self._id += 1
        if type_ in ("MarkdownNote", "Note"):
            n = Node(self, self._id, type_, kw, pos, title, size or [520, 400])
            self.nodes.append(n)
            return n
        if type_ not in info():
            raise KeyError(f"ComfyUI has no node {type_}")
        n = Node(self, self._id, type_, {}, pos, title, size)
        for k, v in kw.items():
            if isinstance(v, tuple) and isinstance(v[0], Node):
                n.links_in[k] = v
            else:
                n.values[k] = v
        self.nodes.append(n)
        return n

    def note(self, pos, text, size=None):
        return self.add("MarkdownNote", pos, size=size, text=text)

    def group(self, title, box, color="#3f789e"):
        self.groups.append({"title": title, "bounding": box, "color": color, "font_size": 24, "flags": {}})

    # -- the UI format
    def _inputs(self, n):
        spec = info()[n.type]["input"]
        req, opt = spec.get("required", {}), spec.get("optional", {})
        sockets, widgets = [], []
        for group, items in (("required", req), ("optional", opt)):
            for name, s in items.items():
                t = s[0]
                if t == "COMFY_AUTOGROW_V3":
                    tmpl = s[1]["template"]
                    inner = next(iter(tmpl["input"]["required"].values()))
                    for sub in tmpl["names"]:
                        key = f"{name}.{sub}"
                        if key in n.links_in:
                            sockets.append((key, inner[0], True, sub))
                    continue
                if t == "COMFY_DYNAMICCOMBO_V3":
                    choice = n.values.get(name, s[1]["options"][0]["key"])
                    widgets.append((name, choice))
                    o = next(o for o in s[1]["options"] if o["key"] == choice)
                    for sub, ss in {**o["inputs"].get("required", {}), **o["inputs"].get("optional", {})}.items():
                        widgets.append((f"{name}.{sub}", n.values.get(f"{name}.{sub}", _default(ss))))
                    continue
                if _is_widget(s) and not (s[1] if len(s) > 1 else {}).get("socketless"):
                    widgets.append((name, n.values.get(name, _default(s))))
                    if (s[1] if len(s) > 1 else {}).get("control_after_generate"):
                        widgets.append(("control_after_generate", n.values.get("control", "randomize")))
                    if (s[1] if len(s) > 1 else {}).get("image_upload"):
                        widgets.append(("upload", "image"))
                else:
                    sockets.append((name, "*" if isinstance(t, list) else t, group == "optional", name))
        return sockets, widgets

    def to_ui(self):
        links, lid = [], 0
        out_links = {}
        ui_nodes = []
        for order, n in enumerate(self.nodes):
            d = {"id": n.id, "type": n.type, "pos": list(n.pos), "size": n.size or [320, 120], "flags": {},
                 "order": order, "mode": 0, "properties": {"Node name for S&R": n.type}}
            if n.title:
                d["title"] = n.title
            if n.type in ("MarkdownNote", "Note"):
                d.update(inputs=[], outputs=[], widgets_values=[n.values["text"]], color="#432", bgcolor="#653")
                ui_nodes.append(d)
                continue
            sockets, widgets = self._inputs(n)
            ins = []
            for name, t, optional, label in sockets:
                link = None
                if name in n.links_in:
                    src, slot = n.links_in[name]
                    lid += 1
                    link = lid
                    links.append([lid, src.id, slot, n.id, len(ins), self.out_names(src.type) and info()[src.type]["output"][slot]])
                    out_links.setdefault((src.id, slot), []).append(lid)
                i = {"name": name, "localized_name": label, "type": t, "link": link}
                if optional:
                    i["shape"] = 7
                ins.append(i)
            d["inputs"] = ins
            d["widgets_values"] = [v for _, v in widgets]
            ui_nodes.append(d)
        for d, n in zip(ui_nodes, self.nodes):
            if n.type in ("MarkdownNote", "Note"):
                continue
            outs = info()[n.type]["output"]
            names = self.out_names(n.type)
            d["outputs"] = [{"name": names[i], "localized_name": names[i], "type": t,
                             "links": out_links.get((n.id, i)) or None} for i, t in enumerate(outs)]
        return {"id": f"ld-{self.name}", "revision": 0, "last_node_id": self._id, "last_link_id": lid,
                "nodes": ui_nodes, "links": links, "groups": self.groups, "config": {},
                "extra": {"ds": {"scale": 0.6, "offset": [40, 40]}}, "version": 0.4}

    # -- the API format (to queue it ourselves)
    def to_api(self):
        p = {}
        for n in self.nodes:
            if n.type in ("MarkdownNote", "Note"):
                continue
            _, widgets = self._inputs(n)
            ins = {k: v for k, v in widgets if k not in ("control_after_generate", "upload")}
            for k, (src, slot) in n.links_in.items():
                ins[k] = [str(src.id), slot]
            p[str(n.id)] = {"class_type": n.type, "inputs": ins, "_meta": {"title": n.title or n.type}}
        return p


# ---------------------------------------------------------------------------------------------------------------------
# generator blocks: (graph, x, y, prompt node/str, refs [(node, slot)], latent size, seed) -> IMAGE (node, slot)

def gen_qwen21(g, x, y, prompt, refs, width, height, steps=25, denoise=1.0, latent=None, mask=None):
    """Qwen Image 2.1 (edit model, up to 10 references <image1>..; RGBA output)."""
    unet = g.add("UNETLoader", (x, y), unet_name="qwen_image_2.1_int8_convrot.safetensors")
    clip = g.add("CLIPLoader", (x, y + 140), clip_name="qwen3vl_8b_int8_convrot.safetensors", type="qwen_image")
    vae = g.add("VAELoader", (x, y + 280), vae_name="qwen_image_2.1_vae_bf16.safetensors")
    cache = g.add("QwenImage21Cache", (x, y + 400), model=unet["MODEL"])
    kw = {f"images.image_{i + 1}": r for i, r in enumerate(refs)}
    enc = g.add("TextEncodeQwenImage21", (x + 360, y), size=[440, 360], title="Промпт (Qwen 2.1)", clip=clip["CLIP"],
                vae=vae["VAE"], prompt=prompt, negative_prompt="", resolution=1024, **kw)
    if latent is None:
        latent = g.add("EmptyLatentImage", (x + 360, y + 400), title="Размер генерации", width=width, height=height)["LATENT"]
    if mask is not None:
        latent = g.add("SetLatentNoiseMask", (x + 360, y + 540), samples=latent, mask=mask)["LATENT"]
    ks = g.add("KSampler", (x + 840, y), size=[320, 300], model=cache["MODEL"], positive=enc["positive"],
               negative=enc["negative"], latent_image=latent, seed=0, steps=steps, cfg=1.0, sampler_name="euler",
               scheduler="simple", denoise=denoise)
    dec = g.add("VAEDecode", (x + 840, y + 340), samples=ks["LATENT"], vae=vae["VAE"])
    return dec["IMAGE"], vae


def gen_zimage(g, x, y, prompt, refs, width, height, steps=8, denoise=1.0, latent=None, mask=None):
    """Z-Image Turbo (text only; references are ignored -- describe the style in words)."""
    unet = g.add("UNETLoader", (x, y), unet_name="z_image_turbo_int8_convrot.safetensors")
    clip = g.add("CLIPLoader", (x, y + 140), clip_name="qwen_3_4b_fp8_mixed.safetensors", type="lumina2")
    vae = g.add("VAELoader", (x, y + 280), vae_name="ae.safetensors")
    ms = g.add("ModelSamplingAuraFlow", (x, y + 400), model=unet["MODEL"], shift=3.0)
    enc = g.add("CLIPTextEncode", (x + 360, y), size=[440, 260], title="Промпт (Z-Image)", clip=clip["CLIP"], text=prompt)
    neg = g.add("ConditioningZeroOut", (x + 360, y + 300), conditioning=enc["CONDITIONING"])
    if latent is None:
        latent = g.add("EmptySD3LatentImage", (x + 360, y + 400), title="Размер генерации", width=width, height=height)["LATENT"]
    if mask is not None:
        latent = g.add("SetLatentNoiseMask", (x + 360, y + 540), samples=latent, mask=mask)["LATENT"]
    ks = g.add("KSampler", (x + 840, y), size=[320, 300], model=ms["MODEL"], positive=enc["CONDITIONING"],
               negative=neg["CONDITIONING"], latent_image=latent, seed=0, steps=steps, cfg=1.0,
               sampler_name="res_multistep", scheduler="simple", denoise=denoise)
    dec = g.add("VAEDecode", (x + 840, y + 340), samples=ks["LATENT"], vae=vae["VAE"])
    return dec["IMAGE"], vae


def gen_klein4b(g, x, y, prompt, refs, width, height, steps=4, denoise=1.0, latent=None, mask=None):
    """FLUX.2 klein 4B distilled (edit by references: each one a ReferenceLatent)."""
    unet = g.add("UNETLoader", (x, y), unet_name="flux-2-klein-4b-fp8.safetensors")
    clip = g.add("CLIPLoader", (x, y + 140), clip_name="qwen_3_4b_fp8_mixed.safetensors", type="flux2")
    vae = g.add("VAELoader", (x, y + 280), vae_name="flux2-vae.safetensors")
    enc = g.add("CLIPTextEncode", (x + 360, y), size=[440, 260], title="Промпт (FLUX.2 klein)", clip=clip["CLIP"], text=prompt)
    pos, neg = enc["CONDITIONING"], g.add("ConditioningZeroOut", (x + 360, y + 300), conditioning=enc["CONDITIONING"])["CONDITIONING"]
    for i, r in enumerate(refs):
        sc = g.add("ImageScaleToTotalPixels", (x + 360, y + 420 + i * 260), image=r, upscale_method="lanczos", megapixels=1.0)
        le = g.add("VAEEncode", (x + 600, y + 420 + i * 260), pixels=sc["IMAGE"], vae=vae["VAE"])
        pos = g.add("ReferenceLatent", (x + 600, y + 520 + i * 260), conditioning=pos, latent=le["LATENT"])["CONDITIONING"]
        neg = g.add("ReferenceLatent", (x + 600, y + 600 + i * 260), conditioning=neg, latent=le["LATENT"])["CONDITIONING"]
    if latent is None:
        latent = g.add("EmptyFlux2LatentImage", (x + 840, y + 340), title="Размер генерации", width=width, height=height)["LATENT"]
    if mask is not None:
        latent = g.add("SetLatentNoiseMask", (x + 840, y + 480), samples=latent, mask=mask)["LATENT"]
    guider = g.add("CFGGuider", (x + 840, y), model=unet["MODEL"], positive=pos, negative=neg, cfg=1.0)
    sigmas = g.add("Flux2Scheduler", (x + 840, y + 140), steps=steps, width=width, height=height)
    if denoise < 1.0:
        sigmas = g.add("SplitSigmasDenoise", (x + 840, y + 260), sigmas=sigmas["SIGMAS"], denoise=denoise)
        sig = sigmas["low_sigmas"]
    else:
        sig = sigmas["SIGMAS"]
    noise = g.add("RandomNoise", (x + 1180, y), noise_seed=0)
    sampler = g.add("KSamplerSelect", (x + 1180, y + 120), sampler_name="euler")
    sca = g.add("SamplerCustomAdvanced", (x + 1180, y + 240), noise=noise["NOISE"], guider=guider["GUIDER"],
                sampler=sampler["SAMPLER"], sigmas=sig, latent_image=latent)
    dec = g.add("VAEDecode", (x + 1180, y + 420), samples=sca["output"], vae=vae["VAE"])
    return dec["IMAGE"], vae


def gen_krea2(g, x, y, prompt, refs, width, height, steps=8, denoise=1.0, latent=None, mask=None):
    """Krea-2 Turbo with the style-reference LoRA (style from <image1>..<image3>, not their content)."""
    unet = g.add("UNETLoader", (x, y), unet_name="krea2_turbo_int8_convrot.safetensors")
    lora = g.add("LoraLoaderModelOnly", (x, y + 140), model=unet["MODEL"], lora_name="krea2_style_reference.safetensors",
                 strength_model=1.0)
    clip = g.add("CLIPLoader", (x, y + 280), clip_name="qwen3vl_4b_fp8_scaled.safetensors", type="krea2")
    vae = g.add("VAELoader", (x, y + 420), vae_name="qwen_image_vae.safetensors")
    ms = g.add("ModelSamplingFlux", (x, y + 540), model=lora["MODEL"], max_shift=1.15, base_shift=0.5, width=width, height=height)
    kw = {f"image{i + 1}": r for i, r in enumerate(refs[:3])}
    enc = g.add("TextEncodeQwenImageEditPlus", (x + 360, y), size=[440, 260], title="Промпт (Krea-2)", clip=clip["CLIP"],
                vae=vae["VAE"], prompt=prompt, **kw)
    meth = g.add("FluxKontextMultiReferenceLatentMethod", (x + 360, y + 300), conditioning=enc["CONDITIONING"],
                 reference_latents_method="index_timestep_zero")
    neg = g.add("ConditioningZeroOut", (x + 360, y + 420), conditioning=meth["CONDITIONING"])
    if latent is None:
        latent = g.add("EmptyLatentImage", (x + 360, y + 520), title="Размер генерации", width=width, height=height)["LATENT"]
    if mask is not None:
        latent = g.add("SetLatentNoiseMask", (x + 360, y + 660), samples=latent, mask=mask)["LATENT"]
    guider = g.add("CFGGuider", (x + 840, y), model=ms["MODEL"], positive=meth["CONDITIONING"], negative=neg["CONDITIONING"], cfg=1.0)
    sched = g.add("BasicScheduler", (x + 840, y + 140), model=ms["MODEL"], scheduler="simple", steps=steps, denoise=denoise)
    noise = g.add("RandomNoise", (x + 1180, y), noise_seed=0)
    sampler = g.add("KSamplerSelect", (x + 1180, y + 120), sampler_name="euler")
    sca = g.add("SamplerCustomAdvanced", (x + 1180, y + 240), noise=noise["NOISE"], guider=guider["GUIDER"],
                sampler=sampler["SAMPLER"], sigmas=sched["SIGMAS"], latent_image=latent)
    dec = g.add("VAEDecode", (x + 1180, y + 420), samples=sca["output"], vae=vae["VAE"])
    return dec["IMAGE"], vae


def _rgb_block(fn):
    """The block's picture without alpha (Qwen 2.1 decodes RGBA): mixing it with RGB pictures needs three channels."""
    def wrapped(g, x, y, *a, **kw):
        img, vae = fn(g, x, y, *a, **kw)
        split = g.add("SplitImageWithAlpha", (x + 1180, y + 560), image=img)
        return split["IMAGE"], vae
    wrapped.__doc__ = fn.__doc__
    return wrapped


gen_qwen21_rgba = gen_qwen21
gen_qwen21, gen_zimage, gen_klein4b, gen_krea2 = map(_rgb_block, (gen_qwen21, gen_zimage, gen_klein4b, gen_krea2))

MODELS = {"qwen21": gen_qwen21, "zimage": gen_zimage, "klein4b": gen_klein4b, "krea2": gen_krea2}
LABEL = {"qwen21": "Qwen Image 2.1", "zimage": "Z-Image Turbo", "klein4b": "FLUX.2 klein 4B", "krea2": "Krea-2 Turbo + стиль"}
REF_NOTE = {"qwen21": "в промпте — `<image1>`, `<image2>` …", "zimage": "образцов не видит — стиль словами",
            "klein4b": "образцы — «image 1», «image 2» в промпте", "krea2": "берёт стиль образцов (до трёх), не содержание"}


# ---------------------------------------------------------------------------------------------------------------------
# workflows

MEMO = """# ld_00 — памятка: графика E&F под Victoria 3

**Порядок:** карточка (куда идёт картинка, размер, слой, образцы) → генерация своим заданием → доводка (ld_40) →
предпросмотр как в игре (ld_50) → лист вариантов → выбранное в мод (DDS) → стенд в игре, 2–3 темы.

| задание | для чего |
| --- | --- |
| ld_01 | сравнение моделей на одной задаче — лист |
| ld_10 | слой по образцам (орнамент, ткань, маска) — в его виде: серый, без рамки и цвета |
| ld_11 | бесшовный кусок: сдвиг на половину, перерисовка шва, проверка повтором |
| ld_12 | конец + повтор под `spriteborder` и зеркало: широкая шапка любой ширины |
| ld_20 | значок: однотонный фон → прозрачность → размер ванильных |
| ld_30 | иллюстрация в пропорциях игры |
| ld_40 | доводка: увеличение с деталями, перерисовка куска по маске |
| ld_50 | предпросмотр слоёв так, как их сложит игра |

## Размеры
- Генерировать в пропорциях не круче ~4:1 и в 2–4 раза крупнее нужного, потом уменьшать (lanczos). Полоса 10:1 —
  шум, повторы, склейки.
- `texture_density = 2` у шапок и тканей: файл вдвое больше места на экране (шапка 184 px → 92 px).
- Шапка полноэкранного окна: рамка 2556×184, орнамент-половина 1900×184 (край 600 + повтор), зеркало справа.
- Значки товаров — 256×256 RGBA; иллюстрации — по ванильной того же вида (карточка).

## Как игра собирает картинку
- `spriteType = Corneredtiled` + `spriteborder = { 600 0 }`: края по 600 px как есть, середина повтором; `Corneredstretched` — растяжением.
- `mirror = horizontal`: правая половина — зеркало левой.
- Слои шапки (`top_header_bg`): `header_color` → ткань (overlay, 0.3) → бархат (overlay) → тень → маска формы
  (alphamultiply) → **орнамент (overlay, серый)** → рамка → текст. Генерируем только свой слой; образец даём слоем.

## Темы оформления
Скины DLC (`votp`, `ap1`, `ip2`, `ip3`, `ip4`, `ep2`): файл `gfx/interface/X` скин подменяет файлом
`dlc/<dlc>/gfx/skins/<скин>/X` (например `dlc/dlc016_ip4/gfx/skins/ip4/backgrounds/fullscreen_header_dec.dds`). Свой слой —
вариант под каждую тему по её образцу. Образцы тем: узел **V3 Load Game Image**, root = game, путь
`dlc/<dlc>/gfx/skins/<скин>/...` (без `interface/`).

## Узлы vic3 (`V3 …`)
Load Game Image (DDS игры, мода, мастерской по пути), Roll / Seam Mask / Tile (бесшовность), Mirror / Sprite Border
(сборка как в игре), Blend (overlay, multiply, alphamultiply …) / Fill / Gray (слои), Text (шрифт игры), Sheet (лист).
Маска везде как у ComfyUI: 1 = прозрачно / перерисовать.

## Модель
Генератор в заданиях — **{model}** ({refnote}). Смена модели — `py comfy/workflows.py save --model <qwen21|zimage|klein4b|krea2>`
(агент); правки руками в задании сохраняются, пока его не пересобрали.
"""


def wf_memo(model):
    g = Graph("ld_00")
    g.note((0, 0), MEMO.replace("{model}", LABEL[model]).replace("{refnote}", REF_NOTE[model]), size=[900, 1300])
    return g


def _sample(g, pos, path, title, root="game", flat=None):
    """A sample from the game's tree. flat = a colour: the sample laid on it (its transparent parts otherwise reach the
    model as white and it copies them); the result is then {"image": that, "mask": alpha} like the loader's."""
    load = g.add("V3LoadGameImage", pos, title=title, size=[360, 120], root=root, path=path)
    if not flat:
        return load
    fill = g.add("V3Fill", (pos[0], pos[1] + 140), width=load["width"], height=load["height"], color=flat)
    lay = g.add("V3Blend", (pos[0] + 380, pos[1]), title=f"{title} — на ровном фоне", base=fill["IMAGE"], layer=load["image"],
                layer_mask=load["mask"], mode="normal", opacity=1.0, fit="none")
    return {"image": lay["IMAGE"], "mask": load["mask"]}


def _save(g, pos, image, prefix):
    g.add("SaveImage", pos, size=[420, 360], images=image, filename_prefix=prefix)


def wf_compare(model):
    """All four models on one prompt and the same samples; a labelled sheet."""
    g = Graph("ld_01")
    g.note((-640, 0), """# ld_01 — сравнение моделей (В.R10.6)
Один промпт и одни образцы — четыре модели; внизу лист с подписями.
- **Промпт** — узел «Промпт» (общий). Qwen ссылается на образцы как `<image1>`, FLUX.2 klein — «image 1», Krea-2 берёт
  из образцов только стиль, Z-Image образцов не видит.
- **Образцы** — узлы V3 Load Game Image (путь в дереве игры; root = fork — графика мода, workshop — оригинал E&F).
- **Размер** — общий (по умолчанию 1024×1024); для полос — не круче 4:1.
- Три задачи сравнения: узор (слой орнамента), значок (валюта / банк), картинка события.
- Модели грузятся по очереди (12 ГБ): весь лист — несколько минут.""", size=[600, 560])
    prompt = g.add("PrimitiveStringMultiline", (0, 0), title="Промпт", size=[520, 220],
                   value="A Victorian-era engraved ornamental frieze of oak leaves and acorns in the style of <image1>, "
                         "monochrome grey relief on a flat neutral grey background, no frame, no text")
    w = g.add("PrimitiveInt", (0, 260), title="Ширина", value=1024)
    h = g.add("PrimitiveInt", (0, 360), title="Высота", value=1024)
    r1 = _sample(g, (0, 480), "gfx/interface/backgrounds/fullscreen_header_dec.dds", "Образец 1 (стиль)", flat="#808080")
    r2 = _sample(g, (0, 800), "gfx/interface/icons/goods_icons/grain.dds", "Образец 2", flat="#ffffff")
    refs = [r1["image"], r2["image"]]
    outs, labels = [], []
    for i, m in enumerate(MODELS):
        y = 900 + i * 900
        g.group(LABEL[m], [560, y - 60, 1600, 820])
        img, _ = MODELS[m](g, 600, y, prompt["STRING"], refs, w["INT"], h["INT"])
        sc = g.add("ImageScale", (2000, y), title="К размеру холста (для листа)", image=img, upscale_method="lanczos",
                    width=w["INT"], height=h["INT"], crop="center")
        outs.append(sc["IMAGE"])
        labels.append(LABEL[m])
        _save(g, (2000, y + 160), img, f"ld_01/{m}")
    cur = outs[0]
    for i, o in enumerate(outs[1:]):
        cur = g.add("ImageBatch", (2400, 900 + i * 120), image1=cur, image2=o)["IMAGE"]
    sheet = g.add("V3Sheet", (2700, 900), images=cur, labels="\n".join(labels), columns=4, cell_width=512)
    _save(g, (3100, 900), sheet["IMAGE"], "ld_01/sheet")
    return g


def wf_layer(model):
    g = Graph("ld_10")
    g.note((-640, 0), """# ld_10 — слой по образцам
Свой слой в его виде: орнамент — серый рельеф без цвета и рамки (игра красит его overlay поверх ткани), маска — ч/б.
- **Образец 1** — ванильный слой того же вида (орнамент шапки и т. п.): форма и плотность узора.
- **Образец 2** — тот же слой из темы DLC или оригинал E&F: стиль.
- **Размер генерации** — в 2–4 раза крупнее нужного, не круче 4:1. **Итоговый размер** — в тех же пропорциях (кусок
  высотой как ванильный слой, 1536×384 → 736×184); полосу на ширину окна собирают ld_11 и ld_12, не растяжение.
- Образцы лежат на ровном сером: прозрачные места образца иначе доходят до модели белыми, и она их копирует.
- Дальше: бесшовность — ld_11, конец + повтор — ld_12, вид в игре — ld_50.""", size=[600, 420])
    r1 = _sample(g, (0, 0), "gfx/interface/backgrounds/fullscreen_header_dec.dds", "Образец 1 — слой того же вида", flat="#808080")
    r2 = _sample(g, (0, 320), "dlc/dlc016_ip4/gfx/skins/ip4/backgrounds/fullscreen_header_dec.dds",
                 "Образец 2 — тема / оригинал E&F", flat="#808080")
    img, _ = MODELS[model](g, 400, 0, PROMPT_LAYER[model], [r1["image"], r2["image"]], 1536, 384)
    gray = g.add("V3Gray", (1900, 0), image=img, low=0.0, high=1.0, normalize=True)
    fin = g.add("ImageScale", (1900, 200), title="Итоговый размер (те же пропорции: кусок, не полоса)", image=gray["IMAGE"],
                upscale_method="lanczos", width=736, height=184, crop="disabled")
    _save(g, (2250, 0), fin["IMAGE"], "ld_10/layer")
    g.add("PreviewImage", (2250, 420), images=r1["image"], title="Образец для сравнения")
    return g


PROMPT_LAYER = {
    "qwen21": "Create a new seamless horizontal ornament band in the same engraving style, density and grey relief as "
              "<image1>, with motifs of coins, ledgers and laurel inspired by <image2>. Flat grey, no frame, no cut-outs, no colour.",
    "zimage": "Seamless horizontal Victorian engraved ornament band, coins, ledgers and laurel leaves, grey bas-relief, "
              "flat neutral grey background, no frame, no colour, high detail",
    "klein4b": "Create a new horizontal ornament band in the engraving style and grey relief of image 1, motifs of coins, "
               "ledgers and laurel like image 2. Flat grey, no frame, no colour.",
    "krea2": "horizontal Victorian engraved ornament band with coins, ledgers and laurel, grey bas-relief, flat grey background",
}


def wf_seamless(model):
    g = Graph("ld_11")
    g.note((-640, 0), """# ld_11 — бесшовный кусок
1. **Кусок** — результат ld_10 (Load Image или V3 Load Game Image, root = fork).
2. **V3 Roll 0.5** — края куска сходятся в середине: шов, который игра покажет при повторе (`Corneredtiled`).
3. **V3 Seam Mask** — полоса посередине; генератор перерисовывает только её (denoise 0.6–0.9).
4. Вставка по маске, **Roll назад** (−0.5) — края куска нетронуты, шов затянут.
5. **V3 Tile 3×1** — проверка: шва и заметного повтора быть не должно.
Кромки куска (линия, верх и низ полосы) должны совпадать по высоте на обоих краях: полоса перерисовки шва их не
выровняет. Кусок, вырезанный из ванильной половины орнамента (кромка там поднимается), даёт ступеньку — берите кусок
с ровной кромкой или шире полосу (band) и denoise ближе к 1.
`shape = cross` и Roll по обеим осям — для куска, который повторяется и вверх (ткань, фон).""", size=[600, 460])
    src = _sample(g, (0, 0), "gfx/interface/backgrounds/fullscreen_header_dec.dds", "Кусок (замените на свой)", flat="#808080")
    crop = g.add("ImageCrop", (0, 160), title="Повторяемая часть", image=src["image"], width=1200, height=184, x=700, y=0)
    up = g.add("ImageScaleBy", (0, 360), title="×2 для генерации", image=crop["IMAGE"], upscale_method="lanczos", scale_by=2.0)
    roll = g.add("V3Roll", (0, 500), image=up["IMAGE"], x=0.5, y=0.0)
    seam = g.add("V3SeamMask", (0, 660), image=roll["IMAGE"], shape="vertical", band=384, feather=96)
    img, vae = MODELS[model](g, 400, 0, PROMPT_SEAM[model], [roll["IMAGE"]], 2400, 368, denoise=0.9,
                             latent=None, mask=None)
    # encode the rolled piece and repaint only the band: replace the empty latent made by the block
    latent_node = next(n for n in reversed(g.nodes) if n.title == "Размер генерации")
    enc = g.add("VAEEncode", (400, 760), pixels=roll["IMAGE"], vae=vae["VAE"])
    nm = g.add("SetLatentNoiseMask", (400, 880), samples=enc["LATENT"], mask=seam["MASK"])
    _relink(g, latent_node, nm["LATENT"])
    comp = g.add("ImageCompositeMasked", (1900, 0), destination=roll["IMAGE"], source=img, x=0, y=0, resize_source=True,
                 mask=seam["MASK"])
    back = g.add("V3Roll", (1900, 220), title="Roll назад", image=comp["IMAGE"], x=-0.5, y=0.0)
    down = g.add("ImageScaleBy", (1900, 380), title="Итоговый размер", image=back["IMAGE"], upscale_method="lanczos", scale_by=0.5)
    tile = g.add("V3Tile", (2250, 0), image=down["IMAGE"], cols=3, rows=1)
    g.add("PreviewImage", (2250, 160), title="Проверка повтором 3×1", images=tile["IMAGE"])
    _save(g, (2250, 560), down["IMAGE"], "ld_11/piece")
    return g


PROMPT_SEAM = {
    "qwen21": "Repair the vertical seam in the middle of <image1>: continue the ornament smoothly across it so the pattern "
              "is continuous, same style, same grey relief, same scale. Do not change anything else.",
    "zimage": "continuous Victorian engraved ornament band, grey bas-relief, seamless, same scale",
    "klein4b": "Make the ornament in image 1 continuous across the vertical seam in the middle, same style and grey relief.",
    "krea2": "continuous engraved ornament band, grey relief, seamless",
}


def _relink(g, old, new):
    """Point every input fed by old (a latent node) at new instead; drop old."""
    for n in g.nodes:
        for k, (src, slot) in list(n.links_in.items()):
            if src is old:
                n.links_in[k] = new
    g.nodes.remove(old)


def wf_end_repeat(model):
    g = Graph("ld_12")
    g.note((-640, 0), """# ld_12 — конец + повтор (широкая шапка любой ширины)
Как ванильный `fullscreen_header_dec.dds` (1900×184): слева конец 600 px, дальше кусок, который игра повторяет
(`Corneredtiled`, `spriteborder_left = 600`), правая половина окна — зеркало (`mirror = horizontal`).
1. **Повтор** — бесшовный кусок из ld_11, два раза подряд.
2. **Место под конец** слева (Pad) — генератор дорисовывает завершение узора, переходящее в повтор.
3. **Сборка как в игре**: V3 Mirror → V3 Sprite Border (край 600, середина повтором) на ширину окна.
4. Вид в игре — цвет, ткань, орнамент overlay, надпись шрифтом игры (подробно — ld_50).""", size=[600, 440])
    piece = _sample(g, (0, 0), "gfx/interface/backgrounds/fullscreen_header_dec.dds", "Повтор (кусок из ld_11)", flat="#808080")
    crop = g.add("ImageCrop", (0, 160), title="Повторяемая часть", image=piece["image"], width=1200, height=184, x=700, y=0)
    two = g.add("V3Tile", (0, 360), image=crop["IMAGE"], cols=2, rows=1)
    pad = g.add("ImagePadForOutpaint", (0, 480), image=two["IMAGE"], left=600, top=0, right=0, bottom=0, feathering=48)
    up = g.add("ImageScaleBy", (0, 700), title="×2 для генерации", image=pad["IMAGE"], upscale_method="lanczos", scale_by=2.0)
    mk = g.add("MaskToImage", (0, 840), mask=pad["MASK"])
    mup = g.add("ImageScaleBy", (0, 940), image=mk["IMAGE"], upscale_method="bilinear", scale_by=2.0)
    mask = g.add("ImageToMask", (0, 1060), image=mup["IMAGE"], channel="red")
    img, vae = MODELS[model](g, 400, 0, PROMPT_END[model], [up["IMAGE"]], 6000, 368)
    latent_node = next(n for n in reversed(g.nodes) if n.title == "Размер генерации")
    enc = g.add("VAEEncode", (400, 760), pixels=up["IMAGE"], vae=vae["VAE"])
    nm = g.add("SetLatentNoiseMask", (400, 880), samples=enc["LATENT"], mask=mask["MASK"])
    _relink(g, latent_node, nm["LATENT"])
    comp = g.add("ImageCompositeMasked", (1900, 0), destination=up["IMAGE"], source=img, x=0, y=0, resize_source=True,
                 mask=mask["MASK"])
    down = g.add("ImageScaleBy", (1900, 220), title="Итоговый размер", image=comp["IMAGE"], upscale_method="lanczos", scale_by=0.5)
    half = g.add("ImageCrop", (1900, 380), title="Половина: конец + повтор", image=down["IMAGE"], width=1900, height=184, x=0, y=0)
    _save(g, (2250, 0), half["IMAGE"], "ld_12/dec_half")
    mir = g.add("V3Mirror", (2250, 420), image=half["IMAGE"], side="right")
    sb = g.add("V3SpriteBorder", (2250, 560), title="Ширина окна", image=mir["IMAGE"], left=600, right=600, top=0, bottom=0,
               width=2556, height=184, middle="tile")
    col = g.add("V3Fill", (2600, 420), width=2556, height=184, color="#5a2e1e")
    ov = g.add("V3Blend", (2600, 560), base=col["IMAGE"], layer=sb["IMAGE"], mode="overlay", opacity=1.0, fit="stretch")
    txt = g.add("V3Text", (2600, 760), image=ov["IMAGE"], text="Бюджет", size=64)
    g.add("PreviewImage", (2950, 420), title="Вид в игре (упрощённо)", images=txt["IMAGE"], size=[900, 300])
    return g


PROMPT_END = {
    "qwen21": "Fill the empty area on the left of <image1> with an ornamental end flourish of the same engraved grey "
              "ornament: scrolls and leaves curling to a graceful finish at the left edge, flowing into the band on the right.",
    "zimage": "ornamental end flourish of a Victorian engraved grey ornament band, scrolls and leaves",
    "klein4b": "Fill the empty left part of image 1 with a matching ornamental end flourish that flows into the band.",
    "krea2": "ornamental end flourish, engraved grey ornament, scrolls and leaves",
}


def wf_icon(model):
    g = Graph("ld_20")
    g.note((-640, 0), """# ld_20 — значок
1. **Образцы** — ванильные значки того же вида (товары — `gfx/interface/icons/goods_icons/`, 256×256 RGBA) и значок
   оригинала E&F: стиль, ракурс, обводка, свет.
2. Генерация на **однотонном фоне** в 1024×1024.
3. **Прозрачность** — второй проход Qwen 2.1 «удали фон» (выдаёт настоящую альфу).
4. **Итоговый размер** — как у ванильных; предпросмотр на светлой и тёмной подложке.""", size=[600, 400])
    r1 = _sample(g, (0, 0), "gfx/interface/icons/goods_icons/grain.dds", "Образец 1 — ванильный значок", flat="#ffffff")
    r2 = _sample(g, (0, 320), "gfx/interface/icons/goods_icons/gold.dds", "Образец 2 — ванильный значок", flat="#ffffff")
    img, _ = MODELS[model](g, 400, 0, PROMPT_ICON[model], [r1["image"], r2["image"]], 1024, 1024)
    cut, _ = gen_qwen21_rgba(g, 400, 1000, "Remove the background of <image1>, and output a PNG image with transparency",
                        [img], 1024, 1024)
    alpha = g.add("SplitImageWithAlpha", (1900, 1000), image=cut)
    fin = g.add("ImageScale", (1900, 0), title="Итоговый размер", image=alpha["IMAGE"], upscale_method="lanczos",
                width=256, height=256, crop="disabled")
    joined = g.add("JoinImageWithAlpha", (1900, 200), image=fin["IMAGE"], alpha=alpha["MASK"])
    _save(g, (2250, 0), joined["IMAGE"], "ld_20/icon")
    for i, c in enumerate(("#e8dcc0", "#2a2420")):
        bg = g.add("V3Fill", (2250, 420 + i * 300), width=256, height=256, color=c)
        bl = g.add("V3Blend", (2550, 420 + i * 300), base=bg["IMAGE"], layer=fin["IMAGE"], mode="normal", opacity=1.0,
                   fit="stretch", layer_mask=alpha["MASK"])
        g.add("PreviewImage", (2850, 420 + i * 300), title=f"На подложке {c}", images=bl["IMAGE"])
    return g


PROMPT_ICON = {
    "qwen21": "A Victoria 3 style game icon of a stack of gold coins with a bank ledger, painted in the same style, "
              "lighting, outline and three-quarter view as <image1> and <image2>, centred, on a plain flat white background.",
    "zimage": "Victoria 3 style painted game icon, stack of gold coins with a bank ledger, three-quarter view, soft "
              "painterly shading, centred, plain flat white background",
    "klein4b": "A game icon of a stack of gold coins with a bank ledger in the painted style of image 1 and image 2, "
               "centred on a plain white background.",
    "krea2": "game icon, stack of gold coins with a bank ledger, painterly, centred, plain white background",
}


def wf_illustration(model):
    g = Graph("ld_30")
    g.note((-640, 0), """# ld_30 — иллюстрация
Картинка события, окна или загрузочного экрана — в пропорциях ванильной того же места (размер — в карточке).
- **Образец** — ванильная иллюстрация того же места (стиль: живопись XIX века, приглушённая палитра).
- Генерация крупнее (длинная сторона ~2048), **Итоговый размер** — как у ванильной.""", size=[600, 300])
    r1 = _sample(g, (0, 0), "gfx/loadingscreens/victoria3_load_1.dds", "Образец — ванильная иллюстрация")
    img, _ = MODELS[model](g, 400, 0, PROMPT_ILLU[model], [r1["image"]], 1792, 1024)
    fin = g.add("ImageScale", (1900, 0), title="Итоговый размер", image=img, upscale_method="lanczos", width=1120,
                height=640, crop="center")
    _save(g, (2250, 0), fin["IMAGE"], "ld_30/illu")
    return g


PROMPT_ILLU = {
    "qwen21": "A 19th-century oil painting in the style of <image1>: a busy stock exchange hall in 1850s London, brokers "
              "in top hats trading around a large board of quotations, warm gaslight, muted palette.",
    "zimage": "19th-century oil painting, busy stock exchange hall in 1850s London, brokers in top hats around a board "
              "of quotations, warm gaslight, muted palette, academic realism",
    "klein4b": "A 19th-century oil painting in the style of image 1: a busy stock exchange hall in 1850s London, brokers "
               "in top hats, warm gaslight, muted palette.",
    "krea2": "19th-century oil painting, busy stock exchange hall in 1850s London, brokers in top hats, warm gaslight",
}


def wf_refine(model):
    g = Graph("ld_40")
    g.note((-640, 0), """# ld_40 — доводка
**Увеличение с деталями:** RealESRGAN ×4 → к рабочему размеру → тот же генератор по картинке с небольшим denoise
(0.25–0.4): чёткость и детали без смены рисунка → уменьшение до итогового (lanczos).
**Перерисовка куска:** откройте картинку в Load Image → правая кнопка → Open in MaskEditor, закрасьте кусок →
генератор перерисует только его (denoise 0.7–1.0), остальное не тронется.""", size=[600, 360])
    src = g.add("LoadImage", (0, 0), title="Картинка", size=[340, 420], image="top_header_dec.png")
    up_m = g.add("UpscaleModelLoader", (0, 480), model_name="RealESRGAN_x4plus.safetensors")
    up = g.add("ImageUpscaleWithModel", (0, 600), upscale_model=up_m["UPSCALE_MODEL"], image=src["IMAGE"])
    work = g.add("ImageScaleToTotalPixels", (0, 720), title="Рабочий размер", image=up["IMAGE"], upscale_method="lanczos",
                 megapixels=2.0)
    img, vae = MODELS[model](g, 400, 0, PROMPT_REFINE[model], [work["IMAGE"]], 1024, 1024, denoise=0.35)
    latent_node = next(n for n in reversed(g.nodes) if n.title == "Размер генерации")
    enc = g.add("VAEEncode", (400, 760), pixels=work["IMAGE"], vae=vae["VAE"])
    nm = g.add("SetLatentNoiseMask", (400, 880), title="Маска (из MaskEditor; без маски — вся картинка)",
               samples=enc["LATENT"], mask=src["MASK"])
    _relink(g, latent_node, nm["LATENT"])
    fin = g.add("ImageScale", (1900, 0), title="Итоговый размер", image=img, upscale_method="lanczos", width=1900,
                height=184, crop="disabled")
    _save(g, (2250, 0), fin["IMAGE"], "ld_40/refined")
    return g


PROMPT_REFINE = {
    "qwen21": "Sharpen and add fine engraved detail to <image1> without changing its design, layout or colours.",
    "zimage": "sharp fine engraved detail, crisp lines, same design",
    "klein4b": "Sharpen image 1 and add fine detail without changing its design, layout or colours.",
    "krea2": "sharp fine detail, crisp lines",
}


def wf_preview(model):
    g = Graph("ld_50")
    g.note((-640, 0), """# ld_50 — предпросмотр слоёв как в игре
Шапка полноэкранного окна (`fullscreen_top_header`, `gui/shared/backgrounds.gui`): цвет `header_color` → ткань
(overlay 0.3) → бархат (overlay) → маска формы (alphamultiply) → **орнамент (overlay)** → рамка → надпись.
- Свой слой — в узел «Наш орнамент» (root = fork — из мода, или Load Image из выхода ld_12).
- Тема — путь образцов: `gfx/interface/...` (ваниль) или `dlc/<dlc>/gfx/skins/<скин>/...` (без `interface/`).
- Размер — 2556×184 (плотность 2: на экране 92 px). Ширина окна «Бюджета» 1226 → ×2 = 2452.""", size=[600, 380])
    W, H = 2556, 184
    color = g.add("V3LoadGameImage", (0, 0), title="Цвет шапки", root="game", path="gfx/interface/backgrounds/header_color.dds")
    cloth = _sample(g, (0, 160), "gfx/interface/textures/cloth_texture.dds", "Ткань")
    velvet = _sample(g, (0, 320), "gfx/interface/textures/velvet_texture.dds", "Бархат")
    shade = _sample(g, (0, 480), "gfx/interface/backgrounds/top_header_bg_shading.dds", "Тень")
    tmask = _sample(g, (0, 640), "gfx/interface/backgrounds/fullscreen_header_title_mask.dds", "Маска формы")
    dec = _sample(g, (0, 800), "gfx/interface/backgrounds/fullscreen_header_dec.dds", "Наш орнамент (половина)")
    frame = _sample(g, (0, 960), "gfx/interface/backgrounds/fullscreen_header_frame.dds", "Рамка")
    base = g.add("ImageScale", (420, 0), image=color["image"], upscale_method="bilinear", width=W, height=H, crop="disabled")
    b1 = g.add("V3Blend", (420, 160), base=base["IMAGE"], layer=cloth["image"], mode="overlay", opacity=0.3, fit="tile")
    b2 = g.add("V3Blend", (420, 400), base=b1["IMAGE"], layer=velvet["image"], mode="overlay", opacity=1.0, fit="tile")
    b3 = g.add("V3Blend", (420, 640), base=b2["IMAGE"], layer=shade["image"], mode="overlay", opacity=1.0, fit="stretch")
    msb = g.add("V3SpriteBorder", (780, 640), image=tmask["image"], mask=tmask["mask"], left=600, right=600, top=0, bottom=0,
                width=W, height=H, middle="tile")
    b4 = g.add("V3Blend", (780, 880), base=b3["IMAGE"], layer=msb["IMAGE"], layer_mask=msb["MASK"], mode="alphamultiply",
               opacity=1.0, fit="stretch")
    mir = g.add("V3Mirror", (780, 160), image=dec["image"], mask=dec["mask"], side="right")
    dsb = g.add("V3SpriteBorder", (780, 360), title="Орнамент на ширину", image=mir["IMAGE"], mask=mir["MASK"], left=600,
                right=600, top=0, bottom=0, width=W, height=H, middle="tile")
    b5 = g.add("V3Blend", (1140, 160), base=b4["IMAGE"], base_mask=b4["MASK"], layer=dsb["IMAGE"], layer_mask=dsb["MASK"],
               mode="overlay", opacity=1.0, fit="stretch")
    fsb = g.add("V3SpriteBorder", (1140, 400), image=frame["image"], mask=frame["mask"], left=600, right=600, top=0, bottom=0,
                width=W, height=H, middle="tile")
    b6 = g.add("V3Blend", (1140, 640), base=b5["IMAGE"], base_mask=b5["MASK"], layer=fsb["IMAGE"], layer_mask=fsb["MASK"],
               mode="normal", opacity=1.0, fit="stretch")
    txt = g.add("V3Text", (1500, 160), image=b6["IMAGE"], text="Бюджет", size=64)
    bg = g.add("V3Fill", (1500, 520), width=W, height=H, color="#1b1714")
    fin = g.add("V3Blend", (1500, 660), base=bg["IMAGE"], layer=txt["IMAGE"], layer_mask=b6["MASK"], mode="normal",
                opacity=1.0, fit="stretch")
    g.add("PreviewImage", (1860, 160), title="Шапка как в игре", size=[1000, 300], images=fin["IMAGE"])
    _save(g, (1860, 520), fin["IMAGE"], "ld_50/preview")
    return g


WORKFLOWS = {"ld_00_памятка": wf_memo, "ld_01_сравнение_моделей": wf_compare, "ld_10_слой": wf_layer,
             "ld_11_бесшовный_кусок": wf_seamless, "ld_12_конец_и_повтор": wf_end_repeat, "ld_20_значок": wf_icon,
             "ld_30_иллюстрация": wf_illustration, "ld_40_доводка": wf_refine, "ld_50_предпросмотр_слоёв": wf_preview}


def save(model, only=None, out=None):
    for name, fn in WORKFLOWS.items():
        if only and not name.startswith(only):
            continue
        ui = fn(model).to_ui()
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            (Path(out) / f"{name}.json").write_text(json.dumps(ui, ensure_ascii=False, indent=1), encoding="utf-8")
        path = urllib.parse.quote(f"workflows/{name}.json", safe="")
        http(f"/api/userdata/{path}?overwrite=true", ui)
        print(f"saved {name} ({len(ui['nodes'])} nodes)")


def run(name, model, sets, out, previews=False):
    fn = next(f for n, f in WORKFLOWS.items() if n.startswith(name))
    g = fn(model)
    api = g.to_api()
    for s in sets:
        key, val = s.split("=", 1)
        title, _, field = key.rpartition(".")
        hit = False
        for nid, node in api.items():
            if (not title or node["_meta"]["title"] == title or nid == title) and field in node["inputs"] \
                    and not isinstance(node["inputs"][field], list):
                cur = node["inputs"][field]
                node["inputs"][field] = type(cur)(val) if not isinstance(cur, bool) else val.lower() in ("1", "true")
                hit = True
        if not hit:
            raise SystemExit(f"no widget {key}")
    for node in api.values():
        for k in ("seed", "noise_seed"):
            if k in node["inputs"] and node["inputs"][k] == 0:
                node["inputs"][k] = int(time.time() * 1000) % 2**48
    pid = http("/prompt", {"prompt": api})["prompt_id"]
    print("queued", pid, flush=True)
    while True:
        h = http(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                raise SystemExit(json.dumps(st.get("messages"), ensure_ascii=False)[:3000])
            if st.get("completed"):
                break
        time.sleep(2)
    Path(out).mkdir(parents=True, exist_ok=True)
    for nid, o in h[pid]["outputs"].items():
        for im in o.get("images", []):
            if im.get("type") != "output" and not previews:
                continue
            q = urllib.parse.urlencode({k: im[k] for k in ("filename", "subfolder", "type")})
            dst = Path(out) / f"{name}_{nid}_{im['subfolder'].replace('/', '_')}_{im['filename']}"
            dst.write_bytes(http(f"/view?{q}", timeout=120))
            print("saved", dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save")
    s.add_argument("--model", default="qwen21", choices=MODELS)
    s.add_argument("--only")
    s.add_argument("--out", help="also write the JSON files here")
    r = sub.add_parser("run")
    r.add_argument("name")
    r.add_argument("--model", default="qwen21", choices=MODELS)
    r.add_argument("--set", action="append", default=[], help="Title.widget=value (or widget=value for all)")
    r.add_argument("--out", default="comfy_out")
    r.add_argument("--previews", action="store_true", help="also fetch what Preview Image nodes showed")
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "save":
        save(a.model, a.only, a.out)
    elif a.cmd == "run":
        run(a.name, a.model, a.set, a.out, a.previews)
    else:
        print("\n".join(WORKFLOWS))


if __name__ == "__main__":
    main()
