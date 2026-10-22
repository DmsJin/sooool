"""Retain run outcomes, register immutable evidence, and append researcher decisions."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time


@contextmanager
def recording(out, *, game, command, provider, clock, result_file="summary.json", detail_file=None):
    """Record every newly created experiment, including failures during game initialization."""
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(f"Output directory must be new: {out}")
    try:
        yield
    except BaseException as exc:
        if out.is_dir():
            (out / "failure.json").write_text(json.dumps({"type": type(exc).__name__, "message": str(exc)}, indent=2) + "\n")
        raise
    finally:
        if out.is_dir():
            path = out / "manifest.json"
            manifest = json.loads(path.read_text()) if path.exists() else {"game": game, "mode": command}
            manifest.update(game=game, command=command, provider=provider, clock=clock)
            path.write_text(json.dumps(manifest, indent=2) + "\n")
            result_path = out / result_file
            summary = json.loads(result_path.read_text()) if result_path.exists() else None
            interrupted = bool((out / "failure.json").exists() or (summary or {}).get("controller_error") or
                (summary or {}).get("error") or (summary or {}).get("status") in ("interrupted", "stopped") or
                (summary or {}).get("stop_reason") in ("interrupted", "runner_error") or any(
                episode.get("error") or episode.get("status") in ("interrupted", "stopped_or_error")
                for episode in (summary or {}).get("episodes", [])))
            status = "interrupted" if interrupted else "incomplete" if (
                summary is None or summary.get("complete") is False or
                summary.get("status") in ("interrupted", "incomplete", "stopped_or_error")
            ) else "completed"
            evidence = {"manifest": "manifest.json", "result": result_file if result_path.exists() else None}
            if detail_file is not None:
                evidence["details"] = detail_file if (out / detail_file).exists() else None
            row = {"schema_version": 2, "record_id": out.name, "run": str(out),
                   "created_at_unix": time.time(), "game": manifest["game"], "command": manifest["command"],
                   "provider": manifest["provider"], "clock": manifest["clock"], "mode": manifest["mode"],
                   "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "summary": summary, "status": status, "evidence": evidence,
                   "performance_is_independently_confirmed": False}
            if "recipe" in manifest:
                row["recipe"] = manifest["recipe"]
            if manifest["game"] == "rhythm" and "recipe" in manifest:
                recipe = manifest["recipe"]
                accounting = json.loads((out / "accounting.json").read_text()) if (out / "accounting.json").exists() else None
                row.update(policy=recipe.get("policy"), accounting=accounting,
                           hypothesis=recipe.get("hypothesis"), parent_record=recipe.get("parent_record"),
                           outcome=(summary or {}).get("result", (summary or {}).get("evaluator")),
                           complete=bool((summary or {}).get("complete")), passed=bool((summary or {}).get("passed")),
                           real_time_api_acceptance=bool(manifest["mode"] == "realtime_api" and
                               (summary or {}).get("passed") and accounting and accounting["all_settled"]))
            (out / "evaluation-record.json").write_text(json.dumps(row, indent=2) + "\n")


def append_record(run, registry):
    """Append one immutable record under a lock; repeated identical registrations are idempotent."""
    run, registry = Path(run), Path(registry)
    record = json.loads((run / "evaluation-record.json").read_text())
    if record["schema_version"] != 2:
        raise ValueError("Expected a shared version 2 evaluation record")
    manifest = json.loads((run / "manifest.json").read_text())
    if record["game"] != manifest["game"]:
        raise ValueError("Record game does not match the run manifest")
    identity = record["record_id"]
    if not identity or identity != Path(record["run"]).name:
        raise ValueError("Record ID does not match the recorded run path")
    registry.parent.mkdir(parents=True, exist_ok=True)
    with registry.open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        for line in stream:
            old = json.loads(line)
            # Existing registries can also contain historical game-owned records.
            if old["record_id"] == identity:
                if old != record:
                    raise ValueError("Record ID already exists with different evidence")
                return False
        stream.seek(0, 2)
        stream.write(json.dumps(record, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return True


def assess(out, decision, note):
    """Append a researcher decision without changing the run's evidence."""
    out = Path(out).resolve()
    record = json.loads((out / "evaluation-record.json").read_text())
    row = {"created_at_unix": time.time(), "run": str(out), "decision": decision, "note": note,
           "manifest_sha256": record["manifest_sha256"], "mode": record["mode"], "run_status": record["status"]}
    with (out / "assessments.jsonl").open("a") as log:
        log.write(json.dumps(row) + "\n")
    return row
