# Driver for ELRS radio attached to serial port

import construct
import ok_serial
import logging
import time

import trashbot.crsf_protocol

_log = logging.getLogger(__name__)


BOT_PORT = "/dev/ttyAMA0"
BOT_BAUD = 420000

BASE_PORT = "vid_pid=10C4:EA60"  # TODO USB port spec
BASE_BAUD = 921600


class RadioDriver:
    def __init__(self, serial: ok_serial.SerialConnection):
        baud = serial.pyserial.baudrate
        _log.info(f"📻 Using {serial.port_name} at {baud}bps")
        self.serial = serial
        self.buffer = bytearray()
        self.recent: dict[str, construct.Container] = {}

    def poll_frame(self) -> construct.Container | None:
        self.buffer.extend(self.serial.read_sync(timeout=0))
        if frame := trashbot.crsf_protocol.consume_frame(self.buffer):
            _log.debug("Received frame: %s", frame.type)
            frame["mtime"] = time.monotonic()
            self.recent[frame.type] = frame
        return frame

    def send_frame(self, **frame):
        frame_bytes = trashbot.crsf_protocol.build_frame(**frame)
        _log.debug("Sending frame: %s [%r]", frame["type"], frame_bytes)
        self.serial.write(trashbot.crsf_protocol.build_frame(**frame))
