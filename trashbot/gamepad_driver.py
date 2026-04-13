"""Driver for gamepad used to drive Trashbot"""

import evdev
import logging
import select

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
}


class GamepadError(Exception):
    pass


class GamepadDriver:
    def __init__(self, evdev):
        self.evdev = evdev

    def poll_event(self) -> tuple[str, int] | None:
        while True:
            try:
                event = self.evdev.read_one()
            except OSError:
                raise GamepadError("Error reading gamepad")

            if not event:
                return None
            elif event.type == evdev.ecodes.EV_ABS:
                t = AXIS_NAMES.get(event.code) or f"AXIS_{event.code}"
                return (t, event.value)
            elif event.type == evdev.ecodes.EV_KEY:
                t = BUTTON_NAMES.get(event.code) or f"BUTTON_{event.code}"
                return (t, event.value)


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
            _log.warn(f"Error opening input dev {dev_path}")
            continue

        abs_caps = caps.get(evdev.ecodes.EV_ABS, [])
        axes = set(c[0] for c in abs_caps if isinstance(c, tuple))
        if all(c in axes for c in [evdev.ecodes.ABS_X, evdev.ecodes.ABS_Y]):
            _log.info(f"🎮 {dev.name} ({dev.path})")
            return GamepadDriver(dev)
        dev.close()

    raise GamepadError(f"No gamepad found in {len(dev_paths)} input devs")


if __name__ == "__main__":
    main()
