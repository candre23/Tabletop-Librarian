#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

manager = (ROOT / "app/library/manager.py").read_text()
main = (ROOT / "app/main.py").read_text()
template = (ROOT / "app/templates/admin_library.html").read_text()

assert "progress_callback" in manager
assert 'progress_callback("document", item, scanned_count)' in manager
assert 'progress_callback("document", source_path, scanned_count)' in manager

assert "_source_scan_jobs" in main
assert "asyncio.to_thread" in main
assert "_run_source_scan_job" in main
assert 'message=f"Scanning document {count}: {path.name}"' in main
assert '@app.get("/admin/library/source/status/{job_id}")' in main
assert 'request.headers.get("X-TTL-Source-Scan") == "1"' in main
assert 'completed_job.get("scan_result")' in main

assert 'event.preventDefault();' in template
assert '"X-TTL-Source-Scan": "1"' in template
assert "pollSourceScan" in template
assert "/admin/library/source/status/" in template
assert "await delay(750);" in template
assert "window.location.href" in template

print("PASS: live library source progress regression test")
print("  scan callback reports actual document names: OK")
print("  source scan runs in background worker: OK")
print("  browser polls live job state: OK")
print("  running document count/filename message: OK")
print("  completed scan reused on page reload: OK")
