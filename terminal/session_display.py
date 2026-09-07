"""Render saved model history without recording events or executing tools."""
from terminal.markdown import BoldText
from terminal.tool_display import ToolDisplay
from terminal.colors import paint, tool_call, tool_result


def safe_text(value):
    return ''.join(c if c in '\n\t' or c.isprintable() else '\ufffd' for c in str(value))


def history_lines(history):
    calls = {}
    for message in history:
        role = message.get('role')
        content = message.get('content') or ''
        if isinstance(content, list):
            content = '\n'.join(part.get('text', '[media]') for part in content if isinstance(part, dict))
        content = safe_text(content)
        if role == 'user':
            yield '\n'.join('\x1b[48;5;236m\x1b[38;5;255m' + line + '\x1b[0m'
                            for line in ('❯ ' + content).split('\n'))
        elif role == 'assistant':
            if message.get('reasoning_content'):
                yield '✻ ' + safe_text(message['reasoning_content'])
            if content:
                yield paint('● ','assistant') + BoldText().ansi(content, final=True)
            for call in message.get('tool_calls', []):
                function = call.get('function', {})
                display = ToolDisplay()
                yield tool_call(safe_text(display.call(function.get('name', 'tool') +
                                                        '(' + function.get('arguments', '{}') + ')')))
                display.started = None  # Replaying history is not a timed execution.
                calls[call.get('id')] = display
        elif role == 'tool':
            display = calls.pop(message.get('tool_call_id'), ToolDisplay())
            yield tool_result(safe_text(display.result(content, None)))
            for line in display.preview:
                yield paint('    '+safe_text(line),'added' if line.startswith('+') else 'removed' if line.startswith('-') else 'muted')
