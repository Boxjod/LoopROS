"""Atomic composer chips; expanded content is used for submission and persistence."""
from contextlib import contextmanager
from prompt_toolkit.layout.processors import Processor, Transformation


class Composer:
    def __init__(self, buffer, files=lambda: []):
        self.buffer,self.files=buffer,files
        self.blocks={};self.counter=0;self.armed=None;self.suspended=0
        self.previous=buffer.text
        buffer.on_text_changed += self.changed
        buffer.on_cursor_position_changed += self.cursor_changed

    @contextmanager
    def hold(self):
        from prompt_toolkit.filters import to_filter
        previous_validation=self.buffer.validate_while_typing
        self.buffer.validate_while_typing=to_filter(False)
        self.suspended+=1
        try: yield
        finally:
            self.buffer.validate_while_typing=previous_validation
            self.suspended-=1;self.previous=self.buffer.text;self.armed=None

    @property
    def text(self):
        return ''.join(self.blocks[c].get('text','') if c in self.blocks else c for c in self.buffer.text)

    @text.setter
    def text(self,value):
        with self.hold():
            self.buffer.text=value
            self.ensure_images()

    def label(self,char):
        b=self.blocks[char]
        return '[Paste #{} · {} lines]'.format(b['id'],len(b['text'].splitlines())) if b['kind']=='paste' else '[{} #{}]'.format('Video' if b['file'] and str(b['file'][0]).lower().endswith(('.mp4','.mov','.mkv','.webm','.avi')) else 'Image',b['id'])

    @property
    def display_text(self):
        return ''.join(self.label(c) if c in self.blocks else c for c in self.buffer.text)

    def insert(self,kind,text='',file=None,identity=None):
        self.counter=max(self.counter+1,identity or 0)
        # Supplementary private-use characters are single atomic buffer cells.
        char=chr(0xF0000+self.counter)
        if self.counter>=65534: raise ValueError('Composer chip limit reached; start a new terminal')
        self.blocks[char]={'kind':kind,'id':identity or self.counter,'text':text,'file':file}
        self.insert_text(char)
        return char

    def insert_text(self,text):
        if self.suspended:
            from prompt_toolkit.document import Document
            b=self.buffer;p=b.cursor_position
            b.document=Document(b.text[:p]+text+b.text[p:],p+len(text))
        else:self.buffer.insert_text(text)

    def paste(self,text):
        text=text.replace('\r\n','\n').replace('\r','\n')
        # Literal private-use text must never resolve to an existing chip.
        if any(c in self.blocks for c in text):
            self.insert('paste',text)
        elif '\n' in text:
            self.insert('paste',text)
        else: self.insert_text(text)

    def ensure_images(self):
        for file in self.files():
            if not any(b['kind']=='image' and b['file'] is file and c in self.buffer.text for c,b in self.blocks.items()):
                existing=next((c for c,b in self.blocks.items() if b['kind']=='image' and b['file'] is file),None)
                if existing:self.insert_text(existing)
                else:
                    import re
                    match=re.fullmatch(r'\[(?:Image|Video) #(\d+)\]',file[1][0].get('text','')) if file[1] else None
                    self.insert('image',file=file,identity=int(match[1]) if match else None)

    def changed(self,buffer):
        if not self.suspended:
            for char in set(self.previous)-set(buffer.text):
                block=self.blocks.get(char)
                if block and block['kind']=='image':
                    files=self.files()
                    for i,file in enumerate(files):
                        if file is block['file']:
                            files.pop(i);break
            for char in set(buffer.text)-set(self.previous):
                block=self.blocks.get(char)
                if block and block['kind']=='image' and block['file'] is not None:
                    if not any(f is block['file'] for f in self.files()):self.files().append(block['file'])
            self.armed=None
        self.previous=buffer.text

    def cursor_changed(self,buffer):
        if self.armed and self.armed[1]!=buffer.cursor_position:self.armed=None

    def backspace(self):
        b=self.buffer;p=b.cursor_position
        if p and b.text[p-1] in self.blocks:
            mark=(b.text[p-1],p)
            if self.armed==mark:b.delete_before_cursor();self.armed=None
            else:self.armed=mark
            return True
        self.armed=None
        return False

    def reset(self,history=False):
        # History stores expanded content, never an opaque chip reference.
        with self.hold():
            if history and self.text:self.buffer.history.append_string(self.text)
            self.buffer.reset()

    def clear(self):
        with self.hold():self.files().clear();self.buffer.reset()
        self.blocks.clear()

    def snapshot(self):
        blocks={}
        for c in self.buffer.text:
            if c not in self.blocks:continue
            b=self.blocks[c];row={k:b[k] for k in ('kind','id','text')}
            if b['kind']=='image':
                row['file_index']=next((i for i,f in enumerate(self.files()) if f is b['file']),None)
            blocks[c]=row
        return {'raw':self.buffer.text,'blocks':blocks,'counter':self.counter}

    def restore(self,text,metadata=None):
        with self.hold():
            if metadata and isinstance(metadata.get('blocks'),dict):
                for c,row in metadata['blocks'].items():
                    if len(c)!=1 or row.get('kind') not in ('paste','image'):continue
                    b=dict(row);index=b.pop('file_index',None)
                    b['file']=self.files()[index] if isinstance(index,int) and 0<=index<len(self.files()) else None
                    self.blocks[c]=b;self.counter=max(self.counter,b['id'])
                self.counter=max(self.counter,metadata.get('counter',0))
                self.buffer.text=metadata['raw']
            else:
                self.buffer.reset()
                if '\n' in text:self.paste(text)
                else:self.insert_text(text)
            self.ensure_images()
            self.buffer.cursor_position=len(self.buffer.text)

    def prune(self):
        # Once a message is submitted, its buffer undo history has been reset.
        # Retain only the next draft and any attachments awaiting submission.
        self.blocks={c:b for c,b in self.blocks.items() if c in self.buffer.text or
                     (b['kind']=='image' and any(f is b['file'] for f in self.files()))}

    def numbered_files(self):
        result=[]
        for file in self.files():
            block=next((b for c,b in self.blocks.items() if b['file'] is file and c in self.buffer.text),None)
            if block:
                import re
                parts=file[1]
                if parts and re.fullmatch(r'\[(?:Image|Video) #\d+\]',parts[0].get('text','')):parts=parts[1:]
                result.append((file[0],[{'type':'text','text':self.label(next(c for c,b in self.blocks.items() if b is block))},*parts]))
            else:result.append(file)
        return result


class ChipProcessor(Processor):
    def __init__(self,composer):self.composer=composer

    def apply_transformation(self,ti):
        fragments=[];positions=[0];offset=0
        for style,text,*rest in ti.fragments:
            for c in text:
                if c in self.composer.blocks:
                    label=self.composer.label(c)
                    selected=self.composer.armed and self.composer.armed[0]==c
                    fragments.append(('class:chip-selected' if selected else 'class:chip',label))
                    offset+=len(label)
                else:
                    fragments.append((style,c));offset+=1
                positions.append(offset)
        def source_to_display(i):return positions[min(i,len(positions)-1)]
        def display_to_source(i):
            import bisect
            return max(0,bisect.bisect_right(positions,i)-1)
        return Transformation(fragments,source_to_display,display_to_source)
