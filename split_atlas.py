from io import BytesIO
from PIL import Image
import struct

def split_atlas(frame_records, save_dir: str, bitmap: Image.Image):
    for entry in frame_records:
        name = entry['name']
        x = entry['rect_x']
        y = entry['rect_y']
        w = entry['rect_w']
        h = entry['rect_h']
        
        cropped = bitmap.crop((x, y, x + w, y + h))
        save_path = f"{save_dir}/{name}.png"
        cropped.save(save_path)

    print(f"Number of exported texture parts: {len(frame_records)}")

def get_split_json(data: bytes):
    stream = BytesIO(data)

    bitmap_flag = struct.unpack("B", stream.read(1))[0]
    if bitmap_flag != 0xFF:
        raise ValueError("Unexpected format: not a bitmap blit plugin")

    bitmap_count = struct.unpack(">H", stream.read(2))[0]

    for _ in range(bitmap_count):
        width, height = struct.unpack(">HH", stream.read(4))
        marker = struct.unpack(">H", stream.read(2))[0]
        if marker == 65495:
            size = struct.unpack(">I", stream.read(4))[0]
            stream.read(size)
        else:
            stream.seek(-2, 1)
            stream.read(width * height * 4)

    frame_count = struct.unpack(">H", stream.read(2))[0]

    frame_records = []
    for _ in range(frame_count):
        name_len = struct.unpack(">H", stream.read(2))[0]
        name = stream.read(name_len).decode("utf-8")

        total_frames = struct.unpack(">I", stream.read(4))[0]
        for _ in range(total_frames):
            frame_type = struct.unpack("B", stream.read(1))[0]
            if frame_type == 0xFF:
                bitmapDataId = struct.unpack(">H", stream.read(2))[0]
                offsetX = struct.unpack(">h", stream.read(2))[0]
                offsetY = struct.unpack(">h", stream.read(2))[0]
                width = struct.unpack(">H", stream.read(2))[0]
                height = struct.unpack(">H", stream.read(2))[0]
                xOrg = struct.unpack(">f", stream.read(4))[0]
                yOrg = struct.unpack(">f", stream.read(4))[0]
                scaleX = struct.unpack(">f", stream.read(4))[0]
                scaleY = struct.unpack(">f", stream.read(4))[0]
                rotation = struct.unpack(">f", stream.read(4))[0]

                frame_records.append({
                    "name": name,
                    "bitmap_id": bitmapDataId,
                    "rect_x": offsetX,
                    "rect_y": offsetY,
                    "rect_w": width,
                    "rect_h": height,
                    "origin_x": xOrg,
                    "origin_y": yOrg,
                    "scale_x": scaleX,
                    "scale_y": scaleY,
                    "rotation": rotation
                })
            else:
                break

    return frame_records

