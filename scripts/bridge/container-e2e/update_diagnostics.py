"""Bounded diagnostics: never export candidate response bodies or raw errors."""
import time
import re

def failure_evidence(data):
    result = {k: data[k] for k in ("receipt_exists", "receipt_finished", "receipt_read_error", "log_read_error") if type(data.get(k)) is bool}
    counts = data.get("process_counts", {})
    result["process_counts"] = {k: v for k, v in counts.items() if k in ("python", "python3", "python3.11", "git", "npm", "node", "uv") and type(v) is int and 0 <= v <= 10000}
    text = str(data.get("log_tail", ""))[-12000:]
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    lines = []
    for line in text.splitlines()[-80:]:
        if re.search(r"token|password|secret|api.?key|authorization|credential|private.key|bearer", line, re.I):
            line = "[REDACTED]"
        line = re.sub(r"https?://\S+", "[URL]", line)
        line = re.sub(r"[A-Za-z0-9_+/=-]{32,}", "[REDACTED_VALUE]", line)
        lines.append("".join(c for c in line if c.isprintable())[:300])
    result["sanitized_log_tail"] = "\n".join(lines)[-8000:]
    return result



def poll_receipt(fetch, diagnostic, timeout=1800, clock=time.monotonic, sleep=time.sleep):
    start = clock()
    deadline = start + timeout
    diagnostic.update(attempts=0, timed_out=False)
    while clock() < deadline:
        diagnostic['attempts'] += 1
        diagnostic.update(last_error=None, last_http_status=None, summary_present=False)
        try:
            response = fetch()
            status = response.get('status')
            diagnostic['last_http_status'] = status if type(status) is int and 100 <= status <= 599 else None
            if status != 200:
                diagnostic['last_error'] = 'http_error'
            else:
                data = response.get('data') or {}
                summary = data.get('summary') or {}
                diagnostic['summary_present'] = bool(summary)
                if summary.get('finished_at'):
                    diagnostic['elapsed_seconds'] = int(clock() - start)
                    return summary
        except Exception as error:
            # Exception text may include session tokens, URLs or response bodies.
            name = type(error).__name__
            diagnostic['last_error'] = name if name in ('TimeoutError', 'TargetClosedError', 'Error', 'ValueError', 'TypeError', 'AttributeError') else 'poll_exception'
        diagnostic['elapsed_seconds'] = int(clock() - start)
        sleep(5)
    diagnostic['timed_out'] = True
    return None


def log_summary(text):
    """Export only fixed stage/error labels, never untrusted log text."""
    labels = ('snapshot', 'fetch', 'dependencies', 'build', 'restart', 'receipt', 'error', 'failed', 'timeout', 'fatal', 'npm err!', 'traceback', 'killed', 'oom', 'exit code', 'no space left', 'permission denied')
    signals = set()
    for line in text[-16000:].splitlines():
        for label in labels:
            if label in line.lower():
                signals.add(label)
    return {'tail_chars': min(len(text), 16000), 'signals': sorted(signals), 'raw_log_omitted': True}
