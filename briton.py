"""Brit On helper: login -> scan -> capture -> apply reviewed answers.
No API bypass, guessed answers, forced completion, or automatic review tests.
"""
import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright, expect

BASE = 'https://learn.onbriton.com'
ROOT = Path(__file__).resolve().parent


def valid_url(url, kind=None):
    p = urlparse(url)
    if p.scheme != 'https' or p.netloc != 'learn.onbriton.com':
        raise ValueError('URL harus HTTPS learn.onbriton.com')
    if kind and not re.fullmatch(kind, p.path):
        raise ValueError('Rute tidak diizinkan untuk perintah ini: ' + p.path)
    return url


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


async def unique(loc):
    if await loc.count() != 1:
        raise RuntimeError(f'Selector harus tepat satu elemen; ditemukan {await loc.count()}')
    await expect(loc).to_be_visible()
    return loc


async def navigate(page, url):
    await page.goto(valid_url(url), wait_until='domcontentloaded')
    if 'login' in page.url.lower() or await page.locator('input[type=password]').count():
        raise RuntimeError('Sesi belum login. Jalankan perintah login terlebih dahulu.')
    await expect(page.locator('body')).to_be_visible()


async def inventory(page, url, output):
    await navigate(page, valid_url(url, r'/course/lesson/\d+'))
    await page.locator('[onclick^="startLesson("]').first.wait_for()
    entries = await page.locator('[onclick^="startLesson("]').evaluate_all('''els => els.map(e => ({
      onclick:e.getAttribute('onclick'), label:e.innerText.trim(),
      context:e.parentElement.innerText.trim()
    }))''')
    items, seen = [], set()
    for e in entries:
        m = re.fullmatch(r'startLesson\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*;?', e['onclick'])
        if not m:
            continue
        lid, gid = m.groups()
        if gid in seen:
            continue
        seen.add(gid)
        items.append({'group': int(gid), 'url': f'{BASE}/course/learn/{lid}?group={gid}',
                      'label': e['label'], 'context': e['context'],
                      'retry': 'retry' in e['label'].lower()})
    save(output, {'lesson': url, 'activities': items})
    print(f'{len(items)} aktivitas disimpan ke {output}. Tidak ada aktivitas dikirim.')


async def capture(page, url, output):
    await navigate(page, valid_url(url, r'/course/learn/\d+'))
    await page.locator('form[id^="miniQuizForm"]').first.wait_for()
    # Only visible learning content/controls; do not export cookies, hidden fields or scripts.
    data = await page.locator('form[id^="miniQuizForm"]').evaluate_all('''forms => forms.map(f => ({
      id:f.id, text:f.innerText,
      controls:Array.from(f.querySelectorAll('input:not([type=hidden]), select, textarea')).map(e=>({
        tag:e.tagName,type:e.type,name:e.name,id:e.id,qid:e.dataset.qid,
        value:e.type==='password'?null:e.value,
        options:e.tagName==='SELECT'?Array.from(e.options).map(o=>({label:o.text,value:o.value})):undefined
      })),
      matches:Array.from(f.querySelectorAll('.LS-lesson-drop-match')).map(e=>({
        qid:e.dataset.qid,prompt:e.querySelector('.LS-lesson-match-text')?.innerText
      })),
      choices:Array.from(f.querySelectorAll('.LS-lesson-drag-match-wrapper,.LS-lesson-drag-item')).map(e=>({
        text:e.innerText,value:e.dataset.value
      }))
    }))''')
    text = await page.locator('body').inner_text()
    save(output, {'url': page.url, 'page_text': text, 'forms': data})
    await page.screenshot(path=str(Path(output).with_suffix('.png')), full_page=True)
    print(f'Soal dan screenshot disimpan: {output}')


async def apply_action(page, action):
    kind = action['type']
    if kind in ('fill', 'check', 'select'):
        # Restrict configurable selectors to the quiz form, never profile/login fields.
        form = await unique(page.locator(action['form']))
        if not (await form.get_attribute('id') or '').startswith('miniQuizForm'):
            raise ValueError('Form harus miniQuizForm')
        loc = await unique(form.locator(action['selector']))
        if kind == 'fill':
            await loc.fill(action['value'])
            await expect(loc).to_have_value(action['value'])
        elif kind == 'check':
            await loc.check()
            await expect(loc).to_be_checked()
        else:
            await loc.select_option(label=action['label'])
            await expect(loc.locator('option:checked')).to_have_text(action['label'])
    elif kind == 'match':
        qid = action['qid']
        if not re.fullmatch(r'q?\d+', qid):
            raise ValueError('qid tidak valid')
        target = await unique(page.locator(f'.LS-lesson-drop-match[data-qid="{qid}"]').filter(
            has=page.locator('.LS-lesson-match-text', has_text=action['question'])))
        pool = page.locator(f'.LS-lesson-drag-match-pool[data-qid="{qid}"]')
        source = await unique(pool.locator('.LS-lesson-drag-match-wrapper').filter(
            has=page.get_by_text(action['answer'], exact=True)))
        await target.scroll_into_view_if_needed()
        await source.drag_to(target)
        dropped = target.locator('.LS-lesson-drop-match-content .LS-lesson-drag-match-wrapper')
        await expect(dropped).to_have_count(1)
        await expect(dropped).to_contain_text(action['answer'])
        await expect(target.locator('.no-answer')).to_be_hidden()
    else:
        raise ValueError('Jenis action tidak didukung: ' + kind)


