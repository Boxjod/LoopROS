"""Small streaming renderer for bold text and fenced code; no execution."""
import re

CODE = 'bg:#262626 #d7d7d7'


class BoldText:
    def __init__(self):
        self.bold = False
        self.pending = ''
        self.fence_pending = ''
        self.code = False
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
                        result.append(('dim', 'Code' + (' · ' + label if label else '') + '\n'))
                    self.line_start = True
                    continue
            if self.code:
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
        return ''.join(styles[style][0] + part + styles[style][1] if style else part
                       for style, part in self.fragments(text, final, line_end))

    def preview(self, text):
        clone = BoldText()
        clone.__dict__.update(self.__dict__)
        return clone.fragments(text)
