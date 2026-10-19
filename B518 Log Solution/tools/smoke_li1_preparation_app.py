import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / 'src'))


class LocalHotkey:
    available = True
    message = 'LI1 isolated Tk verification'

    def __init__(self, _callback):
        pass

    def close(self):
        pass


def wait_for(root, predicate, what, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return
        time.sleep(0.02)
    raise RuntimeError('Timed out waiting for {}'.format(what))


def capture(root, path):
    import Quartz
    from Foundation import NSURL
    root.update()
    windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll,
                                                Quartz.kCGNullWindowID)
    info = next((item for item in windows if item.get('kCGWindowLayer') == 0 and
                 item.get('kCGWindowOwnerPID') == os.getpid() and
                 item.get('kCGWindowName') == root.wm_title()), None)
    if info is None:
        raise RuntimeError('Visible Tk window owned by test App process not found')
    if 'B518' not in root.wm_title():
        raise RuntimeError('Tk root title does not identify the B518 App: {!r}'.format(root.wm_title()))
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
        info['kCGWindowNumber'], Quartz.kCGWindowImageBoundsIgnoreFraming)
    if image is None:
        raise RuntimeError('Quartz could not capture Tk window {}: {}'.format(
            info, [(item.get('kCGWindowName'), item.get('kCGWindowOwnerPID'),
                    item.get('kCGWindowNumber')) for item in windows
                   if item.get('kCGWindowOwnerPID') == os.getpid()]))
    url = NSURL.fileURLWithPath_(str(path))
    writer = Quartz.CGImageDestinationCreateWithURL(url, 'public.png', 1, None)
    Quartz.CGImageDestinationAddImage(writer, image, None)
    if not Quartz.CGImageDestinationFinalize(writer):
        raise RuntimeError('Screenshot failed: {}'.format(path))
    return {'file': path.name, 'window_title': info.get('kCGWindowName', ''),
            'window_owner_pid': info.get('kCGWindowOwnerPID'),
            'tk_root_title': root.wm_title(),
            'physical_pixels': [Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)]}


