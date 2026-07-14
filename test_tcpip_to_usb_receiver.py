import unittest

from tcpip_to_usb_receiver import (
    ReceiverError,
    UsbSerialReceiver,
    parse_serial_line,
)


class FakeSerial:
    def __init__(self, lines):
        self.lines = list(lines)

    def readline(self):
        return self.lines.pop(0) if self.lines else b""

    def reset_input_buffer(self):
        pass

    def close(self):
        pass


class ReceiverTests(unittest.TestCase):
    def test_parse_data_line(self):
        line = parse_serial_line(b"DATA:hello world\r\n")

        self.assertIsNotNone(line)
        self.assertEqual(line.kind, "data")
        self.assertEqual(line.payload, "hello world")

    def test_parse_event_line(self):
        line = parse_serial_line(b"EVT: TCP client connected\n")

        self.assertIsNotNone(line)
        self.assertEqual(line.kind, "event")
        self.assertEqual(line.payload, "TCP client connected")

    def test_receiver_counts_data_only(self):
        messages = []
        serial = FakeSerial([
            b"EVT: TCP server ready\n",
            b"DATA:first\n",
            b"DATA:second\n",
        ])
        receiver = UsbSerialReceiver(serial, output=messages.append)

        received = receiver.run(count=2)

        self.assertEqual(received, 2)
        self.assertEqual(messages, ["EVENT: TCP server ready", "DATA: first", "DATA: second"])

    def test_receiver_timeout(self):
        serial = FakeSerial([])
        receiver = UsbSerialReceiver(serial, output=lambda _message: None)

        with self.assertRaisesRegex(ReceiverError, "等待資料逾時"):
            receiver.run(count=1, timeout=0.01)


if __name__ == "__main__":
    unittest.main()
