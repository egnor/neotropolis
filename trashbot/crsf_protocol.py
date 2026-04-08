# CRSF protocol definitions using the Construct library.
#
# CRSF is a binary frame protocol for RC systems, documented at
# https://github.com/tbs-fpv/tbs-crsf-spec/blob/main/crsf.md
#
# This module defines Construct structs for parsing/building CRSF frames
# with declarative CRC validation, plus a serial reader class.

import fastcrc
import logging
import math
import serial  # type: ignore[import-untyped]
from construct import (
    Array,
    BitStruct,
    BitsInteger,
    ByteSwapped,
    Checksum,
    Computed,
    Const,
    ConstructError,
    ExprAdapter,
    Flag,
    GreedyBytes,
    Int8sb,
    Int8ub,
    Int16sb,
    Int16ub,
    Int24ub,
    Optional,
    Padding,
    Prefixed,
    RawCopy,
    Struct,
    Switch,
    this,
)
from enum import IntEnum

_log = logging.getLogger(__name__)

CRSF_SYNC = 0xC8
CRSF_MAX_FRAME = 64


# === Construct helpers ===


def ScaledValue(subcon, scale, offset=0.0):
    """val = raw * scale + offset, raw = round((val - offset) / scale)."""
    return ExprAdapter(
        subcon,
        decoder=lambda obj, ctx: obj * scale + offset,
        encoder=lambda obj, ctx: round((obj - offset) / scale),
    )


# === Frame types ===


class FrameType(IntEnum):
    GPS = 0x02
    VARIO = 0x07
    BATTERY_SENSOR = 0x08
    BARO_ALT = 0x09
    HEARTBEAT = 0x0B
    LINK_STATISTICS = 0x14
    RC_CHANNELS_PACKED = 0x16
    LINK_STATISTICS_RX = 0x1C
    LINK_STATISTICS_TX = 0x1D
    ATTITUDE = 0x1E
    FLIGHT_MODE = 0x21


# === Payload definitions ===

# RC channels: ELRS uses 172-1811 for -100% to +100%, center 992
_CH_CENTER = 991.5
_CH_RANGE = 819.5


def _decode_channels(obj, ctx) -> list[float]:
    return [(int(ch) - _CH_CENTER) / _CH_RANGE for ch in obj.ch]


def _encode_channels(obj: list[float], ctx) -> dict:
    return {"ch": [round(v * _CH_RANGE + _CH_CENTER) for v in obj]}


_elrs_status = BitStruct(
    Padding(6),
    "armed_ch5" / Flag,
    "armed_switch" / Flag,
)

payload_rc_channels = Struct(
    "channels_scaled"
    / ExprAdapter(
        ByteSwapped(BitStruct("ch" / Array(16, BitsInteger(11)))),
        decoder=_decode_channels,
        encoder=_encode_channels,
    ),
    # ELRS extension: armed status (None if not present)
    "elrs_status" / Optional(_elrs_status),
)

# TX power is an enum index, not milliwatts
_TX_POWER = [0, 10, 25, 100, 500, 1000, 2000, 250, 50]


def _decode_tx_power(obj: int, ctx) -> int:
    return _TX_POWER[obj] if obj < len(_TX_POWER) else obj


def _encode_tx_power(mw: int, ctx) -> int:
    return min(range(len(_TX_POWER)), key=lambda i: abs(_TX_POWER[i] - mw))


payload_link_statistics = Struct(
    "up_rssi_ant1_dbm" / ScaledValue(Int8ub, -1),
    "up_rssi_ant2_dbm" / ScaledValue(Int8ub, -1),
    "up_link_quality" / Int8ub,
    "up_snr" / Int8sb,
    "active_antenna" / Int8ub,
    "rf_mode" / Int8ub,
    "up_tx_power_mw" / ExprAdapter(Int8ub, _decode_tx_power, _encode_tx_power),
    "down_rssi_dbm" / ScaledValue(Int8ub, -1),
    "down_link_quality" / Int8ub,
    "down_snr" / Int8sb,
)

