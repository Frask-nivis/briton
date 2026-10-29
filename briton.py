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
from quiz_checks import format_issues, validate_complete, wait_for_feedback, SNAPSHOT_JS
from progress import Checkpoint, classify, should_block_resume
from existing_answers import inspect_all, inspect_action
from login_helper import load_credentials, ensure_signed_in, login_wall, trusted_origin

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
    if await login_wall(page):
        await ensure_signed_in(page)
        await page.goto(valid_url(url), wait_until='domcontentloaded')
        if await login_wall(page):
            raise RuntimeError('Sesi masih belum login; proses dihentikan tanpa mencoba ulang.')
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
            for warning in format_issues(action['value'], action.get('format')):
                print('PERIKSA FORMAT:', warning)
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


async def apply_plan(page, filename, submit, allow_retry, checkpoint_path=None, status_only=False):
    plan = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
    if plan.get('reviewed') is not True:
        raise ValueError('Periksa jawaban, lalu set reviewed: true sebelum menjalankan.')
    checkpoint = Checkpoint(checkpoint_path or str(Path(filename).with_suffix('.checkpoint.json')), plan)
    print('Checkpoint:', checkpoint.path)
    for n, activity in enumerate(plan['activities'], 1):
        url = valid_url(activity['url'], r'/course/learn/\d+')
        try:
            gid = re.search(r'(?:^|&)group=(\d+)(?:&|$)', urlparse(url).query)
            if not gid:
                raise ValueError('URL harus menyertakan group')
            form_id = 'miniQuizForm' + gid[1]
            await navigate(page, url)
            form = await unique(page.locator('#' + form_id))
            live = classify(await form.evaluate(SNAPSHOT_JS), await form.inner_text())
            previous = checkpoint.state(url)
            print(f'[{n}] {live}: {url}')
            if live == 'graded':
                checkpoint.record(url, 'graded', 'Feedback penilaian terlihat di form situs')
                print('Dilewati: sudah dinilai. Tidak menekan Retry atau Submit.')
                continue
            if should_block_resume(previous, live):
                raise RuntimeError('Submit sebelumnya belum pasti. Periksa hasil di situs; tidak akan kirim ulang.')
            if previous == 'graded':
                raise RuntimeError('Checkpoint mencatat sudah dinilai tetapi feedback situs tidak terlihat; perlu pemeriksaan.')
            if live in ('uncertain','unsupported'):
                raise RuntimeError('Status/jenis aktivitas belum dapat dipastikan dari form yang terlihat')
            if status_only:
                checkpoint.record(url, live, 'Inspeksi status saja; tidak ada pengisian atau submit')
                continue
            # Retry is never evidence of completion; retain the explicit retry permission gate.
            if activity.get('retry') is not False and not allow_retry:
                raise RuntimeError('Status retry belum dipastikan; gunakan --allow-retry jika diizinkan.')
            actions = activity.get('actions', [])
            if not actions:
                raise ValueError('Tidak ada jawaban terverifikasi untuk aktivitas ini')
            for action in actions:
                if action['type'] == 'fill':
                    for warning in format_issues(action['value'], action.get('format')):
                        print('PERIKSA FORMAT:', warning)
            states = await inspect_all(page, actions, form_id)
            checkpoint.record(url, 'filling', 'Semua action lolos pemeriksaan konflik awal')
            for action, state in zip(actions, states):
                # Recheck immediately before a write in case the user changed the page.
                current = await inspect_action(page, action, form_id)
                if current != 'same':
                    await apply_action(page, action)
            await validate_complete(form)
            checkpoint.record(url, 'filled_unsubmitted', 'Semua isian lengkap; belum dikirim')
            await page.screenshot(path=str(ROOT / f'filled-{n}.png'), full_page=True)
            if not submit:
                print(f'[{n}] Terisi dan dicek; BELUM dikirim. Jalankan lagi dengan --submit untuk melanjutkan.')
                return  # Do not navigate away from unsent work.
            if re.search(r'Your answer\s*:', await form.inner_text()):
                raise RuntimeError('Feedback sudah terlihat; submit dibatalkan.')
            button = await unique(form.locator('#quizSubmitBtn' + gid[1]))
            confirm = await asyncio.to_thread(input, f'Kirim jawaban ke {url}? Ketik KIRIM: ')
            if confirm != 'KIRIM':
                print('Submit dibatalkan. Checkpoint terisi-belum-dikirim dipertahankan.')
                return
            await inspect_all(page, actions, form_id)
            await validate_complete(form)
            if re.search(r'Your answer\s*:', await form.inner_text()):
                raise RuntimeError('Aktivitas sudah memiliki feedback; submit dibatalkan.')
            report_path = ROOT / f'after-submit-{n}.json'
            # Persist before the click: a crash between click and feedback must not resend.
            checkpoint.record(url, 'submission_pending', 'Konfirmasi KIRIM diterima; hasil belum dipastikan')
            try:
                await button.click()
                report = await wait_for_feedback(page, form_id)
            except Exception as exc:
                checkpoint.record(url, 'submission_unknown', 'Hasil klik/feedback belum pasti; jangan kirim ulang')
                save(report_path, {'url':url, 'status':'unknown', 'error_type':type(exc).__name__})
                raise RuntimeError('Hasil submit belum pasti; proses berhenti tanpa kirim ulang.') from exc
            report.update({'url':page.url, 'status':'feedback_received'})
            save(report_path, report)
            if classify(await form.evaluate(SNAPSHOT_JS), await form.inner_text()) != 'graded':
                checkpoint.record(url, 'submission_unknown', 'Feedback ada tetapi status penilaian belum pasti')
                raise RuntimeError('Feedback belum dapat dipastikan sebagai hasil penilaian')
            checkpoint.record(url, 'graded', 'Feedback hasil submit telah terlihat dan tersimpan')
            await page.screenshot(path=str(ROOT / f'after-submit-{n}.png'), full_page=True)
            for item in report['feedback']:
                print(item['status'] + ': ' + item['text'])
            await asyncio.to_thread(input, 'Periksa feedback; Enter untuk lanjut ke aktivitas berikutnya... ')
        except (Exception, KeyboardInterrupt):
            # Preserve critical evidence; a generic error must never clear uncertain submission.
            if checkpoint.state(url) not in ('submission_pending','submission_unknown','graded'):
                checkpoint.record(url, 'blocked', 'Proses terhalang; periksa pesan terminal dan situs sebelum melanjutkan')
            print('Berhenti. Checkpoint tersimpan:', checkpoint.path)
            raise


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', default=str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'BritonHelper' / 'browser-profile'))
    ap.add_argument('--credentials-file', help='File JSON kredensial lokal; jangan commit file ini')
    sub = ap.add_subparsers(dest='command', required=True)
    login = sub.add_parser('login')
    login.add_argument('--manual', action='store_true', help='Login sendiri tanpa membaca kredensial otomatis')
    scan = sub.add_parser('scan'); scan.add_argument('--url', required=True); scan.add_argument('--out', default='activities.json')
    cap = sub.add_parser('capture'); cap.add_argument('--url', required=True); cap.add_argument('--out', default='questions.json')
    run = sub.add_parser('apply'); run.add_argument('plan'); run.add_argument('--submit', action='store_true'); run.add_argument('--allow-retry', action='store_true')
    run.add_argument('--checkpoint', help='Path checkpoint, terikat pada isi file jawaban')
    run.add_argument('--status-only', action='store_true', help='Cek status tanpa mengisi atau submit')
    args = ap.parse_args()
    if args.command == 'apply' and args.status_only and args.submit:
        ap.error('--status-only tidak boleh digabung --submit')
    if args.credentials_file:
        os.environ['BRITON_CREDENTIALS_FILE'] = str(Path(args.credentials_file).expanduser())
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(args.profile, headless=False, viewport={'width':1360,'height':900})
        # Keep audio/video and JavaScript: necessary for listening and interactive quizzes.
        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(15000)
        try:
            if args.command == 'login':
                await page.goto(BASE + '/dashboard', wait_until='domcontentloaded')
                if not trusted_origin(page.url):
                    raise RuntimeError('Halaman login bukan origin Brit On yang diizinkan.')
                if await login_wall(page):
                    if not args.manual and load_credentials(args.credentials_file) is not None:
                        await ensure_signed_in(page, args.credentials_file)
                        print('Login otomatis berhasil diverifikasi.')
                    else:
                        await asyncio.to_thread(input, 'Login sendiri di browser. Setelah dashboard muncul, tekan Enter... ')
                if not trusted_origin(page.url) or await login_wall(page):
                    raise RuntimeError('Login belum berhasil diverifikasi.')
                print('Profil browser tersimpan lokal. Jangan dibagikan.')
            elif args.command == 'scan': await inventory(page, args.url, args.out)
            elif args.command == 'capture': await capture(page, args.url, args.out)
            elif args.command == 'apply': await apply_plan(page, args.plan, args.submit, args.allow_retry, args.checkpoint, args.status_only)
        except Exception:
            # Do not capture filled login forms or credential-related pages.
            if trusted_origin(page.url) and not await login_wall(page):
                await page.screenshot(path=str(ROOT / 'error.png'), full_page=True)
            raise
        finally:
            await context.close()


if __name__ == '__main__':
    asyncio.run(main())
