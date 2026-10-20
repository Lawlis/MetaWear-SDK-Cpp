from common import TestMetaWearBase
from ctypes import create_string_buffer
from cbindings import *
import threading
import time

# Responses that arrive after the SDK gave up on the request must be dropped: the timeout already
# freed the pending object and reported failure, so handling them dereferenced freed memory.

RESPONSE_TIMEOUT_MS = 100

class LateResponseBase(TestMetaWearBase):
    # (module, register) of the create command whose response is withheld until the timeout fires
    withheld = None

    def setUp(self):
        self.withhold = True
        super().setUp()
        self.libmetawear.mbl_mw_metawearboard_set_time_for_response(self.board, RESPONSE_TIMEOUT_MS)

    def commandLogger(self, context, board, writeType, characteristic, command, length):
        if self.withhold and (command[0], command[1]) == self.withheld:
            return
        super().commandLogger(context, board, writeType, characteristic, command, length)

    def wait_past_timeout(self):
        time.sleep(RESPONSE_TIMEOUT_MS * 3 / 1000)

class TestLateProcessorResponse(LateResponseBase):
    withheld = (0x09, 0x02)

    def test_late_response_is_dropped(self):
        created = []
        done = threading.Event()
        def on_created(context, processor):
            created.append(processor)
            done.set()
        created_fn = FnVoid_VoidP_VoidP(on_created)

        signal = self.libmetawear.mbl_mw_acc_get_acceleration_data_signal(self.board)
        self.libmetawear.mbl_mw_dataprocessor_rss_create(signal, None, created_fn)
        self.assertTrue(done.wait(2))
        self.wait_past_timeout()

        self.notify_mw_char(create_string_buffer(b'\x09\x02\x00', 3))

        self.assertEqual([None], created)

    def test_creates_after_late_response(self):
        created = []
        done = threading.Event()
        def on_created(context, processor):
            created.append(processor)
            done.set()
        created_fn = FnVoid_VoidP_VoidP(on_created)

        signal = self.libmetawear.mbl_mw_acc_get_acceleration_data_signal(self.board)
        self.libmetawear.mbl_mw_dataprocessor_rss_create(signal, None, created_fn)
        self.assertTrue(done.wait(2))
        self.wait_past_timeout()
        self.notify_mw_char(create_string_buffer(b'\x09\x02\x00', 3))

        done.clear()
        self.withhold = False
        self.libmetawear.mbl_mw_dataprocessor_rss_create(signal, None, created_fn)
        self.assertTrue(done.wait(2))

        self.assertEqual(2, len(created))
        self.assertIsNone(created[0])
        self.assertIsNotNone(created[1])

class TestLateLoggerResponse(LateResponseBase):
    withheld = (0x0b, 0x02)

    def test_late_response_is_dropped(self):
        signal = self.libmetawear.mbl_mw_switch_get_state_data_signal(self.board)
        self.libmetawear.mbl_mw_datasignal_log(signal, None, self.logger_created)
        self.assertTrue(self.events["log"].wait(2))
        self.wait_past_timeout()

        self.notify_mw_char(create_string_buffer(b'\x0b\x02\x00', 3))

        self.assertEqual([None], self.loggers)

class TestLateTimerResponse(LateResponseBase):
    withheld = (0x0c, 0x02)

    def test_late_response_is_dropped(self):
        self.libmetawear.mbl_mw_timer_create(self.board, 1000, 1, 0, None, self.timer_signal_ready)
        self.assertTrue(self.events["timer"].wait(2))
        self.wait_past_timeout()

        self.notify_mw_char(create_string_buffer(b'\x0c\x02\x00', 3))

        self.assertEqual([None], self.timerSignals)
