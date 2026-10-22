"""Verify HC7 matrix coverage, PNG hashes/dimensions and measured ROI consistency."""
import argparse
import hashlib
import itertools
import json
import struct
import subprocess
from pathlib import Path


def verify(directory):
    directory = Path(directory)
    matrix = json.loads((directory / "matrix.json").read_text())
    expected = set(itertools.product(
        ((1440, 900), (1152, 720)), (1.0, 1.5), (1, 10, 11, 20), ("en", "zh-TW")))
    actual = [(tuple(c["display_resolution"]), c["requested_tk_scaling"],
               c["capacity"], c["language"]) for c in matrix["cases"]]
    assert len(actual) == len(expected) and set(actual) == expected
    source_root = Path(__file__).resolve().parents[1]
    current_src_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD:B518 Log Solution/src"],
        cwd=source_root, text=True).strip()
    assert matrix["app_src_tree"] == current_src_tree, "runtime source tree changed"
    script = source_root / "scripts" / "capture_hc7_geometry.py"
    assert hashlib.sha256(script.read_bytes()).hexdigest() == matrix["capture_script_sha256"]
    count = 0
    for case in matrix["cases"]:
        captures = {c["state"]: c for c in case["captures"]}
        assert set(captures) == {"normal-clear", "long-pending-bright",
                                 "long-pending-dim", "long-cleared"}
        assert case["geometry_unchanged_across_reminder_and_timer_states"]
        assert case["heartbeat_advanced_while_reminder_active"]
        assert captures["long-pending-bright"]["reminder_foreground"] == "#dc2626"
        assert captures["long-pending-dim"]["reminder_foreground"] == "#7f1d1d"
        assert captures["normal-clear"]["pending_count"] == 0
        assert captures["long-cleared"]["pending_count"] == 0
        assert captures["long-pending-bright"]["pending_count"] == 12
        assert captures["long-pending-dim"]["pending_count"] == 12
        assert captures["long-pending-bright"]["reminder_text"]
        assert captures["long-cleared"]["reminder_text"] == ""
        assert captures["long-pending-bright"]["heartbeat_state"] != captures["long-pending-dim"]["heartbeat_state"]
        for state, capture in captures.items():
            expected_text = "00:00" if state == "normal-clear" else "10000:00"
            assert capture["timer_text"] == expected_text
            assert capture["controls"] == case["controls_content_tk"]
            path = directory / capture["screenshot"]
            image = path.read_bytes()
            assert image[:8] == b"\x89PNG\r\n\x1a\n"
            width, height = struct.unpack(">II", image[16:24])
            assert capture["image_pixels"] == {"width": width, "height": height}
            assert hashlib.sha256(image).hexdigest() == capture["sha256"]
            sx, sy = capture["pixels_per_tk_unit"]
            x, y, w, h = capture["controls"]["timer"]
            roi = [round(x*sx), round(y*sy), round(w*sx), round(h*sy)]
            assert roi == capture["timer_roi_pixels"]
            x, y, w, h = roi
            assert 0 <= x < x+w <= width and 0 <= y < y+h <= height
            left, top, right, bottom = capture["timer_pixels"]["glyph_bbox_pixels_xyxy"]
            assert x < left < right < x+w and y < top < bottom < y+h
            assert capture["timer_pixels"]["dark_pixel_count"] > 0
            count += 1
    assert matrix["matrix_case_count"] == len(expected)
    assert matrix["image_count"] == count == 128
    assert matrix["local_only"] and not matrix["remote_jetkvm_verified"]
    print("PASS: 32/32 Cartesian cases, 128/128 PNG hashes/dimensions and ROI records")
    print("Glyph bbox/count are capture-time AppKit measurements; this offline check validates provenance and consistency.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    verify(parser.parse_args().directory)