async def apply_plan(page, filename, submit, allow_retry):
    plan = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
    if plan.get('reviewed') is not True:
        raise ValueError('Periksa jawaban, lalu set reviewed: true sebelum menjalankan.')
    for n, activity in enumerate(plan['activities'], 1):
        url = valid_url(activity['url'], r'/course/learn/\d+')
        if activity.get('retry') is not False and not allow_retry:
            raise ValueError('Status retry belum dipastikan. Set retry:false hanya jika belum dikerjakan, atau gunakan --allow-retry.')
        await navigate(page, url)
        actions = activity.get('actions', [])
        if not actions:
            raise ValueError('Tidak ada jawaban. Berhenti tanpa submit.')
        for action in actions:
            await apply_action(page, action)
        await page.screenshot(path=str(ROOT / f'filled-{n}.png'), full_page=True)
        if not submit:
            print(f'[{n}] Terisi dan dicek; BELUM dikirim. Screenshot: filled-{n}.png')
            await asyncio.to_thread(input, 'Periksa browser; Enter untuk melanjutkan... ')
            continue
        form_ids = {a['form'] for a in actions if 'form' in a}
        gid = re.search(r'(?:^|&)group=(\d+)(?:&|$)', urlparse(url).query)
        if not gid:
            raise ValueError('URL harus menyertakan group')
        form = page.locator('#miniQuizForm' + gid[1])
        await unique(form)
        # Text/input completeness; drop and choice correctness still depends on reviewed plan.
        for inp in await form.locator('input[type=text],textarea').all():
            if await inp.is_visible() and not (await inp.input_value()).strip():
                raise RuntimeError('Ada isian kosong; submit dibatalkan.')
        for slot in await form.locator('.LS-lesson-drop-match-content,.LS-lesson-drop-category-content').all():
            if await slot.is_visible() and not await slot.locator('.LS-lesson-drag-item,.LS-lesson-drag-match-wrapper').count():
                raise RuntimeError('Ada drop slot kosong; submit dibatalkan.')
        button = await unique(form.locator('#quizSubmitBtn' + gid[1]))
        confirm = await asyncio.to_thread(input, f'Kirim jawaban ke {url}? Ketik KIRIM: ')
        if confirm != 'KIRIM':
            raise RuntimeError('Submit dibatalkan pengguna.')
        await button.click()
        # Do not retry submit on timeout: server may already have accepted it.
        await page.screenshot(path=str(ROOT / f'after-submit-{n}.png'), full_page=True)
        print('Submit diklik; periksa hasil browser. Tidak mengklaim skor sebelum hasil terlihat.')
        await asyncio.to_thread(input, 'Periksa hasil; Enter untuk melanjutkan... ')


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', default=str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'BritonHelper' / 'browser-profile'))
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('login')
    scan = sub.add_parser('scan'); scan.add_argument('--url', required=True); scan.add_argument('--out', default='activities.json')
    cap = sub.add_parser('capture'); cap.add_argument('--url', required=True); cap.add_argument('--out', default='questions.json')
    run = sub.add_parser('apply'); run.add_argument('plan'); run.add_argument('--submit', action='store_true'); run.add_argument('--allow-retry', action='store_true')
    args = ap.parse_args()
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(args.profile, headless=False, viewport={'width':1360,'height':900})
        # Keep audio/video and JavaScript: necessary for listening and interactive quizzes.
        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(15000)
        try:
            if args.command == 'login':
                await page.goto(BASE + '/dashboard', wait_until='domcontentloaded')
                await asyncio.to_thread(input, 'Login sendiri di browser. Setelah dashboard muncul, tekan Enter... ')
                if urlparse(page.url).netloc != 'learn.onbriton.com' or 'login' in page.url.lower() or await page.locator('input[type=password]').count():
                    raise RuntimeError('Login belum berhasil diverifikasi.')
                print('Profil browser tersimpan lokal. Jangan dibagikan.')
            elif args.command == 'scan': await inventory(page, args.url, args.out)
            elif args.command == 'capture': await capture(page, args.url, args.out)
            elif args.command == 'apply': await apply_plan(page, args.plan, args.submit, args.allow_retry)
        except Exception:
            await page.screenshot(path=str(ROOT / 'error.png'), full_page=True)
            raise
        finally:
            await context.close()


if __name__ == '__main__':
    asyncio.run(main())
