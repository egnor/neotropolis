#!/usr/bin/env python3
"""
Example of receiving CRSF-format commands from an ELRS receiver on a Pi
Assumes the ELRS receiver has been set to 115200 baud rate output
https://thedevanaproject.com/2025/01/20/how-to-decode-rc-commands-from-an-elrs-receiver-module-with-a-raspberry-pi/
"""

import time
import serial

# CRSF Broadcast Frame (sync bytes <= 0x27 )
# Offset |        Usage        | CRC | Comment
#   0    |      sync byte      | No  | uint8, e.g. 0xEE -> to TX module, 0xC8 -> to FC, 0xEC -> FC to RX
#   1    |    frame length     | No  | uint8, entire frame size -2 (allowed values: 2-62)
#   2    |         type        | Yes | uint8, e.g. 0x02 -> GPS data
#   3    |       payload       | Yes | payload with length n bytes
#  n+4   |      checksum       | No  | uint8, basic CRC8 using polynomial 0xD5 (-> DVB-S2)

# CRSF Extended Frame (sync bytes >= 0x28 )
# Offset |        Usage        | CRC | Comment
#   0    |      sync byte      | No  | uint8, e.g. 0xEE -> to TX module, 0xC8 -> to FC, 0xEC -> FC to RX
#   1    |    frame length     | No  | uint8, entire frame size -2 (allowed values: 2-62)
#   2    |         type        | Yes | uint8, e.g. 0x02 -> GPS data
#   3    | destination address | Yes | uint8, e.g. 0xC8 -> Flight Controller
#   4    |    origin address   | Yes | uint8, e.g. 0xEA -> Remote Control
#   5    |       payload       | Yes | payload with length n bytes
#  n+6   |      checksum       | No  | uint8, basic CRC8 using polynomial 0xD5 (-> DVB-S2)

############################################
############# Helper functions #############
############################################


# Function to calculate the DVB-S2 CRC
# I have actually no clue how the algorithm works, but it apparently does.
def calculate_DVB_S2_checksum(data: list[int]) -> int:
    checksum = 0x00
    for byte in data:
        checksum ^= byte
        for _ in range(8):
            if checksum & 0x80:
                checksum = (checksum << 1) ^ 0xD5
            else:
                checksum <<= 1
            checksum &= 0xFF
    return checksum


def unpack(packedValues: list[int]):
    rcChannelValues = [0] * 16
    tempValues = [0] * 22 * 8
    if len(packedValues) == 22:
        # Here we decode the 22 bytes of 8 bits into 16 channels of 11 bits
        # More about this here: https://github.com/tbs-fpv/tbs-crsf-spec/blob/main/crsf.md#0x16-rc-channels-packed-payload
        # We have to reverse the arrays because of the "endianness" of the packed data
        # As a first step, we string all payload bytes into one large binary array of 22*8 = 176 bits
        for index, packedValue in enumerate(reversed(packedValues)):
            tempValues[index * 8 : (index + 1) * 8] = f"{packedValue:08b}"
        tempValues = "".join(tempValues)
        # Then we segment this array into 16 channels of 11 bits each, transform the binary values into INTs
        # and map them according to the CRSF specification. PAY ATTENTION TO WHAT MAPPING YOUR TRANSMITTER USES!
        # More about this topic here: https://www.expresslrs.org/software/switch-config/
        # We use the "WIDE" switch configuration mode
        for index in range(len(rcChannelValues)):
            rcChannelValues[index] = int(
                round(
                    (int(tempValues[index * 11 : (index + 1) * 11], 2) - 992)
                    * 5
                    / 8
                    + 1500
                )
            )
        rcChannelValues = list(reversed(rcChannelValues))
    else:
        print(f"There are {len(packedValues)} bytes, not 22 bytes in this list")
    return rcChannelValues


def messageSegmentation(message: list[int]):
    if not calculate_DVB_S2_checksum(
        message[2:]
    ):  # A CRC check with the checksum included returns 0 if correct.
        if len(message) >= 3:
            if len(message) == message[1] + 2:
                syncByte = message[0]
                frameLength = message[1]
                messageType = message[2]
                checksum = message[-1]
                if message[2] <= int(0x27):  # broadcast frame
                    payload = message[3:-1]
                    return [
                        syncByte,
                        frameLength,
                        messageType,
                        payload,
                        checksum,
                    ]
                elif messageType >= int(0x28):  # extended frame
                    destinationAdress = message[3]
                    originAdress = message[4]
                    payload = message[5:-1]
                    return [
                        syncByte,
                        frameLength,
                        messageType,
                        destinationAdress,
                        originAdress,
                        payload,
                        checksum,
                    ]
                else:
                    print("Not a valid messageType: ", message[2])
            else:
                print(
                    "Payload size incorrect, effective frameLength is ",
                    len(message) - 2,
                    " while it should be ",
                    message[1],
                )
        else:
            print("Message is less than 3 bytes: Invalid")
    else:
        print("CRC check failed")
    return None


##############################################
######### Initialize some parameters #########
##############################################

# Set up serial connection (RPi -> Receiver Module)
SERIAL_PORT = "/dev/ttyAMA0"
BAUD_RATE = (
    115200  # Default, can be changed in the Modules Web-Interface if necessary
)
serialReceiver = serial.Serial(SERIAL_PORT, BAUD_RATE)

# Initialization of serial buffers
buffer = bytearray()
message = None

# Initialization of timer variables
# It's important to check for received messages in a short enough regular interval
# As the transmitter is constantly sending new messages, the buffer would otherwise grow indefinitely
_lasttimeRead = time.monotonic()
dtRead = 0.001  # in seconds -> approx. 1kHz sampling rate, must be faster the refresh rate on your transmitter

while True:
    if time.monotonic() - _lasttimeRead >= dtRead:
        _lasttimeRead = time.monotonic()
        # Read buffer content and look for messages
        # Were only looking for RC commands, so we only have to look for sync byte 0xC8
        buffer.extend(bytearray(serialReceiver.read(serialReceiver.in_waiting)))
        if len(buffer) == 0:
            pass
        # print("Buffer is empty")
        elif len(buffer) >= 128:
            # print("Buffer grew too large -> discarded")
            buffer = bytearray()
        elif buffer.count(0xC8) == 0:
            # print('Buffer: ', buffer, ' doesn\'t contain a sync byte -> discarded')
            buffer = bytearray()
        elif (
            buffer.count(0xC8) >= 1
        ):  # There is at least one sync byte 0xC8 in the buffer
            del buffer[
                : buffer.find(0xC8)
            ]  # Delete all content before the sync byte
            if len(buffer) >= 2:
                if buffer[1] + 2 > 64:
                    # print('Invalid frame length > 64 bytes: ', buffer[1]+2, ' -> discarded')
                    buffer = bytearray()
                elif (
                    len(buffer) >= buffer[1] + 2
                ):  # There is a complete message if the buffer is at least as long as defined by the frame size byte
                    message = buffer[: buffer[1] + 2]
                    del buffer[
                        : buffer[1] + 2
                    ]  # Remove the message from the buffer
                    segmentedMessage = messageSegmentation(
                        list(map(int, message))
                    )
                    if segmentedMessage is not None:
                        rcChannelValues = unpack(segmentedMessage[-2])
                        print("Decoded Channel Values:", rcChannelValues)
                else:
                    pass  # print('The message is not long enough yet: less than specified frame length')
            else:
                pass  # print('The message is not long enough yet: less than 2 bytes')
        else:
            # print('Something went wrong -> discarded')
            buffer = bytearray()
