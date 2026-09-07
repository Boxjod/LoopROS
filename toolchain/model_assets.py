"""Immutable in-memory MJCF assets; imported files must match their manifest."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET


def safe_path(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or '\\' in value or ':' in value:
        raise ValueError('Unsafe asset path: ' + value)
    return value


def snapshot(scene):
    scene = Path(scene)
    content = scene.read_bytes()
    manifest_path = scene.parent / '.loop-assets.json'
    if not manifest_path.exists():
        return content, {}, hashlib.sha256(content).hexdigest()
    manifest = json.loads(manifest_path.read_text())
    assets = {}
    digest = hashlib.sha256()
    for name, expected in sorted(manifest['files'].items()):
        safe_path(name)
        path = scene.parent / name
        if not path.resolve().is_relative_to(scene.parent.resolve()):
            raise ValueError('Asset escapes model directory')
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected:
            raise ValueError('Asset checksum mismatch: ' + name)
        if name.lower().endswith('.xml'):
            root = ET.fromstring(data)
            if root.find('.//plugin') is not None:
                raise ValueError('Engine plugins are not supported by library import')
            for element in root.iter():
                for key in ('file', 'meshdir', 'texturedir', 'assetdir'):
                    if element.get(key):
                        safe_path(element.get(key))
        assets[name] = data
        digest.update(name.encode() + b'\0' + actual.encode())
    if scene.name not in assets:
        raise ValueError('Scene is missing from asset manifest')
    return assets[scene.name], assets, digest.hexdigest()
