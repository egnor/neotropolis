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
    Array,
    BitStruct,
    BitsInteger,
    Checksum,
    Const,
    ConstructError,
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
    Pass,
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
    GPS_Time=0x03,
    GPS_Extended=0x06,
    Variometer_Sensor=0x07,
    Battery_Sensor=0x08,
    Barometric_Altitude=0x09,
    Airspeed=0x0A,
    Heartbeat=0x0B,
    RPM=0x0C,
    Temp=0x0D,
    Voltages=0x0E,
    VTX_Telemetry=0x10,
    Barometer=0x11,
    Magnetometer=0x12,
    Accel_Gyro=0x13,
    Link_Statistics=0x14,
    RC_Channels_Packed=0x16,
    Link_Statistics_RX=0x1C,
    Link_Statistics_TX=0x1D,
    Attitude=0x1E,
    MAVLink=0x1F,
    Flight_Mode=0x21,
    ESP_NOW=0x22,
    # Extended frame types (dest_addr + orig_addr precede payload)
    Device_Ping=0x28,
    Device_Info=0x29,
    Parameter_Settings_Entry=0x2B,
    Parameter_Read=0x2C,
    Parameter_Write=0x2D,
    ELRS_Status=0x2E,
    Command=0x32,
    Remote_Related=0x3A,
    KISS_Req=0x78,
    KISS_Resp=0x79,
    MSP_Req=0x7A,
    MSP_Resp=0x7B,
    MSP_Write=0x7C,
    Ardupilot_Resp=0x80,
)


def ScaledValue(subcon, scale, offset=0.0):
    """val = raw * scale + offset, raw = round((val - offset) / scale)."""
    return ExprAdapter(
        subcon,
        decoder=lambda obj, ctx: obj * scale + offset,
        encoder=lambda obj, ctx: round((obj - offset) / scale),
    )


# RC channels: ELRS uses 172-1811 for -100% to +100%, center 992
_CH_MIN = 172
_CH_MAX = 1811
_CH_SCALE = 2.0 / (_CH_MAX - _CH_MIN)
_CH_OFFSET = -0.5 * (_CH_MIN + _CH_MAX) * _CH_SCALE

# ELRS sends raw channel value 0 on link loss/failsafe, which scales to this.
# Any channel value outside ±1.0 is beyond normal range; this value (~-1.21)
# specifically indicates the receiver has no link.
CHANNEL_FAILSAFE = _CH_OFFSET

_rc_channel = ScaledValue(BitsInteger(11), _CH_SCALE, _CH_OFFSET)

_elrs_status_byte = BitStruct(
    Padding(6),
    "armed_ch5" / Flag,
    "armed_switch" / Flag,
)

_rc_channels_payload = BitStruct(
    "scaled_values" / Array(16, _rc_channel),
    "elrs_status" / Optional(_elrs_status_byte),  # ELRS extension
)

# TX power is an enum index, not milliwatts
_tx_to_mw = [0, 10, 25, 100, 500, 1000, 2000, 250, 50]

_link_statistics_payload = Struct(
    "up_rssi_ant1_dbm" / ScaledValue(Int8ub, -1),
    "up_rssi_ant2_dbm" / ScaledValue(Int8ub, -1),
    "up_link_quality" / Int8ub,
    "up_snr" / Int8sb,
    "active_antenna" / Int8ub,
    "rf_mode" / Int8ub,
    "up_tx_power_mw" / Mapping(Int8ub, {k: v for v, k in enumerate(_tx_to_mw)}),
    "down_rssi_ant1_dbm" / ScaledValue(Int8ub, -1),
    "down_link_quality" / Int8ub,
    "down_snr" / Int8sb,
    "down_rssi_ant2_dbm" / Optional(ScaledValue(Int8ub, -1)),  # ELRS extension
)

_battery_sensor_payload = Struct(
    "voltage_v" / ScaledValue(Int16ub, 0.1),
    "current_a" / ScaledValue(Int16ub, 0.1),
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
    "rate_us" / ScaledValue(Int32ub, 0.1),  # desired RC packet interval
    "offset_us" / ScaledValue(Int32sb, 0.1),  # phase offset for sync
)

_heartbeat_payload = Struct(
    "origin_address" / Int16ub,
)

_frame_payload = Switch(
    this.type,
    {
        "RC_Channels_Packed": _rc_channels_payload,
        "Link_Statistics": _link_statistics_payload,
        "Battery_Sensor": _battery_sensor_payload,
        "Flight_Mode": _flight_mode_payload,
        "Remote_Related": _remote_related_payload,
        "Heartbeat": _heartbeat_payload,
    },
    default=Pass,
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


def parse_frame(input: collections.abc.Buffer) -> dict:
    result = frame.parse(input)
    return {"type": result.value.type, **result.value.payload}


def build_frame(type: str, **rest) -> bytes:
    return frame.build({"value": {"type": type, "payload": rest}})


def consume_frame(buffer: bytearray) -> dict | None:
    while len(buffer) >= 4:
        # Scan for sync byte
        idx = buffer.find(frame.sync.value)
        if idx < 0:
            buffer.clear()
            break
        if idx > 0:
            del buffer[:idx]
            continue

        frame_size = buffer[1] + 2
        if not 4 <= frame_size <= 64:
            del buffer[:1]
            continue
        if len(buffer) < frame_size:
            break

        try:
            parsed_frame = parse_frame(buffer[:frame_size])
            del buffer[:frame_size]
            return parsed_frame
        except ConstructError as e:
            log.debug("Bad frame: %s", e)
            del buffer[:1]  # skip sync byte, re-sync

    return None
