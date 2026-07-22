import unittest

from upper_computer_simulator import ProtocolError, make_batch, parse_result_frame


class UpperComputerProtocolTests(unittest.TestCase):
    def test_batch_joins_non_empty_slots_with_crlf(self):
        assignments, frame = make_batch("BT", "20260722-001", ["SN001", "", "SN003", ""])
        self.assertEqual(assignments, {1: "SN001", 3: "SN003"})
        self.assertEqual(frame, b"BT:JOB=20260722-001;1=SN001,3=SN003\r\n")

    def test_batch_rejects_invalid_and_duplicate_serials(self):
        with self.assertRaises(ProtocolError):
            make_batch("DFU", "JOB-1", ["SN 001"])
        with self.assertRaises(ProtocolError):
            make_batch("FCT", "JOB-1", ["SN001", "SN001"])

    def test_result_parser_keeps_each_sn_status(self):
        result = parse_result_frame("RESULT:FCT:JOB=JOB-1;1=SN001,PASS;3=SN003,TIMEOUT")
        self.assertIsNotNone(result)
        self.assertEqual(result.station, "FCT")
        self.assertEqual(result.job_id, "JOB-1")
        self.assertEqual(result.results, {1: ("SN001", "PASS"), 3: ("SN003", "TIMEOUT")})
        self.assertIsNone(parse_result_frame("READY Arduino TCP-to-USB bridge"))

    def test_result_parser_rejects_malformed_status(self):
        with self.assertRaises(ProtocolError):
            parse_result_frame("RESULT:BT:JOB=JOB-1;1=SN001,GOOD")


if __name__ == "__main__":
    unittest.main()
