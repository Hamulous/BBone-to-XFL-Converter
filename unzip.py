from struct import unpack
import zlib
from pathlib import Path

def unzip(file_path):
    with open(file_path, "rb") as f:
        data = f.read() 

    object_name = str(Path(file_path).name).split(".")[0]

    # 1. Read header
    file_type = unpack(">H", data[0:2])[0]
    if file_type != 0x5678:
        raise Exception("Not a valid BBONE file")

    header_len = unpack(">H", data[2:4])[0]  # e.g. 0x0020 = 32 bytes
    compressed_data = data[header_len:]

    # 2. Decompress using zlib
    uncompressed = zlib.decompress(compressed_data)

    plugin_map = []
    ptr = 0
    while True:
        plugin_id = uncompressed[ptr]
        ptr += 1
        if plugin_id == 0:
            break
        offset = unpack(">I", uncompressed[ptr:ptr+4])[0]
        ptr += 4
        length = unpack(">I", uncompressed[ptr:ptr+4])[0]
        ptr += 4
        plugin_map.append({
            "id": plugin_id,
            "offset": offset,
            "length": length
        })

    plugin_data_blob = uncompressed[ptr:]

    plugin_contents = {}
    for plugin in plugin_map:
        raw = plugin_data_blob[plugin["offset"]:plugin["offset"] + plugin["length"]]
        plugin_contents[plugin["id"]] = raw

    return object_name, plugin_contents