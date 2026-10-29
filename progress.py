"""Conservative activity status and resumable, plan-bound checkpoints."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def classify(snapshot, text):
    # Retry labels and completion icons are deliberately not consulted.
    if re.search(r'Your answer\s*:\s*(?:Correct\b|Incorrect\b|\S[^\n]*,\s*Correct\s*:)', text, re.I):
        return 'uncertain' if snapshot.get('can_submit') else 'graded'
    if re.search(r'Your answer\s*:', text, re.I):
        return 'uncertain'
    controls = [c for c in snapshot['controls'] if c['visible'] and not c.get('disabled')]
    slots = snapshot.get('total_slots', 0)
    if not controls and not slots:
        return 'unsupported'
    for c in controls:
        if c['type'] in ('radio','checkbox') and c.get('checked'):
            return 'filled_unsubmitted'
        if c['tag'] == 'SELECT' and any(not o['placeholder'] and o['value'].strip() for o in c.get('selected', [])):
            return 'filled_unsubmitted'
        if c['type'] in ('text','textarea') and c.get('value','').strip():
            return 'filled_unsubmitted'
    if slots > snapshot.get('empty_slots', slots):
        return 'filled_unsubmitted'
    return 'unanswered'


class Checkpoint:
    def __init__(self, path, plan):
        self.path = Path(path)
        fingerprint = hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.data = {'version':1, 'plan_sha256':fingerprint, 'activities':{}}
        if self.path.exists():
            old = json.loads(self.path.read_text(encoding='utf-8'))
            if old.get('version') != 1 or old.get('plan_sha256') != fingerprint:
                raise ValueError('Checkpoint bukan untuk versi file jawaban ini; gunakan path checkpoint baru.')
            self.data = old

    def state(self, url):
        return self.data['activities'].get(url, {}).get('status')

    def record(self, url, status, reason):
        self.data['activities'][url] = {'status':status, 'reason':reason,
            'updated_at':datetime.now(timezone.utc).isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + '.tmp')
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)


def should_block_resume(previous, live):
    # A failed click may have reached the server. Never silently resend it.
    return previous in ('submission_pending','submission_unknown') and live != 'graded'
