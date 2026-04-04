# ODrive Python API Cheat Sheet (0.6.11.dev1)

The docs at docs.odriverobotics.com still say CAN support is "coming soon" and
point to raw `python-can` examples. **That's outdated.** Version 0.6.11.dev1
has full CAN support built in. This cheat sheet documents the actual API from
reading the installed package source.

## Connection & Discovery

```python
import odrive

# Over SocketCAN (our setup: USB-CAN adapter exposed as can0)
odrv = odrive.find_sync(interfaces=["can:can0"])

# Multiple devices
odrv1, odrv2 = odrive.find_sync(interfaces=["can:can0"], count=2)

# By serial number
odrv = odrive.find_sync(serial_number="3561396F3231", interfaces=["can:can0"])

# With timeout (seconds)
odrv = odrive.find_sync(interfaces=["can:can0"], timeout=10)

# Async version (for asyncio code)
odrv = await odrive.find_async(interfaces=["can:can0"])
```

**Interface strings:**
- `"can:can0"` — Linux SocketCAN (our case)
- `"usb"` — USB direct
- `"usbcan"` or `"usbcan:1000000"` — ODrive USB-CAN adapter with optional baudrate
- Default (no `interfaces` arg) = `{"usb", "usbcan"}`

## Sync vs Async

`find_sync()` returns a `SyncObject` — property access is direct and blocking:
```python
pos = odrv.axis0.pos_estimate          # read
odrv.axis0.controller.input_vel = 5.0  # write
odrv.save_configuration()              # function call
```

`find_async()` returns an `AsyncObject` — must use `.read()`/`.write()`:
```python
pos = await odrv.axis0.pos_estimate.read()
await odrv.axis0.controller.input_vel.write(5.0)
await odrv.save_configuration()
```

Both are dynamically generated from the device's JSON endpoint schema.
The property tree is the same as what odrivetool shows.

## Axis States & Calibration

```python
from odrive.enums import AxisState

# Request a state change
odrv.axis0.requested_state = AxisState.FULL_CALIBRATION_SEQUENCE
odrv.axis0.requested_state = AxisState.CLOSED_LOOP_CONTROL
odrv.axis0.requested_state = AxisState.IDLE

# Read current state
state = odrv.axis0.current_state  # AxisState enum value
```

Key states:
| State | Value | Use |
|-------|-------|-----|
| `IDLE` | 1 | Motor off |
| `FULL_CALIBRATION_SEQUENCE` | 3 | Motor + encoder calibration |
| `MOTOR_CALIBRATION` | 4 | Motor only |
| `ENCODER_OFFSET_CALIBRATION` | 7 | Encoder only |
| `CLOSED_LOOP_CONTROL` | 8 | Active control |
| `HOMING` | 11 | Find home position |

## Control Modes

```python
from odrive.enums import ControlMode, InputMode

# Velocity control
odrv.axis0.controller.config.control_mode = ControlMode.VELOCITY_CONTROL
odrv.axis0.controller.config.input_mode = InputMode.PASSTHROUGH
odrv.axis0.controller.input_vel = 2.0  # turns/sec

# Velocity with ramp
odrv.axis0.controller.config.input_mode = InputMode.VEL_RAMP
odrv.axis0.controller.config.vel_ramp_rate = 0.5  # turns/sec^2
odrv.axis0.controller.input_vel = 2.0

# Position control
odrv.axis0.controller.config.control_mode = ControlMode.POSITION_CONTROL
odrv.axis0.controller.config.input_mode = InputMode.PASSTHROUGH
odrv.axis0.controller.input_pos = 10.0  # turns

# Trapezoidal trajectory
odrv.axis0.controller.config.input_mode = InputMode.TRAP_TRAJ
odrv.axis0.trap_traj.config.vel_limit = 2.0
odrv.axis0.trap_traj.config.accel_limit = 0.5
odrv.axis0.trap_traj.config.decel_limit = 0.5
odrv.axis0.controller.input_pos = 10.0

# Torque control
odrv.axis0.controller.config.control_mode = ControlMode.TORQUE_CONTROL
odrv.axis0.controller.input_torque = 0.5  # Nm
```

## Reading Feedback

```python
odrv.axis0.pos_estimate        # position [turns]
odrv.axis0.vel_estimate        # velocity [turns/sec]
odrv.axis0.motor.torque_estimate
odrv.axis0.motor.mechanical_power
odrv.axis0.motor.electrical_power
odrv.axis0.current_state       # AxisState enum
odrv.axis0.active_errors       # ODriveError flags
odrv.axis0.disarm_reason       # why it stopped
odrv.vbus_voltage              # bus voltage [V]
odrv.ibus                      # bus current [A]
```

## Error Handling

