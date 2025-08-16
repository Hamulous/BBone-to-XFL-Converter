#!/usr/bin/env python3
# BBone/Player JSON + PNGs -> Animate XFL (viewer parity)
# - PNGs live in library/media/
# - DOMDocument bitmap href = "media/<file>.png" (relative to Library root)
# - main.xfl lists all files under library/ so Animate loads them reliably
# - Optional: .bbone -> animation.json and atlas-split image export
# - Flow: (bbone?) -> gen json -> export images -> ask PNG folder -> out/name/fps/size

import os, sys, json, shutil, argparse
from pathlib import Path
import xml.etree.ElementTree as ET

# ===== repo helpers (must be present next to this script) =====
def bbone_unzip(bbone_path: Path):
    from unzip import unzip  # returns (object_name, {plugin_id: bytes})
    obj, plugins = unzip(str(bbone_path))
    return obj, plugins

def generate_json_from_bbone(bbone_path: Path) -> dict:
    obj, plugins = bbone_unzip(bbone_path)
    from get_animation import get_animation_json
    from split_atlas import get_split_json
    from get_animation_labels import parse_frame_labels
    plist      = get_split_json(plugins[1])
    animation  = get_animation_json(plugins[2])  # expects bytes
    labels     = parse_frame_labels(plugins[3])
    return {"plist": plist, "labels": labels, "animation": animation}

def export_images_from_bbone(bbone_path: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    obj, plugins = bbone_unzip(bbone_path)
    from get_atlas import parse_atlas
    from split_atlas import get_split_json, split_atlas
    atlas_img = parse_atlas(plugins[1])
    plist     = get_split_json(plugins[1])
    split_atlas(plist, str(out_dir), atlas_img)
    return list(out_dir.glob("*.png"))

# ===== XML helpers =====
NS   = "http://ns.adobe.com/xfl/2008/"
XSI  = "http://www.w3.org/2001/XMLSchema-instance"
DPIK = 0.78125  # stage scale
q    = lambda t: f"{{{NS}}}{t}"

def write_xml(path: Path, root: ET.Element):
    if "xmlns" not in root.attrib: root.set("xmlns", NS)
    if "xmlns:xsi" not in root.attrib: root.set("xmlns:xsi", XSI)
    tree = ET.ElementTree(root)
    try: ET.indent(tree, space="  ")
    except Exception: pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(path), encoding="utf-8", xml_declaration=True)

def build_domdocument(stage_w: float, stage_h: float, fps: int):
    root = ET.Element(q("DOMDocument"), {
        "xmlns:xsi": XSI, "frameRate": str(fps),
        "width": f"{float(stage_w):.6f}", "height": f"{float(stage_h):.6f}",
        "xflVersion": "2.971"
    })
    folders = ET.SubElement(root, q("folders"))
    for name in ("media","image","sprite","label"):
        ET.SubElement(folders, q("DOMFolderItem"), {"name": name, "isExpanded":"true"})
    ET.SubElement(root, q("media"))
    ET.SubElement(root, q("symbols"))
    tls = ET.SubElement(root, q("timelines"))
    ET.SubElement(tls, q("DOMTimeline"), {"name":"animation"})
    return root

def add_symbol_include(dom_root: ET.Element, rel_href: str):
    dom_root.find(q("symbols")).append(ET.Element("Include", {"href": rel_href}))

def register_media(dom_root: ET.Element, media_pngs):
    """
    Files physically live in xfl/library/media/*.png
    But href must be 'media/<file>.png' (relative to the Library root).
    """
    mnode = dom_root.find(q("media"))
    for i, p in enumerate(sorted(media_pngs, key=lambda x: x.name), start=1):
        ET.SubElement(mnode, q("DOMBitmapItem"), {
            "name": f"media/{p.stem}",
            "href": f"media/{p.name}",
            "itemID": f"bit_{i}",
            "allowSmoothing": "true",
            "useImportedJPEGData": "false"
        })

def build_main_xfl(xfl_root: Path):
    """
    Create main.xfl and enumerate all files under library/ so Animate loads them.
    """
    root = ET.Element(q("DOMFlashFile"), {"version": "2", "xmlns:xsi": XSI})
    files = ET.SubElement(root, q("files"))

    def add(rel_path: str, ftype: str | None = None):
        attrs = {"path": rel_path.replace("\\", "/")}
        if ftype: attrs["type"] = ftype
        ET.SubElement(files, q("DOMFile"), attrs)

    # Always include DOMDocument.xml
    add("DOMDocument.xml", "application/vnd.adobe.xfl.document")

    # Include everything under library/
    lib = xfl_root / "library"
    if lib.exists():
        for p in lib.rglob("*"):
            if p.is_file():
                ftype = "image/png" if p.suffix.lower() == ".png" else None
                add(str(p.relative_to(xfl_root)), ftype)

    write_xml(xfl_root / "main.xfl", root)

