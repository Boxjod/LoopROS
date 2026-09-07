"""Export the whitelisted public pages and local assets; no runtime data."""
from pathlib import Path
import argparse
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from _version import __version__

WEBSITE_FILES = ('index.html', 'zh-CN.html', 'install.html', 'style.css', 'site.js', 'favicon.png', 'logo.png', 'workbench.html', 'workbench.css', 'workbench.js', 'three.module.min.js', 'three.LICENSE.txt')


def export_website(output, url, version=__version__):
    output.mkdir(parents=True, exist_ok=True)
    for name in WEBSITE_FILES:
        source = ROOT / ('assets/logo.png' if name == 'logo.png' else
                         'assets/workbench/' + name if name.startswith(('workbench.', 'three.')) else
                         'website/' + name)
        if name.endswith(('.html', '.js')):
            content = source.read_text(encoding='utf-8').replace('../assets/logo.png', 'logo.png')
            content = content.replace('https://loopmaster.box2ai.com/LoopROS', url.rstrip('/'))
            content = re.sub(r'\b0\.0\.1\b', version, content)
            (output / name).write_text(content, encoding='utf-8')
        else:
            shutil.copy2(source, output / name)
    return WEBSITE_FILES


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--url', default='https://loopmaster.box2ai.com/LoopROS')
    args = parser.parse_args()
    export_website(args.output, args.url)
