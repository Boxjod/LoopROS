"""Check exported or live bilingual install guides using headless Chrome."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading


def validate(url, output):
    from playwright.sync_api import sync_playwright
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True,
                                    args=['--no-sandbox', '--no-proxy-server'])
        try:
            for language in ('index.html', 'zh-CN.html'):
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                response = page.goto(url.rstrip('/') + '/' + language)
                assert response.status == 200
                for board in ('rpi', 'orange', 'jetson'):
                    page.locator('[data-platform=' + board + ']').click()
                    assert page.locator('#command').inner_text().endswith(' -s -- --terminal-only')
                    assert page.locator('#light').is_disabled()
                guide = page.locator('#platform-guide')
                assert 'ESP32-C3' in guide.inner_text()
                assert 'Rust' in guide.inner_text() and 'Arduino C++' in guide.inner_text()
                assert 'pio run -d firmware/esp32 -e esp32c3' in guide.inner_text()
                assert 'UNO R3' in guide.inner_text()
                page.locator('[data-platform=esp32c3]').click()
                assert 'pio run -d firmware/esp32 -e esp32c3' in page.locator('#command').inner_text()
                assert '--terminal-only' not in page.locator('#command').inner_text()
                assert page.locator('#terminal-option').is_hidden()
                assert 'secrets.h' in page.locator('#after-install').inner_text()
                assert page.locator('#firmware-guide-link a').get_attribute('href') == '#esp32-guide'
                assert page.locator('#esp32-guide').count() == 1
                for width in (1440, 390, 320):
                    page.set_viewport_size({'width': width, 'height': 1000})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (language, width)
                    page.screenshot(path=str(output / (language + '-' + str(width) + '.png')), full_page=True)
                assert not errors, errors
                checks.append({'page': language, 'board_commands': 3, 'esp32c3_selector': True, 'widths': [1440, 390, 320], 'page_errors': errors})
                page.close()
        finally:
            browser.close()
    (output / 'result.json').write_text(json.dumps({'url': url, 'checks': checks}, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--bundle', type=Path)
    source.add_argument('--url')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.url:
        validate(args.url, args.output)
        return
    handler = partial(SimpleHTTPRequestHandler, directory=str(args.bundle.resolve()))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        validate('http://127.0.0.1:' + str(server.server_port), args.output)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


if __name__ == '__main__':
    main()
