"""Minimal safe streaming **bold**; keeps state across chunks and wrapped rows."""
class BoldText:
    def __init__(self):
        self.bold=False
        self.pending=''

    def fragments(self,text,final=False):
        text=self.pending+text
        self.pending=''
        if not final and text.endswith('*') and not text.endswith('**'):
            text=text[:-1];self.pending='*'
        result=[]
        parts=text.split('**')
        for i,part in enumerate(parts):
            if i: self.bold=not self.bold
            if part: result.append(('bold' if self.bold else '',part))
        return result

    def ansi(self,text,final=False):
        return ''.join(('\x1b[1m'+part+'\x1b[22m') if style else part for style,part in self.fragments(text,final))

    def preview(self,text):
        clone=BoldText();clone.bold=self.bold;clone.pending=self.pending
        return clone.fragments(text)
