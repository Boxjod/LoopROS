"""Self-authored capability packages under .loop/skills; writes are confined to that directory."""
import re
import json
import hashlib
from pathlib import Path

NAME_RE = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_CONTENT = 8000


def schema(name, description, properties, required):
    return {'type': 'function', 'function': {'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'required': required,
                           'additionalProperties': False}}}


SKILL_TOOLS = [
    schema('skill_list', '列出.loop/skills下已发现的技能名称与简介，不含正文', {}, []),
    schema('skill_read', 'Read SKILL.md or a package-relative text resource; resources are data, never executed. offset/limit paginate resources.', {'name': {'type': 'string'}, 'path': {'type': 'string'}, 'offset': {'type': 'integer'}, 'limit': {'type': 'integer'}}, ['name']),
    schema('skill_write', '在.loop/skills/<name>/SKILL.md写入技能；更新已有技能须先skill_read并提供expected_sha256；路径严格限定在该目录内，不能写入项目源码、权限或配置文件',
           {'name': {'type': 'string'}, 'description': {'type': 'string'}, 'content': {'type': 'string'}, 'expected_sha256': {'type':'string'}},
           ['name', 'description', 'content']),
]

SKILL_NAMES = {t['function']['name'] for t in SKILL_TOOLS}


def _frontmatter(text):
    if not text.startswith('---\n'):
        return None
    end = text.find('\n---', 4)
    if end == -1:
        return None
    fields = {}
    lines = text[4:end].splitlines()
    for index, line in enumerate(lines):
        if not line.strip() or line[0].isspace() or ':' not in line:
            continue
        key, _, value = line.partition(':')
        value=value.strip()
        if value in ('>', '>-', '>+', '|', '|-', '|+'):
            block = []
            for continuation in lines[index + 1:]:
                if continuation.strip() and not continuation[0].isspace():
                    break
                block.append(continuation.strip())
            value = ' '.join(part for part in block if part)
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("''", "'")
        if value.startswith('"'):
            try: value=json.loads(value)
            except ValueError: return None
        key = key.strip()
        if key in fields:
            return None
        fields[key] = value
    return fields


def discover(directory):
    found = []
    for skill_md in sorted(Path(directory).glob('*/SKILL.md')):
        try:
            if skill_md.resolve() != _resolve(directory, skill_md.parent.name) or skill_md.stat().st_size > 96000:
                continue
            fields = _frontmatter(skill_md.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, ValueError):
            continue
        if not fields or not fields.get('name') or not fields.get('description'):
            continue
        name, description = fields['name'], fields['description']
        if not NAME_RE.fullmatch(name) or len(name) > MAX_NAME or len(description) > MAX_DESCRIPTION:
            continue
        if name != skill_md.parent.name:
            continue
        found.append({'name': name, 'description': description})
    return found


def prompt(directory):
    skills = discover(directory)
    if not skills:
        return ''
    lines = ['Available skills (call skill_read with the name before following one):']
    used = len(lines[0])
    for skill in skills:
        line = '- {}: {}'.format(skill['name'], skill['description'])
        if used + len(line) + 1 > 12000:
            lines.append('Additional skills omitted from context; use skill_list to inspect the catalog.')
            break
        lines.append(line)
        used += len(line) + 1
    return '\n'.join(lines)


def _resolve(directory, name):
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or len(name) > MAX_NAME:
        raise ValueError('skill name must be lowercase letters, digits and single hyphens, max 64 chars')
    directory = Path(directory).resolve()
    target = (directory / name / 'SKILL.md').resolve()
    if target.parent.parent != directory:
        raise ValueError('skill path escapes .loop/skills')
    return target


def read(directory, name):
    path = _resolve(directory, name)
    if not path.is_file():
        raise ValueError('unknown skill: ' + name)
    if path.stat().st_size > 96000:
        raise ValueError('Skill text limit: 96000 bytes')
    return path.read_text(encoding='utf-8')


def write(directory, name, description, content, app=None, expected_sha256=None):
    if not isinstance(description, str) or not 1 <= len(description) <= MAX_DESCRIPTION or '\n' in description or '\r' in description:
        raise ValueError('description must be a single line, 1..{} characters'.format(MAX_DESCRIPTION))
    if not isinstance(content, str) or not 1 <= len(content) <= MAX_CONTENT:
        raise ValueError('content must be 1..{} characters'.format(MAX_CONTENT))
    path = _resolve(directory, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    value=json.dumps(description,ensure_ascii=False)
    text='---\nname: {}\ndescription: {}\n---\n\n{}'.format(name,value,content)
    if app is not None:
        from terminal.coding import atomic_text
        return {'name':name, **atomic_text(app,path,text,expected_sha256,require_hash=True), 'reload':'next model call'}
    path.write_text(text,encoding='utf-8')
    return {'name': name, 'path': str(path)}


def tool(app, name, args):
    from terminal.home import loop_home
    directory = loop_home() / 'skills'
    if name in ('skill_read', 'skill_list'):
        app.permissions.check(name, args)
    if name == 'skill_write':
        if not isinstance(args, dict) or not {'name','description','content'} <= set(args) or set(args)-{'name','description','content','expected_sha256'}:
            raise ValueError('name, description and content are required')
        app.permissions.check(name, args)
        return write(directory, args['name'], args['description'], args['content'],app,args.get('expected_sha256'))
    if name == 'skill_read':
        if not isinstance(args, dict) or 'name' not in args or set(args)-{'name','path','offset','limit'}:
            raise ValueError('name required; path, offset and limit optional')
        root = _resolve(directory, args['name']).parent
        relative = args.get('path', 'SKILL.md')
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Use a package-relative resource path')
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Resource escapes skill package')
        from terminal.files import read_file
        result = read_file(str(path), args.get('offset'), args.get('limit'))
        resources = []
        # Bounded shallow listing; deeper resources can be read by exact path.
        for folder in ('references', 'scripts', 'assets'):
            parent = root / folder
            if parent.is_symlink() or not parent.is_dir():
                continue
            import itertools
            for child in itertools.islice(parent.iterdir(), 100):
                if child.is_file() and not child.is_symlink():
                    resources.append(str(child.relative_to(root)))
        return {'name': args['name'], **result, 'resources': sorted(resources),
                'resource_listing': 'up to 100 immediate files per references/scripts/assets directory; not exhaustive'}
    if name == 'skill_list':
        if args != {}:
            raise ValueError('no arguments expected')
        return {'skills': discover(directory)}
    raise ValueError('unregistered tool')
