"""Official Fuel catalogue and bounded single-link OBJ/STL to MJCF import."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
from urllib.parse import quote, urlsplit, unquote
import xml.etree.ElementTree as ET
import zipfile

API = 'https://fuel.gazebosim.org/1.0/'
SOURCES = [
    {'name':'Google Scanned Objects', 'url':'https://app.gazebosim.org/GoogleResearch/fuel/collections/Scanned%20Objects', 'scope':'Scanned household items; not an exhaustive furniture library; rigid scans have no articulated doors.', 'import':'Fuel single-link OBJ/STL'},
    {'name':'Open Robotics Fuel', 'url':'https://app.gazebosim.org/OpenRobotics', 'scope':'Furniture, rooms and simulation props. Check each model license.', 'import':'Fuel single-link OBJ/STL; complex SDF rejected explicitly'},
    {'name':'MuJoCo Menagerie', 'url':'https://github.com/google-deepmind/mujoco_menagerie', 'scope':'Articulated robots with MJCF actuators', 'import':'Pinned GitHub bundles'},
    {'name':'RoboCasa', 'url':'https://github.com/robocasa/robocasa', 'scope':'Articulated kitchen fixtures; requires its fixture composition and asset pipeline', 'import':'Reference; no generic fixture converter'},
    {'name':'PartNet-Mobility / SAPIEN', 'url':'https://sapien.ucsd.edu/', 'scope':'Articulated furniture; dataset access and URDF conversion required', 'import':'Reference; not automatically downloaded'},
]
ALIASES={'衣柜':'wardrobe','柜子':'cabinet','橱柜':'cabinet','杯子':'mug','马克杯':'mug','家具':'furniture','日常物品':'household','google scanned objects':'mug','gso':'mug'}


def search(query):
    from loop_robot.terminal.model_library import fetch
    term=ALIASES.get(query.lower(),query.lower())
    rows=json.loads(fetch(API+'models?q='+quote(term)+'&per_page=100'))
    matches=[]
    for row in rows:
        if row.get('owner') not in ('GoogleResearch','OpenRobotics'): continue
        # Full-text description hits can be shoes mentioning a wardrobe.
        name=row['name']
        if not all(t in name.lower().replace('_',' ') for t in term.split()): continue
        matches.append({'model':name, 'provider':'fuel','owner':row['owner'], 'local':False,
                        'source_url':API+quote(row['owner'])+'/models/'+quote(name),
                        'license':row.get('license_name'), 'license_url':row.get('license_url')})
    return matches


def convert(files):
    """Intentionally narrow SDF subset; reject transforms/joints, never flatten them."""
    root=ET.fromstring(files['model.sdf'])
    model=root.find('model')
    if model is None or len(model.findall('link'))!=1 or model.findall('joint'):
        raise ValueError('Fuel importer requires a single rigid link; articulated SDF needs a dedicated converter')
    link=model.find('link')
    for parent in (model,link,*link.findall('visual'),*link.findall('collision')):
        pose=parent.find('pose')
        if pose is not None and (pose.attrib or any(float(v)!=0 for v in (pose.text or '').split())):
            raise ValueError('Non-identity SDF poses require a dedicated converter')
    visual=link.find('visual/geometry/mesh')
    if visual is None or len(link.findall('visual'))!=1:
        raise ValueError('Fuel importer requires one OBJ/STL visual mesh')
    uri=visual.findtext('uri','')
    if uri.startswith('model://'):
        uri=uri[len('model://'):].split('/',1)[-1]
    from loop_robot.toolchain.model_assets import safe_path
    uri=safe_path(uri)
    if uri not in files or Path(uri).suffix.lower() not in ('.obj','.stl'):
        raise ValueError('Fuel mesh must be an included OBJ/STL file')
    scale=[float(v) for v in visual.findtext('scale','1 1 1').split()]
    import math
    if len(scale)!=3 or any(not math.isfinite(v) or v<=0 for v in scale): raise ValueError('Invalid mesh scale')
    xml=ET.Element('mujoco')
    asset=ET.SubElement(xml,'asset')
    ET.SubElement(asset,'mesh',name='scan',file=uri,scale=' '.join(map(str,scale)))
    textures=[p for p in files if p.lower().endswith('.png') and not p.startswith('thumbnails/')]
    material={}
    if len(textures)==1:
        ET.SubElement(asset,'texture',name='scan_texture',type='2d',file=textures[0])
        ET.SubElement(asset,'material',name='scan_material',texture='scan_texture')
        material={'material':'scan_material'}
    body=ET.SubElement(ET.SubElement(xml,'worldbody'),'body',name='object')
    fixed=model.findtext('static','false').strip().lower() in ('true','1')
    if not fixed: ET.SubElement(body,'freejoint',name='free')
    mass=float(link.findtext('inertial/mass','0.2'))
    if not math.isfinite(mass) or not 0<mass<=1000: raise ValueError('Invalid source mass')
    ET.SubElement(body,'geom',name='scan',type='mesh',mesh='scan',mass=str(mass),**material)
    return ET.tostring(xml), {'collision':'MuJoCo convex mesh hull approximation; concave cavities not preserved',
                            'mass_kg':mass,'mass_source':'SDF' if link.find('inertial/mass') is not None else 'assumed',
                            'articulated':False,'fixed':fixed,'textures_loaded':len(textures)==1}


def install(directory, source):
    from loop_robot.terminal.model_library import fetch, LOCK
    from loop_robot.toolchain.model_assets import safe_path, snapshot
    url=urlsplit(source)
    parts=url.path.strip('/').split('/')
    if url.scheme!='https' or url.netloc!='fuel.gazebosim.org' or url.query or url.fragment or len(parts)!=4 or parts[0]!='1.0' or parts[2]!='models' or parts[1] not in ('GoogleResearch','OpenRobotics'):
        raise ValueError('Use the exact official Fuel model source_url returned by model_library')
    name=unquote(parts[3]); safe_path(name)
    identity='fuel_'+parts[1].lower()+'_'+hashlib.sha256(source.encode()).hexdigest()[:12]
    with LOCK:
        cached=sorted((Path(directory)/identity).glob('*/.loop-assets.json'))
        if cached:
            meta=json.loads(cached[-1].read_text()); scene=cached[-1].parent/'scene.xml'; snapshot(scene)
            return {**meta,'scene':str(scene.resolve()),'cached':True}
        metadata=json.loads(fetch(source))
        blob=fetch(source+'/tip/'+quote(name)+'.zip',limit=80*1024*1024)
        digest=hashlib.sha256(blob).hexdigest()
        files={}
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            entries=archive.infolist()
            if len(entries)>1500 or sum(x.file_size for x in entries)>300*1024*1024: raise ValueError('Fuel archive size limit exceeded')
            for entry in entries:
                if entry.is_dir(): continue
                path=safe_path(entry.filename)
                if (entry.external_attr>>16)&0o170000==0o120000: raise ValueError('Symlink in Fuel archive')
                if path in files: raise ValueError('Duplicate Fuel archive path')
                if Path(path).suffix.lower() in ('.sdf','.config','.obj','.stl','.mtl','.png','.jpg','.txt','.pbtxt') or Path(path).name.upper().startswith(('LICENSE','NOTICE','COPYING')):
                    files[path]=archive.read(entry)
        xml, assumptions=convert(files)
        files['scene.xml']=xml
        files['SOURCE.json']=json.dumps(metadata,ensure_ascii=False,indent=2).encode()
        destination=Path(directory)/identity/digest
        destination.parent.mkdir(parents=True,exist_ok=True)
        temp=Path(tempfile.mkdtemp(prefix='.download-',dir=destination.parent))
        try:
            for path,data in files.items():
                target=temp/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            meta={'model':name,'provider':'fuel','source_url':source,'archive_sha256':digest,
                  'license':metadata.get('license_name'),'license_url':metadata.get('license_url'),
                  'files':{p:hashlib.sha256(d).hexdigest() for p,d in files.items()},'assumptions':assumptions}
            (temp/'.loop-assets.json').write_text(json.dumps(meta,indent=2))
            content,assets,_=snapshot(temp/'scene.xml')
            import mujoco
            mujoco.MjModel.from_xml_string(content.decode(),assets=assets)
            temp.rename(destination)
            return {**meta,'scene':str((destination/'scene.xml').resolve()),'cached':False}
        finally:
            if temp.exists(): shutil.rmtree(temp)
