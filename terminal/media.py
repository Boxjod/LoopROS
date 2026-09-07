"""Bounded local attachments; videos become sampled image frames."""
import base64
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import os
import shlex
import threading
from urllib.parse import unquote, urlparse

IMAGE_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif'}
VIDEO_TYPES = {'.mp4', '.mov', '.mkv', '.webm', '.avi'}
_IMAGE_MENTION = re.compile(r"""['"]?([^\s'"]+\.(?:png|jpe?g|webp|gif))['"]?""", re.I)


def dropped_paths(text):
    """Recognize a composer containing only local media paths, never prose."""
    try:
        paths = shlex.split(text)
    except ValueError:
        return []
    result = []
    for value in paths:
        if value.startswith('file://'):
            uri = urlparse(value)
            if uri.netloc not in ('', 'localhost'):
                return []
            value = unquote(uri.path)
        path = Path(value).expanduser()
        if path.suffix.lower() not in IMAGE_TYPES.keys() | VIDEO_TYPES or not path.is_file():
            return []
        result.append(str(path))
    return result


def mentioned_image(text):
    """Best-effort auto-attach for prose that references an existing local image; silent no-op otherwise."""
    seen = set()
    for match in _IMAGE_MENTION.finditer(text):
        candidate = match.group(1)
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            path = Path(candidate).expanduser().resolve(strict=True)
        except OSError:
            continue
        if not path.is_file() or path.suffix.lower() not in IMAGE_TYPES:
            continue
        try:
            return [(str(path), [image_part(path)])]
        except ValueError:
            continue
    return []


def clipboard_image():
    """Read PNG only on explicit request, with bounded output and no shell."""
    if os.environ.get('WAYLAND_DISPLAY') and shutil.which('wl-paste'):
        command = ['wl-paste', '--no-newline', '--type', 'image/png']
    elif os.environ.get('DISPLAY') and shutil.which('xclip'):
        command = ['xclip', '-selection', 'clipboard', '-t', 'image/png', '-o']
    else:
        raise ValueError('Clipboard images require wl-paste (Wayland) or xclip (X11); use /attach PATH instead')
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    # A reader timeout also bounds stalled clipboard owners.
    timer = threading.Timer(5, process.kill)
    timer.start()
    try:
        data = process.stdout.read(8 * 1024 * 1024 + 1)
        if len(data) > 8 * 1024 * 1024:
            raise ValueError('Image limit: 8 MiB')
        if process.wait(timeout=1) or not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('No PNG image in clipboard; copy an image or use /attach PATH')
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
    return [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(data).decode()}}]


def image_part(path):
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('Image limit: 8 MiB')
    data = path.read_bytes()
    return {'type': 'image_url', 'image_url': {'url': 'data:' + IMAGE_TYPES[path.suffix.lower()] + ';base64,' + base64.b64encode(data).decode()}}


def attachment(path):
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file() or path.stat().st_size > 100 * 1024 * 1024:
        raise ValueError('Attachment must be a file of at most 100 MiB')
    if path.suffix.lower() in IMAGE_TYPES:
        return [image_part(path)]
    if path.suffix.lower() not in VIDEO_TYPES:
        raise ValueError('Supported: PNG/JPEG/WebP/GIF, MP4/MOV/MKV/WebM/AVI')
    if not shutil.which('ffmpeg'):
        raise ValueError('Video attachments require ffmpeg')
    with tempfile.TemporaryDirectory(prefix='loop-ros-frames-') as directory:
        # Restrict demuxer protocols: a local playlist must not fetch external URLs.
        result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
                                 '-i', str(path), '-vf', 'fps=1/5,scale=768:768:force_original_aspect_ratio=decrease',
                                 '-frames:v', '6', str(Path(directory) / '%02d.jpg')],
                                capture_output=True, timeout=30)
        frames = sorted(Path(directory).glob('*.jpg'))
        if result.returncode or not frames:
            raise ValueError('Unable to extract video frames')
        return [{'type': 'text', 'text': 'Video samples: up to six frames at 5-second intervals from the first 30 seconds; no audio.'},
                *[image_part(frame) for frame in frames]]
