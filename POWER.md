# Trashbot Pi 5V power delivery

Design notes for the Pi's 5V supply path. See `TRASHBOT.md` for overall
system context.

## Current architecture

```
24V BAT ── 24V→12V DCDC (20A) ── 12V rail (shared with video Tx, etc.)
                                      │
                                      └── 6 ft 18 AWG, XT30 inline ──┐
                                                                     │
                        (inside Pi enclosure / "top hat", sealed)    │
                                                                     │
      12V→5V DCDC (10A) ◄──────────────────────────────────────────┘
             │
             ├── short pigtail → USB-C screw terminal → Pi
             └── ELRS RX, etc.
```

- 24V→12V DCDC (20A, 20–60V input): <https://www.amazon.com/dp/B0CS2KJSKS>
- 12V→5V DCDC (10A, 8–32V input): <https://www.amazon.com/dp/B0GHK3B5YS>

The 6 ft wire carries **12V**, not 5V. Step-down to 5V happens locally,
inches from the Pi.

**Why this works:**

- Pi power at 12V = ~2.3A on the long wire (vs ~5A at 5V for same load,
  accounting for ~90% DCDC efficiency).
- Wire voltage drop scales linearly with current: ~0.46× the drop.
- Wire power loss scales with I²: ~0.21× the heat in the wire.
- The local DCDC's 8–32V input range absorbs any remaining drop — the Pi
  sees regulated 5V regardless of what happens on the long run.
- All 12V connectors elsewhere on the bot are XT30; convention preserved.

## Measured behavior

Under combined stress (`stress-ng` all cores + `iperf3 -u -b 100M` + `fio`
random-write with fsync, plus a Claude Code session):

| State  | `EXT5V_V` |
| ------ | --------: |
| Idle   | ~5.18V    |
| Stress | ~5.11V (never observed below 5.10V) |

Undervoltage threshold is ~4.63V, so headroom is ~0.48V under worst-case
observed load. No undervoltage events logged. `vcgencmd get_throttled`
stays clean.

## Open concerns / followups

**Thermal.** The top hat now contains Pi + local 12V→5V DCDC + USB-CAN +
ELRS RX, all on magnet feet for standoff ventilation but with the box
sealed. DCDC dissipates ~3W under full Pi load. Knockouts with vents are
available; tradeoff is ventilation vs. dust ingress (target environment is
dusty). **Plan:** monitor temperatures during extended operation, pop
knockouts in the field if needed.

**Bulk cap deferred.** A 470–1000µF low-ESR cap at the Pi 5V input was in
the original plan. Current margins are so comfortable it's not worth the
effort yet. Keep in back pocket if undervoltage returns.

**USB-C screw terminal at Pi end** is not ideal (~35mΩ per leg measured),
but the run is now only a few inches and the current is regulated by the
local DCDC, so it's not a meaningful problem. Dupont-to-GPIO would be
cleaner but the DCDC pigtails are too thick for Dupont crimps — would
require a splice. Revisit only if problems resurface.

**No EMI / ripple filtering installed.** The local DCDC is a cheap
switching module; its output likely has 50–200mVpp of switching ripple and
couples HF noise onto the shared 12V rail. Nothing has been measured with
a scope yet. Candidate additions if problems appear:

- Clip-on ferrite or inline ferrite bead on the 12V input to the local
  DCDC — kills HF conducted noise coming in from (or going out to) the
  shared 12V rail.
- Same on the 5V output going into the Pi, if PMIC behavior gets twitchy.
- LC pi filter on the output if ripple turns out to matter for anything
  downstream (probably doesn't — the Pi PMIC has its own regulation).

**Ripple not characterized.** `EXT5V_V` looks steady under stress, but
`vcgencmd pmic_read_adc` samples too slowly to see switching ripple (the
DCDC likely runs at hundreds of kHz; the ADC samples at best tens of Hz).
A scope measurement across the Pi 5V pins during stress would be the real
check. Not doing it preemptively because current symptoms are fine.

## Stress / regression procedure

Run concurrently and watch `dmesg -w` + `EXT5V_V`:

```bash
# CPU
stress-ng --cpu $(nproc) --cpu-method matrixprod -t 120s

# NVMe (bursty, fsync-heavy — mimics apt install)
fio --name=rand --filename=/var/tmp/fiotest --size=2G --rw=randwrite \
    --bs=4k --direct=1 --fsync=1 --runtime=120 --time_based

# WiFi (TX bursts — current-hungry direction)
iperf3 -c <host> -u -b 100M -t 120

# Log PMIC 5V at 10Hz
while true; do vcgencmd pmic_read_adc | grep EXT5V_V; sleep 0.1; done \
  | ts '%H:%M:%.S' > volts.log

# Watch sticky throttle bits
watch -n 0.5 'vcgencmd get_throttled; vcgencmd pmic_read_adc | grep EXT5V'
```

In the **original** configuration, `iperf3 -u -b 100M` + `stress-ng`
hard-crashed the Pi (PMIC cut power, required power cycle). Current
configuration runs the full trio with >0.4V of headroom.

## History (what was tried before this worked)

**Original design** ran 5V directly up the 6 ft 18 AWG wire with
screw-terminal USB-C adapters inline and at the Pi. Total round-trip
resistance ~250mΩ (77mΩ wire + 140mΩ connectors + ~30–50mΩ inside the
Pi). Symptoms:

- Intermittent `hwmon4: Undervoltage detected!` / `Voltage normalised`
  pairs in `dmesg`, 2.0s apart (driver hysteresis, not actual duration).
- Sticky bits in `get_throttled` (0x50000 = bits 16+18: undervoltage +
  throttling have occurred).
- Under `stress-ng` + `iperf3 -u -b 100M`: hard crash, cold power cycle.

**Incremental fix that helped but wasn't enough:** inline USB-C screw
terminal → hand-soldered XT60, Dupont-to-GPIO at the Pi end. Reduced
each leg from ~95mΩ to ~70mΩ. Still not enough — the 18 AWG wire alone
was ~77mΩ round-trip, and the 6 ft run was not practical to replace
(stuffed through a chain of pipes).

**Actual fix:** raise voltage on the long wire to 12V, step down locally.
Current architecture above. No changes needed to the 6 ft wire itself.

## Reference: Pi 5 throttle bits

| Bit | Mask    | Meaning                               |
| --: | ------: | ------------------------------------- |
| 0   | 0x1     | Under-voltage detected (current)      |
| 1   | 0x2     | Arm frequency capped (current)        |
| 2   | 0x4     | Currently throttled (current)         |
| 3   | 0x8     | Soft temperature limit (current)      |
| 16  | 0x10000 | Under-voltage has occurred (sticky)   |
| 17  | 0x20000 | Arm frequency capping has occurred    |
| 18  | 0x40000 | Throttling has occurred (sticky)      |
| 19  | 0x80000 | Soft temperature limit has occurred   |

Low nibble = right now. High nibble = since last boot. Sticky bits clear
only on reboot or `vcgencmd get_throttled 0x0` (newer firmware).
