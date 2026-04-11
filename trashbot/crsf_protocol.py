# CRSF protocol definitions using the Construct library.
#
# CRSF is a binary frame protocol for RC systems, documented at
# https://github.com/tbs-fpv/tbs-crsf-spec/blob/main/crsf.md
#
# This module defines Construct structs for parsing/building CRSF frames
# with declarative CRC validation, plus a serial reader class.

import collections.abc
import fastcrc
import logging
from construct import (
    Adapter,
    BitStruct,
    Bytes,
    Checksum,
    Const,
    ConstructError,
    Container,
    CString,
    Enum,
    ExprAdapter,
    Flag,
    FocusedSeq,
    OffsettedEnd,
    Int8sb,
    Int8ub,
    Int16ub,
    Int24ub,
    Int32sb,
    Int32ub,
    Mapping,
    Optional,
    Padding,
    Prefixed,
    RawCopy,
    Struct,
    Switch,
    this,
)

log = logging.getLogger(__name__)

# All known frame types, for reference (we do not support most of them)
frame_type = Enum(
    Int8ub,
    GPS=0x02,
    GPSTime=0x03,
    GPSExtended=0x06,
    VariometerSensor=0x07,
    BatterySensor=0x08,
    BarometricAltitude=0x09,
    Airspeed=0x0A,
    Heartbeat=0x0B,
    RPM=0x0C,
    Temp=0x0D,
    Voltages=0x0E,
    VTXTelemetry=0x10,
    Barometer=0x11,
    Magnetometer=0x12,
    AccelGyro=0x13,
    LinkStatistics=0x14,
    RCChannelsPacked=0x16,
    LinkStatisticsRX=0x1C,
    LinkStatisticsTX=0x1D,
    Attitude=0x1E,
    MAVLink=0x1F,
    FlightMode=0x21,
    ESPNOW=0x22,
    # Extended frame types (dest_addr + orig_addr precede payload)
    DevicePing=0x28,
    DeviceInfo=0x29,
    ParameterSettingsEntry=0x2B,
    ParameterRead=0x2C,
    ParameterWrite=0x2D,
    ELRSStatus=0x2E,
    Command=0x32,
    RemoteRelated=0x3A,
    KISSReq=0x78,
    KISSResp=0x79,
    MSPReq=0x7A,
    MSPResp=0x7B,
    MSPWrite=0x7C,
    ArdupilotResp=0x80,
)


def _Scaled(subcon, scale, offset=0.0, digits=0):
    """val = raw * scale + offset, raw = round((val - offset) / scale).
    If digits is nonzero, decoded values are rounded to that many decimals."""

    def decode(obj, ctx):
        val = obj * scale + offset
        return round(val, digits) if digits else val

    return ExprAdapter(
        subcon,
        decoder=decode,
        encoder=lambda obj, ctx: round((obj - offset) / scale),
    )


# RC channels: ELRS uses 172-1811 for -100% to +100%, center 992
_CH_MIN = 172
_CH_MAX = 1811
_CH_SCALE = 2.0 / (_CH_MAX - _CH_MIN)
_CH_OFFSET = -0.5 * (_CH_MIN + _CH_MAX) * _CH_SCALE

# ELRS sends raw channel value 0 on link loss/failsafe, which scales to this.
# Any channel value outside ±1.0 is beyond normal range; this value (-1.21)
# specifically indicates the receiver has no link.
CHANNEL_FAILSAFE = round(_CH_OFFSET, 3)


class _RCChannels(Adapter):
    """Pack/unpack 16 × 11-bit channels matching the ELRS wire format.

    The CRSF spec describes RCChannelsPacked as a C bitfield (crsf_channels_s
    in ExpressLRS's crsf_protocol.h), declared with __attribute__((packed)).
    On ELRS's little-endian GCC targets, that means fields are packed LSB-first
    across the byte stream: ch0 occupies bits 0..10, ch1 bits 11..21, etc., of
    the 22-byte payload interpreted as a little-endian integer. (The spec's
    "big-endian" note refers to multi-byte scalars, not bitfield order.)

    Construct's built-in BitStruct reads bits MSB-first, which is wrong here
    and causes neighboring channels to bleed into each other, so we do the
    bit-slicing directly on a raw byte payload.
    """

    def _decode(self, data, ctx, path):
        val = int.from_bytes(data, "little")
        return [
            round(((val >> (11 * i)) & 0x7FF) * _CH_SCALE + _CH_OFFSET, 3)
            for i in range(16)
        ]

    def _encode(self, obj, ctx, path):
        val = 0
        for i, ch in enumerate(obj):
            raw = round((ch - _CH_OFFSET) / _CH_SCALE)
            val |= (raw & 0x7FF) << (11 * i)
        return val.to_bytes(22, "little")


