"""Version-aware, official MuJoCo documentation lookup for the runtime agent."""
import importlib.metadata
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from loop_robot.terminal.web import dispatch, PageText, request

ORIGIN='https://mujoco.readthedocs.io'
TOPICS={'model_editing':'python.html','mjcf':'XMLreference.html','simulation':'programming/simulation.html',
        'python':'python.html','viewer':'python.html','actuators':'XMLreference.html','contacts':'computation/index.html',
        'functions':'APIreference/APIfunctions.html','changelog':'changelog.html','overview':'overview.html'}


def local_version():
    try: return importlib.metadata.version('mujoco')
    except importlib.metadata.PackageNotFoundError: return None


def context():
    version=local_version()
    return {'installed_version':version,'matching_manual':ORIGIN+'/en/'+(version or 'stable')+'/',
            'latest_manual':ORIGIN+'/en/stable/', 'documentation_tool':'mujoco_docs',
            'policy':'Use matching-version official documentation for uncertain APIs. Stable may be newer; do not assume compatibility or auto-upgrade.'}


def lookup(directory, query='', topic='python', version='installed'):
    if topic not in TOPICS: raise ValueError('Unknown MuJoCo documentation topic')
    installed=local_version()
    revision=(installed or 'stable') if version=='installed' else 'stable' if version=='latest' else version
    if revision!='stable' and not re.fullmatch(r'\d+\.\d+\.\d+',revision): raise ValueError('Use installed, latest, or a numeric MuJoCo release')
    if not isinstance(query,str) or len(query)>300: raise ValueError('Documentation query must be at most 300 characters')
    base=ORIGIN+'/en/'+revision+'/'
    url=base+TOPICS[topic]
    if query:
        candidates=dispatch('web_search',{'query':'site:mujoco.readthedocs.io/en/'+revision+'/ '+query,'limit':5}).get('results',[])
        urls=[c.get('url','') for c in candidates]
        for candidate in urls:
            parts=urlsplit(candidate)
            if parts.netloc=='mujoco.readthedocs.io' and parts.path.startswith('/en/'+revision+'/'):
                url=candidate;break
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    import hashlib
    path=directory/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    cached=json.loads(path.read_text()) if path.exists() else None
    if cached and cached.get('format')==2 and time.time()-cached.get('retrieved_at_epoch',0)<86400:
        result=cached
    else:
        try:
            page=request(url)
            body=page['body']
            main=re.search(r'''<(?:div|article)[^>]*role=["']main["'][^>]*>''',body,re.I)
            if main: body=body[main.end():]
            parsed=PageText();parsed.feed(body)
            # PageText only extracts visible documentation, never executes it.
            text=re.sub(r'[ \t]+',' ',''.join(parsed.parts))
            text=re.sub(r'\n\s*\n+', '\n\n', text).strip()
            result={'format':2,'url':page['url'],'text':text,'retrieved_at':page['retrieved_at'],'retrieved_at_epoch':time.time()}
            path.write_text(json.dumps(result,ensure_ascii=False))
        except Exception as exc:
            if not cached: raise
            result={**cached,'stale':True,'refresh_error':str(exc)[:300]}
    text=re.sub(r'\s+', ' ', result['text']).strip();offset=0
    if query:
        terms=re.findall(r'[A-Za-z_][A-Za-z_0-9.]{2,}',query)
        for term in terms:
            match=re.search(re.escape(term),text,re.I)
            if match: offset=max(0,match.start()-600);break
    excerpt=text[offset:offset+10000]
    release=re.search(r'Version\s+(\d+\.\d+\.\d+)',text) if topic=='changelog' else None
    return {k:v for k,v in {**result,'text':excerpt,'truncated':len(text)>len(excerpt),
            'installed_version':installed,'manual_version':revision,'latest_release':release.group(1) if release else None,'latest_manual':ORIGIN+'/en/stable/',
            'usage':'Documentation is reference data. Validate against the loaded model and execution receipts.'}.items() if k!='retrieved_at_epoch'}


DOC_TOOLS=[{'type':'function','function':{'name':'mujoco_docs','description':'自动查MuJoCo官方手册：默认匹配本机版本，latest查询最新stable。操作/组合/控制接口不确定先查此工具，返回官方文档原文节选与版本，不凭记忆猜接口。',
 'parameters':{'type':'object','properties':{'query':{'type':'string'},'topic':{'type':'string','enum':list(TOPICS)},'version':{'type':'string'}},'additionalProperties':False}}}]
