"""Driver for gamepad used to drive Trashbot"""

import evdev
import logging
from typing import cast

_log = logging.getLogger(__name__)

AXIS_NAMES = {
    evdev.ecodes.ABS_X: "LX",
    evdev.ecodes.ABS_Y: "LY",
    evdev.ecodes.ABS_Z: "LT",
    evdev.ecodes.ABS_RX: "RX",
    evdev.ecodes.ABS_RY: "RY",
    evdev.ecodes.ABS_RZ: "RT",
    evdev.ecodes.ABS_HAT0X: "DX",
    evdev.ecodes.ABS_HAT0Y: "DY",
}

BUTTON_NAMES = {
    evdev.ecodes.BTN_SOUTH: "A",
    evdev.ecodes.BTN_EAST: "B",
    evdev.ecodes.BTN_NORTH: "X",
    evdev.ecodes.BTN_WEST: "Y",
    evdev.ecodes.BTN_TL: "LB",
    evdev.ecodes.BTN_TR: "RB",
    evdev.ecodes.BTN_SELECT: "SELECT",
    evdev.ecodes.BTN_START: "START",
    evdev.ecodes.BTN_MODE: "GUIDE",
    evdev.ecodes.BTN_THUMBL: "LS",
    evdev.ecodes.BTN_THUMBR: "RS",
    evdev.ecodes.KEY_RECORD: "RECORD",
}


class GamepadError(Exception):
    pass


class GamepadDriver:
    def __init__(self, *, dev: evdev.InputDevice, caps: dict):
        self.evdev = dev
        self.axis_info = dict(caps.get(evdev.ecodes.EV_ABS, []))
        self.recent: dict[str, int] = {}

    def poll_event(self) -> tuple[str, int] | None:
        while True:
            try:
                ev = self.evdev.read_one()
            except OSError:
                raise GamepadError("Error reading gamepad")

            if not ev:
                return None

            out_type, out_value = "", 0
            if ev.type == evdev.ecodes.EV_ABS:
                out_type = AXIS_NAMES.get(ev.code) or f"AXIS_{ev.code}"
                if ev.value and (info := self.axis_info.get(ev.code)):
                    limit = -info.min if ev.value < 0 else info.max
                    out_value = ev.value / limit
                else:
                    out_value = ev.value
            elif ev.type == evdev.ecodes.EV_KEY:
                out_type = BUTTON_NAMES.get(ev.code) or f"BUTTON_{ev.code}"
                out_value = ev.value

            if out_type:
                self.recent[out_type] = out_value
                return (out_type, out_value)


def connect() -> GamepadDriver:
    _log.info("🔎 Scanning for gamepad...")

    try:
        dev_paths = evdev.list_devices()
    except OSError:
        raise GamepadError("Error listing input devices")

    for dev_path in dev_paths:
        try:
            dev = evdev.InputDevice(dev_path)
            caps = dev.capabilities()
        except OSError:
            _log.warning(f"Error opening input dev {dev_path}")
            continue

        abs_caps = cast(
            list[tuple[int, evdev.AbsInfo]],
            caps.get(evdev.ecodes.EV_ABS, []),
        )
        axes = {c[0] for c in abs_caps}
        if all(c in axes for c in (evdev.ecodes.ABS_X, evdev.ecodes.ABS_Y)):
            _log.info(f"🎮 {dev.name} ({dev.path})")
            return GamepadDriver(dev=dev, caps=caps)
        dev.close()

    raise GamepadError(f"No gamepad found in {len(dev_paths)} input devs")
