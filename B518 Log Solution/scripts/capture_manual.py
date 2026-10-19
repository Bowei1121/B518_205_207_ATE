"""Run asserted desktop stories and publish only a complete set of manual assets."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

APP = Path(__file__).resolve().parents[1]
REPO = APP.parent
# Stable filenames decouple the manual from acceptance-ticket names.
STORIES = (
    ("home", "test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed",
     {"main-page": "home"}),
    ("settings", "test_profile_editor_uses_three_equal_action_columns_and_browse_label",
     {"hf5-settings": "configuration", "settings-events": "events",
      "settings-retention": "retention"}),
    ("recovery", "test_recovery_acknowledges_only_manually_and_session_retry_keeps_evidence_once",
     {"hf2-alarm-pending": "alarm-pending", "hf2-alarm-acknowledged": "alarm-acknowledged",
      "hf2-session-recovered": "save-recovered"}),
    ("review", "test_hm3_conflict_and_alarm_layout_stays_fixed_across_languages",
     {"conflict-review": "conflict", "round-alarm": "round-alarm"}),
    ("history", "test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail",
     {"history-events": "history", "app-diagnostics": "diagnostics",
      "history-diagnostics": "history-diagnostics"}),
)
LIFECYCLE = (
    ("li1", "smoke_li1_preparation_app.py",
     ("preparing", "monitoring", "activity", "complete")),
    ("li2", "smoke_li2_manual_stop_app.py",
     ("preparing-stop", "preparing-stop-cancelled", "mixed-terminal-stop",
      "all-terminal-review", "manual-stop-released")),
)


def png_metadata(path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise RuntimeError("Invalid PNG: " + str(path))
    width, height = struct.unpack(">II", data[16:24])
    if width < 100 or height < 100:
        raise RuntimeError("Screenshot too small: " + str(path))
    # Decode the actual bitmap too: reject black/blank captures before publication.
    from AppKit import NSBitmapImageRep
    from Foundation import NSData
    bitmap = NSBitmapImageRep.imageRepWithData_(NSData.dataWithBytes_length_(data, len(data)))
    if bitmap is None:
        raise RuntimeError("Undecodable PNG: " + str(path))
    colours = set()
    for y in range(0, height, max(1, height // 40)):
        for x in range(0, width, max(1, width // 40)):
            colour = bitmap.colorAtX_y_(x, y)
            colours.add((round(colour.redComponent(), 2), round(colour.greenComponent(), 2),
                         round(colour.blueComponent(), 2)))
    if len(colours) < 8:
        raise RuntimeError("Blank/black screenshot: " + str(path))
    return {"pixels": [width, height], "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO / "Manual/Photo/generated")
    parser.add_argument("--evidence", type=Path,
                        default=REPO / "docs/manual/evidence/latest")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Requires a macOS Aqua desktop, Tk and PyObjC")
    output, evidence = args.output.resolve(), args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    # A fresh directory prevents stale screenshots from satisfying this run.
    evidence = evidence / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    evidence.mkdir(parents=True)
    records = []
    env = dict(os.environ, B518_TK_TESTS="1", B518_TK_CAPTURE_METHOD="view-cache")
    env["PYTHONPATH"] = os.pathsep.join(str(APP / name) for name in ("src", "tests", "tools"))
    # Isolate Tcl interpreters and native window lifetimes between stories.
    with tempfile.TemporaryDirectory(prefix="b518-manual-") as temporary:
        stage = Path(temporary)
        for story, method, assets in STORIES:
            raw = evidence / story
            raw.mkdir(parents=True, exist_ok=True)
            env["B518_TK_EVIDENCE_DIR"] = str(raw)
            test_id = "test_log_solution_ui.LogSolutionUiTests." + method
            command = [sys.executable, "scripts/run_tests.py", test_id]
            print("Capturing " + story, flush=True)
            with (raw / "test.log").open("w") as log:
                subprocess.run(command, cwd=APP, env=env, stdout=log,
                               stderr=subprocess.STDOUT, check=True, timeout=180)
            for source, name in assets.items():
                for language in ("zh-TW", "en"):
                    filename = name + "-" + language + ".png"
                    source_path = raw / (source + "-" + language + ".png")
                    metadata = png_metadata(source_path)
                    shutil.copyfile(source_path, stage / filename)
                    records.append(dict(file=filename, language=language, test=test_id,
                                        source=source_path.name, **metadata))
        for story, script, assets in LIFECYCLE:
            raw = evidence / story
            raw.mkdir(parents=True, exist_ok=True)
            smoke_env = dict(env)
            smoke_env["B518_" + story.upper() + "_EVIDENCE_DIR"] = str(raw)
            print("Capturing " + story, flush=True)
            with (raw / "test.log").open("w") as log:
                subprocess.run([sys.executable, "tools/" + script], cwd=APP, env=smoke_env,
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
            for name in assets:
                filename = name + ".png"
                metadata = png_metadata(raw / filename)
                shutil.copyfile(raw / filename, stage / filename)
                records.append(dict(file=filename, language="en", test="tools/" + script,
                                    source=filename, **metadata))
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True))
        manifest = dict(captured_at=datetime.now(timezone.utc).isoformat(),
                        source_commit=revision, working_tree_dirty=dirty,
                        source_files={str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in sorted(list((APP / "src").glob("*.py")) +
                                                         [APP / "tests/test_log_solution_ui.py", Path(__file__)] +
                                                         [APP / "tools" / item[1] for item in LIFECYCLE])},
                        python=sys.version, platform=platform.platform(),
                        capture_method="NSWindow.contentView live Tk view cache",
                        scope="Application content; not physical KVM, occlusion or native focus evidence",
                        images=records)
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        # Nothing is published if any assertion, capture or validation above fails.
        output.mkdir(parents=True, exist_ok=True)
        for path in stage.iterdir():
            shutil.copyfile(path, output / path.name)
        print("Published {} screenshots to {}".format(len(records), output))


if __name__ == "__main__":
    main()
