"""Command-name completion from the same help text shown by /help."""
import re

from prompt_toolkit.completion import Completer, Completion


class SlashCompleter(Completer):
    def __init__(self, help_text, sessions=None, permissions=None):
        self.sessions = sessions
        self.permissions = permissions
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
            '/resume': '[ID] Browse and resume saved conversations', '/history': '[ID] Preview full conversation and summaries', '/new': 'Start a new conversation', '/cancel-turn': 'Cancel the active turn',
            '/quit': 'Exit the terminal',
            '/rename': 'NAME Rename the current session',
            '/sessions': '[QUERY] Search saved conversations',
            '/export': '[ID] Export a conversation to Markdown',
        })

    def get_completions(self, document, complete_event):
        prefix = document.text
        if document.cursor_position != len(prefix) or '\n' in prefix or '\r' in prefix:
            return
        parts = prefix.split()
        if prefix and prefix[-1].isspace():
            parts.append('')
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
        if self.sessions and len(parts) == 2 and parts[0] in ('/resume', '/history'):
            typed=parts[1]
            for row in self.sessions():
                if typed.casefold() in (row['id'] + ' ' + row['title']).casefold():
                    yield Completion(row['id'],start_position=-len(typed),display=row['id']+' '+row['title'],display_meta=str(row['turns'])+' turns | '+row['updated'])
            return
        if (not prefix.startswith('/') or any(c.isspace() for c in prefix)
                or document.cursor_position != len(prefix)):
            return
        for name, description in self.commands.items():
            if name.startswith(prefix):
                yield Completion(name, start_position=-len(prefix), display_meta=description)
