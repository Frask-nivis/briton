"""Inspect all planned answers first; never overwrite a different existing answer."""
import re


async def unique(loc):
    if await loc.count() != 1:
        raise RuntimeError('Kontrol jawaban tidak unik atau belum tersedia')
    await loc.wait_for(state="visible")
    return loc


async def inspect_action(page, action, form_id):
    kind = action['type']
    if kind in ('fill','check','select'):
        form = await unique(page.locator(action['form']))
        if await form.get_attribute('id') != form_id:
            raise ValueError('Action mengarah ke form aktivitas lain')
        loc = await unique(form.locator(action['selector']))
        if await loc.is_disabled():
            raise RuntimeError('Kontrol jawaban disabled; tidak diubah')
        if kind == 'fill':
            old = await loc.input_value()
            if old == action['value']:
                return 'same'
            if old:  # Even whitespace is existing content, not permission to erase it.
                raise RuntimeError('Konflik isian teks; jawaban lama dipertahankan')
            return 'empty'
        if kind == 'check':
            if await loc.is_checked():
                return 'same'
            if await loc.get_attribute('type') == 'radio':
                name = await loc.get_attribute('name')
                if not name:
                    raise RuntimeError('Radio tanpa nama tidak bisa diperiksa')
                checked = await form.locator('input[type=radio]:checked').evaluate_all(
                    '(els,name)=>els.some(e=>e.name===name)', name)
                if checked:
                    raise RuntimeError('Konflik pilihan radio; pilihan lama dipertahankan')
            return 'empty'
        selected = await loc.evaluate('e=>Array.from(e.selectedOptions).map(o=>({text:o.text,value:o.value,disabled:o.disabled,hidden:o.hidden}))')
        if len(selected)==1 and selected[0]['text']==action['label']:
            return 'same'
        for o in selected:
            placeholder = o['disabled'] or o['hidden'] or not o['value'].strip() or not o['text'].strip() or re.fullmatch(r'select an answer|choose(?: an? (?:answer|option))?|pilih(?: jawaban)?',o['text'].strip(),re.I)
            if not placeholder:
                raise RuntimeError('Konflik dropdown; pilihan lama dipertahankan')
        options = await loc.locator('option').evaluate_all('(els)=>els.map(o=>o.text)')
        if options.count(action['label']) != 1:
            raise RuntimeError('Label dropdown tidak tersedia secara unik')
        return 'empty'
    if kind == 'match':
        qid = action['qid']
        if not re.fullmatch(r'q?\d+',qid):
            raise ValueError('qid tidak valid')
        form = await unique(page.locator('#'+form_id))
        target = await unique(form.locator(f'.LS-lesson-drop-match[data-qid="{qid}"]').filter(
            has=page.locator('.LS-lesson-match-text',has_text=action['question'])))
        dropped = target.locator('.LS-lesson-drop-match-content .LS-lesson-drag-match-wrapper')
        if await dropped.count():
            if await dropped.count()==1 and (await dropped.inner_text()).strip()==action['answer'].strip():
                return 'same'
            raise RuntimeError('Konflik pasangan; isi slot lama dipertahankan')
        source = form.locator(f'.LS-lesson-drag-match-pool[data-qid="{qid}"] .LS-lesson-drag-match-wrapper').filter(
            has=page.get_by_text(action['answer'],exact=True))
        await unique(source)
        return 'empty'
    raise ValueError('Jenis action belum didukung: '+kind)


async def inspect_all(page, actions, form_id):
    # No writes here. A conflict late in the plan must block every earlier write.
    return [await inspect_action(page, action, form_id) for action in actions]