_elrs_status_byte = BitStruct(
    Padding(6),
    "armed_ch5" / Flag,
    "armed_switch" / Flag,
)

_rc_channels_payload = Struct(
    "scaled_values" / _RCChannels(Bytes(22)),
    "elrs_status" / Optional(_elrs_status_byte),  # ELRS extension
)

# TX power is an enum index, not milliwatts
_tx_to_mw = [0, 10, 25, 100, 500, 1000, 2000, 250, 50]

_link_statistics_payload = Struct(
    "up_rssi_ant1_dbm" / _Scaled(Int8ub, -1),
    "up_rssi_ant2_dbm" / _Scaled(Int8ub, -1),
    "up_link_quality" / Int8ub,
    "up_snr" / Int8sb,
    "active_antenna" / Int8ub,
    "rf_mode" / Int8ub,
    "up_tx_power_mw" / Mapping(Int8ub, {k: v for v, k in enumerate(_tx_to_mw)}),
    "down_rssi_ant1_dbm" / _Scaled(Int8ub, -1),
    "down_link_quality" / Int8ub,
    "down_snr" / Int8sb,
    "down_rssi_ant2_dbm" / Optional(_Scaled(Int8ub, -1)),  # ELRS extension
)

_battery_sensor_payload = Struct(
    "voltage_v" / _Scaled(Int16ub, 0.1),
    "current_a" / _Scaled(Int16ub, 0.1),
    "capacity_used_mah" / Int24ub,
    "remaining_pct" / Int8ub,
)

_flight_mode_payload = Struct(
    "flight_mode" / CString("utf8"),
)

# Extended frame: dest_addr and orig_addr precede the subtype/payload.
# ELRS TX sends this every ~200ms to tell the host the desired RC packet rate.
_remote_related_payload = Struct(
    "dest_addr" / Int8ub,
    "orig_addr" / Int8ub,
    "sub_type" / Int8ub,  # 0x10 = timing, 0x3C = game
    "rate_us" / _Scaled(Int32ub, 0.1),  # desired RC packet interval
    "offset_us" / _Scaled(Int32sb, 0.1),  # phase offset for sync
)

_heartbeat_payload = Struct(
    "origin_address" / Int16ub,
)

_frame_payload = Switch(
    this.type,
    {
        "RCChannelsPacked": _rc_channels_payload,
        "LinkStatistics": _link_statistics_payload,
        "BatterySensor": _battery_sensor_payload,
        "FlightMode": _flight_mode_payload,
        "RemoteRelated": _remote_related_payload,
        "Heartbeat": _heartbeat_payload,
    },
    default=Struct(),
)

_frame_body = Struct(
    "type" / frame_type,
    "payload" / OffsettedEnd(-1, _frame_payload),  # don't consume CRC byte
)

_frame_data = Prefixed(
    Int8ub,
    FocusedSeq(
        "body",
        "body" / RawCopy(_frame_body),
        "crc" / Checksum(Int8ub, fastcrc.crc8.dvb_s2, this.body.data),
    ),
)

frame = FocusedSeq("data", "sync" / Const(b"\xc8"), "data" / _frame_data)


def parse_frame(input: collections.abc.Buffer) -> Container:
    result = frame.parse(input)
    return Container(type=result.value.type, **result.value.payload)


def build_frame(*, type: str, **rest) -> bytes:
    return frame.build({"value": {"type": type, "payload": rest}})


def consume_frame(buffer: bytearray) -> Container | None:
    while len(buffer) >= 4:
        # Scan for sync byte
        sync_index = buffer.find(frame.sync.value)
        if sync_index < 0:
            buffer.clear()
            break
        if sync_index > 0:
            log.debug("Skipping %d bytes", sync_index)
            del buffer[:sync_index]
            continue

        frame_size = buffer[1] + 2
        if not 4 <= frame_size <= 64:
            log.debug("Bad frame size: %d", frame_size)
            del buffer[:1]
            continue
        if len(buffer) < frame_size:
            break

        try:
            parsed_frame = parse_frame(buffer[:frame_size])
            del buffer[:frame_size]
            log.debug("Received frame type=%s", parsed_frame["type"])
            return parsed_frame
        except ConstructError as e:
            log.debug("Bad frame: %s", e)
            del buffer[:1]  # skip sync byte, re-sync

    return None