payload_battery_sensor = Struct(
    "voltage_v" / ScaledValue(Int16ub, 0.1),
    "current_a" / ScaledValue(Int16ub, 0.1),
    "capacity_used_mah" / Int24ub,
    "remaining_pct" / Int8ub,
)

payload_attitude = Struct(
    "pitch_deg" / ScaledValue(Int16sb, 180.0 / (math.pi * 10000)),  # degrees
    "roll_deg" / ScaledValue(Int16sb, 180.0 / (math.pi * 10000)),
    "yaw_deg" / ScaledValue(Int16sb, 180.0 / (math.pi * 10000)),
)

payload_heartbeat = Struct(
    "origin_address" / Int16ub,
)


# === Main frame definition ===
#
# Prefixed handles the length field automatically (parse and build).
# CRSF length counts type+payload+CRC, but Prefixed measures only
# what it wraps (type+payload), so ExprAdapter adjusts by 1 for CRC.
# RawCopy captures raw type+payload bytes for CRC validation.
# GreedyBytes in the default Switch case works because Prefixed
# bounds the stream.

# Length field: CRSF stores (inner + 1) to account for the trailing
# CRC byte which is outside the Prefixed block.
_crsf_length: ExprAdapter = ExprAdapter(
    Int8ub,
    decoder=lambda obj, ctx: obj - 1,
    encoder=lambda obj, ctx: obj + 1,
)

crsf_frame = Struct(
    "sync" / Const(bytes([CRSF_SYNC])),
    "body"
    / Prefixed(
        _crsf_length,
        RawCopy(
            Struct(
                "type" / Int8ub,
                "payload"
                / Switch(
                    this.type,
                    {
                        FrameType.RC_CHANNELS_PACKED: payload_rc_channels,
                        FrameType.LINK_STATISTICS: payload_link_statistics,
                        FrameType.BATTERY_SENSOR: payload_battery_sensor,
                        FrameType.ATTITUDE: payload_attitude,
                        FrameType.HEARTBEAT: payload_heartbeat,
                    },
                    default=GreedyBytes,
                ),
            ),
        ),
    ),
    "crc" / Checksum(Int8ub, fastcrc.crc8.dvb_s2, this.body.data),
    # Flattened accessors (callers can use frame.type, frame.payload)
    "type" / Computed(this.body.value.type),
    "payload" / Computed(this.body.value.payload),
)


# === Stream scanner ===


def consume_frame(buffer: bytearray) -> dict | None:
    pass


class CrsfReader:
    """Read CRSF frames from a serial port."""

    def __init__(self, port: str, baudrate: int = 420000):
        self.serial = serial.Serial(port, baudrate, timeout=0)
        self._buf = bytearray()

    def read_frames(self):
        """Read available data and yield parsed CRSF frames."""
        waiting = self.serial.in_waiting
        if waiting:
            self._buf.extend(self.serial.read(waiting))

        while len(self._buf) >= 4:
            # Scan for sync byte
            try:
                idx = self._buf.index(CRSF_SYNC)
            except ValueError:
                self._buf.clear()
                return
            if idx > 0:
                del self._buf[:idx]

            if len(self._buf) < 2:
                return

            length = self._buf[1]
            if not 2 <= length <= 62:
                del self._buf[:1]
                continue

            frame_size = length + 2
            if len(self._buf) < frame_size:
                return

            raw = bytes(self._buf[:frame_size])
            del self._buf[:frame_size]

            try:
                yield crsf_frame.parse(raw)
            except ConstructError as e:
                _log.debug("bad frame: %s", e)

    def write(self, data: bytes) -> None:
        """Write raw bytes (e.g. from build_battery_telemetry)."""
        self.serial.write(data)

    def close(self) -> None:
        self.serial.close()
