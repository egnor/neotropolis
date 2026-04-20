# Trashbot design notes

Trashbot is a modest, low speed remotely operated tank-tread ground vehicle
to be a mission component for
[Crux Industries](https://theimmersivemachine.com/faq-page/crux/),
a faction at [Neotropolis](https://www.neotropolis.com/), a cyberpunk-themed
immersive event/festival in Southern California.

Neotropolis attendees will operate the bot (with supervision) using
a camera view and a controller and accomplish various tasks. Operators
will have camera and audio feed but only be able to communicate back
by choosing emoji to display on LED panels which are the robot's "eyes".
Creative interactions "in the wild" with passersby will likely be
part of mission goals for operators.

## Components

Onboard power, propulsion, and control

- [TR500S robot chassis](https://www.ebay.com/itm/184923700908?var=692710822231)
- 24V, 10AH lithium battery
- 2x [ODrive S1](https://docs.odriverobotics.com/v/latest/hardware/s1-datasheet.html)
  motor controllers
- [20-60V→12V 20A DC-DC](https://www.amazon.com/dp/B0CS2KJSKS) feeds a
  shared 12V rail (video Tx, microphone, camera, and Pi top-hat subsystem)
- [8-32V→5V 10A DC-DC](https://www.amazon.com/dp/B0GHK3B5YS) inside the Pi
  enclosure steps 12V down to 5V locally for the Pi and ELRS RX
- See [POWER.md](POWER.md) for power delivery details and history
- [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/)
- [ODrive USB-CAN adapter](https://shop.odriverobotics.com/products/usb-can-adapter)

Remote control link (operator to trashbot, bidirectional)

- [ExpressLRS](https://www.expresslrs.org/) over LoRa, using
  [CRSF protocol](https://github.com/tbs-fpv/tbs-crsf-spec/blob/main/crsf.md)
  (16ch 11-bit @ up to 200Hz, plus telemetry return)
- [RadioMaster Nomad Dual 1W Gemini Xrossband](https://radiomasterrc.com/products/nomad-dual-1w-gemini-xrossband-elrs-rf-module)
  TX module (2x LR1121, simultaneous 2.4GHz + 900MHz, 1W, ~$58)
- [RadioMaster DBR4](https://radiomasterrc.com/products/dbr4-dual-band-xross-gemini-receiver)
  dual-band Gemini Xrossband RX (2x LR1121, 100mW telemetry, ~$39)
- TX module connects to operator Pi via USB-C (remapped to CRSF I/O,
  full-duplex; configure at `elrs_tx.local/hardware.html`).
  Needs external 7-13V power for the RF PA.
- RX module connects to robot Pi via UART (separate TX/RX pins, 3.3V TTL,
  420kbaud on `/dev/ttyAMA0` with `dtoverlay=uart0-pi5`).
  Powered from robot 5V rail.
- Operator Pi reads gamepad + StreamDeck, maps to CRSF channels, sends
  to TX module. Robot Pi decodes channels into motor/emoji/lighting commands.
- Telemetry (battery, RSSI, link quality) flows back via CRSF return path.
- ref: [Devana Project: send commands from Pi](https://thedevanaproject.com/2025/01/27/how-to-send-rc-commands-with-a-raspberry-pi-and-elrs-transmitter-module/)
- ref: [Devana Project: decode commands on Pi](https://thedevanaproject.com/2025/01/20/how-to-decode-rc-commands-from-an-elrs-receiver-module-with-a-raspberry-pi/)
- ref: [crsf-parser Python library](https://github.com/AlessioMorale/crsf_parser)
- ref: [elrs-joystick-control (USB CRSF)](https://github.com/kaack/elrs-joystick-control)

Emoji displays ("eyes")

- 2x [Beetronics 10" industrial HDMI monitor](https://www.beetronics.com/10-inch-monitor-4-3)
  (9.7" diagonal, 1024x768 native, 4:3) -- installed and working

Remote audio/video (trashbot to operator)

- [8W 1.3GHz analog VTX/VRX](https://www.kimpok.com/sale-51038869-1-2g-1-3g-fpv-vrx-vtx-8w-wireless-video-receiver-and-transmitter-long-range-transmission.html)
  - Tx pigtail (10cm) JST-PH: GND, audio, 12V, video
  - Tx PCB Picoblade: GND, audio, 12V, video
- [Foxeer T-Rex Mini analog camera](https://www.foxeer.com/foxeer-t-rex-mini-1500tvl-6ms-low-latency-super-wdr-fpv-camera-g-314)
  - 5-pin Picoblade: VCC, GND, VID, (OSD), (VSEN)
- [CCTV 12V microphone](https://www.amazon.com/dp/B07G88FY8M)
  - pigtail with GND, +12V, audio out
- ref: [Oscar Liang's guide to analog FPV](https://oscarliang.com/1-2ghz-fpv-guide/)
- ref: [Oscar Liang's antenna guide](https://oscarliang.com/best-fpv-antenna/)
  (his other guides are good too)

Operator control station

- [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/)
- TV (with CVBS input) for video feed
- Display for system status (armed state, battery, RSSI, link quality)
- Second display or StreamDeck keys for status (battery, RSSI, link quality)
- USB gamepad for driving the robot
- [StreamDeck XL](https://www.elgato.com/us/en/p/stream-deck-plus-xl) for
  emoji selection, lighting control, and other aux functions
- ref: [streamdeck Python library](https://github.com/abcminiuser/python-elgato-streamdeck)

## Control channel mapping

Using ELRS "Wide" switch mode (default in firmware v3+) at 150-250Hz packet
rate. The RX auto-follows whatever mode the TX is configured for; only TX
needs config.

| Ch    | Role (AETR) | Use                        | Over-the-air resolution |
|-------|-------------|----------------------------|-------------------------|
| 1     | aileron     | steering                   | 10 bit, every packet    |
| 2     | elevator    | left eye emoji             | 10 bit, every packet    |
| 3     | throttle    | drive throttle (fwd/back)  | 10 bit, every packet    |
| 4     | rudder      | right eye emoji            | 10 bit, every packet    |
| 5     | aux1        | arm                        | 1 bit, every packet     |
| 6     | aux2        | radio PTT (bool)           | 6 bit, round-robin ~/7  |
| 7-12  | aux3-8      | LED effects / TBD          | 6 bit, round-robin ~/7  |
| 13-16 | -           | unused in Wide mode        | -                       |

Encoding emoji on the stick channels (ele/rud) instead of splitting across
aux channels is deliberate: 10 bit = 1024 slots fits the ~1400 base emoji
count (after trimming skin tones, gender ZWJ sequences, and flags) with a
little curation. A stock R/C controller will cycle through emoji when the
right stick moves -- harmless -- and ch1/ch3 still drive the bot with no
radio config. No commit protocol is needed: a dropped packet just stales
the last value, never tears a split index.

### CRSF / ELRS bit encoding

CRSF carries 11 bits per channel on the wire (0-2047). The "normal" servo
range 172-1811 maps linearly to 988-2012µs pulse widths (1500µs center
at 992, scale 8/5 ticks per µs); values outside that range are "extended
limits" used by ELRS to signal failsafe (raw 0) or overdrive.

ELRS packs stick channels into 10 bits OTA, so 1024 distinct values survive
end-to-end, not 2048. The CRSF -> OTA -> CRSF round trip is NOT the identity
for arbitrary CRSF values -- it snaps to the nearest OTA grid point. To
transmit a 10-bit index N losslessly, encode on the grid explicitly:

    crsf_raw = 172 + round(N * 1639 / 1023)     # 1639 = 1811 - 172
    N        = round((crsf_raw - 172) * 1023 / 1639)

Aux channels in Wide mode carry 6 bits OTA (64 positions, spread across a
subset of the CRSF range in ~25-unit steps). Hybrid mode uses a different
encoding for ch6-11 (3 bit / 6 position), so standardize on Wide mode to
keep aux grids stable across TX setups.

## Open Questions

- RANGE: ELRS Gemini Xrossband should give 1-3km+ even at ground level in a
  crowded RF environment. Probably fine for around the megablock; roaming the
  city would need real-world testing. WiFi is not needed for the control link.
- WIFI: Another faction is promising an enterprise-grade WiFi deployment, but
  it's not clear they'll come through, or that it would perform well. Not
  needed for control or video (both have dedicated radio links), but could be
  useful for software updates, monitoring, or a secondary data channel.
- OPERATOR UX: What does the control station look like? What gamepad?
