import csv
import io
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from rswmt_monitoring import RsWmtLogMonitor, parse_rswmt_csv, parse_rswmt_log
from monitoring_round import RoundCoordinator

START = datetime(2026, 9, 11, 5, 44, 16)
HEADER = ['Serial Number', 'Test Pass/Fail Status', 'List of Failing Tests', 'Error Description',
          'Test Start Time', 'Test Stop Time', 'PRODUCT',
          'tc=Slot:tech=None:band=None;subtc=None:rate=None:freq=None:pwr=None;']


def result_text(slot=1, sn='TESTSERIAL0001', status='Pass', start='2026/11/09 05:44:16'):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(['Overlay', 'SmtCal'] + [''] * 6)
    writer.writerow(HEADER)
    for name in ('Upper Limits', 'Lower Limits', 'Apple Pass Upper Limits',
                 'Apple Pass Lower Limits', 'Measurement Unit'):
        writer.writerow([name + '----->'] + [''] * 7)
    writer.writerow([sn, status, '[]', '', start, '2026/11/09 05:45:44', 'B518', slot])
    return stream.getvalue()


def log_text(slot=1, sn='TESTSERIAL0001', close=False):
    text = ("2026-09-11 05:44:16,688 STATE:TestRunner Add-in 'initialize'...\n"
            '2026-09-11 05:44:16,793 DEBUG:instrument >> \'CONFigure:SCSTools:VARiable:DEFine "instance_active_%s", 0, INSTrument\\n\'\n' % slot)
    if sn:
        text += '2026-09-11 05:44:27,462 DEBUG:HciCommunication << 30 bytes: .[....MLB#..' + sn + ' 05 5B\n'
    text += '2026-09-11 05:44:28,000 PASS:TestRunner Item complete.\n'
    if close:
        text += "2026-09-11 05:45:44,401 STATE:TestRunner Add-in 'shutdown'...\n"
    return text


class RsWmtTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / 'output/SmtCal'
        self.output.mkdir(parents=True)
        self.seconds = 0
        self.events = []

    def monitor(self, **kwargs):
        return RsWmtLogMonitor(self.output, now=lambda: START + timedelta(seconds=self.seconds),
                              monotonic=lambda: self.seconds, session_root=self.root / 'sessions',
                              callback=self.events.append, **kwargs)

    def write_result(self, slot=1, sn=None, **kwargs):
        sn = 'TESTSERIAL000{}'.format(slot) if sn is None else sn
        path = self.output / '2026-09-11_05-45-44' / (sn + '_2026-09-11_05-45-44.csv')
        path.parent.mkdir(exist_ok=True)
        path.write_text(result_text(slot, sn, **kwargs))
        return path

    def test_csv_slot_is_not_filename_order_and_date_is_export_day_month(self):
        for slot in range(1, 5):
            record = parse_rswmt_csv(self.write_result(slot))
            self.assertEqual((record.slot, record.status, record.started), (slot, 'PASS', START))

    def test_failure_without_serial_is_fail_not_notest(self):
        record = parse_rswmt_csv(self.write_result(sn='', status='Fail'))
        self.assertEqual((record.status, record.sn), ('FAIL', ''))

    def test_reject_partial_invalid_slot_unknown_status_and_serial_mismatch(self):
        path = self.write_result()
        for text in (result_text()[:-3], result_text(slot=0), result_text(status='Running'),
                     result_text(sn='OTHER000001'), result_text(status='Pass', sn='')):
            path.write_text(text)
            self.assertIsNone(parse_rswmt_csv(path))

    def test_header_and_limit_rows_are_not_results(self):
        path = self.write_result()
        path.write_text('\n'.join(result_text().splitlines()[:-1]) + '\n')
        self.assertIsNone(parse_rswmt_csv(path))

    def test_summary_file_is_not_a_dut_result(self):
        path = self.output / 'Summary_2026-09-11_05-45-44.csv'
        path.write_text(result_text(sn='SUMMARY'))
        self.assertIsNone(parse_rswmt_csv(path))

    def test_live_log_keeps_first_slot_serial_on_conflict(self):
        rounds = RoundCoordinator()
        rounds.start('BT', lambda callback: RsWmtLogMonitor(
            self.output, slots=(1,), now=lambda: START + timedelta(seconds=self.seconds),
            monotonic=lambda: self.seconds, session_root=self.root / 'sessions', callback=callback,
        ), run_async=False)
        (self.output / 'first.log').write_text(log_text(sn='TESTSERIAL0001'))
        rounds.poll_once()
        (self.output / 'second.log').write_text(log_text(sn='OTHER0000001'))
        rounds.poll_once()
        snapshot = rounds.snapshot()
        self.assertEqual(snapshot.results[0].sn, 'TESTSERIAL0001')
        self.assertEqual(len(snapshot.pending_conflicts), 1)
        self.assertEqual(snapshot.pending_conflicts[0].candidate.sn, 'OTHER0000001')
        rounds.stop()

    def test_old_content_copied_after_start_is_ignored(self):
        monitor = self.monitor()
        self.write_result(start='2026/11/09 05:40:00')
        monitor.poll_once()
        self.seconds = 5
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, 'WAITING')

    def test_log_testing_and_completing_never_item_pass(self):
        for slot in range(1, 5):
            record = parse_rswmt_log(log_text(slot), 'live.log')
            self.assertEqual((record.slot, record.status), (slot, 'TESTING'))
        self.assertEqual(parse_rswmt_log(log_text(close=True), 'live.log').status, 'COMPLETING')
        self.assertIsNone(parse_rswmt_log(log_text() + log_text(2), 'mixed.log'))

    def test_final_only_all_slots_stability_and_no_repeated_results(self):
        monitor = self.monitor(start_timeout_seconds=240)
        self.seconds = 88
        for slot in (4, 2, 1, 3):
            self.write_result(slot)
        monitor.poll_once()
        self.assertTrue(all(r.status == 'COMPLETING' for r in monitor.results.values()))
        self.seconds = 92.9
        monitor.poll_once()
        self.assertTrue(all(r.status == 'COMPLETING' for r in monitor.results.values()))
        self.seconds = 93
        monitor.poll_once()
        self.assertTrue(all(r.status == 'PASS' for r in monitor.results.values()))
        count = len([e for e in self.events if e.status == 'PASS'])
        monitor.poll_once()
        self.assertEqual(len([e for e in self.events if e.status == 'PASS']), count)
        self.seconds = 96
        monitor.poll_once()
        self.assertFalse(monitor.finished)

    def test_live_log_partial_writes_and_stable_csv_are_handled_by_adapter(self):
        monitor = self.monitor(test_timeout_seconds=5)
        path = self.output / 'live.log'
        text = log_text()
        path.write_text(text[:50])
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, 'WAITING')
        with path.open('a') as handle:
            handle.write(text[50:])
        self.write_result()
        monitor.poll_once()
        self.assertEqual(monitor.results[1].sn, 'TESTSERIAL0001')
        self.seconds = 5
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, 'PASS')
        path.write_text(log_text(close=True))
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, 'PASS')

    def test_timeout_latches_slot_and_late_csv_does_not_overwrite(self):
        rounds = RoundCoordinator(monotonic=lambda: self.seconds)

        def create(callback):
            return RsWmtLogMonitor(
                self.output, callback=callback,
                now=lambda: START + timedelta(seconds=self.seconds),
                monotonic=lambda: self.seconds, start_timeout_seconds=30,
                test_timeout_seconds=5, round_timeout_seconds=100,
                session_root=self.root / 'sessions',
            )

        rounds.start('BT', create, run_async=False)
        monitor = rounds.monitor
        (self.output / 'live.log').write_text(log_text())
        rounds.poll_once()
        self.seconds = 5
        rounds.poll_once()
        self.assertEqual(monitor.results[1].status, 'TIMEOUT')
        self.assertEqual(monitor.results[2].status, 'WAITING')
        self.write_result()
        rounds.poll_once()
        self.seconds = 10
        rounds.poll_once()
        self.assertEqual(monitor.results[1].status, 'TIMEOUT')

    def test_existing_files_ignored_and_stopped_monitor_frozen(self):
        self.write_result()
        (self.output / 'live.log').write_text(log_text())
        monitor = self.monitor()
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, 'WAITING')
        monitor.stop()
        self.write_result(2)
        self.seconds = 40
        monitor.poll_once()
        self.assertTrue(all(r.status == 'STOPPED' for r in monitor.results.values()))

    def test_other_round_does_not_mix_into_current_round(self):
        monitor = self.monitor()
        self.write_result()
        monitor.poll_once()
        self.write_result(2, start='2026/11/09 05:44:17')
        self.seconds = 6
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, 'PASS')
        self.assertEqual(monitor.results[2].status, 'WAITING')
        self.assertTrue(any('different test start' in e.message for e in self.events))

    def test_csv_change_restarts_stability_wait(self):
        monitor = self.monitor()
        path = self.write_result()
        monitor.poll_once()
        self.seconds = 4
        path.write_text(result_text(status='Fail'))
        monitor.poll_once()
        self.seconds = 5
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, 'COMPLETING')
        self.seconds = 9
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, 'FAIL')


if __name__ == '__main__':
    unittest.main()
