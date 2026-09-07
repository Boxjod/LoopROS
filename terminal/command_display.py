"""Readable interactive command results; dispatch retains its JSON contract."""
import json


def format_command_result(command, result):
    if not isinstance(result, str):
        data = result
    else:
        try:
            data = json.loads(result)
        except (ValueError, TypeError):
            return result
    if isinstance(data, dict) and 'rules' in data and 'mode' in data:
        lines = ['Permissions', 'Profiles: default | plan | cautious (ask all) | yolo (allow all)',
                 'Profile: ' + str(data.get('profile', 'custom')), 'Mode: ' + str(data['mode']),
                 'Real hardware: ' + str(data.get('real_hardware', 'unknown')), '']
        for rule in ('allow', 'ask', 'deny'):
            names = sorted(name for name, value in data['rules'].items() if value == rule)
            lines.append(rule.upper() + ' (' + str(len(names)) + ')')
            lines.extend('  ' + name for name in names)
            if not names: lines.append('  —')
            lines.append('')
        lines.append('Change a rule: /permissions ask|deny|allow ACTION')
        return '\n'.join(lines)
    def lines(value, depth=0):
        indent = '  ' * depth
        if isinstance(value, dict):
            if not value: yield indent + '(empty)'
            for key, item in value.items():
                label = str(key).replace('_', ' ')
                if isinstance(item, (dict, list)):
                    yield indent + label + ':'
                    yield from lines(item, depth + 1)
                else: yield indent + label + ': ' + scalar(item)
        elif isinstance(value, list):
            if not value: yield indent + '(none)'
            for item in value:
                if isinstance(item, (dict, list)):
                    yield indent + '•'
                    yield from lines(item, depth + 1)
                else: yield indent + '• ' + scalar(item)
        else: yield indent + scalar(value)
    def scalar(value):
        if value is None: return '—'
        if isinstance(value, bool): return 'yes' if value else 'no'
        return str(value)
    return '\n'.join(lines(data))
