# Driver for ELRS radio attached to serial port

import construct
import ok_serial
import logging
import time

import trashbot.crsf_protocol

_log = logging.getLogger(__name__)


BOT_PORT = "/dev/ttyAMA0"
BOT_BAUD = 420000

BASE_PORT = "..."  # TODO USB port spec
BASE_BAUD = 420000


class RadioDriver:
    def __init__(self, serial: ok_serial.SerialConnection):
        self.serial = serial
        self.buffer = bytearray()
        self.recent = {}

    def poll_frame(self) -> construct.Container | None:
        self.buffer.extend(self.serial.read_sync(timeout=0))
        if frame := trashbot.crsf_protocol.consume_frame(self.buffer):
            frame.mtime = time.monotonic()
            self.recent[frame.type] = frame
        return frame

    def send_frame(self, **frame):
        self.serial.write(trashbot.crsf_protocol.build_frame(**frame))
