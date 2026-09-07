"""Model-specific reasoning choices from endpoint metadata or cited documentation."""
import hashlib
import time
from urllib.parse import urlsplit
from loop_robot.terminal.config import REASONING_EFFORTS

OPENAI_DOC = 'https://developers.openai.com/api/docs/models/'
QWEN_DOC = 'https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions'


def metadata(item):
    """Accept explicit enumerations only; a boolean capability is not a tier list."""
    levels = item.get('supported_reasoning_efforts', item.get('reasoning_efforts'))
    if levels is None and isinstance(item.get('reasoning_effort'), dict):
        levels = item['reasoning_effort'].get('enum')
    if not isinstance(levels, list) or any(not isinstance(v, str) for v in levels):
        return None
    return [v for v in REASONING_EFFORTS if v in levels]


def identity(client):
    config = client.config
    return (config['base_url'].rstrip('/'), config.get('protocol', 'openai'),
            hashlib.sha256((client.resolved_key() or '').encode()).hexdigest())


def remember(app, models, binding=None):
    app.reasoning_catalog = (binding if binding is not None else identity(app.client), time.monotonic(), models)


def choices(app):
    config = app.client.config
    model = config['model']
    cached = getattr(app, 'reasoning_catalog', None)
    if cached and cached[0] == identity(app.client) and time.monotonic() - cached[1] < 300:
        for item in cached[2]:
            if item['id'] == model and 'reasoning_efforts' in item:
                return {'choices': ['default', *item['reasoning_efforts']],
                        'source': 'Current endpoint /models metadata (current credentials)',
                        'notice': 'Endpoint-declared levels; no inference probe was sent.'}
    tiers, source = None, None
    if model == 'gpt-6-astra':
        tiers = ['low', 'medium', 'high', 'xhigh', 'max']
        source = OPENAI_DOC + model
    elif model in ('gpt-5.6', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna'):
        tiers = ['none', 'low', 'medium', 'high', 'xhigh', 'max']
        source = OPENAI_DOC + ('gpt-5.6-sol' if model == 'gpt-5.6' else model)
    elif model.startswith('qwen3.8-') and config.get('protocol', 'openai') == 'openai':
        tiers, source = ['low', 'medium', 'xhigh'], QWEN_DOC
    if tiers is not None:
        host = urlsplit(config['base_url']).hostname
        official = host == 'api.openai.com' if source.startswith(OPENAI_DOC) else host in ('dashscope.aliyuncs.com', 'dashscope-intl.aliyuncs.com')
        return {'choices': ['default', *tiers], 'source': source,
                'notice': 'Official documentation, checked 2026-09-08.' + ('' if official else ' Gateway support is not verified; endpoint metadata takes precedence.')}
    return {'choices': ['default'], 'source': 'Unknown',
            'notice': 'No supported levels reported or documented here. Default omits the reasoning parameter.'}


def set_effort(app, effort):
    capability = choices(app)
    if effort not in capability['choices']:
        raise ValueError('Choose ' + ', '.join(capability['choices']) + '. ' + capability['notice'])
    from loop_robot.terminal.settings import update
    config = dict(app.client.config)
    if effort == 'default':
        config.pop('reasoning_effort', None)
    else:
        config['reasoning_effort'] = effort
    update(app, 'profiles', {'operation': 'save', 'name': app.providers.selected()['master'],
                            'config': config, 'replace': True})
    return {'model': app.client.config['model'],
            'requested_reasoning_effort': app.client.config.get('reasoning_effort', 'provider default'), **capability}
