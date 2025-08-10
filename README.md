# BBone to XFL Converter

This tool is a fork of [SproutNan's .bbone decompiler](https://github.com/SproutNan/BBone_Decom) which converts PvZ2 `.bbone` skeleton/animation files and associated sprites into Adobe Animate XFL projects.  
(It is primarily intended to convert `.bbone` files found [here](https://github.com/map220v/TencentPvZOL/tree/main/GameRes/swf/td/anmi).)

---

## NOTICE

This project is a **work in progress**. Many features may not function as intended due to limited testing.  
If you encounter any issues, please create an issue on this project’s repository or contact me on Discord (`hamulous`).

---

## Features
- Reads `.bbone` files and extracts sprite parts.
- Loads an external `animation.json` you will need to obtain from the [original project decompiler](https://github.com/SproutNan/BBone_Decom)  for frame/timeline data.
- Generates `.xfl` files compatible with Adobe Animate.
- Preserves frame-by-frame animation data from the original PvZ2 animation.
- Supports alias mapping for mismatched sprite names.
- Can trace missing or unused sprites for debugging.

---

## Requirements
- **Python 3.8+**
- Required libraries: `Pillow`, `lxml`, `argparse`

---

## Usage
```bash
python bbone_to_xfl.py "<path-to.bbone>" --animjson "<path-to-animation.json>"
```

### Optional Flags (Mostly Used for Debugging)
- `--verbose` : Prints detailed log information.
- `--trace-names` : Lists all parts found and their usage counts.
- `--report-missing` : Lists missing sprites between `animation.json` and `.bbone` data.
- `--alias old_name=new_name` : Remaps animation sprite names to atlas names.
- `--identity-sprite` : Creates a static sprite with all parts at registration points.

---

## Example
```bash
python bbone_to_xfl.py "decoder/zombie_gunman.bbone" ^
  --animjson "decoder/animation.json" ^
  --alias zombie_ghostwrite_arms_outer_upper=zombie_egypt_arm_outer_upper ^
  --trace-names --report-missing --verbose
```

---

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
- Polish up layers by reverse-engineering the original project’s animation player.
- Program an output for a data.json in Sen 4 Format
- Ensure all features are fully functional.

---

## Credits
- [Hamulous](https://github.com/Hamulous) — Author of `bbone_to_xfl.py`  
- [SproutNan](https://github.com/SproutNan) — Everything Else
