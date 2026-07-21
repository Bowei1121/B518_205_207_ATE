import unittest

from upper_computer_simulator import ProtocolError, make_batch, parse_result_frame


class UpperComputerProtocolTests(unittest.TestCase):
    def test_batch_joins_non_empty_slots_with_crlf(self):
        values, frame = make_batch(["SN001", "", "SN003", ""])
        self.assertEqual(values, ["SN001", "SN003"])
        self.assertEqual(frame, b"SN001,SN003\r\n")

    def test_batch_rejects_invalid_and_duplicate_serials(self):
        with self.assertRaises(ProtocolError):
            make_batch(["SN 001"])
        with self.assertRaises(ProtocolError):
            make_batch(["SN001", "SN001"])

    def test_result_parser_keeps_each_sn_status(self):
        self.assertEqual(
            parse_result_frame("RESULT:SN001,PASS;SN002,FAIL;SN003,TIMEOUT"),
            {"SN001": "PASS", "SN002": "FAIL", "SN003": "TIMEOUT"},
        )
        self.assertIsNone(parse_result_frame("READY Arduino TCP-to-USB bridge"))

    def test_result_parser_rejects_malformed_status(self):
        with self.assertRaises(ProtocolError):
            parse_result_frame("RESULT:SN001,GOOD")


if __name__ == "__main__":
    unittest.main()