# ===== math / utils =====
def sanitize(s: str) -> str: return s.replace(".", "_")
def mul(a, b):
    return (a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5])
def mat(a=1,b=0,c=0,d=1,tx=0,ty=0): return (float(a),float(b),float(c),float(d),float(tx),float(ty))

def build_png_index(media_dir: Path):
    files = list(media_dir.glob("*.png"))
    idx = {}
    for p in files:
        s = p.stem
        for k in {s, s.lower(), s.replace(".","_"), s.replace("_","."), s.lower().replace(".","_")}:
            idx.setdefault(k, p)
    return files, idx

def find_png_for_name(name: str, idx: dict):
    if name in idx: return idx[name]
    key = name.replace(".","_")
    if key in idx: return idx[key]
    low = name.lower()
    if low in idx: return idx[low]
    for k, p in idx.items():
        if low in k.lower() or k.lower() in low:
            return p
    return None

def dfs_draw_order(frames, shared):
    order=[]
    if not frames: return order
    def walk(node, fi):
        n = sanitize(node.get("name",""))
        if n: order.append(n)
        kids = node.get("children")
        if node.get("references_shared_animation"):
            sa = shared.get(node["references_shared_animation"])
            if isinstance(sa, list) and sa:
                fr = sa[int(fi) % len(sa)] or {}
                kids = fr.get("children", kids)
        if isinstance(kids, list):
            for ch in kids: walk(ch, fi)
    for b in frames[0].get("children", []): walk(b, 0)
    return order

def parse_size_token(tok: str):
    tok = tok.lower().replace(" ", "")
    if "x" not in tok: raise ValueError("size must look like WxH, e.g. 512x384")
    w, h = tok.split("x", 1)
    return float(w), float(h)

# ===== symbol writers =====
def image_symbol_xml(stem: str, ox=0.0, oy=0.0, sx=1.0, sy=1.0):
    root = ET.Element(q("DOMSymbolItem"), {"name": f"image/{stem}", "symbolType":"graphic", "xmlns:xsi": XSI})
    tl  = ET.SubElement(ET.SubElement(root, q("timeline")), q("DOMTimeline"), {"name": stem})
    layer = ET.SubElement(ET.SubElement(tl, q("layers")), q("DOMLayer"))
    frm   = ET.SubElement(ET.SubElement(layer, q("frames")), q("DOMFrame"), {"index":"0"})
    elems = ET.SubElement(frm, q("elements"))
    inst  = ET.SubElement(elems, q("DOMBitmapInstance"), {"libraryItemName": f"media/{stem}"})
    matn  = ET.SubElement(inst, q("matrix"))
    ET.SubElement(matn, q("Matrix"), {
        "a": f"{float(sx):.6f}", "b": "0.000000",
        "c": "0.000000",          "d": f"{float(sy):.6f}",
        "tx": f"{float(ox):.6f}", "ty": f"{float(oy):.6f}"
    })
    return root

def sprite_symbol_xml(name: str, image_symbol_name: str):
    root = ET.Element(q("DOMSymbolItem"), {"name": f"sprite/{name}", "symbolType":"graphic", "xmlns:xsi": XSI})
    tl  = ET.SubElement(ET.SubElement(root, q("timeline")), q("DOMTimeline"), {"name": name})
    layer = ET.SubElement(ET.SubElement(tl, q("layers")), q("DOMLayer"), {"name":"1"})
    frm   = ET.SubElement(ET.SubElement(layer, q("frames")), q("DOMFrame"), {"index":"0", "duration":"1"})
    elems = ET.SubElement(frm, q("elements"))
    ET.SubElement(elems, q("DOMSymbolInstance"), {
        "libraryItemName": image_symbol_name, "firstFrame":"0", "symbolType":"graphic", "loop":"loop"
    })
    return root

# ===== prompt helpers =====
def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'): s = s[1:-1]
    return s
def _resolve(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(_strip_quotes(p)))

def prompt_file_optional(prompt, default: str | None = None):
    while True:
        line = input(f"{prompt}{' ['+default+']' if default else ''}: ").strip()
        if line == "" and default: line = default
        if line == "": return None
        path = Path(_resolve(line))
        if path.is_file(): return path
        print("  -> File not found. Press Enter to skip or try again.")

