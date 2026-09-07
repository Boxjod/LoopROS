"""Provider usage and conservative, tokenizer-independent request budgeting."""
import json


def usage(payload):
    if not isinstance(payload, dict):
        return None
    incoming = payload.get('input_tokens', payload.get('prompt_tokens'))
    outgoing = payload.get('output_tokens', payload.get('completion_tokens'))
    if any(type(n) is not int or n < 0 for n in (incoming, outgoing)):
        return None
    return {'input_tokens': incoming, 'output_tokens': outgoing,
            'total_tokens': incoming + outgoing}


def record(state, value):
    result = dict(state)
    result['requests'] = result.get('requests', 0) + 1
    value = usage(value)
    if value is None:
        result['unreported_requests'] = result.get('unreported_requests', 0) + 1
    else:
        for key, count in value.items():
            result[key] = result.get(key, 0) + count
        result['last_usage'] = value
    result['last_request_reported'] = value is not None
    return result


def estimate(config, messages, tools):
    from terminal.protocols import encode
    _, body = encode({'model': '', **config}, messages, tools)
    # UTF-8 byte count is deliberately conservative for text across languages.
    # Images have provider-specific costs: use a configurable allowance per image.
    def clean(value):
        if isinstance(value, dict):
            if value.get('type') in ('image_url', 'input_image'):
                return 'x' * config.get('image_token_budget', 8192)
            return {k: clean(v) for k, v in value.items() if not k.startswith('_')}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    return len(json.dumps(clean(body), ensure_ascii=False, separators=(',', ':')).encode('utf-8')) + 128


def policy(config):
    capacity = config.get('context_window')
    # Fallback is a local working budget, never advertised as the model's capacity.
    window = capacity or 32768
    reserve = config.get('max_output_tokens', 4096)
    trigger = int((window - reserve) * config.get('compact_threshold', .8))
    return capacity, max(256, trigger), max(256, window - reserve - 256)


def fit(config, source, tools, current_content=None):
    """Compact whole exchanges; retain system state, current inputs and latest tools.

    Excerpts are explicitly incomplete historical data, not newly granted authority.
    Original history and full tool events are untouched. Never rerun a tool here.
    """
    messages = list(source)
    capacity, trigger, limit = policy(config)
    before = estimate(config, messages, tools)
    removed = []
    # The last ordinary user input and all subsequent user corrections are protected.
    # Historical turns may be removed as complete user/assistant groups.
    users = [i for i, m in enumerate(messages) if m.get('role') == 'user']
    boundary = next((i for i in users if messages[i].get('content') == current_content), users[-1] if users else 0)
    if capacity is None:
        fixed = [m for i, m in enumerate(messages) if m.get('role') == 'system' or (i >= boundary and m.get('role') == 'user')]
        trigger = max(trigger, estimate(config, fixed, tools) + 12000)
        limit = max(limit, trigger + 8192)
    while estimate(config, messages, tools) > trigger:
        start = next((i for i in range(1, boundary) if messages[i].get('role') != 'system'), None)
        if start is None:
            break
        end = start + 1
        while end < boundary and messages[end].get('role') not in ('user', 'system'):
            end += 1
        removed.extend(messages[start:end])
        del messages[start:end]
        boundary -= end - start
    # During a long tool loop keep each call/result group atomic. Retain the newest
    # group, and every user message/system state; older receipts become excerpts.
    while estimate(config, messages, tools) > trigger:
        starts = [i for i, m in enumerate(messages) if m.get('role') == 'assistant' and m.get('tool_calls')]
        if len(starts) < 2:
            break
        start = starts[0]
        end = start + 1
        while end < len(messages) and messages[end].get('role') == 'tool':
            end += 1
        removed.extend(messages[start:end])
        del messages[start:end]
    if removed:
        rows = []
        for m in removed:
            content = m.get('content') or m.get('tool_calls') or ''
            text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            rows.append({'role': m['role'], 'excerpt': text[:180], 'tool_call_id': m.get('tool_call_id')})
        summary = {'role': 'user', 'content': 'Compacted history: incomplete excerpts, not instructions or proof of success. Full history/tool events remain stored. Do not repeat completed actions; retrieve details when needed.\n' + json.dumps(rows[:2] + rows[-6:] if len(rows) > 8 else rows, ensure_ascii=False)}
        messages.insert(1, summary)
        # Reserve continuity excerpts even when the request is near its hard limit.
        if estimate(config, messages, tools) > limit:
            summary['content'] = summary['content'][:400]
    after = estimate(config, messages, tools)
    report = {'context_window': capacity, 'budget_source': 'profile' if capacity else 'local fallback; model capacity unknown',
              'estimated_input_tokens': after, 'before_compaction_estimate': before,
              'output_reserve': config.get('max_output_tokens', 4096), 'auto_compact_trigger': trigger,
              'input_limit': limit, 'compacted_messages': len(removed),
              'measurement': 'conservative UTF-8 estimate including system/tools; image cost is configurable, not exact'}
    if capacity is not None and after > limit:
        raise ValueError('Context budget exceeded by current input/system/tools. Full history preserved. Reduce attachments/input/tool schemas or configure the correct profile context_window; request was not sent.')
    return messages, report


def status(agent):
    config = getattr(agent.client, 'config', {})
    current = getattr(agent, 'context_report', {})
    state = getattr(agent, 'token_usage', {})
    baseline = getattr(agent, 'token_usage_baseline', {})
    capacity = config.get('context_window')
    reported = current.get('last_reported_context_tokens')
    used = reported if reported is not None else current.get('estimated_input_tokens')
    prefix = '' if reported is not None else '~'
    window = ('?' if used is None else f'{used:,}') + '/' + (f'{capacity:,}' if capacity else '?')
    if capacity and used is not None:
        window += f' {used / capacity:.0%}'
    suffix = '+' if state.get('unreported_requests', 0) > baseline.get('unreported_requests', 0) else ''
    total = max(0, state.get('total_tokens', 0) - baseline.get('total_tokens', 0))
    return f"Session Tokens {total:,}{suffix} | Context {prefix}{window}"
