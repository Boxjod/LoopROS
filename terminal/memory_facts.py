"""Bounded local extraction of reusable hints, never execution authority."""
import ipaddress
import json
import re
from core.experience import terms


def extract(text, receipts=()):
    memories = []
    entities = sorted({t for t in terms(text[:16000]) if re.fullmatch(r'[a-z][a-z0-9_-]{2,}', t)})[:12]
    # Preserve user-supplied context, including hypothetical/negative wording.
    # An address in a request is a hint, not a successful connection.
    for sentence in re.split(r'[\n。！？]', text[:16000]):
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
        if len(memories) == 4:
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
    return list({json.dumps(m, sort_keys=True, ensure_ascii=False): m for m in memories}.values())
