# Trashbot Pi 5V power delivery notes

Diagnostic notes and improvement plan for the Pi's 5V supply path.
Background context lives in `TRASHBOT.md`; this file is specifically about
the 24V→5V→Pi chain and the undervoltage issues observed on it.

## The problem

Pi 5 occasionally logs undervoltage events:

```
hwmon hwmon4: Undervoltage detected!
hwmon hwmon4: Voltage normalised
```

The "Voltage normalised" timestamp is always exactly 2.0s after "detected";
that's driver hysteresis, not actual event duration. Real dip is likely
sub-millisecond.

`vcgencmd get_throttled` returns sticky bits after events:

- `0x10000` (bit 16) = under-voltage has occurred
- `0x40000` (bit 18) = throttling has occurred
- Cleared only on reboot (or `vcgencmd get_throttled 0x0` on newer firmware)

Worst case: a combined stress test (stress-ng + iperf3 UDP flood) hard-killed
the Pi — PMIC tripped, required power cycle. Also caused a window of bad WiFi
post-reboot (see separate HDMI EMI issue — not power-related, unplug HDMI to
fix).

## Power path

```
7S VBAT ── DCDC ── pigtail ── Wago ── short wire ── USB-C F/M ── 6ft 18AWG ── USB-C M → Pi
```

