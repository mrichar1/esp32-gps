# EPS32 GPS

Micropython code for an ESP32 device to act as an intermediate gateway for a serial GPS module.

Tested with ESP32 C3 Supermini devices.

## Features

(Features in _italics_ are planned).

* (USB) Serial GPS (pass-through)
* Bluetooth LE Serial GPS
* Rewriting of NMEA sentences on-the-fly (e.g. PQTMEPE -> GPGST accuracy sentences).
* _GPS Device Writes (RTCM corrections, Config commands etc)_
* _NTRIP Client (for Rover)_
* _NTRIP Caster (for Base stations)_

## Setup

```
# Set up virtual env
python3 -mvenv env
env/bin/pip install -r requirements.txt

# Flash ESP32 module (Change port to suit your device)
env/bin/esptool [--port /dev/ttyACM0] erase_flash

# Install Micropython (Download from https://micropython.org/download/)
env/bin/esptool [--port /dev/ttyACM0] --baud 460800 write_flash 0 ESP32_MODEL-DATE-VERSION.bin

# Test access to the device
env/bin/rshell -p /dev/ttyACM0
```

## Configuration

Modify the config values at the top of `main.py`, then upload to the device:

```
# Access the device
env/bin/rshell -p /dev/ttyACM0

# Copy code to device
> cp main.py blue.py gps.py /pyboard

# Reset the device to run the code.
```

## Wiring

* ESP32 3.3v -> GPS VIN Pin
* ESP32 Gnd -> GPS Gnd Pin
* ESP32 GPIO Pin 1 (TX) -> GPS RX Pin
* ESP32 GPIO Pin 0 (RX) -> GPS TX Pin

_The default TX/RX Pins 0 and 1 can be altered in the config. Remember to connect TX -> RX and vice-versa between GPS and ESP32!_

## Testing

* USB Serial output: `cat /dev/ttyACM0` - look for NMEA messages.
* Bluetooth LE: Android - install SW Maps, add Bluetooth LE device by name (default is `ESP32_GPS`).

