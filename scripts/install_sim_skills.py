"""Install maintained Loop simulation skill packages without overwriting user files."""
from pathlib import Path
import shutil
import sys


def install(destination):
    source=Path(__file__).resolve().parents[1]/'configs'/'skills'
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    result=[]
    for package in sorted(source.iterdir()):
        if not (package/'SKILL.md').is_file(): continue
        target=destination/package.name
        if target.exists():
            result.append({'name':package.name,'status':'preserved_existing','path':str(target)})
        else:
            shutil.copytree(package,target)
            result.append({'name':package.name,'status':'installed','path':str(target)})
    return result


if __name__=='__main__':
    import argparse,json
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from launcher import _bootstrap
    _bootstrap(legacy=False)
    from loop_robot.terminal.home import loop_home
    parser=argparse.ArgumentParser();parser.add_argument('--destination',type=Path,default=loop_home()/'skills')
    print(json.dumps(install(parser.parse_args().destination),ensure_ascii=False,indent=2))
