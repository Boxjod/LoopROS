"""Command-name completion from the same help text shown by /help."""
import re

from prompt_toolkit.completion import Completer, Completion


class SlashCompleter(Completer):
    def __init__(self, help_text, sessions=None, permissions=None, models=None, agents=None, roles=None):
        self.sessions = sessions
        self.permissions = permissions
        self.models = models
        self.agents = agents
        self.roles = roles
        self.commands = {}
        for line in help_text.splitlines():
            if line.startswith('/'):
                names = re.match(r'(/[\w-]+(?:, /[\w-]+)*)', line)
                if names:
                    for name in names[0].split(', '):
                        self.commands.setdefault(name, line[names.end():].strip())
        self.commands.update({
            '/attach': 'PATH Attach media', '/detach': 'Remove attachments',
            '/paste': 'Attach clipboard image', '/queue': '[clear|resume] Inspect, clear or run queued work',
            '/resume': '[TITLE] Browse and resume saved conversations', '/history': '[TITLE] Preview full conversation and summaries', '/new': '[GOAL] Start a new conversation with fresh work', '/cancel-turn': 'Cancel the active turn',
            '/quit': 'Exit the terminal',
            '/rename': 'NAME Rename the current session',
            '/sessions': '[QUERY] Search saved conversations',
            '/export': '[TITLE] Export a conversation to Markdown',
        })
        first = ('/model', '/mode', '/permissions', '/resume', '/help')
        self.commands = {**{name: self.commands[name] for name in first if name in self.commands},
                         **{name: value for name, value in self.commands.items() if name not in first}}

    def get_completions(self, document, complete_event):
        prefix = document.text
        if document.cursor_position != len(prefix) or '\n' in prefix or '\r' in prefix:
            return
        parts = prefix.split()
        if parts and parts[0] == '/reasoning' and len(parts) <= 2:
            from terminal.config import REASONING_EFFORTS
            word = parts[1] if len(parts) == 2 else ''
            if len(parts) == 2 or prefix.endswith(' '):
                for value in ('default', *REASONING_EFFORTS):
                    if value.startswith(word): yield Completion(value, start_position=-len(word))
                return
        if parts and parts[0] == '/node' and (len(parts) == 1 and prefix.endswith(' ') or len(parts) == 2 and not prefix.endswith(' ')):
            word = parts[1] if len(parts) == 2 else ''
            for verb in ('profiles', 'start', 'use', 'status', 'logs', 'send', 'stop', 'list', 'help'):
                if verb.startswith(word):
                    yield Completion(verb, start_position=-len(word), display_meta='Node command; no model request')
            return
        if prefix and prefix[-1].isspace():
            parts.append('')
        if prefix.startswith('/') and len(parts) == 2 and parts[0] == '/spawn' and self.roles:
            for role in self.roles():
                if role.casefold().startswith(parts[1].casefold()):
                    yield Completion(role, start_position=-len(parts[1]), display_meta='Role; then enter a task')
            return
        if prefix.startswith('/') and len(parts) >= 2 and parts[0] == '/skills':
            if len(parts) == 2:
                for verb in ('list','inspect','run','status','logs','stop','save'):
                    if verb.startswith(parts[1]): yield Completion(verb,start_position=-len(parts[1]))
            elif parts[1] in ('inspect','run','status','logs','stop'):
                from toolchain.offline_skill import catalog
                typed = ' '.join(parts[2:])
                for row in catalog():
                    if typed.casefold() in row['title'].casefold():
                        yield Completion(row['title'],start_position=-len(typed),display_meta=row['name'])
            return
        if prefix.startswith('/') and len(parts) == 2 and parts[0] == '/agents':
            for view in ('active', 'all'):
                if view.startswith(parts[1]):
                    yield Completion(view, start_position=-len(parts[1]))
            return
        if prefix.startswith('/') and len(parts) >= 2 and parts[0] in ('/send','/result','/stop-agent','/agent-messages') and self.agents:
            if parts[0] == '/send' and len(parts) > 2:
                return
            typed = prefix[len(parts[0]):].lstrip()
            for row in self.agents():
                if parts[0] in ('/send','/stop-agent') and row['state'] not in ('running','queued'):
                    continue
                label = row['title'] + ' · ' + row['role'] + ' ' + row['reference']
                if typed.casefold() in (label + ' ' + row['agent_id']).casefold():
                    yield Completion(row['reference'], start_position=-len(typed), display=label,
                                     display_meta=row['state'])
            return
        if len(parts) >= 2 and parts[0] == '/model' and self.models:
            typed = prefix[len('/model'):].lstrip()
            for row in self.models():
                if typed.casefold() in row['id'].casefold():
                    yield Completion(row['id'], start_position=-len(typed),
                                     display_meta=row['company'] + ' | ' + row['date'])
            return
        if len(parts) == 2 and parts[0] in ('/mode', '/fast'):
            options = ('sim', 'real', 'plan') if parts[0] == '/mode' else ('on', 'off', 'status')
            for option in options:
                if option.startswith(parts[1]):
                    yield Completion(option, start_position=-len(parts[1]))
            return
        if len(parts) == 2 and parts[0] == '/switch' and prefix.startswith('/switch'):
            options = {
                'setup': 'Configure provider, API type, key and model',
                'list': 'List saved provider profiles',
                'reload': 'Apply the selected profile',
                'master': '[PROFILE] Select the current model',
                'expert': '[PROFILE] Legacy alias for the current model',
            }
            for name, description in options.items():
                if name.startswith(parts[1]) and name != parts[1]:
                    yield Completion(name, start_position=-len(parts[1]), display_meta=description)
            return
        if self.permissions and len(parts) >= 2 and parts[0] == '/permissions':
            if len(parts) == 2:
                for mode in ('ask', 'deny', 'allow', 'default', 'plan', 'cautious', 'yolo'):
                    if mode.startswith(parts[-1]):
                        labels = {'default': 'Default rules', 'plan': 'Planning only', 'cautious': 'Ask for every registered action', 'yolo': 'Allow all registered actions'}
                        yield Completion(mode, start_position=-len(parts[-1]), display_meta=labels.get(mode, 'Then select an action'))
            elif len(parts) == 3 and parts[1] in ('ask', 'deny', 'allow'):
                for action, mode in sorted(self.permissions().items()):
                    if action.startswith(parts[-1]):
                        yield Completion(action, start_position=-len(parts[-1]), display_meta='Current: ' + mode)
            return
        if self.sessions and len(parts) >= 2 and parts[0] in ('/resume', '/history', '/export'):
            typed = prefix[len(parts[0]):].lstrip()
            for row in self.sessions():
                label = row.get('label', row['title'])
                if typed.casefold() in (row['id'] + ' ' + label).casefold():
                    yield Completion(label, start_position=-len(typed), display=label,
                                     display_meta=str(row['turns'])+' turns | '+row['updated'])
            return
        if (not prefix.startswith('/') or any(c.isspace() for c in prefix)
                or document.cursor_position != len(prefix)):
            return
        for name, description in self.commands.items():
            if prefix == '/' and name == '/history':
                continue
            if name.startswith(prefix):
                yield Completion(name, start_position=-len(prefix), display_meta=description)
