"""Camera contracts and portable observations. No renderer imported at module load."""
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zlib


def vector(value, size, name):
    if not isinstance(value, (list, tuple)) or len(value) != size or any(
            isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in value):
        raise ValueError(name + ' requires {} finite numbers'.format(size))
    return list(map(float, value))


def identifier(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', name):
        raise ValueError('Use an identifier of at most 64 letters, digits or underscores')
    return name


def camera_config(config):
    if not isinstance(config, dict) or set(config) - {'name', 'parent', 'position', 'quaternion', 'width', 'height', 'fovy', 'near', 'far'}:
        raise ValueError('Invalid camera fields')
    value = {'parent': 'world', 'position': [1.5, 0, 1.5], 'quaternion': [1, 0, 0, 0],
             'width': 320, 'height': 240, 'fovy': 45., 'near': .01, 'far': 100., **config}
    identifier(value.get('name'))
    if not isinstance(value['parent'], str) or not value['parent']:
        raise ValueError('parent must identify an existing body/prim or world')
    value['position'] = vector(value['position'], 3, 'position')
    q = vector(value['quaternion'], 4, 'quaternion wxyz')
    norm = math.sqrt(sum(x*x for x in q))
    if norm < 1e-10:
        raise ValueError('quaternion must be nonzero')
    value['quaternion'] = [x/norm for x in q]
    for key in ('width', 'height'):
        if type(value[key]) is not int or not 16 <= value[key] <= 1024:
            raise ValueError(key + ' must be 16..1024')
    for key in ('fovy', 'near', 'far'):
        if isinstance(value[key], bool) or not isinstance(value[key], (float, int)) or not math.isfinite(value[key]):
            raise ValueError('Invalid camera ' + key)
    if not 1 < value['fovy'] < 179 or not 0 < value['near'] < value['far']:
        raise ValueError('Invalid field of view or clipping planes')
    return value


def rotation(q):
    import numpy as np
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def calibration(config, position, orientation):
    """orientation is the camera-to-world rotation with OpenGL camera axes."""
    import numpy as np
    fy = .5*config['height']/math.tan(math.radians(config['fovy'])/2)
    transform = np.eye(4)
    transform[:3, :3] = orientation
    transform[:3, 3] = position
    return {'intrinsics': [[fy, 0, config['width']/2], [0, fy, config['height']/2], [0, 0, 1]],
            'camera_to_world': transform.tolist(), 'camera_axes': 'OpenGL: +X right, +Y up, -Z forward',
            'pixel_axes': '+u right, +v down', 'depth_units': 'metres', 'depth_kind': 'image_plane',
            'width': config['width'], 'height': config['height'], 'near': config['near'], 'far': config['far']}


def png(path, rgb):
    """Lossless RGB PNG without a mandatory Pillow dependency."""
    import numpy as np
    pixels = np.asarray(rgb, dtype=np.uint8)
    h, w, channels = pixels.shape
    if channels != 3:
        raise ValueError('RGB image required')
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data) & 0xffffffff)
    raw = b''.join(b'\0' + row.tobytes() for row in pixels)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', w,h,8,2,0,0,0))
                           + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def save_capture(directory, observation, frames):
    import numpy as np
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    cameras = {}
    for name, frame in frames.items():
        identifier(name)
        rgb, depth, mask = frame['rgb'], frame['depth'], frame['segmentation']
        png(directory/(name+'.png'), rgb)
        np.savez_compressed(directory/(name+'.npz'), rgb=rgb, depth=depth, segmentation=mask)
        finite = np.isfinite(depth) & (depth > 0)
        cameras[name] = {**frame['calibration'], 'labels': frame.get('labels', {}),
                         'rgb': str((directory/(name+'.png')).resolve()),
                         'arrays': str((directory/(name+'.npz')).resolve()),
                         'rgb_sha256': hashlib.sha256((directory/(name+'.png')).read_bytes()).hexdigest(),
                         'mean_rgb': float(np.mean(rgb)), 'rgb_variance': float(np.var(rgb)),
                         'valid_depth_fraction': float(finite.mean()),
                         'visibility_verdict': 'unverified'}
    result = {'observation': observation, 'cameras': cameras,
              'semantic_verdict': 'unverified', 'path': str((directory/'capture.json').resolve())}
    (directory/'capture.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    return result
