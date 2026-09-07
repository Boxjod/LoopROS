"""Read-only local text file access; never serves credentials or internal state databases."""
from pathlib import Path
import hashlib

MAX_BYTES = 64 * 1024


def schema(name, description, properties, required):
    return {'type': 'function', 'function': {'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'required': required,
                           'additionalProperties': False}}}


FILE_TOOLS = [
    schema('read_image', 'Read a local image and send its pixels through the configured visual model route for analysis. Use for PNG/JPEG/WebP/GIF; do not invent image details.', {'path': {'type':'string'}}, ['path']),
    schema('read_file', '读取本地文本文件内容（相对路径按项目根目录解析，也接受绝对路径）；用offset/limit分页读取大文件；仅支持文本，不支持图片/二进制；不能读取.loop凭据文件或任何.sqlite/.db内部状态库',
           {'path': {'type': 'string'}, 'offset': {'type': 'integer'}, 'limit': {'type': 'integer'}}, ['path']),
]

FILE_NAMES = {t['function']['name'] for t in FILE_TOOLS}


def _denied(path):
    from terminal.home import loop_home
    if path.name in ('.env', 'id_rsa', 'id_ed25519', 'config.local.json') or any(part in ('.ssh', '.aws') for part in path.parts):
        return True
    if path.suffix.lower() in ('.sqlite', '.db'):
        return True
    try:
        return path == (loop_home() / 'credentials.json').resolve()
    except OSError:
        return False


def read_file(path, offset=None, limit=None):
    if not isinstance(path, str) or not path:
        raise ValueError('path must be a non-empty string')
    if offset is not None and (not isinstance(offset, int) or offset < 1):
        raise ValueError('offset must be a positive integer (1-indexed)')
    if limit is not None and (not isinstance(limit, int) or limit < 1):
        raise ValueError('limit must be a positive integer')
    resolved = Path(path).expanduser()
    if not resolved.is_absolute():
        from terminal.config import ROOT
        resolved = ROOT / resolved
    try:
        resolved = resolved.resolve(strict=True)
    except OSError:
        raise ValueError('file not found: ' + str(resolved)) from None
    if not resolved.is_file():
        raise ValueError('not a file: ' + str(resolved))
    if _denied(resolved):
        raise ValueError('reading credentials or internal state databases is not permitted')
    if resolved.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('file too large for read_file; request a narrower offset/limit range')
    try:
        text = resolved.read_bytes().decode('utf-8')
    except UnicodeDecodeError:
        raise ValueError('not a UTF-8 text file; binary and image content are not supported by read_file') from None
    lines = text.split('\n')
    total = len(lines)
    start = (offset - 1) if offset else 0
    if start >= total:
        raise ValueError('offset {} is beyond end of file ({} lines total)'.format(offset, total))
    end = min(start + limit, total) if limit else total
    body = '\n'.join(lines[start:end])
    result = {'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(), 'path': str(resolved), 'start_line': start + 1, 'end_line': start + (end - start), 'total_lines': total}
    encoded = body.encode('utf-8')
    if len(encoded) > MAX_BYTES:
        body = encoded[:MAX_BYTES].decode('utf-8', errors='ignore')
        result['truncated'] = 'byte_limit'
    elif end < total:
        result['next_offset'] = end + 1
    result['content'] = body
    return result


def tool(app, name, args):
    if not isinstance(args, dict) or set(args) - {'path', 'offset', 'limit'} or 'path' not in args:
        raise ValueError('path is required; offset/limit are optional')
    from terminal.coding import resolve
    path=resolve(app,args['path'])
    if name == 'read_image':
        if set(args) != {'path'}: raise ValueError('read_image takes path only')
        from terminal.media import IMAGE_TYPES, image_part
        if path.suffix.lower() not in IMAGE_TYPES or not path.is_file(): raise ValueError('Image file not found or unsupported type')
        media=image_part(path)
        return {'path':str(path), 'image_loaded':True, 'mime_type':IMAGE_TYPES[path.suffix.lower()], '_media':[media]}
    return read_file(str(path), args.get('offset'), args.get('limit'))
