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

Remote control (operator to trashbot)

- LoRa radio ???
- MAYBE: [Adafruit LoRa Radio Bonnet](https://www.adafruit.com/product/4074)
- MAYBE: [Waveshare USB to LoRA](https://www.waveshare.com/usb-to-lora.htm)
- MAYBE: [WaveShare LoRaWAN Node Module for Raspberry Pi](https://www.waveshare.com/sx1262-lorawan-hat.htm)
- MAYBE: [WaveShare LoRa HAT for Raspberry Pi](https://www.waveshare.com/sx1262-868m-lora-hat.htm)
- OTHER: PineDio USB LoRa, RangePi, LoStik, xDot, Dragino, etc.
- ref: [ExpressLRS](https://www.expresslrs.org/) (uses LoRa?)
- ref: [LoRa RC Controller using Arduino](https://www.electroniclinic.com/lora-rc-controller-using-arduino/)
- ref: [LoRa and LoRaWAN Radio for Raspberry Pi](https://learn.adafruit.com/lora-and-lorawan-radio-for-raspberry-pi)
- ref: https://github.com/Boyyt357/DIY-LoRa-Long-Range-RC-Control-System-TX-RX-

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
- HDMI TV
- Analog (CVBS) to HDMI converter
- [8BitDo Pro 3](https://www.8bitdo.com/pro3/) game controller
- 2x [StreamDeck XL](https://www.elgato.com/us/en/p/stream-deck-plus-xl) for
  emoji selection

Open Questions

- RANGE: How far can this thing go? Just around the megablock, or can it roam
  the city? More is better obviously.
- WIFI: Another faction is promising an enterprise-grade WiFi deployment, but
  it's not clear they'll come through, or that it would perform well
- OPERATOR UX: What does the control station look like?
- EMOJI PANELS: What are they? HUB75? HDMI screens? Where are they mounted?
