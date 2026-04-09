import fastcrc
import pytest
from construct import ConstructError

from trashbot.crsf_protocol import (
    CHANNEL_FAILSAFE,
    ScaledValue,
    Int8ub,
    _link_statistics_payload,
    _rc_channels_payload,
    consume_frame,
    frame,
)


def make_frame(type_id: int, payload: bytes) -> bytes:
    """Build a raw CRSF frame: sync + length + type + payload + CRC."""
    body = bytes([type_id]) + payload
    crc = fastcrc.crc8.dvb_s2(body)
    return b"\xc8" + bytes([len(body) + 1]) + body + bytes([crc])


# --- ScaledValue ---


def test_scaled_value_round_trip():
    sv = ScaledValue(Int8ub, 0.5, 10.0)
    # raw=100 -> 100 * 0.5 + 10 = 60.0
    assert sv.parse(b"\x64") == 60.0
    # 60.0 -> round((60.0 - 10.0) / 0.5) = 100
    assert sv.build(60.0) == b"\x64"


def test_scaled_value_negative_scale():
    sv = ScaledValue(Int8ub, -1)
    # raw=50 -> 50 * -1 = -50
    assert sv.parse(b"\x32") == -50
    assert sv.build(-50) == b"\x32"


# --- Channel encoding ---


def test_channels_center():
    """All zeros should encode to center values and decode back."""
    channels = [0.0] * 16
    encoded = _rc_channels_payload.build(
        {"scaled_values": channels, "elrs_status": None}
    )
    parsed = _rc_channels_payload.parse(encoded)
    for i, v in enumerate(parsed.scaled_values):
        assert abs(v) < 0.001, f"ch{i} center: {v}"


def test_channels_limits():
    """±1.0 should round-trip within 11-bit quantization error."""
    channels = [1.0 if i % 2 == 0 else -1.0 for i in range(16)]
    encoded = _rc_channels_payload.build(
        {"scaled_values": channels, "elrs_status": None}
    )
    parsed = _rc_channels_payload.parse(encoded)
    for i, v in enumerate(parsed.scaled_values):
        assert abs(v - channels[i]) < 0.002, f"ch{i}: {v}"


def test_channel_failsafe_constant():
    parsed = _rc_channels_payload.parse(b"\0" * 22)
    for i, v in enumerate(parsed.scaled_values):
        assert v == CHANNEL_FAILSAFE, f"ch{i}: {v}"  # _exactly_ equal


# --- Frame parsing (known types) ---


def test_parse_link_statistics():
    raw = frame.build(
        {
            "value": {
                "type": "Link_Statistics",
                "payload": {
                    "up_rssi_ant1_dbm": -50,
                    "up_rssi_ant2_dbm": -55,
                    "up_link_quality": 100,
                    "up_snr": 10,
                    "active_antenna": 0,
                    "rf_mode": 4,
                    "up_tx_power_mw": 100,
                    "down_rssi_ant1_dbm": -60,
                    "down_link_quality": 95,
                    "down_snr": 8,
                    "down_rssi_ant2_dbm": -62,
                },
            }
        }
    )
    parsed = frame.parse(raw)
    body = parsed.value
    assert body.type == "Link_Statistics"
    assert body.payload.up_rssi_ant1_dbm == -50
    assert body.payload.up_link_quality == 100
    assert body.payload.down_rssi_ant2_dbm == -62


def test_parse_rc_channels():
    channels = [0.5, -0.5] + [0.0] * 14
    payload = _rc_channels_payload.build(
        {"scaled_values": channels, "elrs_status": None}
    )
    raw = make_frame(0x16, payload)
    parsed = frame.parse(raw)
    body = parsed.value
    assert body.type == "RC_Channels_Packed"
    assert body.payload.scaled_values[0] == pytest.approx(0.5, abs=0.002)
    assert body.payload.scaled_values[1] == pytest.approx(-0.5, abs=0.002)


