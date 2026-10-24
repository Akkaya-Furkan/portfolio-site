"""Optional Chromium/axe audit; writes observed results and viewport screenshots."""
import argparse
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright
from build import ROOT


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--axe', type=Path, required=True)
    parser.add_argument('--chromium', default='/usr/bin/google-chrome')
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT/'site')))
    Thread(target=server.serve_forever, daemon=True).start()
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'checks': [], 'console_errors': [], 'http_errors': []}
    screenshot_dir = ROOT/'docs/screenshots'
    screenshot_dir.mkdir(exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=args.chromium, headless=True)
            report['chromium_version'] = browser.version
            for name, width, height in [('desktop', 1440, 1100), ('mobile', 390, 844)]:
                page = browser.new_page(viewport={'width': width, 'height':height}, device_scale_factor=1)
                page.on('pageerror', lambda err: report['console_errors'].append(str(err)))
                page.on('response', lambda response: report['http_errors'].append({'url':response.url,'status':response.status}) if response.status >= 400 else None)
                for path in sorted((ROOT/'site').glob('*.html')):
                    response = page.goto(f'http://127.0.0.1:{server.server_port}/{path.name}')
                    assert response.status == 200
                    no_overflow = page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    assert no_overflow, (name, path.name)
                    page.add_script_tag(path=str(args.axe.resolve()))
                    if path.name == 'index.html':
                        page.keyboard.press('Tab')
                        assert page.locator(':focus').inner_text() == 'Skip to content'
                        assert page.locator(':focus').evaluate('(e) => e.getBoundingClientRect().top >= 0')
                        focus = page.locator(':focus').evaluate('(e) => getComputedStyle(e).outlineStyle')
                        assert focus != 'none'
                        page.locator(':focus').evaluate('(e) => e.blur()')
                        page.screenshot(path=str(screenshot_dir/f'{name}.png'))
                        page.locator('details').evaluate_all('(elements) => elements.forEach(e => e.open = true)')
                    results = page.evaluate('''async () => await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa','best-practice']}})''')
                    report['axe_version'] = results['testEngine']['version']
                    report['checks'].append({'viewport':name,'width':width,'page':path.name,'no_horizontal_overflow':no_overflow,
                                              'violations':results['violations'], 'incomplete_count':len(results['incomplete']),
                                              'passed_rules':len(results['passes'])})
                page.close()
            browser.close()
    finally:
        server.shutdown()
    (ROOT/'docs/browser-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    violations = sum(len(c['violations']) for c in report['checks'])
    print(f"Browser pages/viewports: {len(report['checks'])}; axe violations: {violations}; HTTP errors: {len(report['http_errors'])}; screenshots: 2")
    assert violations == 0 and not report['console_errors'] and not report['http_errors']


if __name__ == '__main__':
    main()
