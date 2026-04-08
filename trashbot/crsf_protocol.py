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
from construct import (
    Array,
    BitStruct,
    BitsInteger,
    ByteSwapped,
    Checksum,
    Const,
    Construct,
    ConstructError,
    Enum,
    ExprAdapter,
    Flag,
    FocusedSeq,
    GreedyBytes,
    Int8sb,
    Int8ub,
    Int16sb,
    Int16ub,
    Int24ub,
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


def ScaledValue(subcon, scale, offset=0.0):
    """val = raw * scale + offset, raw = round((val - offset) / scale)."""
    return ExprAdapter(
        subcon,
        decoder=lambda obj, ctx: obj * scale + offset,
        encoder=lambda obj, ctx: round((obj - offset) / scale),
    )


_payload_type = Enum(
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
)


# RC channels: ELRS uses 172-1811 for -100% to +100%, center 992
_CH_CENTER = 991.5
_CH_RANGE = 819.5


def _decode_channels(obj, ctx) -> list[float]:
    return [(int(ch) - _CH_CENTER) / _CH_RANGE for ch in obj.ch]


def _encode_channels(obj: list[float], ctx) -> dict:
    return {"ch": [round(v * _CH_RANGE + _CH_CENTER) for v in obj]}


_channel_values = ExprAdapter(
    ByteSwapped(BitStruct("ch" / Array(16, BitsInteger(11)))),
    decoder=_decode_channels,
    encoder=_encode_channels,
)

_elrs_status = BitStruct(
    Padding(6),
    "armed_ch5" / Flag,
    "armed_switch" / Flag,
)

payload_rc_channels = Struct(
    "scaled_values" / _channel_values,
    "elrs_status" / Optional(_elrs_status),
)

# TX power is an enum index, not milliwatts
_tx_to_mw = [0, 10, 25, 100, 500, 1000, 2000, 250, 50]

payload_link_statistics = Struct(
    "up_rssi_ant1_dbm" / ScaledValue(Int8ub, -1),
    "up_rssi_ant2_dbm" / ScaledValue(Int8ub, -1),
    "up_link_quality" / Int8ub,
    "up_snr" / Int8sb,
    "active_antenna" / Int8ub,
    "rf_mode" / Int8ub,
    "up_tx_power_mw" / Mapping(Int8ub, {k: v for v, k in enumerate(_tx_to_mw)}),
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

_frame_payloads: dict[str, Construct] = {  # type: ignore[type-arg]
    "RC_Channels_Packed": payload_rc_channels,
    "Link_Statistics": payload_link_statistics,
    "Battery_Sensor": payload_battery_sensor,
    "Attitude": payload_attitude,
    "Heartbeat": payload_heartbeat,
}

_frame_body = FocusedSeq(
    "payload",
    "type" / _payload_type,
    "payload" / Switch(this.type, _frame_payloads, default=GreedyBytes),
)

_frame_data = Prefixed(
    Int8ub,
    FocusedSeq(
        "body",
        "body" / RawCopy(_frame_body),
        "crc" / Checksum(Int8ub, fastcrc.crc8.dvb_s2, this.body),
    ),
)

crsf_frame = FocusedSeq("data", "sync" / Const(b"\xc8"), "data" / _frame_data)


def consume_frame(buffer: bytearray) -> dict | None:
    while len(buffer) >= 4:
        # Scan for sync byte
        idx = buffer.find(crsf_frame.sync.value)
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
            parsed_frame = crsf_frame.parse(buffer[:frame_size])
            del buffer[:frame_size]
            return parsed_frame
        except ConstructError as e:
            log.debug("bad frame: %s", e)

    return None
