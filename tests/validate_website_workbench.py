"""Real Chrome + isolated local server. Requires optional playwright and Chrome."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def validate(output):
    from playwright.sync_api import sync_playwright
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='loop-web-browser-') as state:
        server=subprocess.Popen([sys.executable,'-m','loop_robot.terminal.web_workbench','--port','0','--state-dir',state],
                                cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            line=server.stdout.readline().strip()
            if not line.startswith('Loop workbench: '): raise RuntimeError('Local server failed: '+server.stderr.read())
            url=line.split('Loop workbench: ',1)[1]
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,
                    args=['--no-sandbox','--no-proxy-server','--enable-unsafe-swiftshader'])
                page=browser.new_page(viewport={'width':1512,'height':982},device_scale_factor=1)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url)
                page.wait_for_function("() => document.getElementById('connection').textContent.includes('已连接')")
                page.screenshot(path=str(output/'initial.png'))
                page.locator('#quick-room').click()
                page.wait_for_function("() => document.querySelectorAll('.object-row').length===10 && document.getElementById('busy-label').textContent==='就绪'")
                page.locator('#box-form button').click()
                page.wait_for_function("() => document.querySelectorAll('.object-row').length===11 && document.getElementById('busy-label').textContent==='就绪'")
                page.locator('.object-row',has_text='cube').click()
                page.locator('#move-position').fill('0.6, 0, 0.8');page.locator('#move-form button').first.click()
                page.wait_for_function("() => document.getElementById('busy-label').textContent==='就绪'")
                page.screenshot(path=str(output/'desktop.png'))
                page.locator('[data-panel=cameras]').click()
                page.locator('#camera-width').fill('320');page.locator('#camera-height').fill('240')
                page.locator('#camera-form button').click()
                page.wait_for_function("() => document.querySelectorAll('#camera-list input').length===1 && document.getElementById('busy-label').textContent==='就绪'")
                page.locator('#capture').click();page.wait_for_selector('.capture-card img')
                page.wait_for_function("() => document.querySelector('.capture-card img').complete && document.querySelector('.capture-card img').naturalWidth>0")
                page.screenshot(path=str(output/'camera.png'))
                page.locator('[data-panel=learning]').click();page.locator('#task-target').fill('0.6, 0, 0.8')
                assert page.locator('#task-form').evaluate('(form) => form.checkValidity()')
                page.locator('#task-form button').click()
                page.wait_for_function("() => document.getElementById('evaluation').textContent.includes('reach') && document.getElementById('busy-label').textContent==='就绪'")
                page.locator('#record').click();page.wait_for_selector('#approval-dialog[open]')
                page.locator('#approve').click();page.wait_for_selector('.dataset a')
                download_url=page.locator('.dataset a').get_attribute('href')
                assert page.request.get(url.replace('/workbench.html',download_url)).body().startswith(b'\x89HDF')
                page.screenshot(path=str(output/'dataset.png'))
                page.locator('#layout-tab').click();page.set_viewport_size({'width':390,'height':844})
                page.screenshot(path=str(output/'mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'Mobile horizontal overflow'
                assert not errors,errors
                (output/'browser-result.json').write_text(json.dumps({'page_errors':errors,'room_objects':10,
                    'box_added_and_moved':True,'actual_camera_png':True,'dataset_approved_and_downloaded':True,
                    'mobile_width':390,'horizontal_overflow':False},indent=2))
                browser.close()
        finally:
            server.terminate()
            try: server.wait(timeout=15)
            except subprocess.TimeoutExpired: server.kill();server.wait()


if __name__=='__main__':
    validate(ROOT/'artifacts/website-workbench')
