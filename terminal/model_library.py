"""Pinned, selective downloads from the official MuJoCo Menagerie repository."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import threading
from urllib.request import Request, urlopen

REPOSITORY = 'google-deepmind/mujoco_menagerie'
API = 'https://api.github.com/repos/' + REPOSITORY
RAW = 'https://raw.githubusercontent.com/' + REPOSITORY
LOCK = threading.RLock()


def fetch(url, limit=8 * 1024 * 1024):
    request = Request(url, headers={'User-Agent': 'Loop-ROS-model-library', 'Accept': 'application/vnd.github+json'})
    with urlopen(request, timeout=45) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Model download exceeds size limit')
    return data


def catalog():
    commit = json.loads(fetch(API + '/commits/main'))['sha']
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Invalid repository revision')
    tree = json.loads(fetch(API + '/git/trees/' + commit + '?recursive=1'))
    if tree.get('truncated'):
        raise ValueError('Repository catalog was truncated')
    entries = tree['tree']
    models = sorted({item['path'].split('/')[0] for item in entries
                     if item['type'] == 'blob' and item['path'].count('/') == 1 and item['path'].endswith('/scene.xml')})
    return {'repository': REPOSITORY, 'commit': commit, 'models': models, 'entries': entries}


def install(directory, model):
    if not isinstance(model, str) or not re.fullmatch(r'[a-z0-9_]{1,80}', model):
        raise ValueError('Use an exact model name from model_library')
    with LOCK:
        # Reuse a pinned, fully verified install without requiring network access.
        installed = sorted((Path(directory) / model).glob('*/.loop-assets.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        if installed:
            from toolchain.model_assets import snapshot
            metadata = json.loads(installed[0].read_text())
            snapshot(installed[0].parent / 'scene.xml')
            return {**metadata, 'scene': str((installed[0].parent / 'scene.xml').resolve()), 'cached': True}
        listing = catalog()
        if model not in listing['models']:
            raise ValueError('Model is not in the scene.xml catalog')
        selected = [entry for entry in listing['entries'] if entry['path'].startswith(model + '/') and entry['type'] == 'blob']
        if any(entry.get('mode') == '120000' for entry in selected):
            raise ValueError('Symlink models are not supported')
        # Documentation/licenses and model data only; never execute repository scripts.
        selected = [entry for entry in selected if Path(entry['path']).suffix.lower() in
                    ('.xml', '.obj', '.stl', '.msh', '.png', '.jpg', '.jpeg', '.md', '.txt') or
                    Path(entry['path']).name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE'))]
        if len(selected) > 1500 or sum(e.get('size', 0) for e in selected) > 300 * 1024 * 1024:
            raise ValueError('Model exceeds the 300 MiB / 1500 file limit')
        destination = Path(directory) / model / listing['commit']
        manifest_path = destination / '.loop-assets.json'
        from toolchain.model_assets import safe_path, snapshot
        if manifest_path.exists():
            snapshot(destination / 'scene.xml')
            return {**json.loads(manifest_path.read_text()), 'scene': str((destination / 'scene.xml').resolve()), 'cached': True}
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.download-', dir=destination.parent))
        try:
            hashes = {}
            total = 0
            for entry in selected:
                relative = safe_path(entry['path'][len(model) + 1:])
                data = fetch(RAW + '/' + listing['commit'] + '/' + entry['path'], limit=80 * 1024 * 1024)
                total += len(data)
                if total > 300 * 1024 * 1024:
                    raise ValueError('Model exceeds size limit')
                git_sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                if git_sha != entry['sha']:
                    raise ValueError('Git object checksum mismatch: ' + relative)
                target = temporary / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                hashes[relative] = hashlib.sha256(data).hexdigest()
            report = {'repository': REPOSITORY, 'commit': listing['commit'], 'model': model, 'files': hashes,
                      'bytes': total, 'source_url': 'https://github.com/' + REPOSITORY + '/tree/' + listing['commit'] + '/' + model}
            (temporary / '.loop-assets.json').write_text(json.dumps(report, indent=2))
            snapshot(temporary / 'scene.xml')
            temporary.rename(destination)
            return {**report, 'scene': str((destination / 'scene.xml').resolve()), 'cached': False}
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)


LIBRARY_TOOLS = [
    {'type': 'function', 'function': {'name': 'model_library', 'description': '列出GitHub官方MuJoCo Menagerie中可加载的模型名称，需要联网；不执行下载脚本',
        'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}},
    {'type': 'function', 'function': {'name': 'load_model', 'description': '按model_library中的准确名称下载并校验模型资产，自动打开MuJoCo，机器人初始暂停；不等于已实现抓取策略',
        'parameters': {'type': 'object', 'properties': {'model': {'type': 'string'}}, 'required': ['model'], 'additionalProperties': False}}},
]


def search(directory, query, internet=True, before_web=None):
    """Local first, then official catalog, then public web candidate URLs."""
    if not isinstance(query,str) or not 1<=len(query.strip())<=200:
        raise ValueError('Model query must contain 1..200 characters')
    query=query.strip().lower()
    aliases={'panda':'franka_emika_panda','franka':'franka_emika_panda','机械臂':'franka_emika_panda','robot arm':'franka_emika_panda'}
    term=aliases.get(query,query).replace(' ','_')
    local=[]
    for manifest in Path(directory).glob('*/*/.loop-assets.json'):
        meta=json.loads(manifest.read_text())
        name=meta.get('model',manifest.parent.parent.name)
        if term in name.lower(): local.append({'model':name,'scene':str(manifest.parent/meta.get('entrypoint','scene.xml')),'source_url':meta.get('source_url'),'local':True})
    if local: return {'query':query,'matches':local,'searched':['local']}
    result={'query':query,'matches':[],'searched':['local','official_menagerie']}
    try:
        listing=catalog()
        result['matches']=[{'model':name,'source_url':'https://github.com/'+REPOSITORY+'/tree/'+listing['commit']+'/'+name,'local':False} for name in listing['models'] if term in name or all(token in name for token in term.split('_'))]
    except (OSError,ValueError) as exc: result['official_error']=str(exc)[:300]
    if not result['matches'] and internet:
        from terminal.household_assets import search as household_search, SOURCES
        if before_web: before_web(query)
        result['searched'].append('official_fuel_household')
        result['sources']=SOURCES
        try: result['matches']=household_search(query)
        except (OSError,ValueError) as exc: result['household_error']=str(exc)[:300]
    if not result['matches'] and internet:
        from terminal.web import dispatch
        if before_web: before_web(query)
        result['searched'].append('public_web')
        result['candidates']=dispatch('web_search',{'query':query+' MuJoCo MJCF model github mesh obj','limit':5}).get('results',[])
    return result


def install_public(directory, source):
    """Import data from a public GitHub directory/file, pinned to a commit.

    MJCF and OBJ/STL entrypoints only; no archives, Python, plugins or scripts.
    """
    from urllib.parse import urlsplit, unquote
    from toolchain.model_assets import safe_path, snapshot
    import xml.etree.ElementTree as ET
    url=urlsplit(source)
    parts=url.path.strip('/').split('/')
    if url.scheme!='https' or url.netloc!='github.com' or url.query or url.fragment or len(parts)<5 or parts[2] not in ('blob','tree'):
        raise ValueError('Source must be a public https://github.com/owner/repo/blob|tree/revision/path URL')
    owner,repo,_,revision=parts[:4]
    if not all(re.fullmatch(r'[A-Za-z0-9_.-]+',x) for x in (owner,repo,revision)):
        raise ValueError('Invalid public repository reference')
    entry=safe_path(unquote('/'.join(parts[4:])))
    if parts[2]=='tree': entry=entry.rstrip('/')+'/scene.xml'
    if Path(entry).suffix.lower() not in ('.xml','.obj','.stl'):
        raise ValueError('Public entrypoint must be MJCF XML or OBJ/STL mesh')
    repository=owner+'/'+repo
    api='https://api.github.com/repos/'+repository
    commit=json.loads(fetch(api+'/commits/'+revision))['sha']
    if not re.fullmatch('[0-9a-f]{40}',commit): raise ValueError('Invalid pinned commit')
    identity='public_'+hashlib.sha256((repository+'/'+entry).encode()).hexdigest()[:16]
    destination=Path(directory)/identity/commit
    cached=destination/'.loop-assets.json'
    if cached.exists():
        meta=json.loads(cached.read_text());snapshot(destination/'scene.xml')
        return {**meta,'scene':str((destination/'scene.xml').resolve()),'cached':True}
    tree=json.loads(fetch(api+'/git/trees/'+commit+'?recursive=1'))
    if tree.get('truncated'): raise ValueError('Public asset tree truncated')
    prefix=str(Path(entry).parent);prefix='' if prefix=='.' else prefix+'/'
    selected=[e for e in tree['tree'] if e['type']=='blob' and e['path'].startswith(prefix) and
              (Path(e['path']).suffix.lower() in ('.xml','.obj','.stl','.msh','.png','.jpg','.jpeg','.md','.txt') or Path(e['path']).name.upper().startswith(('LICENSE','COPYING','NOTICE')))]
    # Include root license even when importing an object subtree.
    selected += [e for e in tree['tree'] if e['type']=='blob' and '/' not in e['path'] and e not in selected and e['path'].upper().startswith(('LICENSE','COPYING','NOTICE'))]
    if not any(e['path']==entry for e in selected): raise ValueError('Source entrypoint does not exist')
    if any(e.get('mode')=='120000' for e in selected): raise ValueError('Symlink assets are unsupported')
    if len(selected)>1500 or sum(e.get('size',0) for e in selected)>300*1024*1024: raise ValueError('Public asset size limit exceeded')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.download-',dir=destination.parent))
    try:
        hashes={};total=0
        for e in selected:
            path=safe_path(e['path'][len(prefix):] if e['path'].startswith(prefix) else e['path'])
            data=fetch('https://raw.githubusercontent.com/'+repository+'/'+commit+'/'+e['path'],limit=80*1024*1024)
            total+=len(data)
            if total>300*1024*1024: raise ValueError('Public asset size limit exceeded')
            if hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=e['sha']: raise ValueError('Git object checksum mismatch')
            target=temporary/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            hashes[path]=hashlib.sha256(data).hexdigest()
        relative=entry[len(prefix):]
        if relative!='scene.xml':
            root=ET.Element('mujoco')
            if relative.endswith('.xml'): ET.SubElement(root,'include',file=relative)
            else:
                ET.SubElement(ET.SubElement(root,'asset'),'mesh',name='imported_mesh',file=relative)
                body=ET.SubElement(ET.SubElement(root,'worldbody'),'body',name='object')
                ET.SubElement(body,'geom',type='mesh',mesh='imported_mesh')
            data=ET.tostring(root);(temporary/'scene.xml').write_bytes(data);hashes['scene.xml']=hashlib.sha256(data).hexdigest()
        meta={'repository':repository,'commit':commit,'model':identity,'files':hashes,'bytes':total,'source_url':source,'entrypoint':'scene.xml'}
        (temporary/'.loop-assets.json').write_text(json.dumps(meta,indent=2));snapshot(temporary/'scene.xml')
        temporary.rename(destination)
        return {**meta,'scene':str((destination/'scene.xml').resolve()),'cached':False}
    finally:
        if temporary.exists(): shutil.rmtree(temporary)


def resolve(directory, query, source=None, before_web=None):
    if source:
        if source.startswith('https://fuel.gazebosim.org/'):
            from terminal.household_assets import install as install_fuel
            return install_fuel(directory,source)
        return install_public(directory,source)
    findings=search(directory,query,before_web=before_web)
    if findings['matches']:
        match=findings['matches'][0]
        if match.get('local'):
            from toolchain.model_assets import snapshot
            snapshot(match['scene'])
            meta=json.loads(Path(match['scene']).with_name('.loop-assets.json').read_text())
            return {**meta,'scene':match['scene'],'cached':True}
        if match.get('provider')=='fuel':
            from terminal.household_assets import install as install_fuel
            errors=[]
            for candidate in findings['matches']:
                try: return install_fuel(directory,candidate['source_url'])
                except (ValueError,OSError) as exc: errors.append(candidate['model']+': '+str(exc))
            raise ValueError('Fuel models found but import failed: '+'; '.join(errors))
        return install(directory,match['model'])
    # Try a concrete downloadable public entrypoint from the search evidence.
    errors=[]
    for candidate in findings.get('candidates',[]):
        url=candidate.get('url','')
        if re.match(r'https://github.com/[^/]+/[^/]+/(?:blob/[^/]+/.+\.(?:xml|obj|stl)|tree/[^/]+/.+)$',url):
            try: return install_public(directory,url)
            except (ValueError,OSError) as exc: errors.append(str(exc)[:200])
    error=ValueError('未找到可直接导入的模型资产：'+query+'；已搜索本地、官方模型库和公开网页。需要实际MJCF或OBJ/STL链接。')
    error.details={'error':'asset_not_found','message':str(error),'retryable':False,'search':findings,'import_errors':errors}
    raise error


# Retain names while extending their behavior to additive scene operations.
LIBRARY_TOOLS[0]['function']['description']='搜索模型：先本地，再官方Menagerie，缺失时搜索Google Scanned Objects / Open Robotics Fuel，再搜索互联网公开MJCF/网格来源。返回sources资源知识库与许可证。空参数列官方目录。'
LIBRARY_TOOLS[0]['function']['parameters']['properties']={'query':{'type':'string'}}
LIBRARY_TOOLS[1]['function']['description']='加入模型到当前场景并自动重启窗口，保留原有桌椅物品；支持物品检索名，缺失自动搜索下载。support指定桌/椅name自动计算基座高度。'
LIBRARY_TOOLS[1]['function']['parameters']['properties'].update({'name':{'type':'string'},'support':{'type':'string'},'position':{'type':'array','items':{'type':'number'},'minItems':3,'maxItems':3},'source':{'type':'string'}})
LIBRARY_TOOLS.append({'type':'function','function':{'name':'compose_scene','description':'实际组合、添加、移除、移动场景物品并自动重启MuJoCo；保留当前场景，不输出待用户粘贴的XML。',
 'parameters':{'type':'object','properties':{'base':{'type':'string','enum':['current','empty']},'add':{'type':'array','items':{'type':'object'}},'remove':{'type':'array','items':{'type':'string'}},'move':{'type':'array','items':{'type':'object'}},'assumptions':{'type':'array','items':{'type':'string'}},'unsupported':{'type':'array','items':{'type':'string'}}},'additionalProperties':False}}})

_COMPOSITION_ITEM = {'type':'object','properties':{
    'name':{'type':'string'},'kind':{'type':'string','enum':['table','chair','wardrobe','box','sphere','cylinder','asset']},
    'query':{'type':'string'},'source':{'type':'string'},'support':{'type':'string'},
    'position':{'type':'array','items':{'type':'number'},'minItems':3,'maxItems':3},
    'size':{'type':'array','items':{'type':'number'},'description':'box: [full_length,full_width,full_height]; sphere: [radius] (ONE number); cylinder: [radius,full_height] (TWO numbers)'},
    'height':{'type':'number'},'mass':{'type':'number'},'yaw':{'type':'number'},
    'color':{'type':'array','items':{'type':'number'},'minItems':4,'maxItems':4}},'required':['name','kind'],'additionalProperties':False}
LIBRARY_TOOLS[-1]['function']['parameters']['properties']['add']['items']=_COMPOSITION_ITEM
LIBRARY_TOOLS[-1]['function']['parameters']['properties']['move']['items']={'type':'object','properties':{key:_COMPOSITION_ITEM['properties'][key] for key in ('name','support','position','yaw')},'required':['name','support'],'additionalProperties':False}
