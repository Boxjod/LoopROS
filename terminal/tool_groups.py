"""Compact presentation batches; execution and raw receipts stay independent."""
from collections import Counter
from terminal.tool_display import ToolDisplay


class ToolGroups:
    def __init__(self):
        self.pending=[]
        self.groups=[]
        self.current=None

    def call(self,text):
        display=ToolDisplay()
        label=display.call(text)
        self.current={'display':display,'call':label,'name':display.name,'time':display.clock}

    def result(self,text,event_id):
        row=self.current or {'display':ToolDisplay(),'call':'tool','name':'tool','time':''}
        display=row.pop('display')
        row.update(summary=display.result(text,event_id),preview=list(display.preview),event_id=event_id,
                   elapsed=display.elapsed,tokens=display.local_tokens)
        self.pending.append(row)
        self.current=None
        return row

    def flush(self):
        if not self.pending: return None
        rows,self.pending=self.pending,[]
        self.groups.append(rows)
        return len(self.groups),rows

    def label(self,rows):
        names=Counter(row['name'] or 'tool' for row in rows)
        brief=', '.join(name+(' ×'+str(count) if count>1 else '') for name,count in list(names.items())[:3])
        return '{} calls · {} · {:.1f}s · ~{} local tokens'.format(len(rows),brief,sum(r['elapsed'] for r in rows),sum(r['tokens'] for r in rows))

    def details(self,index=None):
        rows=self.pending if index is None and self.pending else self.groups[-1] if index is None and self.groups else self.groups[index-1] if index is not None and 1<=index<=len(self.groups) else []
        if not rows: return 'No tool calls in this conversation view.'
        lines=[self.label(rows),'Local tokens estimate call arguments + result text; not API billing.']
        for row in rows:
            lines.extend([row['time']+' '+row['call'],'  '+row['summary']])
            lines.extend('    '+line for line in row['preview'])
        return '\n'.join(lines)
