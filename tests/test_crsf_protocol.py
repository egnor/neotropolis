import construct
import pytest

import trashbot.crsf_protocol


# --- Scaled values ---


def test_scaled_round_trip():
    sv = trashbot.crsf_protocol._Scaled(construct.Int8ub, 0.5, 10.0)
    # raw=100 -> 100 * 0.5 + 10 = 60.0
    assert sv.parse(b"\x64") == 60.0
    # 60.0 -> round((60.0 - 10.0) / 0.5) = 100
    assert sv.build(60.0) == b"\x64"


def test_scaled_negative_scale():
    sv = trashbot.crsf_protocol._Scaled(construct.Int8ub, -1)
    # raw=50 -> 50 * -1 = -50
    assert sv.parse(b"\x32") == -50
    assert sv.build(-50) == b"\x32"


# --- Channel encoding ---


def test_channels_center():
    """All zeros should encode to center values and decode back."""
    channels = [0.0] * 16
    encoded = trashbot.crsf_protocol._rc_channels_payload.build(
        {"scaled_values": channels, "elrs_status": None}
    )
    parsed = trashbot.crsf_protocol._rc_channels_payload.parse(encoded)
    for i, v in enumerate(parsed.scaled_values):
        assert abs(v) < 0.001, f"ch{i} center: {v}"


def test_channels_limits():
    """±1.0 should round-trip within 11-bit quantization error."""
    channels = [1.0 if i % 2 == 0 else -1.0 for i in range(16)]
    encoded = trashbot.crsf_protocol._rc_channels_payload.build(
        {"scaled_values": channels, "elrs_status": None}
    )
    parsed = trashbot.crsf_protocol._rc_channels_payload.parse(encoded)
    for i, v in enumerate(parsed.scaled_values):
        assert abs(v - channels[i]) < 0.002, f"ch{i}: {v}"


def test_channel_failsafe_constant():
    parsed = trashbot.crsf_protocol._rc_channels_payload.parse(b"\0" * 22)
    for i, v in enumerate(parsed.scaled_values):
        assert v == trashbot.crsf_protocol.CHANNEL_FAILSAFE, f"ch{i}: {v}"


# --- Frame parsing (known types) ---


def test_parse_link_statistics():
    raw = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.LinkStatistics,
        up_rssi_ant1_dbm=-50,
        up_rssi_ant2_dbm=-55,
        up_link_quality=100,
        up_snr=10,
        active_antenna=0,
        rf_mode=4,
        up_tx_power_mw=100,
        down_rssi_ant1_dbm=-60,
        down_link_quality=95,
        down_snr=8,
        down_rssi_ant2_dbm=-62,
    )
    parsed = trashbot.crsf_protocol.parse_frame(raw)
    assert parsed.type == "LinkStatistics"
    assert parsed.up_rssi_ant1_dbm == -50
    assert parsed.up_link_quality == 100
    assert parsed.down_rssi_ant2_dbm == -62


def test_parse_rc_channels():
    raw = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.RCChannelsPacked,
        scaled_values=[0.5, -0.5] + [0.0] * 14,
        elrs_status=None,
    )
    parsed = trashbot.crsf_protocol.parse_frame(raw)
    assert parsed.type == "RCChannelsPacked"
    assert parsed.scaled_values[0] == pytest.approx(0.5, abs=0.002)
    assert parsed.scaled_values[1] == pytest.approx(-0.5, abs=0.002)


def test_parse_flight_mode():
    raw = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.FlightMode,
        flight_mode="ARMED",
    )
    parsed = trashbot.crsf_protocol.parse_frame(raw)
    assert parsed.type == "FlightMode"
    assert parsed.flight_mode == "ARMED"


def test_parse_battery_sensor():
    # 25.0V = raw 250, 10.0A = raw 100, 1500mAh, 75%
    raw = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.BatterySensor,
        voltage_v=25.0,
        current_a=10.0,
        capacity_used_mah=1500,
        remaining_pct=75,
    )
    parsed = trashbot.crsf_protocol.parse_frame(raw)
    assert parsed.type == "BatterySensor"
    assert parsed.voltage_v == pytest.approx(25.0, abs=0.1)
    assert parsed.current_a == pytest.approx(10.0, abs=0.1)
    assert parsed.remaining_pct == 75


# --- Unknown type / forward compat ---


def test_parse_unknown_type():
    """Unknown types parse without error; payload is Pass (None)."""
    raw = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.GPS
    )
    parsed = trashbot.crsf_protocol.parse_frame(raw)
    assert parsed.type == "GPS"


def test_forward_compat_extra_bytes():
    """Extra trailing bytes in a known type are silently ignored."""
    raw_body = trashbot.crsf_protocol._frame_body.build(
        {
            "type": trashbot.crsf_protocol.frame_type.LinkStatistics,
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
    )

    # Append 2 hypothetical future bytes before CRC
    raw = trashbot.crsf_protocol.frame.build({"data": raw_body + b"\xaa\xbb"})
    parsed = trashbot.crsf_protocol.parse_frame(raw)
    assert parsed.type == "LinkStatistics"
    assert parsed.up_rssi_ant1_dbm == -50


# --- CRC validation ---


def test_bad_crc_rejected():
    raw = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.FlightMode,
        flight_mode="OK",
    )
    edited = bytearray(raw)
    edited[-1] ^= 0xFF  # corrupt CRC
    with pytest.raises(construct.ConstructError):
        trashbot.crsf_protocol.parse_frame(raw[:-1] + bytes([raw[-1] ^ 0xFF]))


# --- consume_frame ---


def test_consume_frame_basic():
    f1 = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.FlightMode,
        flight_mode="A",
    )
    f2 = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.FlightMode,
        flight_mode="B",
    )
    buf = bytearray(f1 + f2)
    r1 = trashbot.crsf_protocol.consume_frame(buf)
    assert r1 is not None
    assert r1.flight_mode == "A"
    r2 = trashbot.crsf_protocol.consume_frame(buf)
    assert r2 is not None
    assert r2.flight_mode == "B"
    assert trashbot.crsf_protocol.consume_frame(buf) is None
    assert len(buf) == 0


def test_consume_frame_skips_garbage():
    f = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.FlightMode,
        flight_mode="OK",
    )
    r = trashbot.crsf_protocol.consume_frame(bytearray(b"\xff\xfe\xfd" + f))
    assert r is not None
    assert r.flight_mode == "OK"


def test_consume_frame_incomplete():
    """Incomplete frame stays in buffer for later."""
    f = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.FlightMode,
        flight_mode="HI",
    )
    buf = bytearray(f[:3])  # only partial
    assert trashbot.crsf_protocol.consume_frame(buf) is None
    assert len(buf) == 3  # preserved, waiting for more data


def test_consume_frame_bad_crc_resyncs():
    """Bad CRC skips the sync byte and recovers the next valid frame."""
    bad = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.FlightMode,
        flight_mode="BAD",
    )
    good = trashbot.crsf_protocol.build_frame(
        type=trashbot.crsf_protocol.frame_type.FlightMode,
        flight_mode="GOOD",
    )
    raw = bytearray(bad[:-1] + bytes([bad[-1] ^ 0xFF]) + good)
    r = trashbot.crsf_protocol.consume_frame(raw)
    assert r is not None
    assert r.flight_mode == "GOOD"


def test_consume_frame_bad_length():
    """Frame with absurd length byte is skipped."""
    # sync + length=255 (>64)
    r = trashbot.crsf_protocol.consume_frame(bytearray(b"\xc8\xff\x00\x00"))
    assert r is None
