"""Compact tool presentation. Raw events remain in the local transcript."""
import json
import time


def shorten(value, limit=100):
    text = ' '.join(str(value).split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


class ToolDisplay:
    def __init__(self):
        self.name = None
        self.started = None

    def call(self, text):
        name, separator, payload = text.partition('(')
        self.name = name if separator else None
        self.started = time.monotonic()
        try:
            args = json.loads(payload[:-1])
        except (ValueError, TypeError):
            args = {}
        if not isinstance(args, dict):
            args = {}
        title = {'web_search': 'Web Search', 'web_weather': 'Weather', 'web_fetch': 'Web Fetch'}.get(name, name)
        key = {'web_search': 'query', 'web_weather': 'location', 'web_fetch': 'url'}.get(name)
        if key and key in args:
            return title + '(' + json.dumps(shorten(args[key]), ensure_ascii=False) + ')'
        return shorten(title) + '(' + shorten(json.dumps(args, ensure_ascii=False), 80) + ')'

    def result(self, text, event_id):
        elapsed = f' · {time.monotonic() - self.started:.1f}s' if self.started is not None else ''
        name = self.name
        self.name = self.started = None
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        summary = 'Returned data'
        if isinstance(data, dict):
            review = data.get('review')
            state = data.get('viewer') if isinstance(data.get('viewer'), dict) else data
            nested_review = state.get('review')
            failed_review = next((r for r in (review, nested_review) if isinstance(r, dict)
                                  and r.get('verdict') in ('fail', 'inconclusive')), None)
            if data.get('error'):
                summary = 'Error: ' + shorten(data.get('message') or data['error'], 150)
            elif data.get('supported') is False:
                summary = 'Unsupported: ' + shorten(data.get('reason', 'adapter unavailable'))
            elif name == 'devices':
                summary = '{} USB · {} serial/video · {} input nodes'.format(len(data.get('usb_devices', [])), len(data.get('devices', [])), len(data.get('input_devices', [])))
            elif state.get('error'):
                summary = 'Error: ' + shorten(state['error'], 150)
            elif failed_review:
                summary = 'Review: ' + failed_review['verdict'] + ' · ' + shorten(failed_review.get('reason', ''), 100)
            elif data.get('state') in ('queued', 'starting', 'failed', 'unresponsive', 'stopped'):
                summary = 'State: ' + data['state']
            elif isinstance(data.get('viewer'), dict):
                summary = ('Scene loaded in viewer' if state.get('window_open') else
                           'Scene saved; window not open: ' + shorten(state.get('error', 'unconfirmed'), 120))
            elif data.get('executed') is True:
                summary = 'Executed: ' + str(data.get('action', 'command'))
            elif name == 'model_library' and isinstance(data.get('models'), list):
                summary = str(len(data['models'])) + ' models available'
            elif isinstance(review, dict) and review.get('verdict'):
                summary = 'Review: ' + str(review['verdict']) + ' · ' + shorten(review.get('reason', ''), 100)
            elif data.get('locations') == []:
                summary = 'No matching location; more location detail needed'
            elif data.get('window_open') is False:
                summary = 'Window not confirmed open'
            elif data.get('state') in ('queued', 'starting', 'failed', 'unresponsive', 'stopped'):
                summary = 'State: ' + data['state']
            elif name == 'web_search' and isinstance(data.get('results'), list):
                summary = f"1 search · {len(data['results'])} results"
            elif name == 'web_weather' and isinstance(data.get('current'), dict):
                summary = 'Weather data retrieved'
            elif name == 'web_fetch':
                summary = 'Page retrieved' + (' · truncated' if data.get('truncated') else '')
        return shorten(summary, 170) + elapsed + f' · /details {event_id}'
