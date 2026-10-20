from common import TestMetaWearBase, to_string_buffer
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
        # The board made the processor anyway, so its slot is freed
        self.assertIn([0x09, 0x06, 0x00], self.command_history)

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
        self.assertIn([0x0b, 0x03, 0x00], self.command_history)

class TestLateTimerResponse(LateResponseBase):
    withheld = (0x0c, 0x02)

    def test_late_response_is_dropped(self):
        self.libmetawear.mbl_mw_timer_create(self.board, 1000, 1, 0, None, self.timer_signal_ready)
        self.assertTrue(self.events["timer"].wait(2))
        self.wait_past_timeout()

        self.notify_mw_char(create_string_buffer(b'\x0c\x02\x00', 3))

        self.assertEqual([None], self.timerSignals)
        self.assertIn([0x0c, 0x05, 0x00], self.command_history)

class TestPartialLoggerTimeout(TestMetaWearBase):
    # Acceleration needs two log entries; the board answers the first and the second times out

    def setUp(self):
        self.entry_replies = 0
        super().setUp()
        self.libmetawear.mbl_mw_metawearboard_set_time_for_response(self.board, RESPONSE_TIMEOUT_MS)

    def commandLogger(self, context, board, writeType, characteristic, command, length):
        if (command[0], command[1]) == (0x0b, 0x02):
            self.entry_replies += 1
            if self.entry_replies > 1:
                return
        super().commandLogger(context, board, writeType, characteristic, command, length)

    def test_made_entries_are_removed(self):
        signal = self.libmetawear.mbl_mw_acc_get_acceleration_data_signal(self.board)
        self.libmetawear.mbl_mw_datasignal_log(signal, None, self.logger_created)
        self.assertTrue(self.events["log"].wait(2))

        self.assertEqual([None], self.loggers)
        self.assertIn([0x0b, 0x03, 0x00], self.command_history)

        # The second entry's reply arrives late
        self.notify_mw_char(create_string_buffer(b'\x0b\x02\x01', 3))
        self.assertIn([0x0b, 0x03, 0x01], self.command_history)

class TestLateAnonymousSignalResponse(TestMetaWearBase):
    # Replies to the logger slot and processor chain reads that create_anonymous_datasignals sends

    def setUp(self):
        self.boardType = TestMetaWearBase.METAWEAR_MOTION_R_BOARD
        self.withheld = None
        self.results = []
        self.result_ready = threading.Event()
        def created(context, board, signals, length):
            self.results.append(length)
            self.result_ready.set()
        self.created_fn = FnVoid_VoidP_VoidP_VoidP_UInt(created)

        super().setUp()
        self.libmetawear.mbl_mw_metawearboard_set_time_for_response(self.board, RESPONSE_TIMEOUT_MS)

    def slot_response(self, slot):
        return to_string_buffer([0x0b, 0x82])

    def commandLogger(self, context, board, writeType, characteristic, command, length):
        prev = len(self.full_history)
        super().commandLogger(context, board, writeType, characteristic, command, length)
        if prev == len(self.full_history):
            return

        response = None
        if (command[0], command[1]) == (0x03, 0x83):
            response = to_string_buffer([0x03, 0x83, 40, 8])
        elif (command[0], command[1]) == (0x13, 0x83):
            response = to_string_buffer([0x13, 0x83, 40, 3])
        elif (command[0], command[1]) == (0x19, 0x82):
            response = to_string_buffer([0x19, 0x82, 0x1, 0xf])
        elif (command[0], command[1], command[2]) == self.withheld:
            response = None
        elif (command[0], command[1]) == (0x0b, 0x82):
            response = self.slot_response(command[2])
        elif (command[0], command[1]) == (0x09, 0x82):
            response = self.processor_response(command[2])

        if response is not None:
            self.schedule_response(response)

    def sync(self):
        self.result_ready.clear()
        self.libmetawear.mbl_mw_metawearboard_create_anonymous_datasignals(self.board, None, self.created_fn)
        self.assertTrue(self.result_ready.wait(2))

class TestLateLoggerSlotResponse(TestLateAnonymousSignalResponse):
    def slot_response(self, slot):
        if slot == 0x00:
            return to_string_buffer([0x0b, 0x82, 0x03, 0x04, 0xff, 0x60])
        if slot == 0x01:
            return to_string_buffer([0x0b, 0x82, 0x03, 0x04, 0xff, 0x24])
        return to_string_buffer([0x0b, 0x82])

    def test_late_response_is_dropped(self):
        self.withheld = (0x0b, 0x82, 0x00)
        self.sync()
        time.sleep(RESPONSE_TIMEOUT_MS * 3 / 1000)

        self.notify_mw_char(self.slot_response(0x00))
        time.sleep(RESPONSE_TIMEOUT_MS * 3 / 1000)

        self.assertEqual([Const.STATUS_ERROR_TIMEOUT], self.results)

        self.withheld = None
        self.sync()
        self.assertEqual([Const.STATUS_ERROR_TIMEOUT, 1], self.results)

class TestLateProcessorChainResponse(TestLateAnonymousSignalResponse):
    PROCESSOR_CONFIG = [0x09, 0x82, 0x19, 0x07, 0xff, 0xe0, 0x08, 0x17, 0x14, 0x00, 0x00, 0x00, 0xd0, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]

    def slot_response(self, slot):
        if slot == 0x00:
            return to_string_buffer([0x0b, 0x82, 0x09, 0x03, 0x00, 0x60])
        return to_string_buffer([0x0b, 0x82])

    def processor_response(self, id):
        if id == 0x00:
            return to_string_buffer(self.PROCESSOR_CONFIG)
        return to_string_buffer([0x09, 0x82])

    def test_reports_failure_once(self):
        self.withheld = (0x09, 0x82, 0x00)
        self.sync()
        time.sleep(RESPONSE_TIMEOUT_MS * 3 / 1000)

        self.notify_mw_char(to_string_buffer(self.PROCESSOR_CONFIG))
        time.sleep(RESPONSE_TIMEOUT_MS * 3 / 1000)

        self.assertEqual([Const.STATUS_ERROR_TIMEOUT], self.results)

        self.withheld = None
        self.sync()
        self.assertEqual(2, len(self.results))
        self.assertNotEqual(Const.STATUS_ERROR_TIMEOUT, self.results[1])
