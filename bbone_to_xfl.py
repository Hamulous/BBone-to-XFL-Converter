import os, sys, json, argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from xml.etree.ElementTree import Element, SubElement, ElementTree

# Helpers (must be next to this file)
from unzip import unzip
from split_atlas import split_atlas, get_split_json
from get_atlas import parse_atlas
from get_animation import get_animation_json
from get_animation_labels import parse_frame_labels

# ---------------- XML utils ----------------
def _indent(e, lvl=0):
    i = "\n" + "  "*lvl
    if len(e):
        if not (e.text or "").strip():
            e.text = i + "  "
        for c in e:
            _indent(c, lvl+1)
        if not (e.tail or "").strip():
            e.tail = i
    else:
        if lvl and not (e.tail or "").strip():
            e.tail = i

def _writexml(root: Element, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    _indent(root)
    ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

def _matrix(parent, m: Dict[str, float]):
    M = SubElement(parent, "Matrix")
    M.set("a",  str(m.get("a", 1.0)))
    M.set("b",  str(m.get("b", 0.0)))
    M.set("c",  str(m.get("c", 0.0)))
    M.set("d",  str(m.get("d", 1.0)))
    M.set("tx", str(m.get("tx", 0.0)))
    M.set("ty", str(m.get("ty", 0.0)))
    return M

def _color(parent, c: Dict[str, float]):
    if not c: return
    C = SubElement(parent, "Color")
    C.set("redMultiplier",   str(c.get("redMultiplier",   1.0)))
    C.set("greenMultiplier", str(c.get("greenMultiplier", 1.0)))
    C.set("blueMultiplier",  str(c.get("blueMultiplier",  1.0)))
    C.set("alphaMultiplier", str(c.get("alphaMultiplier", 1.0)))

def _float(v, d=0.0):
    try: return float(v)
    except Exception: return float(d)

# ---------------- name normalization ----------------
def _norm_name(n: str) -> str:
    if not n: return ""
    n = n.strip()
    if "/" in n: n = n.split("/")[-1]
    if "\\" in n: n = n.split("\\")[-1]
    if n.lower().endswith(".png"): n = n[:-4]
    return n

# ---------- composition (matches web viewer) ----------
# M' = M · T(ox,oy) · S(sx,sy)
def compose_instance_matrix(frame_m: Dict[str, float], plist_rec: Dict[str, float]) -> Dict[str, float]:
    a  = _float(frame_m.get("a", 1.0))
    b  = _float(frame_m.get("b", 0.0))
    c  = _float(frame_m.get("c", 0.0))
    d  = _float(frame_m.get("d", 1.0))
    tx = _float(frame_m.get("tx", 0.0))
    ty = _float(frame_m.get("ty", 0.0))

    ox = _float(plist_rec.get("origin_x", 0.0))
    oy = _float(plist_rec.get("origin_y", 0.0))
    sx = _float(plist_rec.get("scale_x", 1.0))
    sy = _float(plist_rec.get("scale_y", 1.0))

    tx1 = a*ox + c*oy + tx
    ty1 = b*ox + d*oy + ty

    return {"a": a*sx, "b": b*sx, "c": c*sy, "d": d*sy, "tx": tx1, "ty": ty1}

# ---------- library builders ----------
def _media_item(name) -> Element:
    ns = "http://ns.adobe.com/xfl/2008/"
    return Element("DOMBitmapItem", {"xmlns": ns, "name": f"media/{name}", "href": f"media/{name}.png"})

def _image_symbol(name) -> Element:
    ns = "http://ns.adobe.com/xfl/2008/"
    sym = Element("DOMSymbolItem", {"xmlns": ns, "name": f"image/{name}", "itemID": f"image/{name}", "lastModified":"0"})
    tl  = SubElement(sym, "timeline"); dt = SubElement(tl, "DOMTimeline", {"name": f"image/{name}"})
    layers = SubElement(dt, "layers")
    lyr = SubElement(layers, "DOMLayer", {"name": "Layer 1", "color": "#4F81BD"})
    frs = SubElement(lyr, "frames")
    f0  = SubElement(frs, "DOMFrame", {"index": "0", "duration": "1"})
    els = SubElement(f0, "elements")
    SubElement(els, "DOMBitmapInstance", {"libraryItemName": f"media/{name}", "name": f"{name}_bmp"})
    return sym

# ---------- sprite builders ----------
def _sprite_symbol(symname: str,
                   frames: List[Dict[str,Any]],
                   piece_names: List[str],
                   labels: Dict[str,int],
                   plist: Dict[str,Dict[str,float]],
                   include_unused: bool,
                   report_missing: bool,
                   trace_names: bool,
                   only: Optional[List[str]],
                   aliases: Dict[str, str],
                   global_scale: float) -> Element:
    """
    Frame-by-frame export with aliasing and global scale:
      • Labels on their own layer (sparse spans).
      • Layers only for pieces that actually appear (unless include_unused=True or filtered via --only).
      • Every timeline frame gets duration=1; instance only when present.
      • Child names normalized + alias-mapped to atlas names.
      • Global scale multiplies a,b,c,d,tx,ty on each instance.
    """
    ns = "http://ns.adobe.com/xfl/2008/"
    sym = Element("DOMSymbolItem", {"xmlns": ns, "name": f"sprite/{symname}",
                                    "itemID": f"sprite/{symname}", "lastModified":"0"})
    tl  = SubElement(sym, "timeline")
    dt  = SubElement(tl, "DOMTimeline", {"name": symname})
    layers = SubElement(dt, "layers")

    total = max(1, len(frames))

    # Map frames -> { atlasPieceName: childNode } and count usage
    fmap: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}
    for f in frames:
        per = {}
        for ch in (f.get("children") or []):
            raw = ch.get("name")
            n = _norm_name(raw)
            if not n:
                continue
            n = aliases.get(n, n)  # apply alias if provided
            per[n] = ch
            counts[n] = counts.get(n, 0) + 1
        fmap.append(per)

    atlas_set = set(piece_names)
    used = set(k for k, v in counts.items() if v > 0)

    if report_missing:
        missing = sorted(n for n in used if n not in atlas_set)
        if missing:
            print("[warn] names in frames but not in atlas (after normalization/alias):",
                  ", ".join(missing[:20]) + (" ..." if len(missing) > 20 else ""))

    # Labels layer (sparse)
    if labels:
        lab_layer = SubElement(layers, "DOMLayer", {"name": "__labels__", "color": "#FF9900"})
        lab_frames = SubElement(lab_layer, "frames")
        starts = sorted({max(0, int(v) - 1) for v in labels.values()})
        if not starts or starts[0] != 0:
            starts = [0] + starts
        starts += [total]
        for i in range(len(starts) - 1):
            s, e = starts[i], starts[i+1]
            dur = max(1, e - s)
            name_here = next((lbl for lbl, v in labels.items() if max(0, int(v)-1) == s), None)
            attrs = {"index": str(s), "duration": str(dur)}
            if name_here: attrs["name"] = name_here
            SubElement(lab_frames, "DOMFrame", attrs)

    # Decide which layers to build
    if only:
        only_norm = {_norm_name(x) for x in only}
        order = [n for n in piece_names if n in only_norm]
    else:
        order = list(piece_names) if include_unused else [n for n in piece_names if n in used]

    if trace_names:
        print("[trace] piece usage (frame count) -> layered?:")
        all_names = sorted(set(list(piece_names) + list(used)))
        for n in all_names:
            flag = "YES" if n in order else "no"
            print(f"  {n:35s} {counts.get(n,0):5d}  {flag}")

    # Build layers
    for li, name in enumerate(order):
        lyr = SubElement(layers, "DOMLayer", {
            "name": name, "color": "#%06X" % (0x444444 + (li * 123457) % 0xBBBBBB)
        })
        frs = SubElement(lyr, "frames")
        pinfo = plist.get(name, {})

        for idx in range(total):
            df = SubElement(frs, "DOMFrame", {"index": str(idx), "duration": "1"})
            node = fmap[idx].get(name)
            if not node:
                continue  # empty frame
            els = SubElement(df, "elements")
            inst = SubElement(els, "DOMSymbolInstance", {
                "libraryItemName": f"image/{name}",
                "name": f"{name}_inst"
            })
            composed = compose_instance_matrix(node.get("matrix", {}), pinfo)
            # apply global scale (e.g., 0.78125 for 1536->1200)
            s = global_scale
            if s != 1.0:
                composed = {
                    "a":  composed["a"]  * s,
                    "b":  composed["b"]  * s,
                    "c":  composed["c"]  * s,
                    "d":  composed["d"]  * s,
                    "tx": composed["tx"] * s,
                    "ty": composed["ty"] * s,
                }
            _matrix(SubElement(inst, "matrix"), composed)
            _color(inst, node.get("color", {}))

    return sym