def prompt_file_required(prompt, default: str | None = None):
    while True:
        line = input(f"{prompt}{' ['+default+']' if default else ''}: ").strip()
        if line == "" and default: line = default
        path = Path(_resolve(line))
        if path.is_file(): return path
        print("  -> File not found. Try again.")

def prompt_dir_required(prompt, default: str | None = None):
    while True:
        line = input(f"{prompt}{' ['+default+']' if default else ''}: ").strip()
        if line == "" and default: line = default
        path = Path(_resolve(line))
        if path.is_dir(): return path
        print("  -> Folder not found. Try again.")

def prompt_text(prompt, default: str | None = None):
    line = input(f"{prompt}{' ['+default+']' if default else ''}: ").strip()
    return line if line else (default or "")

def prompt_float(prompt, default):
    while True:
        raw = input(f"{prompt} [{default}]: ").strip()
        if raw == "": return float(default)
        try: return float(raw)
        except ValueError: print("  -> Enter a number (e.g., 512).")

# ===== main =====
def main():
    ap = argparse.ArgumentParser(description="Export JSON+PNGs to XFL with media in library/. Optional .bbone→JSON & image export.")
    ap.add_argument("--bbone", help="Path to .bbone")
    ap.add_argument("--generate-json", action="store_true")
    ap.add_argument("--only-json", action="store_true")
    ap.add_argument("--export-images", action="store_true")
    ap.add_argument("--json", help="Path to animation.json (if you already have it)")
    ap.add_argument("--images", help="Folder of PNGs (if you already have them)")
    ap.add_argument("--out", help="Output folder for the XFL project")
    ap.add_argument("--name", help="Project name (<name>.xfl)")
    ap.add_argument("--fps", type=int)
    ap.add_argument("--size", help="Stage/content size WxH")
    ap.add_argument("--width", type=float)
    ap.add_argument("--height", type=float)
    ap.add_argument("--write-filelist", action="store_true")
    args = ap.parse_args()

    # Optional BBone
    bbone_path = Path(_resolve(args.bbone)) if args.bbone else None
    if not (bbone_path and bbone_path.is_file()):
        bbone_path = prompt_file_optional("===Hamulous' .BBone file to .xfl launcher===\n\nBBone file")

    json_path = None
    json_obj  = None
    exported_images_dir = None  # staging export (before we know out/name)

    # Generate JSON first
    if bbone_path:
        do_gen = args.generate_json or (input("Generate animation.json from this BBone? [Y/n]: ").strip().lower() in ("", "y", "yes"))
        if do_gen:
            default_json_out = str(bbone_path.with_suffix(".json"))
            ans = prompt_text("Where to save animation.json", default_json_out)
            json_out_path = Path(_resolve(ans))
            if json_out_path.exists() and json_out_path.is_dir():
                json_out_path = json_out_path / (bbone_path.stem + ".json")
            if str(ans).rstrip().endswith(("\\", "/")):
                json_out_path = json_out_path / (bbone_path.stem + ".json")
            json_out_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"\nGenerating animation JSON → {json_out_path} ...")
            try:
                json_obj = generate_json_from_bbone(bbone_path)
            except Exception as e:
                print("Failed to decode .bbone:", repr(e))
                json_obj = None
            else:
                json_out_path.write_text(json.dumps(json_obj, ensure_ascii=False, indent=2), encoding="utf-8")
                print("animation.json written")
                json_path = json_out_path
            if args.only_json:
                print("Done (only-json)."); return

        # Export images now (staging near the .bbone)
        want_imgs = args.export_images or (input("Export images/PNGs from this BBone? [Y/n]: ").strip().lower() in ("", "y", "yes"))
        if want_imgs:
            exported_images_dir = bbone_path.parent / f"{bbone_path.stem}_images"
            try:
                files = export_images_from_bbone(bbone_path, exported_images_dir)
                print(f"Exported {len(files)} image(s) → {exported_images_dir}")
            except Exception as e:
                print("Image export failed:", repr(e))
                exported_images_dir = None

    # Animation JSON path (required)
    if not json_path:
        if args.json:
            jp = Path(_resolve(args.json)); 
            if not jp.is_file(): raise FileNotFoundError(f"JSON not found: {jp}")
            json_path = jp
        else:
            json_path = prompt_file_required("Animation JSON path")

    # PNG folder (default to staging export)
    if args.images:
        img_dir = Path(_resolve(args.images))
        if not img_dir.is_dir(): raise FileNotFoundError(f"PNG folder not found: {img_dir}")
    else:
        default_images = str(exported_images_dir) if exported_images_dir else None
        if default_images and not Path(default_images).is_dir(): default_images = None
        img_dir = prompt_dir_required("PNG folder", default_images)

    # Now out/name/fps/size
    out_dir = Path(_resolve(args.out)) if args.out else Path(_resolve(prompt_text("Output folder", str(Path.cwd() / "out_xfl"))))
    out_dir.mkdir(parents=True, exist_ok=True)
    proj_name = args.name or prompt_text("Project name (<name>.xfl)", (bbone_path.stem if bbone_path else json_path.stem))
    try:
        fps = int(args.fps if args.fps is not None else (input("FPS [30]: ").strip() or "30"))
    except Exception:
        fps = 30

    # If user kept the staging export as PNGs, move it next to the project
    if exported_images_dir and img_dir.resolve() == exported_images_dir.resolve():
        final_images_dir = out_dir / f"{proj_name}_images"
        try:
            if final_images_dir.exists(): shutil.rmtree(final_images_dir)
            shutil.move(str(exported_images_dir), str(final_images_dir))
            img_dir = final_images_dir
            print(f"Moved images to {final_images_dir}")
        except Exception as e:
            print("Could not move images next to the project:", repr(e))

    # Load JSON (for size + timelines)
    json_obj = json.loads(json_path.read_text(encoding="utf-8")) if json_obj is None else json_obj
    anim   = json_obj.get("animation", json_obj)
    frames = anim.get("frames", [])
    shared = anim.get("shared_animations", {})
    plist  = {it.get("name"): it for it in json_obj.get("plist", [])}
    base_w = float(anim.get("width")  or json_obj.get("width")  or 390)
    base_h = float(anim.get("height") or json_obj.get("height") or 390)
    if not frames:
        print("ERROR: no frames in JSON"); sys.exit(3)

    # Stage size
    if args.size:
        tgt_w, tgt_h = parse_size_token(args.size)
    elif args.width is not None or args.height is not None:
        tgt_w = float(args.width)  if args.width  is not None else base_w
        tgt_h = float(args.height) if args.height is not None else base_h
        if args.width is not None and args.height is None:  tgt_h = tgt_w * (base_h / base_w)
        if args.height is not None and args.width is None:  tgt_w = tgt_h * (base_w / base_h)
    else:
        print("\n— Stage/Content Size —")
        tgt_w = prompt_float("Target width (px)",  base_w)
        tgt_h = prompt_float("Target height (px)", base_h)

    stage_w = tgt_w * DPIK
    stage_h = tgt_h * DPIK
    g_sx = tgt_w / base_w
    g_sy = tgt_h / base_h

    # Build XFL tree
    xfl = out_dir / f"{proj_name}.xfl"
    if xfl.exists(): shutil.rmtree(xfl)
    xfl.mkdir(parents=True, exist_ok=True)

    # Library folders (media lives under library/)
    lib_dir   = xfl / "library"
    media_dir = lib_dir / "media"
    lib_img   = lib_dir / "image"
    lib_spr   = lib_dir / "sprite"
    for d in (media_dir, lib_img, lib_spr): d.mkdir(parents=True, exist_ok=True)

    # Copy PNGs into library/media
    for p in img_dir.glob("*.png"):
        (media_dir / p.name).write_bytes(p.read_bytes())

    # Build DOM + register bitmaps
    dom = build_domdocument(stage_w, stage_h, fps=fps)
    media_files, png_idx = build_png_index(media_dir)
    register_media(dom, media_files)

    # Collect all piece names seen in frames/plist
    names=set()
    def collect(children):
        if not isinstance(children, list): return
        for b in children:
            n=b.get("name")
            if n: names.add(n)
            kids=b.get("children")
            if isinstance(kids, list): collect(kids)
    for fr in frames: collect(fr.get("children", []))
    for n in plist.keys(): names.add(n)

    # Write image symbols (library/image) and sprite wrappers (library/sprite)
    def write_sym(path: Path, elem: ET.Element, href_rel: str):
        write_xml(path, elem); add_symbol_include(dom, href_rel)

    name_to_image={}
    for n in sorted(names):
        png = find_png_for_name(n, png_idx)
        if not png: continue
        st = plist.get(n, {})
        ox = float(st.get("origin_x",0) or 0); oy=float(st.get("origin_y",0) or 0)
        sx = float(st.get("scale_x",1) or 1);  sy=float(st.get("scale_y",1) or 1)
        write_sym(lib_img / f"{png.stem}.xml", image_symbol_xml(png.stem, ox, oy, sx, sy), f"image/{png.stem}.xml")
        name_to_image[n] = f"image/{png.stem}"

    for n, img_sym in name_to_image.items():
        nm = sanitize(n)
        write_sym(lib_spr / f"{nm}.xml", sprite_symbol_xml(nm, img_sym), f"sprite/{nm}.xml")

    # Compose per-frame transforms into timeline layers
    def compose_list(bone, pw, pa, fi):
        name = bone.get("name","")
        M = bone.get("matrix", {}) or {}
        a = float(M.get("a",1)); b = float(M.get("b",0)); c = float(M.get("c",0)); d = float(M.get("d",1))
        tx = float(M.get("tx",0)); ty = float(M.get("ty",0))
        local = (a,b,c,d,tx,ty)
        world = mul(pw, local)
        alpha = float((bone.get("color") or {}).get("alphaMultiplier", 1.0)) * pa
        out = [(name, world, alpha)]
        kids = bone.get("children")
        if bone.get("references_shared_animation"):
            sa = shared.get(bone["references_shared_animation"])
            if isinstance(sa, list) and sa:
                eff = int(fi) % len(sa); fr = sa[eff] or {}
                kids = fr.get("children", kids)
        if isinstance(kids, list):
            for ch in kids: out += compose_list(ch, world, alpha, fi)
        return out

    layer_frames = {sanitize(n): {} for n in name_to_image}
    for fi, fr in enumerate(frames):
        for bone in fr.get("children", []):
            for nm, (A,B,C,D,TX,TY), alpha in compose_list(bone, mat(), 1.0, fi):
                key = sanitize(nm)
                if key not in layer_frames: continue
                layer_frames[key][fi] = {"name": f"sprite/{key}", "m": (A,B,C,D,TX,TY), "alpha": alpha}

    # Viewer order -> XFL top-first
    bottom_to_top = dfs_draw_order(frames, shared)
    bottom_to_top = [sanitize(n) for n in bottom_to_top if sanitize(n) in layer_frames] + \
                    [n for n in layer_frames.keys() if n not in [sanitize(x) for x in bottom_to_top]]
    top_first = list(reversed(bottom_to_top))

    # Stage timeline
    tl = dom.find(q("timelines")).find(q("DOMTimeline"))
    layers = ET.SubElement(tl, q("layers"))
    g_sx = tgt_w / base_w; g_sy = tgt_h / base_h

    for lname in top_first:
        fnode = ET.SubElement(ET.SubElement(layers, q("DOMLayer"), {"name": lname}), q("frames"))
        fmap = layer_frames[lname]
        for fi in range(len(frames)):
            frm = ET.SubElement(fnode, q("DOMFrame"), {"index": str(fi), "duration":"1"})
            if fi not in fmap: continue
            entry = fmap[fi]
            elems = ET.SubElement(frm, q("elements"))
            inst = ET.SubElement(elems, q("DOMSymbolInstance"), {
                "libraryItemName": entry["name"], "firstFrame":"0", "symbolType":"graphic", "loop":"loop"
            })
            a,b,c,d,tx,ty = entry["m"]
            a *= g_sx; b *= g_sx; c *= g_sy; d *= g_sy; tx *= g_sx; ty *= g_sy
            mnode = ET.SubElement(inst, q("matrix"))
            ET.SubElement(mnode, q("Matrix"), {"a": f"{a:.6f}","b": f"{b:.6f}","c": f"{c:.6f}","d": f"{d:.6f}",
                                               "tx": f"{tx:.6f}","ty": f"{ty:.6f}"})
            if entry["alpha"] != 1.0:
                col = ET.SubElement(inst, q("color"))
                ET.SubElement(col, q("Color"), {
                    "redMultiplier":"1.000000","greenMultiplier":"1.000000","blueMultiplier":"1.000000",
                    "alphaMultiplier": f"{entry['alpha']:.6f}"
                })

    # Write DOM and main.xfl (manifest)
    write_xml(xfl / "DOMDocument.xml", dom)
    build_main_xfl(xfl)

    # Optional legacy filelist.xml (not required by Animate)
    if args.write_filelist:
        root = ET.Element("flash_archive", {"xmlns:xsi": XSI})
        def add_rel(p: Path):
            rel = str(p.relative_to(xfl)).replace("\\","/")
            ET.SubElement(root, "file", {"path": rel})
        add_rel(xfl / "DOMDocument.xml"); add_rel(xfl / "main.xfl")
        for p in (xfl / "library").rglob("*"):
            if p.is_file(): add_rel(p)
        ET.ElementTree(root).write(xfl / "filelist.xml", encoding="utf-8", xml_declaration=True)

    print("\nOK  XFL created:", xfl)
    print(f"Stage size written: {stage_w:.2f} x {stage_h:.2f} (after × {DPIK})")

if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print()
