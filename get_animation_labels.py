import struct

def parse_frame_labels(data: bytes):
    pos = 0
    labels = {}

    count = struct.unpack_from(">I", data, pos)[0]
    pos += 4

    for _ in range(count):
        name_len = struct.unpack_from(">H", data, pos)[0]
        pos += 2

        name_bytes = data[pos:pos + name_len]
        try:
            name = name_bytes.decode('ascii')
        except UnicodeDecodeError:
            name = name_bytes.decode('latin1')
        pos += name_len

        frame = struct.unpack_from(">I", data, pos)[0]
        pos += 4

        labels[name] = frame

    return labels