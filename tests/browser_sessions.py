"""Optional browser regressions for stale sessions; all model API requests are mocked."""
import argparse
import json
from pathlib import Path


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser-path', required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--base-url', default='http://localhost:8422')
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    jid = 'a' * 32
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=args.browser_path)
        page = browser.new_page()
        page.add_init_script(f"sessionStorage.setItem('ledger-job','{jid}')")
        page.route('**/api/briefs/**', lambda r: r.fulfill(status=404, json={'error': 'Brief not found or expired.'}))
        page.goto(args.base_url)
        page.locator('#upload-error').wait_for(state='visible')
        assert 'upload your files again' in page.locator('#upload-error').inner_text()
        assert page.evaluate("() => sessionStorage.getItem('ledger-job')") is None
        page.locator('.example-card').first.get_by_role('button', name='Load example').click()
        page.locator('#generate:not([disabled])').wait_for()
        repo = page.locator('.project-repo')
        assert repo.get_attribute('href') == 'https://github.com/aka-vm/servicer-report-reader'
        page.close()

        page = browser.new_page()
        page.add_init_script(f"sessionStorage.setItem('ledger-job','{jid}')")
        count = [0]
        def route_api(route):
            if route.request.url.endswith('/ask'):
                route.fulfill(status=404, json={'error': 'Brief not found or not ready.'})
            else:
                count[0] += 1
                if count[0] == 1:
                    route.fulfill(status=503, json={'error': 'Temporary failure'})
                else:
                    route.fulfill(json={'status': 'done', 'report': report})
        page.route('**/api/briefs/**', route_api)
        page.goto(args.base_url)
        page.locator('#workspace').wait_for(state='visible')
        assert page.evaluate("() => sessionStorage.getItem('ledger-job')") == jid
        page.locator('#question').fill('What is the cash balance?')
        page.locator('#ask').click()
        page.get_by_text('This brief is no longer available on the server.', exact=False).wait_for()
        assert page.locator('#report h1').inner_text().strip()
        assert report['title'] in page.locator('#report').inner_text()
        assert page.locator('#ask').is_disabled()
        with page.expect_download() as download:
            page.locator('#download').click()
        assert download.value.suggested_filename.endswith('.json')
        page.locator('#new-brief').click()
        page.locator('#welcome').wait_for(state='visible')
        browser.close()
    print('Passed: stale-ID recovery, transient reconnect, expired follow-up with saved report, GitHub repo link.')


if __name__ == '__main__':
    main()
