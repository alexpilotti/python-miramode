# python-miramode

Python module for controlling Mira Mode digital showers via BLE.

Mira Mode is a line of digital showers and bathfills from Mira Showers. They
work great in my experience, but having only a Bluetooth Low Energy (BLE)
interface, they can only be controlled locally via smartphone and not via
Alexa, Google Home and the likes, which makes the whole experience
significantly less useful.

## Alexa, turn on the shower!

To overcome this limitation, here's a Python library that can be used to
control Mira Mode devices from a Raspberry PI or any other computer equipped
with BLE capabilities, allowing an easy integration with projects like
Home Assistant which can then expose the shower outlets as switches to
Alexa or Google Home.

*Disclaimer: this projects contains only the results of personal experiments,
use at your own risk!*

## Requirements

1. Python (3.x preferabily, but works with 2.7 as well)
```
pip install -r requirements.txt
```
2. Gatttool, a common BLE CLI tool on Linux

## Examples

```python
import miramode

# This is the BLE address of the device
address = "xx:xx:xx:xx:xx:xx"
# See below for how to obtain the device_id and client_id
device_id = 1
client_id = 12345

# Turn on the 1st outlet with a 40C degrees water temperature
mira.control_outlets(address, device_id, client_id, True, False, 40)

# Turn on both outlets
mira.control_outlets(address, device_id, client_id, True, True, 40)

# Turn on the bathfill with the default memorized temperature
mira.turn_on_bathfill(address, device_id, client_id)

# Turn off
mira.control_outlets(address, device_id, client_id, False, False, 40)
```

## How to obtain the device and client ids 

At the moment the way in which those ids are obtained is by using a BLE
sniffer, like the *Bluefruit LE Sniffer* from Adafruit, to get packets
exchanged between your phone Mira Mode app and the Mira Shower when an
outlet is turned on, using e.g. Wireshark. This complication can be
avoided by finding out how the device pairing protocol works,
something on the TODO list.

What we are looking for are binary payloads written to the BLE
characterist 0x11 which look for example like this:

*XX:87:05:01:01:90:64:00:YY:YY*

XX is your device id and YYYY is a CRC code obtained from the rest of
the payload plus the client id. Being the client id a 32 bit adapter,
it can be quickly computed with a brute force loop.
