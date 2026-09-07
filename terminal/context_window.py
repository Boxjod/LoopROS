"""Bounded model views; never mutate the durable conversation."""
import json


def size(content):
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    return sum(len(p.get('text', '')) if p.get('type') == 'text' else 2000 for p in content)


def select(history, max_messages=32, budget=12000):
    # Preserve complete user/assistant groups, including multiple steering inputs.
    groups = []
    for message in history:
        if not groups or (message.get('role') == 'user' and groups[-1][-1].get('role') == 'assistant'):
            groups.append([])
        groups[-1].append(message)
    selected = []
    used = 0
    for group in reversed(groups):
        cost = sum(size(m.get('content')) for m in group)
        if len(selected) + len(group) > max_messages or used + cost > budget:
            break
        selected = group + selected
        used += cost
    omitted = history[:len(history)-len(selected)]
    # Excerpts are user statements, never fabricated execution evidence.
    requests = []
    for message in omitted:
        if message.get('role') != 'user':
            continue
        content = message.get('content', '')
        text = content if isinstance(content, str) else ' '.join(p.get('text', '') for p in content)
        if text.strip():
            requests.append(text[:240])
    excerpts = requests[:1] + requests[-6:] if len(requests) > 7 else requests
    recall = '\n'.join('- ' + text for text in excerpts)[:2000]
    return selected, recall, {'stored_messages': len(history), 'selected_messages': len(selected),
        'omitted_messages': len(omitted), 'history_character_units': used,
        'history_budget': budget, 'recall_characters': len(recall), 'message_limit': max_messages,
        'measurement': 'characters; media=2000 units each; not tokens; schemas/system/current turn excluded'}


def tool_text(result, limit=12000):
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= limit:
        return text
    if isinstance(result, dict) and result.get('stdout_path'):
        compact = dict(result)
        # Preserve exit/safety status and real output locations, not just an
        # arbitrary JSON prefix which may hide both the error and next read path.
        for key in ('stdout', 'stderr'):
            value = compact.get(key, '')
            if isinstance(value, str) and len(value) > max(256, limit//4):
                compact[key] = value[:max(256, limit//4)]
                compact[key+'_preview_truncated'] = True
        compact['output_notice'] = 'Output preview only. Read stdout_path/stderr_path with offset/limit for the needed lines; do not rerun the command to retrieve existing output.'
        encoded = json.dumps(compact, ensure_ascii=False)
        if len(encoded) <= limit:
            return encoded
    # Keep JSON parseable and make loss visible; full receipt remains in events.
    return json.dumps({'truncated': True, 'original_characters': len(text),
        'notice': 'Partial tool output. Read a narrower range; full receipt is retained in tool events.',
        'excerpt': text[:max(0, (limit-300)//2)]}, ensure_ascii=False)


def bound_tool_history(messages, budget=48000):
    """Retain protocol pairs while bounding accumulated tool text in a long turn."""
    tools = [m for m in messages if m.get('role') == 'tool']
    total = sum(len(m.get('content', '')) for m in tools)
    for message in tools:
        if total <= budget:
            break
        content = message.get('content', '')
        if len(content) <= 300:
            continue
        excerpt = json.dumps({'truncated': True, 'notice': 'Older tool receipt abbreviated; full result remains in tool events.',
                              'excerpt': content[:100]}, ensure_ascii=False)
        message['content'] = excerpt
        total -= len(content) - len(excerpt)
    return total
