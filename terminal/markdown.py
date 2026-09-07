"""Small streaming renderer for bold text and fenced code; no execution."""
import re
import io
import keyword
import tokenize
import token
import builtins

CODE = 'bg:#262626 #d7d7d7'
SYNTAX = {'keyword':('bg:#262626 #c792ea',183), 'string':('bg:#262626 #a3be8c',150),
          'number':('bg:#262626 #d19a66',173), 'comment':('bg:#262626 #809080',108),
          'function':('bg:#262626 #e5c07b',180), 'builtin':('bg:#262626 #56b6c2',73),
          'operator':('bg:#262626 #89ddff',117), 'added':('bg:#262626 #98c379',114),
          'removed':('bg:#262626 #e06c75',168), 'hunk':('bg:#262626 #61afef',75)}


def python_fragments(source, start):
    lines=source.splitlines(keepends=True)
    offsets=[0]
    for line in lines: offsets.append(offsets[-1]+len(line))
    spans=[]; previous=''
    try:
        for item in tokenize.generate_tokens(io.StringIO(source).readline):
            role=None
            if item.type==token.STRING: role='string'
            elif item.type==token.NUMBER: role='number'
            elif item.type==tokenize.COMMENT: role='comment'
            elif item.type==token.OP: role='operator'
            elif item.type==token.NAME:
                if keyword.iskeyword(item.string): role='keyword'
                elif previous in ('def','class'): role='function'
                elif hasattr(builtins,item.string): role='builtin'
            if role:
                a=offsets[min(item.start[0]-1,len(offsets)-1)]+item.start[1]
                b=offsets[min(item.end[0]-1,len(offsets)-1)]+item.end[1]
                if b>start: spans.append((max(start,a),b,SYNTAX[role][0]))
            if item.type not in (token.INDENT,token.DEDENT,token.NEWLINE,tokenize.NL): previous=item.string
    except (tokenize.TokenError,IndentationError,SyntaxError): pass
    result=[];position=start
    for a,b,style in spans:
        if a>position: result.append((CODE,source[position:a]))
        result.append((style,source[a:b]));position=b
    if position<len(source): result.append((CODE,source[position:]))
    return result



class BoldText:
    def __init__(self):
        self.bold = False
        self.pending = ''
        self.fence_pending = ''
        self.code = False
        self.language = ""
        self.code_source = ""
        self.line_start = True

    def _bold(self, text, final):
        text = self.pending + text
        self.pending = ''
        if not final and text.endswith('*') and not text.endswith('**'):
            text = text[:-1]
            self.pending = '*'
        result = []
        for index, part in enumerate(text.split('**')):
            if index:
                self.bold = not self.bold
            if part:
                result.append(('bold' if self.bold else '', part))
        return result

    def fragments(self, text, final=False, line_end=False):
        text = self.fence_pending + text + ('\n' if line_end else '')
        self.fence_pending = ''
        result = []
        for part in text.splitlines(keepends=True):
            ended = part.endswith('\n')
            if self.line_start and re.match(r'^ {0,3}`', part):
                if not ended and not final and (part.lstrip().startswith('```') or part.strip() in ('`', '``')):
                    self.fence_pending = part
                    continue
                match = re.fullmatch(r' {0,3}```([^`\n]*)\n?', part)
                if match and (not self.code or not match[1].strip()):
                    if self.code:
                        self.code = False
                    else:
                        self.code = True
                        label = match[1].strip()
                        self.language = label.lower()
                        self.code_source = ""
                        result.append(('dim', 'Code' + (' · ' + label if label else '') + '\n'))
                    self.line_start = True
                    continue
            if self.code:
                if self.language in ('python','py','python3'):
                    start = len(self.code_source)
                    self.code_source += part
                    result.extend(python_fragments(self.code_source,start))
                    if len(self.code_source)>65536 and ended: self.code_source=''
                elif self.language in ('diff','patch'):
                    role='added' if part.startswith('+') else 'removed' if part.startswith('-') else 'hunk' if part.startswith('@@') else None
                    result.append((SYNTAX[role][0] if role else CODE,part))
                else:
                    result.append((CODE, part))
            else:
                result.extend(self._bold(part, final or ended))
            self.line_start = ended
        if final and self.pending:
            result.extend(self._bold('', True))
        if line_end and result and result[-1][1].endswith('\n'):
            style, value = result[-1]
            result[-1] = (style, value[:-1])
        return result

    def ansi(self, text, final=False, line_end=False):
        styles = {'bold': ('\x1b[1m', '\x1b[22m'), 'dim': ('\x1b[2m', '\x1b[22m'),
                  CODE: ('\x1b[48;5;235m\x1b[38;5;252m', '\x1b[0m')}
        styles.update({style: ('\x1b[48;5;235m\x1b[38;5;'+str(color)+'m', '\x1b[0m') for style,color in SYNTAX.values()})
        fragments=self.fragments(text, final, line_end)
        return ''.join(styles[style][0] + part + styles[style][1] if style else part
                       for style, part in fragments)

    def preview(self, text):
        clone = BoldText()
        clone.__dict__.update(self.__dict__)
        return clone.fragments(text)
