"""Optional browser QA (Playwright is a development-only dependency).

python tests/browser_smoke.py --browser-path '/path/to/chromium' --live
python tests/browser_smoke.py --browser-path '/path/to/chromium' --report /tmp/report.json
"""
import argparse
import json
import tempfile
from pathlib import Path


def main():
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://localhost:8422')
    parser.add_argument('--browser-path')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if not args.live and not args.report:
        parser.error('Choose --live or --report <generated report JSON>.')
    output = Path(tempfile.mkdtemp(prefix='ledger-browser-'))
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, **({'executable_path': args.browser_path} if args.browser_path else {}))
        page = browser.new_page(viewport={'width': 1440, 'height': 1050})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(args.base_url)
        assert page.locator('#generate').is_disabled()
        for theme in ['dark', 'light', 'auto']:
            page.locator('#theme-select').select_option(theme)
            if theme != 'auto':
                assert page.locator('html').get_attribute('data-theme') == theme
        assert page.locator('.project-repo').get_attribute('href') == 'https://github.com/aka-vm/financial-doc-reader'
        page.screenshot(path=str(output / 'home.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert not page.evaluate('() => document.documentElement.scrollWidth > innerWidth')
        page.screenshot(path=str(output / 'mobile.png'), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1050})
        if not args.live:
            report = json.loads(args.report.read_text())
            def route_api(route):
                if route.request.method == 'POST' and route.request.url.endswith('/api/briefs'):
                    route.fulfill(json={'id': 'a' * 32}, status=202)
                elif route.request.url.endswith('/ask'):
                    route.fulfill(json={'id': 'b' * 32}, status=202)
                elif '/answers/' in route.request.url:
                    route.fulfill(json={'status': 'done', 'result': {'answer': 'A source-backed answer.', 'evidence': [report['facts'][0]['id']]}})
                else:
                    route.fulfill(json={'status': 'done', 'report': report})
            page.route('**/api/briefs**', route_api)
        page.locator('.example-card').first.wait_for()
        assert page.locator('.example-card').count() == 6
        assert page.locator('#examples-count').inner_text() == '6 random'
        types = page.locator('.example-card .example-tag:first-child').all_text_contents()
        assert len(set(types)) == 6
        for card in page.locator('.example-card').all():
            assert 1 <= card.locator('.example-tag').count() <= 3
        page.get_by_role('button', name='Show another six').click()
        assert page.locator('.example-card').count() == 6
        page.locator('.example-card').first.get_by_role('button', name='Load example').click()
        page.locator('#generate:not([disabled])').wait_for()
        page.locator('#generate').click()
        page.locator('#workspace:not([hidden]), #upload-error:not([hidden])').first.wait_for(state='visible', timeout=300000)
        assert page.locator('#workspace').is_visible(), page.locator('#upload-error').inner_text()
        page.locator('.citation').first.click()
        assert page.locator('#evidence-dialog').is_visible()
        page.locator('#close-evidence').click()
        page.locator('#question').fill('What explains the decline in operating cash flow?')
        page.locator('#ask').click()
        page.locator('#ask:not([disabled])').wait_for(state='visible', timeout=180000)
        assert page.locator('#answer').inner_text().strip()
        with page.expect_download() as download:
            page.locator('#download').click()
        download.value.save_as(output / 'brief.json')
        page.screenshot(path=str(output / 'brief.png'), full_page=True)
        page.pdf(path=str(output / 'brief.pdf'), print_background=True, prefer_css_page_size=True)
        assert len(PdfReader(output / 'brief.pdf').pages) >= 1
        page.set_viewport_size({'width': 390, 'height': 844})
        assert not page.evaluate('() => document.documentElement.scrollWidth > innerWidth')
        assert not errors, errors
        browser.close()
    print(f'Browser checks passed. Artifacts: {output}')


if __name__ == '__main__':
    main()
