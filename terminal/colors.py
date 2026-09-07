"""Semantic terminal accents; text remains legible without color."""

CODES = {'tool':'1;38;5;81','argument':'38;5;180','success':'38;5;114',
         'warning':'38;5;222','error':'1;38;5;203','muted':'38;5;245',
         'execute':'1;38;5;141','modify':'1;38;5;222','inspect':'1;38;5;81','status':'38;5;114',
         'assistant':'1;38;5;141','heading':'1;38;5;81','added':'38;5;114','removed':'38;5;203'}


def paint(text, role):
    return '\x1b['+CODES[role]+'m'+text+'\x1b[0m'


TOOL_STYLES = {'inspect':'fg:#5fd7ff bold', 'execute':'fg:#af87ff bold',
               'modify':'fg:#ffdf87 bold', 'status':'fg:#87d787',
               'error':'fg:#ff5f5f bold', 'muted':'fg:#8a8a8a'}


def tool_role(name):
    if name in {'write_file','edit_file','skill_write','skill_export','tool_write','harness_write','settings_update'}:
        return 'modify'
    if name.endswith(('_status','_logs','_diagnose')) or name in {'devices','resource_status'}:
        return 'status'
    if name.endswith(('_run','_start','_stop','_command','_control')) or name in {'run_python','run_sim'}:
        return 'execute'
    return 'inspect'


def detail_style(line):
    import re
    stripped = line.strip()
    if stripped.startswith(('Error:', 'Review: fail', 'State: failed')):
        return TOOL_STYLES['error']
    match = re.match(r'\d{2}:\d{2}:\d{2}\s+(\w+)\(', stripped)
    if match:
        return TOOL_STYLES[tool_role(match[1])]
    if stripped.startswith(('Executed:', 'State:', 'Review:', 'Returned data')):
        return TOOL_STYLES['status']
    return TOOL_STYLES['muted']


def tool_call(text):
    name, sep, args=text.partition('(')
    return paint('Tool › '+name,tool_role(name)) + (paint('('+args,'argument') if sep else '')


def tool_result(text):
    role = 'error' if text.startswith(('Error:', 'Review: fail', 'State: failed')) else 'warning' if text.startswith(('Unsupported:', 'Review: inconclusive', 'State:', 'Window not')) else 'success'
    summary, sep, details=text.partition(' · ')
    return paint('  ↳ '+summary,role)+(paint(sep+details,'muted') if sep else '')
