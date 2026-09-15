"""Read-only fixture probe. Output is untrusted; controller sanitizes it."""
import json
from pathlib import Path

home = Path('/work/home/.hermes')
result = {}
pointer = home / 'logs/update_receipts/latest.json'
result['receipt_exists'] = pointer.is_file()
try:
    if pointer.stat().st_size <= 131072:
        receipt = json.loads(pointer.read_text())
        result['receipt_finished'] = bool(receipt.get('finished_at'))
    else:
        result['receipt_read_error'] = True
except (OSError, ValueError, AttributeError):
    result['receipt_read_error'] = result['receipt_exists']
try:
    with (home / 'logs/update.log').open('rb') as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 12000))
        result['log_tail'] = stream.read(12000).decode('utf-8', 'replace')
except OSError:
    result['log_read_error'] = True
# Process comm only: no command lines, environment or secrets. Not proof of updater identity.
counts = {}
for entry in Path('/proc').iterdir():
    if entry.name.isdigit():
        try:
            name = (entry / 'comm').read_text(errors='replace').strip()
            if name in ('python', 'python3', 'python3.11', 'git', 'npm', 'node', 'uv'):
                counts[name] = counts.get(name, 0) + 1
        except OSError:
            pass
result['process_counts'] = counts
print(json.dumps(result))
