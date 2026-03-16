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

# Components

Robot power and propulsion
- [TR500S robot chassis](https://www.ebay.com/itm/184923700908?var=692710822231)
- 24V, 10AH lithium battery
- 2x [ODrive S1](https://docs.odriverobotics.com/v/latest/hardware/s1-datasheet.html) motor controllers
- [24V-to-12V 20A DC-DC](https://www.amazon.com/dp/B0CS2KJSKS)
- [24V/12V-to-5V 5A DC-DC](https://www.amazon.com/dp/B0FD6M8D7K)

Onboard control
- [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/)
- [ODrive USB-CAN adapter](https://shop.odriverobotics.com/products/usb-can-adapter)

Remote video
- [8W 1.3GHz analog VTX/VRX](https://www.kimpok.com/sale-51038869-1-2g-1-3g-fpv-vrx-vtx-8w-wireless-video-receiver-and-transmitter-long-range-transmission.html)
- [Foxeer Mini Cat 3 analog camera](https://www.foxeer.com/foxeer-mini-cat-3-1200tvl-0-00001lux-starlight-fpv-camera-g-320)

Operator control station
- [Raspberry Pi 5](https://www.raspberrypi.com/products/raspberry-pi-5/)
- HDMI TV
- Analog (CVBS) to HDMI converter
- [8BitDo Pro 3](https://www.8bitdo.com/pro3/) game controller
- 2x [StreamDeck XL](https://www.elgato.com/us/en/p/stream-deck-plus-xl) for emoji selection