def _sprite_identity(symname: str, piece_names: List[str]) -> Element:
    ns = "http://ns.adobe.com/xfl/2008/"
    sym = Element("DOMSymbolItem", {"xmlns": ns, "name": f"sprite/{symname}",
                                    "itemID": f"sprite/{symname}", "lastModified":"0"})
    tl = SubElement(sym, "timeline"); dt = SubElement(tl, "DOMTimeline", {"name": symname})
    layers = SubElement(dt, "layers")
    for li, name in enumerate(piece_names):
        lyr = SubElement(layers, "DOMLayer", {"name": name, "color": "#%06X"%(0x444444 + (li*123457)%0xBBBBBB)})
        frs = SubElement(lyr, "frames")
        df = SubElement(frs, "DOMFrame", {"index":"0", "duration":"1"})
        els = SubElement(df, "elements")
        SubElement(els, "DOMSymbolInstance", {"libraryItemName": f"image/{name}", "name": f"{name}_inst"})
    return sym

def _domdocument(symname, media_items, includes, fps, w, h, main_label="idle", stage_item: Optional[str]=None) -> Element:
    ns = "http://ns.adobe.com/xfl/2008/"
    doc = Element("DOMDocument", {"xmlns": ns, "frameRate": str(fps), "width": f"{w:.6f}", "height": f"{h:.6f}", "xflVersion":"2.971"})
    folders = SubElement(doc, "folders")
    for f in ("media","image","sprite","label"):
        SubElement(folders, "DOMFolderItem", {"name": f, "isExpanded":"true"})
    media = SubElement(doc, "media")
    for n in sorted(media_items): media.append(_media_item(n))
    symbols = SubElement(doc, "symbols")
    for href in includes: SubElement(symbols, "Include", {"href": href})
    timelines = SubElement(doc, "timelines")
    dt = SubElement(timelines, "DOMTimeline", {"name":"Scene 1"})
    layers = SubElement(dt, "layers")
    lyr = SubElement(layers, "DOMLayer", {"name":"root"})
    frs = SubElement(lyr, "frames")
    f0  = SubElement(frs, "DOMFrame", {"index":"0","duration":"1","name": main_label})
    els = SubElement(f0, "elements")
    if stage_item:
        SubElement(els, "DOMSymbolInstance", {"libraryItemName": f"image/{stage_item}", "name":"debugImage"})
    else:
        SubElement(els, "DOMSymbolInstance", {"libraryItemName": f"sprite/{symname}", "name":"rootSymbol"})
    return doc

