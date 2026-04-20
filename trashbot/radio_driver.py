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
        self.counts: dict[str, int] = {}
        self.raise_dsr_mtime = 0.0
        self.raise_dtr_mtime = 0.0

    def poll_frame(self) -> construct.Container | None:
        self.buffer.extend(self.serial.read_sync(timeout=0))
        mtime = time.monotonic()
        if frame := trashbot.crsf_protocol.consume_frame(self.buffer):
            _log.debug("Received frame: %s", frame.type)
            frame["mtime"] = mtime
            self.recent[frame.type] = frame
            self.counts[frame.type] = self.counts.get(frame.type, 0) + 1
        elif self.raise_dsr_mtime and mtime > self.raise_dsr_mtime:
            # reboot processing: raise DSR with DTR low, then raise DTR later
            self.raise_dsr_mtime = 0
            self.raise_dtr_mtime = mtime + 0.050
            self.serial.set_signals(dtr=False, rts=True)
        elif self.raise_dtr_mtime and mtime > self.raise_dtr_mtime:
            # reboot processing: raise DTR to allow normal operation
            self.raise_dtr_mtime = 0
            self.serial.set_signals(dtr=True, rts=True)
        return frame

    def send_frame(self, **frame):
        frame_bytes = trashbot.crsf_protocol.build_frame(**frame)
        _log.debug("Sending frame: %s [%r]", frame["type"], frame_bytes)
        self.serial.write(trashbot.crsf_protocol.build_frame(**frame))

    def attempt_reboot(self):
        """Cycles DSR to reboot the radio ESP32. Only works on the base,
        since the bot doesn't have control signals."""
        self.serial.set_signals(dtr=False, rts=False)
        self.raise_dsr_mtime = time.monotonic() + 0.050
