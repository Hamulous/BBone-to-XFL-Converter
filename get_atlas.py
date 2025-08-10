from pathlib import Path
from io import BytesIO
from PIL import Image
import struct
import numpy as np

def parse_atlas(data: bytes):
    stream = BytesIO(data)
    bitmap_flag = struct.unpack("B", stream.read(1))[0]

    if bitmap_flag != 0xFF:
        raise ValueError("Unexpected format: not a bitmap blit plugin")

    bitmap_count = struct.unpack(">H", stream.read(2))[0]
    bitmaps = []

    for _ in range(bitmap_count):
        width, height = struct.unpack(">HH", stream.read(4))
        marker = struct.unpack(">H", stream.read(2))[0]

        if marker == 65495:  # JPEG marker
            size = struct.unpack(">I", stream.read(4))[0]
            jpeg_data = stream.read(size)
            image = Image.open(BytesIO(jpeg_data)).convert("RGBA")
        else:
            stream.seek(-2, 1)
            pixel_data = stream.read(width * height * 4)
            image = Image.frombytes("RGBA", (width, height), pixel_data)

            arr = np.array(image)
            if arr.shape[2] == 4:
                arr = arr[..., [1, 2, 3, 0]]
            image = Image.fromarray(arr, "RGBA")

        bitmaps.append(image)

    return bitmaps[0]
