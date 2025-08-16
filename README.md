# BBone → Adobe Animate XFL Converter

#### This tool is a fork of [SproutNan's .bbone decompiler](https://github.com/SproutNan/BBone_Decom) which converts PvZ2 `.bbone` skeleton/animation files (plus their sprite atlas) into fully-wired **Adobe Animate XFL** projects. (It is primarily intended to convert `.bbone` files found [here](https://github.com/map220v/TencentPvZOL/tree/main/GameRes/swf/td/anmi).) It can also work from an existing `animation.json` and a folder of PNG parts. The output matches the web player’s draw order and transforms, and uses Animate’s standard **Library** layout with taking into account that you have knowlegde with PvZ2's animation format with this script doing all of your dirty work.
---

## NOTICE

This project is a **work in progress**. Many features may not function as intended due to limited testing. 
If you encounter any issues, please create an issue on this project’s repository or contact me on Discord (`hamulous`).

---

## Features
- Reads `.bbone` files and extracts sprite parts.
- Loads an external `animation.json`
- Loads external png images for the animation.
- Generates `.xfl` files compatible with Adobe Animate.
- Preserves frame-by-frame animation data from the original PvZ2 animation.
- Supports alias mapping for mismatched sprite names.
- Can trace missing or unused sprites for debugging.

---

## Requirements
- **Python 3.8+**
- Required libraries: `Pillow`, `lxml`, `argparse`

---

## Command-line usage & all options

There are two CLIs:

- **Recommended:** `bbone_to_xfl_symbols.py` — modern flow with optional `.bbone → animation.json`, optional image export, and XFL build (media in `library/media`).
- **Advanced / legacy:** `bbone_to_xfl.py` — single-shot converter with extra debugging, aliasing, and filtering tools.

> Pro Tip: On Windows `cmd.exe`, use `^` for line continuation. On macOS/Linux, use `\`.  
> Always quote paths that contain spaces.

---

### A) `bbone_to_xfl_symbols.py` (recommended)

**Generate JSON + export images + build XFL**

- **Windows**
  ```go
  python bbone_to_xfl_symbols.py ^
    --bbone "C:\path\zombie_gunman.bbone" ^
    --generate-json --export-images ^
    --out "C:\path\out_xfl" --name "gunman" ^
    --fps 30 --size 1200x1200

- **macOS/Linux**
  ```go
  python bbone_to_xfl_symbols.py ^
    --bbone "C:\path\zombie_gunman.bbone" ^
    --generate-json --export-images ^
    --out "C:\path\out_xfl" --name "gunman" ^
    --fps 30 --size 1200x1200

---

### Arguments (full reference)
```go
-- bbone <file>: Optional source .bbone file.
-- generate-json: With --bbone, decode and write animation.json.
-- only-json: Stop after generating JSON (no XFL build).
-- export-images: With --bbone, split the atlas to PNG parts.
-- json <file>: Use an existing animation.json.
-- images <dir>: Use an existing folder of PNG parts.
-- out <dir>: Output directory where <name>.xfl is created.
-- name <str>: Project name (folder <name>.xfl).
```
---

### Sizing (choose one approach)
```bash
-- size WxH (e.g. 1200x1200)
-- width <px> and/or --height <px> (missing side keeps aspect)
-- fps <int>: Timeline fps (default 30).
-- write-filelist: Also write a legacy filelist.xml (not required).
```
---

### Notes

- PNGs are copied into library/media/, and DOMDocument.xml references them as href="media/<file>.png".
- main.xfl enumerates all library/** files so Animate loads them immediately.
- Stage size written to XFL is (width × 0.78125) × (height × 0.78125).

### B) bbone_to_xfl.py (advanced / legacy)

This variant includes alias mapping, piece filtering, and debug aids.

Example (Windows)
---
```bash
python bbone_to_xfl.py "decoder\zombie_gunman.bbone" ^
  --animjson "decoder\animation.json" ^
  --alias zombie_ghostwrite_arms_outer_upper=zombie_egypt_arm_outer_upper ^
  --trace-names --report-missing --verbose
```

Example (macOS/Linux)
---
```bash
python3 bbone_to_xfl.py "decoder/zombie_gunman.bbone" \
  --animjson "decoder/animation.json" \
  --alias zombie_ghostwrite_arms_outer_upper=zombie_egypt_arm_outer_upper \
  --trace-names --report-missing --verbose
```

---

### Arguments (full reference)
```
-- <bbone>: Positional path to .bbone.
-- animjson <file>: Override frames/labels/plist with an external animation.json.
-- fps <int>: Timeline fps (default 30).
-- w <px> / --h <px>: Stage width/height (the script applies 0.78125 internally where applicable).
-- scale <float>: Global multiplier applied to all matrices (a,b,c,d,tx,ty) (e.g., 0.78125).
-- debug-piece <name>: Place image/<NAME> directly on stage for quick visual checks.
-- list-pieces: Print all atlas piece names and exit.
-- identity-sprite: Build a 1-frame sprite with all pieces at their registration points.
-- include-unused: Make layers for pieces that never appear in frames.
-- only <csv>: Only build layers for these pieces (comma-separated).
-- alias from=to (repeatable): Map frame names to atlas names; pass multiple flags to add more.
-- report-missing: Warn about names seen in frames that don’t exist in the atlas after normalization/aliasing.
-- trace-names: Print per-piece usage counts and whether it became a layer.
-- verbose: Extra logging.
```
---

### Tips

You can pass multiple --alias flags:

```bash
--alias a=b --alias arm_upper=arm_outer_upper --alias hand=hand_inner
```
Pair --only with --trace-names to quickly isolate and verify specific parts.

## Notes
- PvZ2 reads assets at **1200 resolution** (1536px assets scaled by `0.78125`).
- If your exported animation looks misaligned, enable scaling to match PvZ2’s resolution.
- Missing sprites may require alias mapping via the `--alias` flag.

---

## Output Structure
```
<output>.xfl/
    DOMDocument.xml
    library/
        image/
        media/
        sprite/
```

---

## To-Do
- Polish up layers by reverse-engineering the original project’s animation player. (Still some minor issues like layering)
- Program an output for a data.json in Sen 4 Format

---

## Credits
- [Hamulous](https://github.com/Hamulous) — Author of `bbone_to_xfl.py`  
- [SproutNan](https://github.com/SproutNan) — Everything Else