def main():
    evidence = Path(os.environ.get(
        'B518_LI1_EVIDENCE_DIR',
        APP_ROOT / 'docs' / 'refactoring' / 'evidence' / 'li1-real-app'))
    evidence.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='li1-real-app-'))
    active, archive = temporary / 'active', temporary / 'archive'
    active.mkdir()
    archive.mkdir()
    support = temporary / 'Application Support'
    entered, release = threading.Event(), threading.Event()
    adapter, count = {}, []
    output = []
    root = tk.Tk()
    with patch('b518_log_solution.APP_ROOT', support), \
            patch('b518_log_solution.PREFS_PATH', support / 'preferences.json'):
        import b518_log_solution as app_module
        from b518_log_solution import B518LogSolutionApp
        from kvm_display_contract import state_for_round_snapshot
        from log_monitoring import MonitorEvent
        from monitoring_round import RoundState

        app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                 session_root=support / 'sessions')
        from AppKit import (NSApplicationActivateIgnoringOtherApps, NSRunningApplication)
        NSRunningApplication.runningApplicationWithProcessIdentifier_(os.getpid()).activateWithOptions_(
            NSApplicationActivateIgnoringOtherApps)
        root.deiconify()
        root.lift()
        root.update()
        try:
            profile = app.profiles.get('B518', 'FCT')
            profile = replace(profile, project='B518', machine='FCT', platform='atlas', capacity=2,
                              mapping=((1, 1), (2, 2)),
                              paths=dict(profile.paths, active=str(active), final=str(archive)),
                              timeouts={'start': 30, 'test': 30, 'round': 60})
            app.profiles = app.profiles.with_profile(profile)
            app.project.set('B518')
            app.station.set('FCT')
            app._render_rows()
            registry = app_module.DEFAULT_PLATFORM_REGISTRY
            original = registry.create_monitor

            def blocked_factory(name, **kwargs):
                count.append(name)
                entered.set()
                if not release.wait(10):
                    raise RuntimeError('test source gate timed out')
                adapter['monitor'] = original(name, **kwargs)
                return adapter['monitor']

            with patch.object(registry, 'create_monitor', blocked_factory):
                app.start_button.invoke()
                wait_for(root, entered.is_set, 'source preparation gate')
                wait_for(root, lambda: app.rounds.snapshot().state == RoundState.PREPARING,
                         'public PREPARING snapshot')
                root.update()
                preparing = app.rounds.snapshot()
                if state_for_round_snapshot(preparing).value != 'preparing':
                    raise RuntimeError('PREPARING snapshot did not render the PREPARING marker')
                if str(app.start_button.cget('state')) != 'disabled':
                    raise RuntimeError('Start stayed enabled during PREPARING')
                if str(app.stop_button.cget('state')) != 'normal':
                    raise RuntimeError('Stop was not operable during PREPARING')
                first_id = preparing.round_id
                app.start_button.invoke()
                app._on_local_hotkey(None)
                app._on_global_hotkey()
                app.start_monitor()
                root.update()
                if app.rounds.snapshot().round_id != first_id or len(count) != 1:
                    raise RuntimeError('A button, local/global hotkey, or core start replaced the round')
                output.append({'state': 'preparing', 'round_id': first_id,
                               'start_disabled': True, 'stop_enabled': True,
                               **capture(root, evidence / 'preparing.png')})
                release.set()
                wait_for(root, lambda: app.rounds.snapshot().state == RoundState.RUNNING,
                         'MONITORING after source baseline')
                root.update()
                output.append({'state': state_for_round_snapshot(app.rounds.snapshot()).value,
                               'round_id': app.rounds.snapshot().round_id,
                               'factory_calls': len(count),
                               **capture(root, evidence / 'monitoring.png')})

            monitor = adapter['monitor']
            evidence_detail = {'round_evidence_id': 'LI1-controlled-round'}
            monitor.apply_round_result(1, 'TESTING', 'LI1-SN-1', 'controlled-source',
                                       evidence_detail)
            wait_for(root, lambda: app.rounds.snapshot().results[0].status == 'TESTING' and
                     app.status_rows[1]['status'].cget('text') == 'TESTING',
                     'trusted channel activity in snapshot and HMI')
            output.append({'state': 'monitoring', 'slot1': 'TESTING',
                           'slot2': 'WAITING', **capture(root, evidence / 'activity.png')})

            monitor.apply_round_result(1, 'PASS', 'LI1-SN-1', 'controlled-source',
                                       evidence_detail, lock_terminal=True)
            monitor.apply_round_result(2, 'PASS', 'LI1-SN-2', 'controlled-source',
                                       evidence_detail, lock_terminal=True)
            wait_for(root, lambda: app.rounds.snapshot().state == RoundState.COMPLETED,
                     'normal complete round')
            wait_for(root, lambda: app._rendered_marker_state.value == 'complete',
                     'COMPLETE marker render')
            completed = app.rounds.snapshot()
            if not completed.result_available:
                raise RuntimeError('Normal complete round did not release exact capacity results')
            output.append({'state': state_for_round_snapshot(completed).value,
                           'results': [item.status for item in completed.results],
                           'result_available': completed.result_available,
                           **capture(root, evidence / 'complete.png')})
        finally:
            release.set()
            app.close()

    manifest = {'ticket': 'LI1',
        'command': 'PYTHONPATH=src /opt/anaconda3/bin/python3 tools/smoke_li1_preparation_app.py',
        'environment': {
        'macOS': subprocess.check_output(['/usr/bin/sw_vers', '-productVersion'], text=True).strip(),
        'architecture': platform.machine(), 'python': platform.python_version(),
        'tk': str(tk.TkVersion), 'capture': 'Quartz visible Tk window'},
        'physical_kvm_available': False, 'screens': output}
    (evidence / 'run.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
                                       encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
