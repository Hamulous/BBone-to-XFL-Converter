import struct
from io import BytesIO
from typing import Dict, List, Any, BinaryIO

TYPE_HAS_XY = 1
TYPE_HAS_M_A = 2
TYPE_HAS_M_B = 4
TYPE_HAS_M_C = 8
TYPE_HAS_M_D = 16
TYPE_HAS_ALPHA = 32
TYPE_HAS_COLORTRANSFORM = 64
TYPE_HAS_BLENDMODE = 128
TYPE_HAS_CHILDREN = 256
TYPE_HAS_BATCHES = 512

def read_short(stream: BinaryIO) -> int:
    """Reads a 2-byte signed short in big-endian format."""
    return struct.unpack('>h', stream.read(2))[0]

def read_ushort(stream: BinaryIO) -> int:
    """Reads a 2-byte unsigned short in big-endian format."""
    return struct.unpack('>H', stream.read(2))[0]

def read_int(stream: BinaryIO) -> int:
    """Reads a 4-byte signed integer in big-endian format."""
    return struct.unpack('>i', stream.read(4))[0]

def read_float(stream: BinaryIO) -> float:
    """Reads a 4-byte float in big-endian format."""
    return struct.unpack('>f', stream.read(4))[0]

def read_utf(stream: BinaryIO) -> str:
    """Reads a UTF-8 string prefixed with a 2-byte unsigned short length."""
    length = read_ushort(stream)
    return stream.read(length).decode('utf-8')

# Based on standard Flash ColorTransform structure (8 floats)
def read_color_transform(stream: BinaryIO) -> Dict[str, float]:
    """Reads a full ColorTransform object from the stream."""
    return {
        "redMultiplier": read_float(stream),
        "greenMultiplier": read_float(stream),
        "blueMultiplier": read_float(stream),
        "alphaMultiplier": read_float(stream),
        "redOffset": read_float(stream),
        "greenOffset": read_float(stream),
        "blueOffset": read_float(stream),
        "alphaOffset": read_float(stream),
    }

def parse_child_node(stream: BinaryIO, shared_pool: Dict) -> Dict[str, Any]:
    """
    Recursively parses a single bone node (BlitBoneFrameChild) from the stream.
    This is the core of the recursive descent parser.
    """
    flags = read_short(stream)
    class_name = read_utf(stream)

    # Initialize node with default values
    node = {
        "name": class_name,
        "matrix": {"a": 1.0, "b": 0.0, "c": 0.0, "d": 1.0, "tx": 0.0, "ty": 0.0},
        "color": {"alphaMultiplier": 1.0},
        "children": []
    }

    # Apply properties based on the bitmask flags
    if flags & TYPE_HAS_XY:
        node["matrix"]["tx"] = read_float(stream)
        node["matrix"]["ty"] = read_float(stream)
    
    if flags & TYPE_HAS_M_A: node["matrix"]["a"] = read_float(stream)
    if flags & TYPE_HAS_M_B: node["matrix"]["b"] = read_float(stream)
    if flags & TYPE_HAS_M_C: node["matrix"]["c"] = read_float(stream)
    if flags & TYPE_HAS_M_D: node["matrix"]["d"] = read_float(stream)

    if flags & TYPE_HAS_ALPHA:
        node["color"]["alphaMultiplier"] = read_float(stream)
        
    if flags & TYPE_HAS_COLORTRANSFORM:
        node["color"] = read_color_transform(stream)

    if flags & TYPE_HAS_BLENDMODE:
        node["blendMode"] = read_utf(stream)

    if flags & TYPE_HAS_CHILDREN:
        children_count = read_short(stream)
        for _ in range(children_count):
            child = parse_child_node(stream, shared_pool)
            node["children"].append(child)

    if flags & TYPE_HAS_BATCHES:
        # This node is a container for a shared animation.
        # It doesn't have its own children; its content is defined by the shared animation.
        node["references_shared_animation"] = class_name
        # The actual frame data will be looked up from the shared_pool using this name.
        
    return node

def parse_single_frame_batch(stream: BinaryIO, shared_pool: Dict) -> Dict[str, List]:
    """Parses a single frame's data (BlitBoneFrameBatch)."""
    children_count = read_int(stream)
    frame = {"children": []}
    for _ in range(children_count):
        frame["children"].append(parse_child_node(stream, shared_pool))
    return frame

def decode_animation_chunk(data: bytes) -> Dict[str, Any]:
    """
    Parses the binary data of a Type 2 chunk.
    This is the main entry point for parsing the file content.
    """
    stream = BytesIO(data)
    shared_animations_pool = {}
    
    # 1. Decode the shared animations pool at the beginning of the chunk
    shared_block_count = read_short(stream)
    for _ in range(shared_block_count):
        block_name = read_utf(stream)
        frames_in_block = read_short(stream)
        
        animation_frames = []
        for _ in range(frames_in_block):
            frame_data = parse_single_frame_batch(stream, shared_animations_pool)
            animation_frames.append(frame_data)
        shared_animations_pool[block_name] = animation_frames

    # 2. Decode the main animation timeline
    main_timeline_frames = []
    total_frames = read_int(stream)
    for i in range(total_frames):
        try:
            frame_data = parse_single_frame_batch(stream, shared_animations_pool)
            main_timeline_frames.append(frame_data)
        except struct.error as e:
            print(f"Error parsing main timeline at frame {i+1}/{total_frames}: {e}")
            print("File might be truncated or corrupted.")
            break
            
    return {
        "shared_animations": shared_animations_pool,
        "frames": main_timeline_frames
    }

def get_animation_json(data: bytes):
    print("正在解码动画数据...")
    try:
        decoded_data = decode_animation_chunk(data)
    except Exception as e:
        print(f"解码动画数据时出现错误: {e}")
        import traceback
        traceback.print_exc()
        return
    
    return decoded_data