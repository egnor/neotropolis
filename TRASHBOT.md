# Trashbot design notes

Trashbot is a modest, low speed remotely operated tank-tread ground vehicle
to be a mission component for
[Crux Industries](https://theimmersivemachine.com/faq-page/crux/),
a faction at [Neotropolis](https://www.neotropolis.com/).
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
- [24V-to-12V 20A DC-DC](https://www.amazon.com/dp/B0CS2KJSKS)
- [24V/12V-to-5V 5A DC-DC](https://www.amazon.com/dp/B0FD6M8D7K)
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
- DEV/TEST: [RadioMaster Pocket](https://radiomasterrc.com/products/pocket-radio-controller)
  (ELRS 900MHz) for testing RX independently before Pi integration
- ref: [Devana Project: send commands from Pi](https://thedevanaproject.com/2025/01/27/how-to-send-rc-commands-with-a-raspberry-pi-and-elrs-transmitter-module/)
- ref: [Devana Project: decode commands on Pi](https://thedevanaproject.com/2025/01/20/how-to-decode-rc-commands-from-an-elrs-receiver-module-with-a-raspberry-pi/)
- ref: [crsf-parser Python library](https://github.com/AlessioMorale/crsf_parser)
- ref: [elrs-joystick-control (USB CRSF)](https://github.com/kaack/elrs-joystick-control)

Remote video (trashbot to operator)

- [8W 1.3GHz analog VTX/VRX](https://www.kimpok.com/sale-51038869-1-2g-1-3g-fpv-vrx-vtx-8w-wireless-video-receiver-and-transmitter-long-range-transmission.html)
- [Foxeer Mini Cat 3 analog camera](https://www.foxeer.com/foxeer-mini-cat-3-1200tvl-0-00001lux-starlight-fpv-camera-g-320)
- Alternative: use WiFi, with a USB webcam or PiCam
- Alternative: use analog TV (NTSC) with a signal amplifier
- ref: [Oscar Liang's guide to analog FPV](https://oscarliang.com/1-2ghz-fpv-guide/)
- ref: [Oscar Liang's antenna guide](https://oscarliang.com/best-fpv-antenna/)
  (his other guides are good too)

Operator control station

- [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/)
- HDMI TV for video feed
- Analog (CVBS) to HDMI converter (for 1.3GHz analog video)
- Second display or StreamDeck keys for status (battery, RSSI, link quality)
- USB gamepad (TBD, something with cyberpunk aesthetic; not a standard RC
  controller). Control mapping happens on operator Pi, not robot side.
- 2x [StreamDeck XL](https://www.elgato.com/us/en/p/stream-deck-plus-xl) for
  emoji selection, lighting control, and other aux functions
- ref: [streamdeck Python library](https://github.com/abcminiuser/python-elgato-streamdeck)

Open Questions

- RANGE: ELRS Gemini Xrossband should give 1-3km+ even at ground level in a
  crowded RF environment. Probably fine for around the megablock; roaming the
  city would need real-world testing. WiFi is not needed for the control link.
- WIFI: Another faction is promising an enterprise-grade WiFi deployment, but
  it's not clear they'll come through, or that it would perform well. Not
  needed for control or video (both have dedicated radio links), but could be
  useful for software updates, monitoring, or a secondary data channel.
- OPERATOR UX: What does the control station look like? What gamepad?
- EMOJI PANELS: What are they? HUB75? HDMI screens? Where are they mounted?
- NOMAD AVAILABILITY: RadioMaster Nomad Dual is out of stock at some retailers.
  Fallback: BetaFPV Micro TX V2 900MHz ($60, 2W, SX1262) with GEPRC PA500 RX
  ($26, 500mW telemetry) -- single-band 900MHz only but still excellent range.