```python
from odrive.enums import ODriveError

errors = odrv.axis0.active_errors  # ODriveError IntFlag
if errors != ODriveError.NONE:
    print(f"Errors: {errors}")

odrv.clear_errors()  # clear and re-arm
```

Key error flags: `DC_BUS_OVER_VOLTAGE`, `DC_BUS_UNDER_VOLTAGE`,
`CURRENT_LIMIT_VIOLATION`, `VELOCITY_LIMIT_VIOLATION`,
`WATCHDOG_TIMER_EXPIRED`, `CALIBRATION_ERROR`

## Configuration

```python
# Motor config
odrv.axis0.config.motor.pole_pairs = 7
odrv.axis0.config.motor.torque_constant = 0.04  # Nm/A (8.27 / KV)
odrv.axis0.config.motor.current_soft_max = 20.0  # A
odrv.axis0.config.motor.calibration_current = 5.0  # A

# Controller gains
odrv.axis0.controller.config.pos_gain = 20.0
odrv.axis0.controller.config.vel_gain = 0.16
odrv.axis0.controller.config.vel_integrator_gain = 0.32
odrv.axis0.controller.config.vel_limit = 10.0  # turns/sec

# Encoder selection (0.6.11 style - encoders are top-level objects)
from odrive.enums import EncoderId
odrv.axis0.config.load_encoder = EncoderId.ONBOARD_ENCODER0
odrv.axis0.config.commutation_encoder = EncoderId.ONBOARD_ENCODER0

# CAN config
odrv.config.can.baud_rate = 1000000  # or leave for autobaud (0.6.11)

# Persist to NVM (triggers reboot!)
odrv.save_configuration()

# Factory reset
odrv.erase_configuration()

# Reboot without saving
odrv.reboot()
```

## CAN-Specific Notes

- **Autobaud** (new in 0.6.11): ODrive auto-detects CAN baudrate. No need
  to pre-configure it to match.
- **Node IDs**: 0-62. 0x3f (63) is the unaddressed/broadcast ID.
- **Discovery**: The library handles CAN discovery automatically via the
  same `find_sync()`/`find_async()` API. Unaddressed devices (node_id=0x3f)
  are discovered and can be assigned node IDs.
- **Node ID assignment**: After discovery, configure with
  `odrv.config.can.node_id = N` then `odrv.save_configuration()`.
- CAN node ID changes require a reboot (which save_configuration triggers).

## Device Lost / Reconnection

```python
from odrive import DeviceLostException

try:
    odrv.axis0.controller.input_vel = 1.0
except DeviceLostException:
    # Device disconnected - need to find_sync() again
    odrv = odrive.find_sync(interfaces=["can:can0"])
```

## Watchdog

```python
# Enable watchdog (device faults if not fed within timeout)
odrv.axis0.config.watchdog_timeout = 0.5  # seconds, 0 = disabled

# Feed the watchdog
odrv.axis0.watchdog_feed()
```

## Property Tree Overview

The full tree is large (see `flat_endpoints.json`). Key branches:
```
odrv
├── vbus_voltage, ibus, serial_number
├── config.can.node_id, config.can.baud_rate
├── save_configuration(), reboot(), erase_configuration(), clear_errors()
└── axis0
    ├── current_state, requested_state, active_errors, disarm_reason
    ├── pos_estimate, vel_estimate, is_homed
    ├── watchdog_feed(), set_abs_pos()
    ├── config
    │   ├── motor.pole_pairs, .torque_constant, .current_soft_max, ...
    │   ├── load_encoder, commutation_encoder
    │   └── watchdog_timeout, enable_watchdog
    ├── controller
    │   ├── input_pos, input_vel, input_torque
    │   └── config.control_mode, .input_mode, .vel_limit, .pos_gain, ...
    ├── motor.torque_estimate, .mechanical_power, .electrical_power
    └── trap_traj.config.vel_limit, .accel_limit, .decel_limit
```

Encoders are top-level (not under axis): `onboard_encoder0`, `hall_encoder0`,
`spi_encoder0`, `inc_encoder0`, etc.

## Key Differences from Older Docs / Examples

1. **CAN works natively** — no need for raw `python-can` or `cantools`.
   Just pass `interfaces=["can:can0"]` to `find_sync()`.

2. **Encoder objects restructured** — encoders are now top-level objects
   (e.g., `odrv.onboard_encoder0`), not nested under axis. The axis just
   references them by `EncoderId`.

3. **Async support** — `find_async()` + `await prop.read()` / `await
   prop.write(val)` for asyncio integration.

4. **No `run_state()` / `request_state()` helpers** — just set
   `odrv.axis0.requested_state` directly and poll `current_state` if needed.

5. **Error model simplified** — `active_errors` is a single `ODriveError`
   IntFlag on the axis (no separate motor/encoder/controller error fields).