- DCDC: [24V/12V-to-5V 10A](https://www.amazon.com/dp/B0FD6M8D7K), no
  adjustable output, no remote sense
- 6ft run: 18 AWG, stuffed through pipes (awkward to replace)
- Connectors: screw-terminal USB-C adapters in the middle of the run

## Resistance budget (baseline, approximate)

| Segment             | Round-trip mΩ | Notes                               |
| ------------------- | ------------: | ----------------------------------- |
| 6 ft 18 AWG         |          ~77  | 6.39 mΩ/ft × 6 ft × 2 legs          |
| USB-C screw pair #1 |          ~70  | 2 legs × 35 mΩ measured             |
| USB-C screw pair #2 |          ~70  | 2 legs × 35 mΩ (assumed similar)    |
| Pi internal USB-C path | ~30–50     | undocumented, estimated             |
| **Total**           |     **~250**  |                                     |

At 3 A load: ~0.75 V drop. At 5 A peak: ~1.25 V drop.

Measured sag under stress: 5.19V (unloaded at connector) → 4.79V
(`EXT5V_V` under stress-ng + iperf3), implying ~1.6 A average during
that test. Transient spikes to 4+ A blow through the undervoltage
threshold.

The USB-C screw terminals are the single biggest line-item. Screw-terminal
USB-C is notoriously bad: intermittent contact, small surface area, loosens
over time. Spec for a decent mated USB-C pair is ~10–15 mΩ per leg; measured
35 mΩ suggests these are marginal even when freshly torqued.

## Planned improvements (prioritized by bang/buck)

1. **Replace the USB-C screw-terminal inline connector with XT60.** Different
   form factor from the 12V XT30s already on the bot (XT60 > XT30), avoids
   confusion. Hand-soldered XT60 is <5 mΩ per contact. Biggest single win.

2. **Bypass the Pi's USB-C input entirely — feed 5V into GPIO pins 2/4, GND
   on pin 6 or 9.** Eliminates the second USB-C mating pair (~70 mΩ). Pi 5
   accepts this fine; it just loses USB-PD negotiation (irrelevant with a
   fixed supply).

   Use genuine Amphenol Mini-PV / Dupont pins with proper crimper (already
   on hand). Real pins are rated ~3 A each, ~10–20 mΩ contact. Two pins in
   parallel on 5V and two on GND gives 6 A budget at ~5 mΩ round trip.

   Pi 5 pins 2 and 4 are the same 5V rail on the PCB (same for all GND pins),
   so paralleling is free. Easiest wiring: a separate small Dupont shell on
   pins 2 and 9 for power input, leave the existing ELRS connector on pins
   4/6/8/10 untouched. ELRS taps 5V from the same rail it's already on.

3. **Upgrade the 6 ft run from 18 AWG to 14 AWG.** Drops the wire from ~77
   to ~30 mΩ round trip, saves 0.24 V at 5 A. Only worth doing if the pipes
   are already opened up. 14 AWG won't crimp into Dupont directly — solder-
   splice a 6" 18 AWG pigtail at the Pi end (adds <4 mΩ, negligible) and
   crimp the Dupont pins on that.

4. **Bulk cap at the Pi end.** 1000–2200 µF low-ESR across the 5V rail,
   plus 1–10 µF ceramic in parallel for HF. Won't fix IR drop, but kills the
   sub-ms transients that trip the PMIC. Cheap regardless of other fixes.

5. **Shopping list for a better DCDC (future):** adjustable output (+0.3 V
   trim to compensate for remaining drop) and/or remote sense. Candidates:
   - Pololu D36V50F5 — 5V fixed, 5.5 A, compact, reputable
   - DROK / generic adjustable 5 A buck — cheap, trimpot-adjustable
   - Murata OKR-T/10 — adjustable, through-hole, industrial grade
   - Recom RPM / Vicor — remote-sense capable, overkill for this

## Baseline measurement procedure

Before making changes, record resistances with the milliohm meter (Kelvin
probes) so improvements are quantifiable.

**Full-path loop resistance:**

1. Disconnect DCDC output and Pi end.
2. At the Pi end, short +5V to GND (stub wire between USB-C power pins, or
   across two Dupont pins).
3. Kelvin-probe at the DCDC output terminals.
4. Reading = round-trip loop resistance.

**Per-segment breakdown** (unmate one interface at a time, Kelvin-probe that
segment alone; do + and − legs separately):

| Segment              | + leg mΩ | − leg mΩ | Notes |
| -------------------- | -------: | -------: | ----- |
| DCDC → Wago          |          |          |       |
| Wago → USB-C #1      |          |          |       |
| USB-C #1 mated       |    35    |    35    | existing measurement |
| 6 ft 18 AWG          |   ~38    |   ~38    | (~30 after 14 AWG swap) |
| USB-C #2 mated       |          |          |       |
| Pi USB-C shell/VBUS  |          |          | internal beyond this |
| **TOTAL**            |          |          |       |

**Gotchas:**

- Milliohm meter uses µA; contact resistance under 5 A load can be lower
  (wetted contacts) or worse (oxide breakdown). Relative improvements are
  meaningful; absolute predictions to the Pi's PMIC are not.
- Do a wiggle test at each connector — big swings = marginal joint.
- Re-mate / re-torque before final reading. First mate after idle sits
  higher than re-mated.
- Temperature: ~0.4%/°C for copper; let things cool before baseline.

**Complementary under-load check:**

```bash
# Log PMIC ADC during a stress run
while true; do
  vcgencmd pmic_read_adc | grep EXT5V_V
  sleep 0.1
done | ts '%H:%M:%.S' > volts.log

# Stress in another window
stress-ng --cpu $(nproc) --cpu-method matrixprod -t 60s &
iperf3 -c skully.local -u -b 100M -t 60
```

Simultaneously meter the DCDC output. ΔV between DCDC and Pi under load,
divided by current, = real-world effective path resistance. Compare to the
milliohm-meter sum.

## Repro / stress procedure

Generate combined load to exercise the power path:

```bash
# Pane 1: CPU
stress-ng --cpu $(nproc) --cpu-method matrixprod -t 120s

# Pane 2: NVMe (bursty, fsync-heavy — mimics apt install)
fio --name=rand --filename=/var/tmp/fiotest --size=2G --rw=randwrite \
    --bs=4k --direct=1 --fsync=1 --runtime=120 --time_based

# Pane 3: WiFi (TX bursts — current-hungry direction)
iperf3 -c <host> -u -b 100M -t 120
# CAUTION: UDP flood + stress-ng has hard-crashed this Pi before

# Pane 4: watch it trip
dmesg -w

# Log sticky throttle bits
watch -n 0.5 'vcgencmd get_throttled; vcgencmd pmic_read_adc | grep EXT5V'
```

`iperf3 -u -b 100M` alone doesn't crash the Pi; stacked with stress-ng it
caused a hard power cut in baseline configuration. Use that combination as
the regression test after each improvement.

## Reference: Pi 5 throttle bits

| Bit     | Mask    | Meaning                               |
| ------: | ------: | ------------------------------------- |
| 0       | 0x1     | Under-voltage detected (current)      |
| 1       | 0x2     | Arm frequency capped (current)        |
| 2       | 0x4     | Currently throttled (current)         |
| 3       | 0x8     | Soft temperature limit (current)      |
| 16      | 0x10000 | Under-voltage has occurred (sticky)   |
| 17      | 0x20000 | Arm frequency capping has occurred    |
| 18      | 0x40000 | Throttling has occurred (sticky)      |
| 19      | 0x80000 | Soft temperature limit has occurred   |

Low nibble = right now. High nibble = since last boot / reset.
