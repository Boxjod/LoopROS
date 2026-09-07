"""Bounded local extraction of reusable hints, never execution authority."""
import ipaddress
import json
import re
from loop_robot.core.experience import terms


def extract(text, receipts=()):
    memories = []
    # Feedback is an advisory signal, never success evidence or authority.
    # Ignore fenced examples and quoted/tool transcript lines for this heuristic.
    direct = re.sub(r'```[\s\S]*?```', '', text[:16000])
    # A pasted conversation is evidence to inspect, not a new preference source.
    # Conservatively skip automatic extraction; the original history is retained.
    if re.search(r'(?m)^\s*(?:Tools? [›▸]|❯|●|assistant:|Assistant:|助手[：:])', direct):
        direct = ''
    direct = '\n'.join(line for line in direct.splitlines()
                       if not line.lstrip().startswith(('>', '“', '"')))
    direct = re.sub(r'“[^”]*”|"[^"\n]*"', '', direct)
    for sentence in re.split(r'[\n。！？!?]', direct):
        sentence = sentence.strip()
        if not sentence or sentence.startswith(('>', 'Tool ›', '“', '"')):
            continue
        if not re.search(r'我说过|说了几次|别再|不要再|又在|太浪费|太慢|烦死|搞什么|到底会不会|蠢|妈的|他妈|\bstupid\b|\bstop repeating\b', sentence, re.I):
            continue
        actionable = re.sub(r'他妈的?|妈的|蠢货?|\bstupid\b', '[不满表达]', sentence, flags=re.I)
        memories.append({'kind':'user_feedback', 'category':'correction', 'priority':'high',
                         'text':actionable[:600], 'tags':sorted(terms(sentence))[:20] + ['纠正','correction'],
                         'evidence':'user_feedback_signal_not_execution_evidence'})
        if len(memories) >= 2:
            break
    entities = sorted({t for t in terms(text[:16000]) if re.fullmatch(r'[a-z][a-z0-9_-]{2,}', t)})[:12]
    # Preserve user-supplied context, including hypothetical/negative wording.
    # An address in a request is a hint, not a successful connection.
    for sentence in re.split(r'[\n。！？]', direct):
        addresses = []
        for value in re.findall(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', sentence):
            try:
                addresses.append(str(ipaddress.ip_address(value)))
            except ValueError:
                pass
        explicit = re.search(r'记住|默认|偏好|喜欢|爱好|习惯|用户名|免密|(?:账号|名字|名称).{0,3}(?:叫|是)|不再询问|remember\b|my preference|passwordless|username', sentence, re.I)
        ssh = re.search(r'\bssh\b', sentence, re.I) and re.search(r'\b[\w.-]+@[\w.-]+', sentence)
        if not addresses and not explicit and not ssh:
            continue
        tags = sorted(terms(sentence))[:20] + entities
        connection = addresses or ssh or re.search(r'\bssh\b|免密|用户名|passwordless|username', sentence, re.I)
        if connection:
            tags += ['connection', 'network', '连接', '地址', '设备', '机器人'] + addresses[:4]
        memories.append({'kind': 'connection_hint' if connection else 'user_note',
                         'category': 'connection_profile' if re.search(r'免密|用户名|passwordless|username', sentence, re.I) or ssh else 'preference' if explicit and not connection else 'observation',
                         'text': sentence.strip()[:600], 'tags': sorted(set(tags)),
                         'evidence': 'user_statement_not_verified'})
        if len(memories) >= 4:
            break
    # Only explicitly structured connection fields; never mine free-form logs,
    # code, file bodies or assistant prose for supposedly verified facts.
    for receipt in receipts[-12:]:
        result = receipt.get('result')
        if not isinstance(result, dict) or result.get('error'):
            continue
        connection = result.get('connection', result)
        if not isinstance(connection, dict):
            continue
        values = {key: connection[key] for key in ('host', 'hostname', 'ip', 'address', 'port', 'username', 'transport', 'method')
                  if key in connection and isinstance(connection[key], (str, int)) and not isinstance(connection[key], bool)}
        if not any(key in values for key in ('host', 'hostname', 'ip', 'address')):
            continue
        memories.append({'kind': 'connection_observation', 'values': values,
                         'tool': receipt['tool'], 'tags': ['connection', '连接', '地址', '设备'] + sorted(terms(text))[:16],
                         'evidence': 'historical_tool_observation_not_current_state'})
        if len(memories) >= 6:
            break
    # Deduplicate within a turn. Across turns sources/timestamps remain intact.
    for memory in memories:
        memory['source_role'] = 'tool' if memory['kind']=='connection_observation' else 'user'
        memory['review_status'] = 'source_checked_not_fact_verified'
    return list({json.dumps(m, sort_keys=True, ensure_ascii=False): m for m in memories}.values())