# ---------------- frames discovery ----------------
def _discover_frames(data: Any) -> Tuple[List[dict], str]:
    try_paths = [
        ("frames", data.get("frames")),
        ("anims[0].frames", (data.get("anims") or [{}])[0].get("frames") if data.get("anims") else None),
        ("animations[0].frames", (data.get("animations") or [{}])[0].get("frames") if data.get("animations") else None),
        ("timeline.frames", (data.get("timeline") or {}).get("frames") if data.get("timeline") else None),
    ]
    for p, v in try_paths:
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v, p
    def scan(node, trail="$"):
        if isinstance(node, list):
            if node and isinstance(node[0], dict) and ("children" in node[0] or "matrix" in node[0]):
                return node, trail
            for i, it in enumerate(node):
                r = scan(it, f"{trail}[{i}]")
                if r[0]: return r
        elif isinstance(node, dict):
            for k, v in node.items():
                r = scan(v, f"{trail}.{k}")
                if r[0]: return r
        return [], ""
    return scan(data)

# ---------------- conversion helpers ----------------
def _load_animjson_override(path: str, verbose=False):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    frames = data.get("frames") or []
    labels_raw = data.get("labels") or {}
    labels: Dict[str, int] = {}
    if isinstance(labels_raw, dict):
        labels = {k: int(v) for k, v in labels_raw.items()}
    elif isinstance(labels_raw, list):
        for it in labels_raw:
            n = it.get("name"); fr = it.get("frame")
            if n is not None and fr is not None:
                labels[n] = int(fr)

    plist_list = data.get("plist", []) or []
    plist = {entry.get("name"): entry for entry in plist_list}

    found_path = ""
    if not frames:
        frames, found_path = _discover_frames(data)
        if verbose and frames:
            print(f"[info] discovered frames at: {found_path}  (count={len(frames)})")

    return frames, labels, plist