def test_parse_flight_mode():
    raw = make_frame(0x21, b"ARMED\x00")
    parsed = frame.parse(raw)
    body = parsed.value
    assert body.type == "Flight_Mode"
    assert body.payload.flight_mode == "ARMED"


def test_parse_battery_sensor():
    # 25.0V = raw 250, 10.0A = raw 100, 1500mAh, 75%
    raw = make_frame(0x08, b"\x00\xfa\x00\x64\x00\x05\xdc\x4b")
    parsed = frame.parse(raw)
    body = parsed.value
    assert body.type == "Battery_Sensor"
    assert body.payload.voltage_v == pytest.approx(25.0, abs=0.1)
    assert body.payload.current_a == pytest.approx(10.0, abs=0.1)
    assert body.payload.remaining_pct == 75


# --- Unknown type / forward compat ---


def test_parse_unknown_type():
    """Unknown types parse without error; payload is Pass (None)."""
    raw = make_frame(0x02, b"\x01\x02\x03\x04")  # GPS, no struct
    parsed = frame.parse(raw)
    body = parsed.value
    assert body.type == "GPS"
    assert body.payload is None


def test_forward_compat_extra_bytes():
    """Extra trailing bytes in a known type are silently ignored."""
    payload = _link_statistics_payload.build(
        {
            "up_rssi_ant1_dbm": -50,
            "up_rssi_ant2_dbm": -55,
            "up_link_quality": 100,
            "up_snr": 10,
            "active_antenna": 0,
            "rf_mode": 4,
            "up_tx_power_mw": 100,
            "down_rssi_ant1_dbm": -60,
            "down_link_quality": 95,
            "down_snr": 8,
            "down_rssi_ant2_dbm": -62,
        }
    )
    # Append 2 hypothetical future bytes before CRC
    raw = make_frame(0x14, payload + b"\xaa\xbb")
    parsed = frame.parse(raw)
    body = parsed.value
    assert body.type == "Link_Statistics"
    assert body.payload.up_rssi_ant1_dbm == -50


# --- CRC validation ---


def test_bad_crc_rejected():
    raw = bytearray(make_frame(0x21, b"OK\x00"))
    raw[-1] ^= 0xFF  # corrupt CRC
    with pytest.raises(ConstructError):
        frame.parse(bytes(raw))


# --- consume_frame ---


def test_consume_frame_basic():
    f1 = make_frame(0x21, b"A\x00")
    f2 = make_frame(0x21, b"B\x00")
    buf = bytearray(f1 + f2)
    r1 = consume_frame(buf)
    assert r1 is not None
    assert r1.value.payload.flight_mode == "A"
    r2 = consume_frame(buf)
    assert r2 is not None
    assert r2.value.payload.flight_mode == "B"
    assert consume_frame(buf) is None
    assert len(buf) == 0


def test_consume_frame_skips_garbage():
    garbage = b"\xff\xfe\xfd"
    f = make_frame(0x21, b"OK\x00")
    buf = bytearray(garbage + f)
    r = consume_frame(buf)
    assert r is not None
    assert r.value.payload.flight_mode == "OK"


def test_consume_frame_incomplete():
    """Incomplete frame stays in buffer for later."""
    f = make_frame(0x21, b"HI\x00")
    buf = bytearray(f[:3])  # only partial
    assert consume_frame(buf) is None
    assert len(buf) == 3  # preserved, waiting for more data


def test_consume_frame_bad_crc_resyncs():
    """Bad CRC skips the sync byte and recovers the next valid frame."""
    bad = bytearray(make_frame(0x21, b"BAD\x00"))
    bad[-1] ^= 0xFF  # corrupt CRC
    good = make_frame(0x21, b"GOOD\x00")
    buf = bytearray(bad + good)
    r = consume_frame(buf)
    assert r is not None
    assert r.value.payload.flight_mode == "GOOD"


def test_consume_frame_bad_length():
    """Frame with absurd length byte is skipped."""
    buf = bytearray(b"\xc8\xff\x00\x00")  # sync + length=255 (>64)
    r = consume_frame(buf)
    assert r is None
