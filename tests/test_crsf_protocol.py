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
        channels=[100 * i for i in range(16)],
        elrs_status=None,
    )
    parsed = trashbot.crsf_protocol.parse_frame(raw)
    assert parsed.type == "RCChannelsPacked"
    assert parsed.channels[0] == 0
    assert parsed.channels[1] == 100
    assert parsed.channels[2] == 200
    assert parsed.channels[15] == 1500


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


# --- Channel <-> signed fraction helpers ---


def test_signed_fraction_from_channel_endpoints():
    sf = trashbot.crsf_protocol.signed_fraction_from_channel
    assert sf(172) == pytest.approx(-1.0)
    assert sf(992) == pytest.approx(0.0, abs=1e-3)
    assert sf(1811) == pytest.approx(1.0)
    # ELRS failsafe sends raw 0, which maps below -1.0
    assert sf(0) < -1.0


def test_channel_from_signed_fraction_endpoints_and_clamp():
    cf = trashbot.crsf_protocol.channel_from_signed_fraction
    assert cf(-1.0) == 172
    assert cf(0.0) == 992
    assert cf(1.0) == 1811
    # Out-of-range inputs are clamped to the valid wire range
    assert cf(-5.0) == 172
    assert cf(5.0) == 1811


def test_channel_signed_fraction_round_trip():
    sf = trashbot.crsf_protocol.signed_fraction_from_channel
    cf = trashbot.crsf_protocol.channel_from_signed_fraction
    for raw in (172, 500, 992, 1300, 1811):
        assert cf(sf(raw)) == raw