# ---------------- Time to Convert ----------------
def convert_bbone_to_xfl(
    bbone: Path,
    fps: int = 30,
    width: float = 390,
    height: float = 390,
    animjson_override: Optional[str] = None,
    verbose: bool = False,
    debug_piece: Optional[str] = None,
    list_pieces: bool = False,
    identity_sprite: bool = False,
    include_unused: bool = False,
    report_missing: bool = False,
    trace_names: bool = False,
    only: Optional[List[str]] = None,
    aliases: Optional[Dict[str, str]] = None,
    global_scale: float = 1.0,
) -> Path:
    obj, contents = unzip(str(bbone))
    if verbose:
        print("[info] object:", obj)

    out = bbone.with_suffix(".xfl")
    if out.exists():
        for r, d, f in os.walk(out, topdown=False):
            for x in f:
                try: os.remove(Path(r, x))
                except: pass
            for x in d:
                try: os.rmdir(Path(r, x))
                except: pass
    out.mkdir(exist_ok=True)

    lib = out / "library"
    media = lib / "media"
    image = lib / "image"
    sprite = lib / "sprite"
    label = lib / "label"
    for d in (media, image, sprite, label):
        d.mkdir(parents=True, exist_ok=True)

    # Atlas -> PNG slices
    atlas_bmp = parse_atlas(contents[1])
    recs = get_split_json(contents[1])
    for r in recs:
        r["name"] = r["name"].strip()
    split_atlas(recs, str(media), atlas_bmp)
    piece_names = sorted({r["name"] for r in recs})
    if verbose:
        print(f"[info] exported {len(piece_names)} PNGs to", media)
        print("[info] first few pieces:", ", ".join(piece_names[:8]))

    if list_pieces:
        print("\n".join(piece_names))
        return out

    # Frames / labels / plist (All the main bullshit
    if animjson_override:
        frames, labels, plist = _load_animjson_override(animjson_override, verbose=verbose)
        if verbose:
            print("[info] using override animation.json:", animjson_override)
    else:
        anim = get_animation_json(contents[2]) or {}
        frames = anim.get("frames", [])
        labels = parse_frame_labels(contents[3]) if 3 in contents else {}
        try:
            with open(contents[2], "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}
        plist = {e.get("name"): e for e in (raw.get("plist") or [])}
        if not frames:
            frames, found = _discover_frames(raw)
            if verbose and frames:
                print(f"[info] discovered frames at: {found}  (count={len(frames)})")

    if verbose:
        print(f"[info] frames: {len(frames)}  labels: {len(labels)}  plist entries: {len(plist)}")
        if len(frames) == 0 and not identity_sprite:
            print("[warn] No frames in animation data -> sprite timeline will be empty (use --identity-sprite to preview pieces).")

    # Build image wrapper symbols (no transform)
    for n in piece_names:
        _writexml(_image_symbol(n), image / f"{n}.xml")
    if verbose:
        print(f"[info] image symbols -> {image}")

    alias_map = aliases or {}

    # Main sprite timeline
    if identity_sprite or len(frames) == 0:
        _writexml(_sprite_identity(obj, piece_names), sprite / f"{obj}.xml")
        if verbose:
            print("[info] built identity sprite (single frame, all parts at reg point)")
    else:
        _writexml(
            _sprite_symbol(obj, frames, piece_names, labels, plist,
                           include_unused=include_unused, report_missing=report_missing,
                           trace_names=trace_names, only=only, aliases=alias_map,
                           global_scale=global_scale),
            sprite / f"{obj}.xml"
        )
        if verbose:
            print(f"[info] sprite symbol -> {sprite / (obj + '.xml')}")

    # Root label
    main_label = "idle"
    if labels:
        main_label = sorted(labels.items(), key=lambda kv: kv[1])[0][0]

    # DOMDocument + Includes
    includes = [f"image/{n}.xml" for n in piece_names] + [f"sprite/{obj}.xml"]
    _writexml(_domdocument(obj, piece_names, includes, fps, width, height, main_label, debug_piece),
              out / "DOMDocument.xml")
    if verbose:
        print(f"[info] DOMDocument -> {out/'DOMDocument.xml'}")

    (out / "main.xfl").write_text("PROXY-CS5", encoding="utf-8")
    return out

# ------------------ COOL ASS DEBUG SHIT YES YES YES ------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="BBone -> Animate XFL (dense keys + normalized names + aliases + scale)")
    p.add_argument("bbone", help="Path to .bbone")
    p.add_argument("--animjson", type=str, default=None, help="Path to external animation.json to override frames/labels/plist")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--w", type=float, default=390)
    p.add_argument("--h", type=float, default=390)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--debug-piece", type=str, default=None, help="Place image/<NAME> directly on stage (bypass sprite)")
    p.add_argument("--list-pieces", action="store_true", help="Print all available piece names and exit")
    p.add_argument("--identity-sprite", action="store_true", help="Build a 1-frame sprite with all pieces at reg points")
    p.add_argument("--include-unused", action="store_true", help="Also create layers for pieces that never appear in frames")
    p.add_argument("--report-missing", action="store_true", help="Report names in frames that don't match atlas pieces after normalization/alias")
    p.add_argument("--trace-names", action="store_true", help="Print per-piece usage counts and layering decisions")
    p.add_argument("--only", type=str, default=None, help="Comma-separated list of piece names; build layers only for these")
    p.add_argument("--alias", action="append", default=[], help="Map a frame name to an atlas name, e.g. --alias from=to (repeatable)")
    p.add_argument("--scale", type=float, default=1.0, help="Global scale applied to all matrices (a,b,c,d,tx,ty)")
    a = p.parse_args()

    alias_map: Dict[str, str] = {}
    for pair in a.alias:
        if "=" in pair:
            frm, to = pair.split("=", 1)
            alias_map[_norm_name(frm)] = _norm_name(to)

    out = convert_bbone_to_xfl(
        Path(a.bbone),
        fps=a.fps, width=a.w, height=a.h,
        animjson_override=a.animjson,
        verbose=a.verbose,
        debug_piece=a.debug_piece,
        list_pieces=a.list_pieces,
        identity_sprite=a.identity_sprite,
        include_unused=a.include_unused,
        report_missing=a.report_missing,
        trace_names=a.trace_names,
        only=(a.only.split(",") if a.only else None),
        aliases=alias_map,
        global_scale=a.scale,
    )
    print("XFL written to:", out)
