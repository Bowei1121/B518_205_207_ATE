import unittest

from arduino_mouse_validator import (
    ArduinoMouseValidator,
    InteractiveSpaceController,
    START_ACK,
    STOP_ACK,
    ValidationConfig,
    ValidationError,
)


class FakeSerial:
    def __init__(self, replies):
        self.replies = {key: list(value) for key, value in replies.items()}
        self.pending = []
        self.writes = []
        self.timeout = 0.1

    def write(self, data):
        self.writes.append(data)
        command = data[:1]
        self.pending.extend(self.replies.get(command, []))
        return len(data)

    def flush(self):
        pass

    def readline(self):
        return self.pending.pop(0) if self.pending else b""

    def reset_input_buffer(self):
        self.pending.clear()

    def close(self):
        pass


class FakePointer:
    def __init__(self, positions):
        self.positions = list(positions)
        self.last = self.positions[-1]

    def position(self):
        if self.positions:
            self.last = self.positions.pop(0)
        return self.last

    def close(self):
        pass


class FakeKeyReader:
    def __init__(self, keys):
        self.keys = list(keys)

    def read_key(self):
        return self.keys.pop(0) if self.keys else "q"

    def close(self):
        pass


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        self.now += 0.01
        return self.now

    def sleep(self, duration):
        self.now += duration


def config():
    return ValidationConfig(
        active_duration=0.15,
        stopped_duration=0.10,
        sample_interval=0.05,
        stop_settle_time=0,
        ack_timeout=0.1,
        minimum_active_changes=2,
        expected_movement_interval=0.05,
        movement_interval_tolerance=0.03,
    )


class ValidatorTests(unittest.TestCase):
    def make_validator(self, connection, pointer):
        clock = FakeClock()
        return ArduinoMouseValidator(
            connection,
            pointer,
            config(),
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            output=lambda _message: None,
        )

    def test_full_validation_passes(self):
        connection = FakeSerial(
            {b"S": [(START_ACK + "\n").encode()], b"P": [(STOP_ACK + "\n").encode()]}
        )
        # Four active readings create three changes; three stopped readings are stable.
        pointer = FakePointer([(10, 10), (11, 10), (11, 11), (10, 11), (10, 11), (10, 11), (10, 11)])

        result = self.make_validator(connection, pointer).run()

        self.assertEqual(result.active_changes, 3)
        self.assertAlmostEqual(result.median_active_interval, 0.06)
        self.assertEqual(result.stopped_changes, 0)
        self.assertEqual(connection.writes, [b"S\n", b"P\n"])

    def test_missing_start_ack_fails_and_sends_safety_stop(self):
        connection = FakeSerial({})
        pointer = FakePointer([(0, 0)])

        with self.assertRaisesRegex(ValidationError, "未在"):
            self.make_validator(connection, pointer).run()

        self.assertEqual(connection.writes, [b"S\n", b"P\n"])

    def test_movement_after_stop_fails(self):
        connection = FakeSerial(
            {b"S": [(START_ACK + "\n").encode()], b"P": [(STOP_ACK + "\n").encode()]}
        )
        pointer = FakePointer([(0, 0), (1, 0), (2, 0), (3, 0), (3, 0), (4, 0), (4, 0)])

        with self.assertRaisesRegex(ValidationError, "仍偵測到"):
            self.make_validator(connection, pointer).run()

    def test_wrong_movement_period_fails(self):
        connection = FakeSerial(
            {b"S": [(START_ACK + "\n").encode()], b"P": [(STOP_ACK + "\n").encode()]}
        )
        pointer = FakePointer([(0, 0), (1, 0), (2, 0), (3, 0)])
        clock = FakeClock()
        period_config = ValidationConfig(
            active_duration=0.15,
            stopped_duration=0.10,
            sample_interval=0.05,
            stop_settle_time=0,
            ack_timeout=0.1,
            minimum_active_changes=2,
            expected_movement_interval=0.20,
            movement_interval_tolerance=0.02,
        )
        validator = ArduinoMouseValidator(
            connection,
            pointer,
            period_config,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            output=lambda _message: None,
        )

        with self.assertRaisesRegex(ValidationError, "週期中位數"):
            validator.run()

        self.assertEqual(connection.writes, [b"S\n", b"P\n"])

    def test_interactive_space_toggles_start_then_stop(self):
        connection = FakeSerial(
            {b"S": [(START_ACK + "\n").encode()], b"P": [(STOP_ACK + "\n").encode()]}
        )
        clock = FakeClock()
        controller = InteractiveSpaceController(
            connection,
            config(),
            FakeKeyReader([" ", " ", "q"]),
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            output=lambda _message: None,
        )

        controller.run()

        self.assertEqual(connection.writes, [b"S\n", b"P\n"])

    def test_interactive_exit_sends_safety_stop_when_started(self):
        connection = FakeSerial(
            {b"S": [(START_ACK + "\n").encode()], b"P": [(STOP_ACK + "\n").encode()]}
        )
        clock = FakeClock()
        controller = InteractiveSpaceController(
            connection,
            config(),
            FakeKeyReader([" ", "q"]),
            sleep=clock.sleep,
            monotonic=clock.monotonic,
            output=lambda _message: None,
        )

        controller.run()

        self.assertEqual(connection.writes, [b"S\n", b"P\n"])


if __name__ == "__main__":
    unittest.main()
