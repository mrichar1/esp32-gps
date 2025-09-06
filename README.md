# EPS32 GPS

Micropython code for an ESP32 device to act as an intermediate gateway for a serial GPS module and provide support for RTK/NTRIP services.

Tested with ESP32 C3 Supermini devices and Quectel LC29H(BS/DA/EA) GPS modules.

## Features

(Features in _italics_ are planned).

* (USB) Serial GPS (pass-through).
* Bluetooth LE Serial GPS.
* Rewriting of NMEA sentences on-the-fly (e.g. PQTMEPE -> GPGST accuracy sentences).
* GPS Device Writing (RTCM corrections, Config commands).
* NTRIP `Client` (for Rover), `Server` (for Base Station) and `Caster` (for Base stations).

## Device Setup

Clone this repository, then do the following (assuming ESP32 device is connected on /dev/ttyACM0):

```
# Set up virtual env
python3 -mvenv venv
venv/bin/pip install -r requirements.txt

# Flash ESP32 module (Change port to suit your device)
venv/bin/esptool [--port /dev/ttyACM0] erase_flash

# Install Micropython (Download from https://micropython.org/download/)
venv/bin/esptool [--port /dev/ttyACM0] --baud 460800 write_flash 0 ESP32_MODEL-DATE-VERSION.bin

# Test access to the device
venv/bin/rshell -p /dev/ttyACM0
```

## Configuration

Example configuration is found in `config.defaults.py`. This must be copied to `src/config.py` and modified as required.

```
# Copy default config and modify
cp config.defaults.py src/config.py

# Access the device
env/bin/rshell -p /dev/ttyACM0

# Copy code to device
> cp src/*.py /pyboard

# Reset the device to run the code.
```

## Wiring

For C3 Supermini with a GPS module that requires 3v3 and supports UART:

* ESP32 3.3v -> GPS VIN Pin
* ESP32 Gnd -> GPS Gnd Pin
* ESP32 GPIO Pin 1 (TX) -> GPS RX Pin
* ESP32 GPIO Pin 0 (RX) -> GPS TX Pin

_The default TX/RX Pins 0 and 1 can be altered in the config. Remember to connect TX -> RX and vice-versa between GPS and ESP32!_

## Connecting

You can test GPS NMEA output by doing one of the following (with either `ENABLE_BLUETOOTH` or `ENABLE_USB_SERIAL` set):

* USB Serial output: `cat /dev/ttyACM0`, or `rshell` -> `repl` -> `ctlr-D` - look for NMEA messages.
* Bluetooth LE: Android - connect Bluetooth device, open SW Maps or equivalent, add Bluetooth LE device by name (default is `ESP32_GPS`) and look for location data.

You can test NTRIP `Server` & `Caster` again using SW Maps, PyGPSClient or similar GPS tool that supports NTRIP data.

## GPS Module Configuration

If your GPS device needs custom commands sent to it, these can be set by adding entries to the list in the `GPS_SETUP_COMMANDS` configuration option. These are applied prior to starting any NTRIP services or reading/writing data to/from the GPS device.

## NTRIP Support

NOTE: NTRIP services require Wifi to be enabled to send/receive data from external sources. Yuo can either set the `WIFI` config options to cause a connection to be set up, or manually set up networking in `boot.py`.

This code provide support for `Client`, `Server` and `Caster` NTRIP modes. These can be enabled in parallel by specifying mulitple modes separated by commas for the config option `NTRIP_MODE`.

The most common combination to use is: `NTRIP_MODE = "caster,server"`

This sets up the device to read RTCM data from an RTK-enabled Base Station (`Server`) and offer it up to clients (`Caster`).

### Client

`Client` mode is used to fetch NTRIP data from a `Caster` and write it to the GPS device (this requires an RTK-enabled GPS device).

To use, ensure you set the following configuration options. For example, to connect to Centipede NTRIP Mountpoint called `ABCD`:

```
NTRIP_MODE = "client"
NTRIP_CASTER = "crtk.net"
NTRIP_PORT = 2101
NTRIP_CREDENTIALS = "c:c"
NTRIP_MOUNT = "ABCD"
```

### Server

`Server` mode is used to push NTRIP data being read from an RTK-enabled Base Station to a Caster.

To use, ensure you set the following configuration options. For example, to send data for mount-point `WXYZ` to a private caster:

```
NTRIP_MODE = "server"
NTRIP_CASTER = "mycaster.example.net"
NTRIP_PORT = 2101
NTRIP_CREDENTIALS = "username:password"
NTRIP_MOUNT = "WXYZ"
```

NOTE: If you are using a public Caster you may need to pre-register your Base station to be allowed to send data to it.

### Caster

`Caster` mode is used to receive NTRIP data from one or more `Servers` and pass that data on to one or more `Clients`.

To use, ensure you set the following configuration options.

```
# Common config
NTRIP_MODE = "caster"
# Set to the Caster address (for Server or Client mode)
NTRIP_CASTER = "192.168.1.227"
NTRIP_PORT = 2101
# Authentication details for Servers and Clients
NTRIP_CREDENTIALS = "username:password"
# Mount point to accept Serve data for, and send Client data to
NTRIP_MOUNT = "ESP32"

#Caster Config
NTRIP_CASTER_BIND_ADDRESS = "0.0.0.0"
NTRIP_CASTER_BIND_PORT = 2101
# These values are reported in the SOURCETABLE - but usually do not need to be correct unless your client validates them
NTRIP_BASE_LATITUDE = "56.62"
NTRIP_BASE_LONGITUDE = "-3.94"
NTRIP_COUNTRY_CODE = "GBR"
```

NOTE: The `Caster` module currently only supports connection from a single `Server`, sending data for mount-point specified in `NTRIP_MOUNT` (defaults to ESP32). It can however support multiple clients (rovers) reading that data.

## Testing & Performance

This code has been successfully tested on a C3 Supermini (with a GPS device sending RTCM and NMEA messages) running `Caster` and `Server` NTRIP services, while also streaming location data to SW Maps via Bluetooth, or via USB serial. However in most real-world use these would be split to two separate devices, one Base station and one Rover.

This module writes logs using the proprietary NMEA sentence `$PLOG` - this allows log messages to be interleaved with GPS data on the USB serial output without causing issues with anything consuming the stream.

Any issues, features or comments, especially if tested on other ESP32 or equivalent hardware types, appreciated!
