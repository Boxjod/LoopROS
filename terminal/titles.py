"""Readable titles extracted locally from the first and latest user questions."""
import re


def excerpt(value, limit=28):
    if isinstance(value, list):
        value = ' '.join(p.get('text', '') for p in value if isinstance(p, dict) and p.get('type') == 'text')
    if not isinstance(value, str):
        return ''
    value = re.sub(r'\s+', ' ', ''.join(c if c.isprintable() or c.isspace() else ' ' for c in value)).strip()
    value = re.sub(r'^(?:(?:请|麻烦)(?:你)?(?:帮我)?|帮我)\s*', '', value).strip()
    value = re.split(r'[\n。！？!?]', value, maxsplit=1)[0].strip(' "“”‘’')
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '…'


def question_title(first, last=''):
    first, last = excerpt(first), excerpt(last)
    if not first:
        return last or 'New conversation'
    if not last or last == first:
        return first
    return first + ' · ' + last


def conversation_title(history, task=None):
    task = task or {}
    questions = [m.get('content', '') for m in history if m.get('role') == 'user']
    questions = [q for q in questions if excerpt(q)]
    first = questions[0] if questions else task.get('goal', '')
    last = task.get('latest_request') or (questions[-1] if questions else '')
    return question_title(first, last)


def task_title(task):
    return question_title(task.get('spec', {}).get('goal', ''), task.get('feedback', {}).get('new_input', ''))
