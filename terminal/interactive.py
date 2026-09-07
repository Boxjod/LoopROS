"""Editable composer, scrollable transcript and boundary-delivered user steering."""
import asyncio
from collections import deque
import shlex
import sys
import time
from contextlib import redirect_stdout, redirect_stderr
from concurrent.futures import ThreadPoolExecutor

from prompt_toolkit import PromptSession
from prompt_toolkit.application import run_in_terminal, get_app_session
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition, to_filter
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.layout.containers import VerticalAlign, DynamicContainer, FloatContainer, ConditionalContainer
from prompt_toolkit.layout.screen import WritePosition
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.utils import get_cwidth


class CompactPrompt(DynamicContainer):
    """Do not turn the renderer's remembered height into blank transcript rows."""
    def write_to_screen(self, screen, mouse_handlers, write_position, parent_style, erase_bg, z_index):
        container = self.get_container()
        height = min(write_position.height,
                     container.preferred_height(write_position.width, write_position.height).preferred)
        write_position = WritePosition(write_position.xpos, write_position.ypos, write_position.width, height)
        container.write_to_screen(screen, mouse_handlers, write_position, parent_style, erase_bg, z_index)


class Composer:
    def __init__(self, buffer):
        self.buffer = buffer

    @property
    def text(self):
        return self.buffer.text

    @text.setter
    def text(self, value):
        self.buffer.text = value


from terminal.media import attachment, dropped_paths, clipboard_image
from terminal.ui import welcome
from terminal.session import SessionStore
from terminal.markdown import BoldText
from terminal.completion import SlashCompleter
from terminal.command_display import format_command_result


