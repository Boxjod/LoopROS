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
    verb = command.split()[0] if command.split() else ''
    if isinstance(data, dict) and verb in ('/agents','/spawn','/send','/result','/stop-agent','/agent-messages'):
        def label(row):
            return '{} · {} {}'.format(row.get('title','Agent'), row.get('role',''), row.get('reference','')).strip()
        if verb == '/agents':
            rows = data.get('tasks', [])
            output = ['Agents · running {} · queued {}'.format(data.get('running',0), data.get('queued',0)),
                      'Roles: ' + ', '.join(data.get('roles',[]))]
            for row in rows:
                output.append(label(row) + ' · ' + row['state'])
                if row.get('waiting_reason'): output.append('  Waiting: ' + row['waiting_reason'])
                if row.get('messages_queued'): output.append('  Messages awaiting delivery: ' + str(row['messages_queued']))
            if not rows: output.append('No agents in this view.')
            output.append('/send TARGET message · /result TARGET · /agent-messages TARGET · /stop-agent TARGET')
            return '\n'.join(output)
        if verb == '/agent-messages':
            output = [label(data)]
            for row in data.get('messages',[]):
                output.append('{} · {} · {}: {}'.format(row['message_id'],row['delivery'],row.get('sender_label',row['sender']),row['message']))
            if not data.get('messages'): output.append('No received messages.')
            output.append(data.get('notice',''))
            return '\n'.join(output)
        output = [label(data) + ' · ' + data.get('state','unknown')]
        if verb == '/send':
            output.append('Message {} queued; not yet confirmed delivered.'.format(data.get('message_id','')))
        if data.get('result') is not None:
            output.append(str(data['result']))
        if data.get('state') == 'done':
            output.append('Agent returned; task acceptance still requires evidence.')
        return '\n'.join(output)
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
    task_data = data.get('task') if isinstance(data, dict) else None
    if isinstance(data, dict) and 'spec' in data and 'state' in data:
        task_data = data
    if task_data is not None and command.split()[0] in ('/tasks', '/task'):
        from terminal.titles import task_title
        tasks = task_data if isinstance(task_data, list) else [task_data]
        output = []
        for index, task in enumerate(tasks, 1):
            output.append(str(index) + '. ' + task_title(task) + ' · ' + str(task.get('state', 'unknown')))
            if task.get('feedback'):
                output.extend(lines(task['feedback'], 1))
        if data.get('history'):
            output += ['History'] + list(lines(data['history'], 1))
        return '\n'.join(output) or 'No tasks in this view.'
    return '\n'.join(lines(data))
