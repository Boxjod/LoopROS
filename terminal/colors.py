"""Semantic terminal accents; text remains legible without color."""

CODES = {'tool':'1;38;5;81','argument':'38;5;180','success':'38;5;114',
         'warning':'38;5;222','error':'1;38;5;203','muted':'38;5;245',
         'assistant':'1;38;5;141','heading':'1;38;5;81','added':'38;5;114','removed':'38;5;203'}


def paint(text, role):
    return '\x1b['+CODES[role]+'m'+text+'\x1b[0m'


def tool_call(text):
    name, sep, args=text.partition('(')
    return paint('Tool › '+name,'tool') + (paint('('+args,'argument') if sep else '')


def tool_result(text):
    role = 'error' if text.startswith(('Error:', 'Review: fail', 'State: failed')) else 'warning' if text.startswith(('Unsupported:', 'Review: inconclusive', 'State:', 'Window not')) else 'success'
    summary, sep, details=text.partition(' · ')
    return paint('  ↳ '+summary,role)+(paint(sep+details,'muted') if sep else '')
