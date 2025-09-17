# Example Uses

This document lists some common use cases, along with the main/minimum config required for each case.

## Serial GPS

Read data from a GPS device and output via a serial port.

```
ENABLE_GPS = True
GPS_UART = 1
GPS_TX_PIN = 0
GPS_RX_PIN = 1
GPS_BAUD_RATE = 115200

ENABLE_SERIAL_CLIENT = False        # Output GPS data via serial
SERIAL_UART = 2                     # UART device for serial output
SERIAL_TX_PIN = 3                   # Transmit pin
SERIAL_RX_PIN = 4                   # Receive pin
SERIAL_BAUD_RATE = 115200           # Serial baud rate
LOG_TO_SERIAL = False               # If True, log messages are sent over serial, rather than to sys.stdout (REPL)
```

## Bluetooth GPS

Appear as a Bluetooth GPS device, serving up data from the GPS device.

```
ENABLE_GPS = True               # Also set UART, Pins, Baud as appropriate
ENABLE_BLUETOOTH = True         # Output GPS data via bluetooth device
DEVICE_NAME = "ESP32_GPS"       # (Optional) Set a different bluetooth device name (defaults to ESP32_GPS)
```


## NTRIP

### Client

The NTRIP client will connect to a Caster, read correction data, and then write this to the GPS serial device. The Caster can optionally be running locally or remotely.


```
ENABLE_GPS = True               # Also set UART, Pins, Baud as appropriate

WIFI_SSID = "my_ap"
WIFI_PSK = "my_password"
NTRIP_MODE = "client"
NTRIP_CASTER = "caster.example.com"
NTRIP_PORT = 2101
NTRIP_MOUNT = "ESP32"
NTRIP_CLIENT_CREDENTIALS = "c:c"
```

### Server: Sending Corrections to a Caster

This is the most common reason for running a NTRIP server.

Corrections are read from the Base Station GPS device, and sent to a Caster (local or remote). These can then be fetched by the Rover running an NTRIP client.


```
ENABLE_GPS = True               # Also set UART, Pins, Baud as appropriate

WIFI_SSID = "my_ap"
WIFI_PSK = "my_password"
NTRIP_MODE = "server"
NTRIP_CASTER = "caster.example.com"
NTRIP_PORT = 2101
NTRIP_MOUNT = "ESP32"
NTRIP_SERVER_CREDENTIALS = "c:c"
```

### Server: Sending 'Survey-in' data to a Caster for later PPP/PPK

If your GPS device can send raw RTCM data, you can send this to the Caster instead of just corrections. You can then log this data and use it for PPP or PPK analysis, either via the NRCAN service, or using RTKPost.

Once a fix has been obtained and applied to the Base Station, you can switch it to sending corrections.

**NOTE** While the esp32-gps` Caster will accept raw RTCM data to forward on, some Caster services may only accept correction data. Check with your provider before use.


### Caster

The commonest option is to run the Caster and Server on the same Base Station device, using a wifi connection for Clients to connect remotely.

However the Caster can also run independently, receiving data from one or more Servers hosted elsewhere.

```
ENABLE_GPS = False
WIFI_SSID = "my_ap"
WIFI_PSK = "my_password"
NTRIP_MODE = "caster"
NTRIP_CASTER_BIND_ADDRESS = "0.0.0.0"
NTRIP_CASTER_BIND_PORT = 2101
NTRIP_CLIENT_CREDENTIALS = "c:c"
NTRIP_SERVER_CREDENTIALS = "d:d"
# Sourcetable map - add one STR line to authorise each mountpoint.
# Full details at: https://software.rtcm-ntrip.org/wiki/STR
# RTCM format protocol here: https://github.com/MichaelBeechan/RTCM3.3/blob/main/RTCM3.3.PDF
NTRIP_SOURCETABLE = """
STR;ESP32;ESP32_GPS;RTCM3.3;;2;GLO+GAL+QZS+BDS+GPS;NONE;GBR;56.62;-3.94;0;0;NTRIP ESP32_GPS;none;B;N;15200;ESP32_GPS
ENDSOURCETABLE
"""
NTRIP_SERVER_CREDENTIALS = "c:c"
```


## ESPNow

If wifi isn't available, ESPNow can be used instead for transferring data.

The Base Station device is set up with GPS, ESPNow Sender and NTRIP Server.

A receiver then runs ESPNow Receiver and NTRIP Caster (this device can also run NTRIP Client to read from the local Caster and write to the Rover device).

Sender and Receiver config must each have the MAC address of the other device in their config. If ESPNOW_MODE is set, the MAC address of the device is logged so it can easily be copied into the peers list on the other device.

### Sender

The Sender's role is to read data from a GPS device, and forward it to one or more Receivers.

```
ESPNOW_MODE = "sender"
ESPNOW_PEERS = [ b"\xaa\xaa\xaa\xaa\xaa\xaa", b"\xbb\xbb\xbb\xbb\xbb\xbb"]
```

### Receiver

The Receiver's role is to receive data from a sender, as if it had come from a local GPS device.

Receiver is usually enabled alongside NTRIP Server to send the received data on to a Caster.

```
ESPNOW_MODE = "receiver"
ESPNOW_PEERS = [b"\xcc\xcc\xcc\xcc\xcc\xcc"]
```

**NOTE** The first peer in the list is assumed to be the sender - all others are ignored.