class Terminal:
    def __init__(self, app):
        self.app = app
        self.queue = deque()
        self.attachments = []
        self.paused = False
        self.pending = None
        self.pending_command = None
        self.completion_refresh_pending = False
        self.dismissed_completion = None
        self.model_choices = []
        self.timer = None
        self.continuations = 0
        self.command_busy = False
        self.action_panel = None
        self.viewer_choice = None
        self.viewer_was_open = self.app.viewer.status().get("window_open", False)
        self.selected_task = None
        self.task_action = 0
        self.task_buttons = []
        self.panel_offset = 0
        self.stream_kind = None
        self.markdown = BoldText()
        self.stream_text = ''
        self.stream_started = False
        self.streamed_answer = False
        from terminal.tool_display import ToolDisplay
        self.tool_display = ToolDisplay()
        kb = KeyBindings()

        @kb.add('enter')
        def submit(event):
            if self.command_busy:
                return
            if self.viewer_choice is not None and not self.input.text and not self.attachments:
                reopen = self.viewer_choice == 0
                self.viewer_choice=None
                self.action_panel=None
                if reopen:
                    self.input.text="/viewer"
                    event.app.create_background_task(self.submit())
                event.app.invalidate()
                return
            if self.selected_task and not self.input.text and not self.attachments:
                command = self.task_buttons[self.task_action][1]
                self.input.text = command
                event.app.create_background_task(self.submit())
                return
            buffer = event.current_buffer
            state = buffer.complete_state
            matches = list(self.session.completer.get_completions(buffer.document, CompleteEvent()))
            selected = state.current_completion if state else None
            if selected:
                original_matches = self.session.completer.get_completions(state.original_document, CompleteEvent())
                if (state.new_text_and_position()[0] != buffer.text or
                        not any(c.text == selected.text and c.start_position == selected.start_position for c in original_matches)):
                    selected = None
            exact = any(c.text == buffer.text for c in matches)
            if selected:
                buffer.apply_completion(selected)
            elif matches and not exact:
                buffer.apply_completion(matches[0])
            if (buffer.text.strip() in ('/permissions ask', '/permissions deny', '/permissions allow')
                    or len(buffer.text.split()) == 2 and buffer.text.split()[0] in ('/spawn', '/send')):
                buffer.insert_text(' ')
                buffer.start_completion(select_first=False)
                return
            event.app.create_background_task(self.submit())

        @kb.add('up', filter=Condition(lambda: bool(self.queue) and not self.input.text
                                       and not self.attachments and not self.command_busy))
        def edit_queue(event):
            text, files = self.queue.pop()
            self.attachments = list(files)
            self.input.text = text
            self.input.buffer.cursor_position = len(text)
            self.checkpoint()
            self.ui.invalidate()

        for key in ('up','down'):
            @kb.add(key, filter=Condition(lambda: self.viewer_choice is not None and not self.input.text and not self.attachments and not self.command_busy))
            def choose_viewer(event):
                self.viewer_choice=1-self.viewer_choice
                self.render_viewer_choice()
                event.app.invalidate()

        for key, direction in (('left', -1), ('right', 1)):
            @kb.add(key, filter=Condition(lambda: not self.input.text and not self.attachments and not self.command_busy))
            def switch_task(event, step=direction):
                self.select_task(step)

        for key, direction in (('up', -1), ('down', 1)):
            @kb.add(key, filter=Condition(lambda: self.selected_task is not None and not self.input.text and not self.attachments and not self.command_busy))
            def choose_task_action(event, step=direction):
                self.task_action = (self.task_action + step) % len(self.task_commands())
                self.panel_offset = 0
                self.render_task_panel()

        for key, direction in (('up', -1), ('left', -1), ('down', 1), ('right', 1)):
            @kb.add(key, filter=Condition(lambda: self.input.buffer.complete_state is not None))
            def choose_completion(event, step=direction):
                if step < 0:
                    event.current_buffer.complete_previous()
                else:
                    event.current_buffer.complete_next()

        @kb.add('escape', 'enter')
        @kb.add('c-j')
        def newline(event):
            self.input.buffer.insert_text('\n')

        @kb.add('c-c')
        def cancel(event):
            if self.input.text:
                self.input.text = ''
            elif self.pending or (self.queue and not self.paused):
                self.stop()
                self.checkpoint()
            else:
                event.app.exit()

        @kb.add('c-d')
        def quit_(event):
            if not self.input.text:
                event.app.exit()

        @kb.add('escape')
        def stop_turn(event):
            if event.current_buffer.complete_state:
                event.current_buffer.cancel_completion()
                self.dismissed_completion = event.current_buffer.document
                return
            if self.action_panel is not None:
                self.close_panel()
                return
            if self.pending:
                self.stop()

        @kb.add('pageup', filter=Condition(lambda: self.action_panel is not None))
        def panel_previous(event):
            self.panel_offset = max(0, self.panel_offset - max(1, getattr(self, 'panel_page_size', 1)))
            self.ui.invalidate()

        @kb.add('pagedown', filter=Condition(lambda: self.action_panel is not None))
        def panel_next(event):
            self.panel_offset += max(1, getattr(self, 'panel_page_size', 1))
            self.ui.invalidate()

        @kb.add('c-v')
        def paste_image(event):
            if not self.command_busy:
                event.app.create_background_task(self.paste_image())

        from terminal.app import HELP
        self.session = PromptSession(
            input=get_app_session().input, output=get_app_session().output,
            message=self.prompt_text, multiline=True,
            placeholder=None,
            editing_mode=EditingMode.EMACS,
            prompt_continuation='  ', key_bindings=kb,
            completer=SlashCompleter(HELP, sessions=lambda: self.store.list_sessions(self.app.client.config, limit=None), permissions=lambda: self.app.permissions.snapshot()["rules"], models=lambda: self.model_choices, agents=self.agent_choices, roles=lambda: list(self.app.runtime.definitions)),
            complete_while_typing=Condition(lambda: self.session.default_buffer.text.startswith('/')),
            reserve_space_for_menu=0, complete_style=CompleteStyle.COLUMN, mouse_support=False, erase_when_done=True,
            style=Style.from_dict({'prompt': 'ansicyan bold', 'bottom-toolbar': 'noreverse', 'separator': '#637078', 'hint-selected': 'ansicyan bold'}))
        # PromptSession normally stretches its editable window to absorb spare
        # renderer height. Keep the composer next to the transcript; spare
        # terminal rows belong below it, never between output and input.
        self.session.layout.container.align = VerticalAlign.TOP
        for window in self.session.layout.find_all_windows():
            if getattr(window.content, 'buffer', None) is self.session.default_buffer:
                window.dont_extend_height = to_filter(True)
        # Keep completion state/key bindings, but render candidates in the
        # normal footer instead of cursor-anchored floating menus.
        def remove_floats(container):
            if isinstance(container, FloatContainer):
                container.floats = []
            if (isinstance(container, ConditionalContainer)
                    and getattr(container.content, 'style', None) == 'class:bottom-toolbar'):
                container.filter &= Condition(lambda: self.session.app.output.get_size().rows >= 2)
            for child in container.get_children():
                remove_floats(child)
        remove_floats(self.session.layout.container)
        prompt_layout = self.session.layout.container
        self.session.layout.container = CompactPrompt(lambda: prompt_layout)
        self.ui = self.session.app
        erase = self.ui.renderer.erase
        def erase_frame(leave_alternate_screen=True):
            renderer = self.ui.renderer
            size = self.ui.output.get_size()
            old = renderer._last_size
            screen = renderer._last_screen
            if old and screen and size.columns < old.columns:
                # Reflow can insert rows throughout the old UI, including its
                # footer below the cursor. Include them in the relative erase.
                from prompt_toolkit.data_structures import Point
                cursor = renderer._cursor_pos
                rows = cursor.y
                for y in range(screen.height):
                    if y == cursor.y:
                        continue
                    line = screen.data_buffer[y]
                    used = max((x + max(1, char.width) for x, char in line.items()
                                if char.char.strip()), default=0)
                    rows += max(0, (used + size.columns - 1) // size.columns - 1)
                renderer._cursor_pos = Point(min(cursor.x, size.columns - 1), rows)
            erase(leave_alternate_screen=leave_alternate_screen)
        self.ui.renderer.erase = erase_frame
        # Measure layout and fragments using one snapshot per frame.
        render = self.ui.renderer.render
        def render_frame(*args, **kwargs):
            output = self.ui.output
            get_size = output.get_size
            size = get_size()
            output.get_size = lambda: size
            try:
                if self.ui.renderer._last_size and size != self.ui.renderer._last_size:
                    erase_frame(leave_alternate_screen=False)
                    self.ui._request_absolute_cursor_position()
                return render(*args, **kwargs)
            finally:
                output.get_size = get_size
        self.ui.renderer.render = render_frame
        # Resolve a lone Esc promptly while retaining Alt-Enter key sequences.
        self.ui.ttimeoutlen = .1
        self.ui.timeoutlen = .3
        self.input = Composer(self.session.default_buffer)
        self.input.buffer.on_text_changed += self.schedule_completion_refresh
        self.input.buffer.on_cursor_position_changed += self.schedule_completion_refresh
        self.store = SessionStore(app.state_dir / 'conversation.sqlite')
        saved = self.store.load(app.client.config)
        from terminal.session_task import SessionTask
        self.store.session_id = self.store.session_id or app.session_id
        app.session_id = self.store.session_id
        app.session_task = SessionTask(saved.get('task'), identity=self.store.session_id, history=saved.get('history', []))
        app.agent.history = saved.get('history', app.agent.history)
        app.agent.turn_summaries = saved.get('summaries', [])
        self.queue.extend(saved.get('queue', []))
        self.attachments = saved.get('attachments', [])
        self.draft = saved.get('draft', '')
        self.paused = bool(self.queue)
        from core.tasks import TaskStore
        self.task_store=TaskStore(app.state_dir/'tasks.sqlite')
        self.task_cursor=self.task_store.meta('terminal_seen_event:' + app.session_id) or 0
        self.task_poll_at=0

    def agent_choices(self):
        # Do not leak task titles through completion when status reading is denied.
        if self.app.permissions.snapshot()['rules'].get('agents_status') != 'allow':
            return []
        return self.app.runtime.choices()

    def schedule_completion_refresh(self, buffer):
        if not buffer.text.startswith('/'):
            if buffer.complete_state is not None:
                document = buffer.document
                buffer.cancel_completion()
                buffer.document = document
            return
        # Insertions already trigger prompt_toolkit completion; deletion and
        # cursor edits don't. Defer until text and cursor are both updated.
        if buffer.document != self.dismissed_completion:
            self.dismissed_completion = None
        if self.completion_refresh_pending or not self.ui.is_running:
            return
        self.completion_refresh_pending = True
        asyncio.get_running_loop().call_soon(self.refresh_completion)

    def refresh_completion(self):
        self.completion_refresh_pending = False
        buffer = self.input.buffer
        if (not self.ui.is_running or self.command_busy or buffer.complete_state is not None
                or buffer.document == self.dismissed_completion):
            return
        if buffer.text.startswith('/') and buffer.cursor_position == len(buffer.text):
            buffer.start_completion(select_first=False)

    def checkpoint(self):
        draft = self.input.text
        if draft.strip() in ('/exit', '/quit'):
            draft = ''
        self.store.save(self.app.client.config, self.app.agent.history, self.queue, draft, self.attachments, self.app.agent.turn_summaries, self.app.session_task.snapshot())
        self.bind_task_scope()

    def bind_task_scope(self):
        if self.app.session_id != self.store.session_id:
            self.app.session_id = self.store.session_id
            self.task_cursor = self.task_store.meta('terminal_seen_event:' + self.app.session_id) or 0
            self.task_poll_at = 0
            self.selected_task = None
        with self.app.session_task.lock:
            self.app.session_task.data['session_id'] = self.app.session_id



    def input_placeholder(self):
        hint = '↑ edit queue · ←/→ tasks' if self.queue and not self.attachments else '←/→ tasks · / commands'
        focus = getattr(self.app, 'node_focus', 'master')
        prefix = ('[' + focus + '] ' if focus != 'master' else '') + '❯ '
        budget = max(0, self.ui.output.get_size().columns - get_cwidth(prefix) - 1)
        visible, width = '', 0
        for char in hint:
            width += get_cwidth(char)
            if width > budget:
                break
            visible += char
        return visible

    def separator(self):
        # Leave the terminal's final column empty: a full-width border can be
        # reflowed into transcript rows while the user drags the window edge.
        return '─' * max(0, self.ui.output.get_size().columns - 1)

    def display_budget(self):
        """Reserve editable rows before optional chrome, using one shared budget."""
        size = self.ui.output.get_size()
        columns, rows = max(1, size.columns), max(1, size.rows)
        top, bottom, hint = rows >= 3, rows >= 4, rows >= 2
        input_rows = sum(max(1, (get_cwidth(line.expandtabs(4)) + 2) // columns + 1)
                         for line in self.input.text.split('\n'))
        available = max(0, rows - top - bottom - hint - input_rows)
        stream = bool(self.stream_text) and available > 0
        available -= stream
        queue = min(len(self.queue), 3, available)
        return {'top': top, 'bottom': bottom, 'stream': stream, 'queue': queue,
                'panel': min(8, available - queue)}

    def status_text(self):
        status = '{} | queued {} | attachments {}{}'.format(
            'Working' if self.pending else 'Ready', len(self.queue), len(self.attachments),
            ' | queue paused: /queue resume' if self.paused else ' | Esc stop · Enter send/queue · Ctrl-V image')
        size = self.ui.output.get_size()
        columns = max(1, size.columns)
        budget = self.display_budget()
        available = budget['panel']
        fragments = [('class:separator', self.separator() + '\n')] if budget['bottom'] else []
        state = self.input.buffer.complete_state
        if state and state.completions and available:
            status = '↑/↓ select · Enter apply · Esc close'
            selected = state.complete_index if state.complete_index is not None else 0
            count = min(5, available, len(state.completions))
            start = min(max(0, selected - count + 1), len(state.completions) - count)
            for index in range(start, start + count):
                item = state.completions[index]
                label = ('› ' if index == selected else '  ') + item.display_text
                description = item.display_meta_text
                if description:
                    label += '  ' + description
                fragments.append(('class:hint-selected' if index == selected else 'class:separator',
                                  self.clip_hint(label, columns) + '\n'))
        elif self.action_panel:
            fragments.extend(self.panel_fragments(available))
        elif not self.input.text and not self.attachments:
            status = self.input_placeholder() + ' | ' + status
        fragments.append(('class:separator', self.clip_hint(status, columns)))
        return fragments

    @staticmethod
    def clip_hint(text, columns):
        result, width = '', 0
        for char in str(text):
            char = char if char.isprintable() else ' '
            size = get_cwidth(char)
            if width + size > columns:
                break
            result += char
            width += size
        return result

    def append(self, kind, text):
        # Terminal control sequences returned by a model are displayed as text.
        text = ''.join(c if c in '\n\t' or c.isprintable() else '\ufffd' for c in str(text))
        if kind == 'status':
            self.flush_stream()
            self.streamed_answer = False
            return  # Working state lives in the compact prompt, not the transcript.
        event_id = self.store.record(kind, text)
        if kind in ('tool', 'result'):
            self.flush_stream()
            # A streamed preamble before a tool call is not the final answer.
            self.streamed_answer = False
            if kind == 'tool':
                self.write_line('Tool › ' + self.tool_display.call(text))
            else:
                self.write_line('  ↳ ' + self.tool_display.result(text, event_id))
            if kind == 'result':
                self.checkpoint()
            self.ui.invalidate()
            return
        delta = kind.endswith('_delta')
        if kind == 'answer_delta':
            self.streamed_answer = True
        if delta:
            if self.stream_kind != kind:
                self.flush_stream()
                self.stream_kind = kind
            self.stream_text += text
            while '\n' in self.stream_text:
                line, self.stream_text = self.stream_text.split('\n', 1)
                self.write_stream_line(line, line_end=True)
            # Commit screen-width chunks even when a model never emits newline.
            # Keep only the unfinished last row in the live prompt.
            budget = max(4, self.ui.output.get_size().columns - 4)
            while get_cwidth(self.stream_text) > budget:
                width, end = 0, 0
                for char in self.stream_text:
                    size = get_cwidth(char)
                    if width + size > budget:
                        break
                    width += size
                    end += 1
                self.write_stream_line(self.stream_text[:end])
                self.stream_text = self.stream_text[end:]
        else:
            self.flush_stream()
            prefix = {'Master': '● ', 'Scheduled': '● ', 'You': '❯ ',
                      'You (queued)': '❯ ', 'tool': '● ', 'result': '  ↳ '}.get(kind, kind + ' › ')
            suffix = ' (queued)' if kind == 'You (queued)' else ''
            if kind in ("Master", "Scheduled"):
                text = BoldText().ansi(text, final=True)
            rendered = prefix + text + suffix
            if kind in ('You', 'You (queued)'):
                # Reset each line so the background never leaks into replies or input.
                rendered = '\n'.join('\x1b[48;5;236m\x1b[38;5;255m' + line + '\x1b[0m'
                                     for line in rendered.split('\n'))
            self.write_line(rendered)
        self.ui.invalidate()

    def stream_prefix(self):
        if self.stream_started:
            return '  '
        return '✻ ' if self.stream_kind == 'reasoning_delta' else '● '

    def write_stream_line(self, text, line_end=False):
        rendered = self.markdown.ansi(text, line_end=line_end)
        self.write_line(self.stream_prefix() + rendered if rendered else '')
        if text:
            self.stream_started = True

    def show_panel(self, title, text):
        self.viewer_choice = None
        self.selected_task = None
        text = ''.join(c if c in '\n\t' or c.isprintable() else '\ufffd' for c in str(text))
        self.action_panel = (title, text)
        self.panel_offset = 0
        self.store.record('Operator', title + '\n' + text)
        self.ui.invalidate()

    def close_panel(self):
        self.action_panel = None
        self.viewer_choice = None
        self.selected_task = None
        self.task_buttons = []
        self.task_action = 0
        self.panel_offset = 0
        self.ui.invalidate()

    async def redraw_session(self):
        from terminal.session_display import history_lines
        from terminal.tool_display import ToolDisplay
        self.close_panel()
        self.stream_kind = None
        self.stream_text = ''
        self.stream_started = self.streamed_answer = False
        self.markdown = BoldText()
        self.tool_display = ToolDisplay()
        # Save the new identity before yielding to terminal rendering/background polling.
        self.checkpoint()

        def redraw():
            output = self.ui.output
            output.reset_attributes()
            output.erase_screen()
            output.cursor_goto(0, 0)
            # Legacy Win32 erase_screen already clears its complete buffer.
            if not hasattr(output, 'get_win32_screen_buffer_info'):
                output.write_raw('\x1b[3J')
            output.write('Session · ' + self.store.title(self.app.client.config) + '\n\n')
            for line in history_lines(self.app.agent.history):
                output.write_raw(line + '\n')
            if not self.app.agent.history:
                output.write('No messages yet.\n')
            output.flush()

        await run_in_terminal(redraw)

    def select_task(self, step=0):
        tasks = [task for task in self.task_store.list(limit=None, session_id=self.app.session_id) if task['state'] not in ('succeeded', 'cancelled')]
        tasks.sort(key=lambda task: task['id'])
        if not tasks:
            if self.action_panel is not None and step:
                self.close_panel()
            else:
                self.task_buttons = []
                current = self.app.session_task.snapshot()
                self.show_panel('/tasks', 'Current work: ' + self.store.title(self.app.client.config) + ' · ' + current['state'] + '\n'
                                + (current['goal'] or 'Ready for a task description.') + '\n'
                                + current.get('next_step', '') + '\nNo unfinished background tasks in this session. /tasks all for history. ←/→ or Esc to return.')
            return
        ids = [task['id'] for task in tasks]
        if step:
            # Include the conversation in navigation so Left undoes the first Right.
            choices = [None, *ids]
            index = choices.index(self.selected_task) if self.selected_task in choices else 0
            selected = choices[(index + step) % len(choices)]
            if selected is None:
                self.close_panel()
                return
            self.selected_task = selected
        elif self.selected_task not in ids:
            self.selected_task = ids[0]
        self.task_action = 0
        self.panel_offset = 0
        self.render_task_panel()

    def task_commands(self):
        task = self.task_store.get(self.selected_task)
        commands = [('View details', '/tasks status ' + task['id'])]
        if task['state'] not in ('succeeded', 'cancelled'):
            if task['state'].startswith('waiting_'):
                commands.append(('Resume', '/tasks resume ' + task['id']))
            commands.append(('Cancel task', '/tasks cancel ' + task['id']))
        return commands

    def render_task_panel(self):
        task = self.task_store.get(self.selected_task)
        if task['state'] in ('succeeded', 'cancelled') or task.get('session_id') != self.app.session_id:
            self.selected_task = None
            self.select_task()
            return
        commands = self.task_commands()
        self.task_buttons = commands
        self.task_action = min(self.task_action, len(commands) - 1)
        feedback = task.get('feedback') or {}
        reason = feedback.get('reason') or feedback.get('review', {}).get('reason', '')
        from terminal.titles import task_title
        lines = [task_title(task) + ' · ' + task['state'],
                 '←/→ tasks/chat · ↑/↓ actions · Enter apply · Esc close']
        lines += [('> ' if i == self.task_action else '  ') + '[' + label + ']' for i, (label, _) in enumerate(commands)]
        lines += [task['spec']['goal'], str(reason)]
        text = '\n'.join(lines)
        self.action_panel = ('Tasks', ''.join(c if c in '\n\t' or c.isprintable() else '\ufffd' for c in text))
        self.ui.invalidate()

    def panel_fragments(self, rows):
        if not self.action_panel or rows < 1:
            return []
        title, text = self.action_panel
        columns = max(1, self.ui.output.get_size().columns)
        lines = []
        for line in text.expandtabs(2).splitlines():
            chunk, width = '', 0
            for char in line:
                size = get_cwidth(char)
                if size > columns:
                    char, size = '\ufffd', 1
                if width + size > columns:
                    lines.append(chunk)
                    chunk, width = '', 0
                chunk += char
                width += size
            lines.append(chunk)
        height = max(0, rows - 1)
        self.panel_page_size = height
        self.panel_offset = min(self.panel_offset, max(0, len(lines) - max(1, height)))
        heading = 'Actions · ' + title + ' · PgUp/PgDn scroll · Esc close'
        heading = self.clip_hint(heading, columns)
        return [('class:prompt', heading + '\n'),
                ('', '\n'.join(lines[self.panel_offset:self.panel_offset + height]) + ('\n' if height else ''))]

    def prompt_text(self):
        # The unfinished line belongs to the renderer, never raw stdout. Limit
        # the live preview; flush_stream retains the complete text in scrollback.
        layout = self.display_budget()
        budget = max(0, self.ui.output.get_size().columns - get_cwidth(self.stream_prefix()) - 2)
        clipped = get_cwidth(self.stream_text.replace('\t', ' ')) > budget
        if clipped:
            budget = max(0, budget - 1)  # Reserve a cell for the ellipsis itself.
        width, tail = 0, []
        for char in reversed(self.stream_text.replace('\t', ' ')):
            cell_width = get_cwidth(char)
            if width + cell_width > budget:
                break
            width += cell_width
            tail.append(char)
        preview = ''.join(reversed(tail))
        if clipped and budget:
            preview = '…' + preview
        fragments = []
        if preview and layout['stream']:
            fragments.append(('', self.stream_prefix()))
            fragments.extend(self.markdown.preview(preview))
            fragments.append(('', '\n'))
        if layout['queue']:
            columns = self.ui.output.get_size().columns
            count = layout['queue']
            for i, (text, files) in enumerate(list(self.queue)[-count:]):
                label = ('Queued {} · '.format(len(self.queue)) if i == 0 else '  ') + '❯ '
                line = label + ' '.join(text.split()) + (' [media]' if files else '')
                visible = self.clip_hint(line, max(0, columns - 1))
                if get_cwidth(line) > columns - 1 and columns > 1:
                    visible = self.clip_hint(line, max(0, columns - 2)) + '…'
                fragments.append(('class:separator', visible + '\n'))
        if layout['top']:
            fragments.append(('class:separator', self.separator() + '\n'))
        focus = getattr(self.app, 'node_focus', 'master')
        fragments.append(('class:prompt', ('[' + focus + '] ' if focus != 'master' else '') + '❯ '))
        return fragments

    @staticmethod
    def write_line(text):
        # patch_stdout can safely suspend/repaint the input only after a newline.
        # Flushing a partial line lets the prompt overwrite model output.
        print(text, flush=True)

    def flush_stream(self):
        if self.stream_text:
            self.write_stream_line(self.stream_text)
        if self.markdown.pending or self.markdown.fence_pending:
            self.write_line(self.markdown.ansi('', final=True))
        self.markdown = BoldText()
        self.stream_text = ''
        self.stream_kind = None
        self.stream_started = False

    def stop(self):
        self.paused = True
        self.app.stop_event.set()
        self.append('Cancelled', 'Queue paused. Waiting for the active request/tool to return; /queue resume continues queued messages.')

    def add_attachments(self, additions):
        if len(self.attachments) + len(additions) > 4:
            raise ValueError('Attach 1–4 files per message')
        if sum(len(str(parts)) for _, parts in self.attachments + additions) > 24 * 1024 * 1024:
            raise ValueError('Combined encoded attachment limit: 24 MiB')
        self.attachments.extend(additions)
        self.append('Attached', ', '.join(p for p, _ in additions))

    async def run_prompt(self, callback):
        # The editor is suspended here. Its stdout proxy queues writes on the
        # event loop, which synchronous input() blocks: menus must bypass it.
        def invoke():
            with redirect_stdout(self.prompt_stdout), redirect_stderr(self.prompt_stderr):
                return callback()
        return await run_in_terminal(invoke)

    async def paste_image(self):
        self.command_busy = True
        try:
            self.add_attachments([('clipboard.png', await asyncio.to_thread(clipboard_image))])
            self.checkpoint()
        except Exception as exc:
            self.append('Error', str(exc))
        finally:
            self.command_busy = False
            self.ui.invalidate()

    async def submit(self):
        if self.command_busy:
            return
        self.command_busy = True
        original = self.input.text
        text = original.strip()
        first_word = text.split()[0] if text else ''
        # New keystrokes during asynchronous media conversion belong to the next
        # draft. Never reset that draft when this submission finishes.
        self.input.buffer.reset(append_to_history=True)
        try:
            if not text and not self.attachments:
                return
            if not text.startswith('/'):
                self.action_panel = None
                self.selected_task = None
            if text in ('/quit', '/exit'):
                self.ui.exit()
                return
            if text == '/cancel-turn':
                self.stop()
            elif text == '/queue resume':
                self.paused = False
            elif text in ('/task', '/tasks', '/tasks list'):
                self.select_task()
            elif first_word in ('/rename', '/sessions', '/export'):
                if self.pending:
                    raise ValueError('Wait for the active turn before managing saved conversations')
                self.checkpoint()
                argument = text.partition(' ')[2].strip()
                if first_word == '/rename':
                    name = self.store.rename(self.app.client.config, argument)
                    self.show_panel('/rename', 'Renamed: ' + name)
                elif first_word == '/export':
                    path = self.store.export(self.app.client.config, argument or None)
                    self.show_panel('/export', 'Exported: ' + str(path))
                else:
                    rows = self.store.list_sessions(self.app.client.config, query=argument)
                    self.show_panel('/sessions', '\n'.join(row['label'] + ' | ' + row['updated'] for row in rows) or 'No matching conversations')
            elif first_word in ('/resume','/history','/new'):
                if self.pending:
                    raise ValueError('Wait for the active turn before browsing or switching sessions')
                parts=text.split(maxsplit=1)
                self.checkpoint()
                if parts[0]=='/new':
                    if self.queue or self.attachments:
                        raise ValueError('Clear queued messages and attachments before starting a new session')
                    self.store.new_session()
                    from terminal.session_task import SessionTask
                    self.app.session_task = SessionTask(identity=self.store.session_id)
                    goal = text[len('/new'):].strip()
                    if goal:
                        self.app.session_task.update({'goal': goal, 'state': 'active'})
                    self.app.agent.history=[]
                    self.app.agent.turn_summaries=[]
                    await self.redraw_session()
                    self.show_panel('/new','New conversation: '+self.store.title(self.app.client.config) + '\nSend a message to begin; /tasks shows the current work.')
                elif parts[0]=='/resume' and len(parts)==1:
                    rows=self.store.list_sessions(self.app.client.config)
                    lines=['Saved conversations — choose a title to resume; /history TITLE to preview, /new to start fresh.']
                    for row in rows:
                        lines.append('{} | {} | {} turns'.format(row['label'],row['updated'],row['turns']))
                        if row['last_summary']:
                            from terminal.turn_summary import display
                            lines.append('  '+display(row['last_summary'][0]))
                    self.show_panel('/resume', '\n'.join(lines))
                    self.input.text='/resume '
                    self.input.buffer.cursor_position=len(self.input.text)
                    if self.ui.is_running:
                        self.input.buffer.start_completion(select_first=False)
                elif parts[0]=='/history':
                    data=self.store.read_session(self.app.client.config,parts[1] if len(parts)==2 else self.store.session_id)
                    import json
                    lines=[]
                    for message in data.get('history',[]):
                        content=message.get('content','')
                        if not isinstance(content,str):
                            content='\n'.join(p.get('text','[media]') for p in content)
                        lines.append(message.get('role','message')+': '+content)
                    from terminal.turn_summary import display
                    for summary in data.get('summaries',[]):
                        lines.append(display(summary))
                    self.show_panel('/history', '\n\n'.join(lines) or 'No messages yet')
                else:
                    if self.queue or self.attachments:
                        raise ValueError('Clear queued messages and attachments before switching sessions')
                    data=self.store.resume(self.app.client.config,parts[1])
                    from terminal.session_task import SessionTask
                    self.app.session_task = SessionTask(data.get('task'), identity=self.store.session_id, history=data.get('history', []))
                    self.app.agent.history=data.get('history',[])
                    self.app.agent.turn_summaries=data.get('summaries',[])
                    self.queue.extend(data.get('queue',[]))
                    self.attachments=data.get('attachments',[])
                    self.input.text=data.get('draft','')
                    self.input.buffer.cursor_position=len(self.input.text)
                    self.paused=bool(self.queue)
                    title=self.store.title(self.app.client.config)
                    await self.redraw_session()
                    self.show_panel('/resume','Resumed: '+title+'. History restored above. Continue typing to chat.' + (' Queued messages are paused; /queue resume to run them.' if self.queue else ''))
            elif text == '/queue clear':
                self.queue.clear()
                self.append('Queue', 'Cleared')
            elif text == '/queue':
                self.append('Queue', '\n'.join('{}: {} ({} attachments)'.format(i, t, len(a)) for i, (t, a) in enumerate(self.queue, 1)) or 'Empty')
            elif first_word == '/details':
                parts = text.split()
                if len(parts) > 2 or (len(parts) == 2 and not parts[1].isdigit()):
                    raise ValueError('Usage: /details [result ID]')
                self.append('Details', self.store.tool_details(int(parts[1]) if len(parts) == 2 else None))
            elif text == '/detach':
                self.attachments.clear()
            elif text == '/paste':
                self.add_attachments([('clipboard.png', await asyncio.to_thread(clipboard_image))])
            elif text.startswith('/attach ') or dropped_paths(text):
                paths = shlex.split(text[len('/attach '):]) if text.startswith('/attach ') else dropped_paths(text)
                if not paths or len(self.attachments) + len(paths) > 4:
                    raise ValueError('Attach 1–4 files per message')
                # Validate all before changing the composer; failed input is retained.
                additions = [(p, await asyncio.to_thread(attachment, p)) for p in paths]
                self.add_attachments(additions)
            elif text.startswith('/') or text in self.aliases:
                command = self.aliases.get(text, text)
                if self.pending and command.split()[0] not in ('/node', '/tasks', '/agents', '/spawn', '/send', '/result', '/agent-messages', '/stop-agent', '/help', '/stop', '/permissions', '/requests', '/mode', '/plan'):
                    raise ValueError('Wait for the active turn before using this command')
                if command == '/stop':
                    self.stop()
                agent_commands = ('/agents', '/spawn', '/send', '/result', '/agent-messages', '/stop-agent')
                if command in agent_commands[1:]:
                    data = await asyncio.to_thread(self.app.tool, 'agents_status', {})
                    self.show_panel(command, ('Choose a role, then enter a task.' if command == '/spawn' else
                                             format_command_result('/agents', data)))
                    if not self.input.text:
                        self.input.text = command + ' '
                        self.input.buffer.cursor_position = len(self.input.text)
                        if self.ui.is_running:
                            self.input.buffer.start_completion(select_first=False)
                    return
                if command == '/model':
                    from terminal.setup import discover_models
                    self.model_choices = []
                    config = dict(self.app.client.config)
                    key = self.app.client.resolved_key()
                    if not key:
                        raise ValueError('Configure the current provider key before listing models')
                    self.show_panel('/model', 'Discovering models from the current provider...')
                    self.model_choices = await asyncio.to_thread(discover_models, config, key)
                    self.show_panel('/model', 'Choose a model · company A–Z, newest catalog date first. Catalog listing does not verify tool support.' if self.model_choices else 'No models listed. Enter /model MODEL_ID manually.')
                    if not self.input.text:
                        self.input.text = '/model '
                        self.input.buffer.cursor_position = len(self.input.text)
                        if self.ui.is_running:
                            self.input.buffer.start_completion(select_first=False)
                    return
                if command.split()[0] in ('/viewer', '/scene', '/complex', '/sim', '/models', '/model-load'):
                    self.app.stop_event.clear()
                    self.pending_command = command
                    self.pending = self.executor.submit(self.app.dispatch, command)
                    self.checkpoint()
                    return
                # Existing hidden-key and approval prompts temporarily own the terminal.
                result = (await asyncio.to_thread(self.app.dispatch, command) if command.split()[0] in agent_commands
                          else await self.run_prompt(lambda: self.app.dispatch(command)))
                task_selection = self.selected_task
                self.show_panel(command, format_command_result(command, result))
                if task_selection and command.startswith(('/tasks cancel ', '/tasks resume ')):
                    self.selected_task = task_selection
                    self.task_action = 0
                    self.render_task_panel()
                if command in ('/permissions', '/mode'):
                    self.input.text=command + ' '
                    self.input.buffer.cursor_position=len(self.input.text)
                    if self.ui.is_running:
                        self.input.buffer.start_completion(select_first=False)
                if command.split()[0] in ('/switch', '/key', '/expert-key'):
                    self.model_choices = []
                if command in ('/help', '/shortcuts'):
                    self.append('Editor', 'Type / to find commands · Tab/↑/↓ choose · Enter runs selected command · Esc dismisses · Arrows/Home/End edit · Enter send/queue · Alt-Enter newline · Ctrl-C clear/stop/exit · Esc stop · Ctrl-V or /paste clipboard image · drop media paths then Enter to attach · /attach PATH · /detach · /queue [clear|resume] · /resume [TITLE] · /history [TITLE] · /new · /details [ID] expands a tool result. Scroll using your terminal.')
            elif self.app.node_focus != 'master':
                from terminal.nodes import focused_reply
                focus = self.app.node_focus
                result = await run_in_terminal(lambda: focused_reply(self.app, text, self.attachments))
                self.append('Node ' + focus, result)
            else:
                if len(text) > 16000 or len(self.queue) >= 20:
                    raise ValueError('Limit: 16000 characters per message, 20 queued messages')
                auto_attached = self.attachments[:]
                self.queue.append((text or 'Describe the attached media.', auto_attached))
                self.attachments.clear()
                self.continuations = 0
                self.append('You (queued)' if self.pending or self.paused else 'You', text or '[media]')
            self.checkpoint()
        except Exception as exc:
            current = self.input.text
            self.input.text = original + ('\n' if original and current else '') + current
            self.input.buffer.cursor_position = len(self.input.text)
            self.append('Error', str(exc))
        finally:
            self.command_busy = False
            self.ui.invalidate()

    def render_viewer_choice(self):
        labels=['Reopen last scene','Keep closed']
        self.action_panel=('Simulator closed', 'MuJoCo window closed. Scene file is preserved.\n' + '\n'.join(('> ' if i==self.viewer_choice else '  ')+label for i,label in enumerate(labels))+'\n↑/↓ select · Enter confirm · Esc dismiss')
        self.panel_offset=0

    def poll_viewer(self):
        # Ignore the brief close/open transition while a scene command owns the viewer.
        if self.pending or self.command_busy:return
        state=self.app.viewer.status()
        opened=state.get('window_open',False)
        if self.viewer_was_open and not opened:
            self.append('Simulator', 'Window closed' if state.get('status')=='closed' else 'Window heartbeat unavailable')
            self.selected_task=None
            self.viewer_choice=0
            self.render_viewer_choice()
        self.viewer_was_open=opened

    async def poll(self):
        while True:
            self.poll_viewer()
            if time.monotonic()>=self.task_poll_at:
                for feedback in self.task_store.notifications(self.task_cursor, session_id=self.app.session_id):
                    details=feedback.get('feedback') or {}
                    reason=details.get('reason') or details.get('review',{}).get('reason','')
                    from terminal.titles import task_title
                    self.append('Task feedback',task_title(self.task_store.get(feedback['task_id']))+' · '+feedback['state']+(' · '+str(reason)[:200] if reason else ''))
                    self.task_cursor=feedback['id']
                self.task_store.meta('terminal_seen_event:' + self.app.session_id,self.task_cursor)
                if self.selected_task:
                    self.render_task_panel()
                self.task_poll_at=time.monotonic()+1
            notifications, has_mail = await asyncio.get_running_loop().run_in_executor(
                self.poll_executor, self.app.runtime.poll_notifications)
            for event in notifications:
                self.append('Agent', '{} · {} {} · {}'.format(event.get('title', event['role']), event['role'], event.get('reference', ''), event['state']))
            if self.action_panel and self.action_panel[0].split()[0] == '/agents':
                title = self.action_panel[0]
                if self.app.permissions.snapshot()['rules'].get('agents_status') == 'allow':
                    rows = self.app.runtime.choices()
                    data = {'roles':list(self.app.runtime.definitions),
                            'running':sum(r['state']=='running' for r in rows),
                            'queued':sum(r['state']=='queued' for r in rows),
                            'tasks':[r for r in rows if title != '/agents active' or r['state'] in ('running','queued')]}
                    self.action_panel = (title, format_command_result(title,data))
                else:
                    self.action_panel = (title, 'Agent status permission required.')
            if self.pending and self.pending.done():
                try:
                    answer = self.pending.result()
                    if self.timer:
                        self.app.scheduler.finish(*self.timer, str(answer))
                    if self.pending_command:
                        prefix = ('Returned after cancellation; effects are not automatically rolled back.\n'
                                  if self.app.stop_event.is_set() else '')
                        self.show_panel(self.pending_command, prefix + format_command_result(self.pending_command, answer))
                    elif not self.app.stop_event.is_set() and not self.streamed_answer:
                        self.append('Scheduled' if self.timer else 'Master', answer)
                except Exception as exc:
                    if self.timer:
                        self.app.scheduler.finish(*self.timer, str(exc), failed=True)
                    self.paused = bool(self.queue)
                    hint = ('Queue paused; /queue resume to continue.' if self.paused
                            else 'You can send another message.')
                    if self.pending_command:
                        self.show_panel(self.pending_command, 'Error: ' + str(exc) + '\n' + hint)
                    else:
                        self.append('Master error', str(exc) + '\n' + hint)
                self.flush_stream()
                self.pending = None
                self.pending_command = None
                self.timer = None
                self.streamed_answer = False
                self.checkpoint()
            if not self.pending and not self.paused and not self.command_busy:
                if self.queue:
                    text, files = self.queue.popleft()
                    self.app.stop_event.clear()
                    self.pending = (self.executor.submit(self.app.agent.reply, text, [part for _, parts in files for part in parts])
                                    if files else self.executor.submit(self.app.dispatch, text, focus="master"))
                elif has_mail and self.continuations < 8:
                    self.continuations += 1
                    self.app.stop_event.clear()
                    self.pending = self.executor.submit(self.app.agent.reply, '请处理新到达的子任务消息，依据证据继续协调或汇总。')
                else:
                    job = self.app.scheduler.claim()
                    if job:
                        job_id, period, command = job
                        self.timer = (job_id, period)
                        self.app.stop_event.clear()
                        if command.startswith('/'):
                            try:
                                result = await run_in_terminal(lambda: self.app.dispatch(command, scheduled=True))
                                self.app.scheduler.finish(job_id, period, str(result))
                                self.append('Scheduled', result)
                            except Exception as exc:
                                self.app.scheduler.finish(job_id, period, str(exc), failed=True)
                            self.timer = None
                        else:
                            from terminal.llm import ChatAgent
                            from terminal.app import TOOLS
                            agent = ChatAgent(self.app.client, TOOLS, self.app.scheduled_tool, stop_event=self.app.stop_event)
                            self.pending = self.executor.submit(agent.reply, command)
            self.ui.invalidate()
            await asyncio.sleep(.1)

    async def take_queued_steering(self, budget):
        # This runs on the UI loop, alongside queue editing/clear/pause, never
        # mutating the deque from the model worker thread.
        if self.paused or self.command_busy or self.pending_command or self.timer or self.app.stop_event.is_set():
            return []
        updates = []
        while self.queue:
            text, files = self.queue[0]
            if len(text) > budget:
                break
            self.queue.popleft()
            updates.append((text, [part for _, parts in files for part in parts]))
            budget -= len(text) + 1
        self.ui.invalidate()
        return updates

    async def run(self):
        from terminal.app import ALIASES
        self.aliases = ALIASES
        loop = asyncio.get_running_loop()
        self.app.agent.streaming = True
        def display_event(kind, text):
            self.append(kind, text)
            if kind == 'Steering':
                self.checkpoint()
        self.app.agent.on_event = lambda kind, text: loop.call_soon_threadsafe(display_event, kind, text)
        self.app.agent.take_steering = lambda budget: asyncio.run_coroutine_threadsafe(self.take_queued_steering(budget), loop).result()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.poll_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="loop-broker")
        try:
            print(welcome(self.app.client.config['model'], self.app.expert.config['model'], self.app.permissions.snapshot()['mode'],
                          fast_status=getattr(self.app, 'startup_fast_status', None)))
            print('Enter send/queue · Alt-Enter newline · Esc stop · Ctrl-C clear/stop/exit · Ctrl-V image · /attach PATH · /help')
            if self.app.agent.history or self.queue or self.draft:
                print('Session restored: {} messages, {} queued. /resume to browse sessions; /queue resume to run queued messages.'.format(len(self.app.agent.history), len(self.queue)))
            self.prompt_stdout, self.prompt_stderr = sys.stdout, sys.stderr
            with patch_stdout(raw=True):
                await self.session.prompt_async(
                    default=self.draft, bottom_toolbar=self.status_text, refresh_interval=.2,
                    pre_run=lambda: self.ui.create_background_task(self.poll()))
        finally:
            self.flush_stream()
            self.app.stop_event.set()
            self.app.agent.on_event = lambda *args: None
            self.app.agent.take_steering = None
            await asyncio.to_thread(self.app.nodes.close)
            await asyncio.to_thread(self.executor.shutdown, wait=True)
            await asyncio.to_thread(self.poll_executor.shutdown, wait=True)
            try:
                self.checkpoint()
                print('Session saved: ' + str(self.store.path))
            finally:
                self.store.close()


def run(app):
    asyncio.run(Terminal(app).run())
