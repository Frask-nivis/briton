"""Read-only quiz checks. Never repair answers or resend a submission."""
import re


def format_issues(value, policy=None):
    """Return warnings without changing even one character of the answer."""
    if not isinstance(value, str):
        raise ValueError('Jawaban fill harus string')
    policy = policy or {}
    allowed = {'expected_literal', 'terminal_punctuation'}
    if set(policy) - allowed:
        raise ValueError('Aturan format tidak dikenal')
    issues = []
    if value != value.strip():
        issues.append('Ada spasi di awal/akhir jawaban')
    if any(ord(c) < 32 for c in value):
        issues.append('Ada karakter kontrol/baris baru; periksa format soal')
    if any(c in value for c in '’‘“”'):
        issues.append('Ada tanda kutip melengkung; situs mungkin membandingkan teks secara persis')
    if value.endswith(('.', '?', '!')):
        issues.append('Ada tanda baca akhir; pastikan memang diminta soal/kunci')
    if 'expected_literal' in policy and value != policy['expected_literal']:
        raise ValueError('Jawaban tidak sama persis dengan format.expected_literal yang diperiksa')
    terminal = policy.get('terminal_punctuation')
    if terminal not in (None, 'preserve', 'none', '.', '?', '!'):
        raise ValueError('terminal_punctuation harus preserve, none, ., ?, atau !')
    if terminal == 'none' and value.rstrip().endswith(('.', '?', '!')):
        raise ValueError('Aturan soal melarang tanda baca akhir; perbaiki file jawaban secara manual')
    if terminal in ('.', '?', '!') and not value.endswith(terminal):
        raise ValueError('Tanda baca akhir tidak sesuai aturan soal; perbaiki file jawaban secara manual')
    return issues


def completeness_errors(snapshot):
    errors = []
    radios = {}
    for c in snapshot['controls']:
        if not c['visible'] or c.get('disabled'):
            continue
        label = c.get('name') or c.get('id') or '(tanpa nama)'
        kind = c['type']
        if kind == 'radio':
            if not c.get('name'):
                errors.append('Radio tanpa name tidak bisa divalidasi dengan aman')
            else:
                radios.setdefault(c['name'], []).append(c)
        elif c['tag'] == 'SELECT':
            selected = c.get('selected', [])
            if not selected or any(o['placeholder'] or not o['value'].strip() for o in selected):
                errors.append('Dropdown belum terisi: ' + label)
        elif kind in ('text', 'textarea') and not c.get('value', '').strip():
            errors.append('Isian kosong: ' + label)
        elif kind == 'checkbox' and c.get('required') and not c.get('checked'):
            errors.append('Checkbox wajib belum dipilih: ' + label)
    for name, items in radios.items():
        if sum(bool(i.get('checked')) for i in items) != 1:
            errors.append('Grup radio harus punya tepat satu pilihan: ' + name)
    if snapshot.get('empty_slots', 0):
        errors.append('Ada drop slot kosong; submit dibatalkan')
    return errors


SNAPSHOT_JS = r'''form => {
  const visible = e => !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  return {
    controls: Array.from(form.querySelectorAll('input:not([type=hidden]),select,textarea')).map(e => ({
      tag:e.tagName, type:e.type, name:e.name, id:e.id, visible:visible(e),
      disabled:e.matches(':disabled'), required:e.required, checked:e.checked,
      value:e.value || '',
      selected:e.tagName==='SELECT' ? Array.from(e.selectedOptions).map(o => ({
        value:o.value, placeholder:o.disabled || o.hidden || !o.text.trim() || /^(select an answer|choose(?: an? (?:answer|option))?|pilih(?: jawaban)?)$/i.test(o.text.trim())
      })) : []
    })),
    empty_slots:Array.from(form.querySelectorAll('.LS-lesson-drop-match-content,.LS-lesson-drop-category-content'))
      .filter(e=>visible(e) && !e.querySelector('.LS-lesson-drag-item,.LS-lesson-drag-match-wrapper')).length
  };
}'''


async def validate_complete(form):
    errors = completeness_errors(await form.evaluate(SNAPSHOT_JS))
    if errors:
        raise RuntimeError('\n'.join(errors))


def parse_feedback(text):
    """Report only explicit feedback; unknown is never counted as correct."""
    results = []
    lines = text.splitlines()
    for index, raw in enumerate(lines):
        line = raw.strip()
        if 'Your answer:' not in line:
            continue
        tail = line.split('Your answer:', 1)[1].strip()
        if not tail:
            following = next((v.strip() for v in lines[index + 1:] if v.strip()), '')
            if re.match(r'(?:Incorrect|Correct)\b', following, re.I):
                tail = following
                line += ' ' + following
        state = 'unknown'
        if re.match(r'Incorrect\b', tail, re.I):
            state = 'incorrect'
        elif re.match(r'Correct\b', tail, re.I):
            state = 'correct'
        elif ', Correct:' in tail:
            actual, expected = tail.split(', Correct:', 1)
            state = 'exact_match' if actual.strip() == expected.strip() else 'different_text'
        results.append({'status': state, 'text': line})
    return {'feedback': results, 'correct_explicit': sum(r['status']=='correct' for r in results),
            'incorrect_explicit': sum(r['status']=='incorrect' for r in results),
            'note': 'exact_match/different_text membandingkan teks, bukan klaim skor situs',
            'raw_text': text}


async def wait_for_feedback(page, form_id, timeout=30000):
    # This is an observation only. The caller must never click Submit again on timeout.
    await page.wait_for_function(r'''id => {
      const f=document.getElementById(id);
      if (!f) return false;
      return /Your answer\s*:/.test(f.innerText) && !/Your answer\s*:\s*$/.test(f.innerText.trim());
    }''', arg=form_id, timeout=timeout)
    form = page.locator('[id="' + form_id + '"]')
    # Do not read feedback while the submit button still reports Loading.
    await page.wait_for_function(r'''id => {
      const f=document.getElementById(id);
      if (!f) return false;
      const busy=Array.from(f.querySelectorAll('button')).some(b=>/loading/i.test(b.innerText));
      return /Your answer\s*:/.test(f.innerText) && !busy;
    }''', arg=form_id, timeout=timeout)
    return parse_feedback(await form.inner_text())
