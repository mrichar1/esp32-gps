""" Config variables - accessed as config.X in main.py"""

# GPS device configuration
ENABLE_GPS = True                   # Enable GPS device for reading via UART serial.
GPS_UART = 1                        # UART device for GPS connection
GPS_TX_PIN = 0                      # ESP32 pin - connected to GPS RX pin
GPS_RX_PIN = 1                      # ESP32 pin - connected to GPS TX pin
GPS_BAUD_RATE = 115200              # For LC29HEA, set 460800 - set to 115200 for most other models
GPS_SETUP_COMMANDS = []             # List of NMEA commands (without $ and checksum) to be sent to GPS device on startup.

# NMEA/Data configuration
PQTMEPE_TO_GGST = False             # Convert PQTMEPE messages to GGST (for accuracy info from Quectel devices)

# USB serial configuration
ENABLE_SERIAL_CLIENT = True         # Output GPS data via serial
SERIAL_UART = 2                     # UART device for serial output
SERIAL_TX_PIN = 3                   # Transmit pin
SERIAL_RX_PIN = 4                   # Receive pin
SERIAL_BAUD_RATE = 115200           # Serial baud rate
LOG_TO_SERIAL = False               # If True, log messages are sent over serial, rather than to sys.stdout (REPL)

# Bluetooth configuration
DEVICE_NAME = "ESP32_GPS"           # Bluetooth device name
ENABLE_BLUETOOTH = True             # Output via bluetooth device

# Wifi credentials - needed for NTRIP services
# Either set here, or ensure wifi is enabled in boot.py
WIFI_SSID = ""                      # SSID for Wifi Access Point
WIFI_PSK = ""                       # PSK for Wifi Access Point
WIFI_TXPOWER = None                 # Some boards (e.g. C3) have more stable connections with reduced txpower (txpower=5)

# ESPNow config
ESPNOW_MODE = "sender"              # ESP Mode can be sender or receiver (or empty to disable)
# If ESPMODE = sender, send to all peers.
# If receiver, receive data from the first peer in the list as if it was a local GPS device.
ESPNOW_PEERS = [b"\xbb\xbb\xbb\xbb\xbb\xbb"] # List of mac addresses for peers.

# NTRIP configuration
NTRIP_MODE = "client"               # To enable NTRIP services, comma-separated list of: client (pull NTRIP data from caster), server (upload NTRIP data to a caster), caster (read/write to servers/clients)

# Client/Server config
NTRIP_CASTER = "crtk.net"           # NTRIP caster address
NTRIP_PORT = 2101                   # NTRIP caster port
NTRIP_MOUNT = "ESP32"               # NTRIP mount. Note there is no support for NEAR/GGA automatic mountpoints.
NTRIP_CLIENT_CREDENTIALS = "c:c"    # NTRIP client credentials (in form user:pass). Centipede: "c:c". rtk2go: "your@email.com:none" (for all modes)
NTRIP_SERVER_CREDENTIALS = "c:c"    # NTRIP server credentials (in form user:pass).

# Caster config
NTRIP_CASTER_BIND_ADDRESS = "0.0.0.0"  # Address to bind the NTRIP caster
NTRIP_CASTER_BIND_PORT = 2101       # Port to bind the NTRIP caster
# Sourcetable map - add one STR line to authorise each mountpoint.
# Full details at: https://software.rtcm-ntrip.org/wiki/STR
# RTCM format protocol here: https://github.com/MichaelBeechan/RTCM3.3/blob/main/RTCM3.3.PDF
NTRIP_SOURCETABLE = """
STR;ESP32;ESP32_GPS;RTCM3.3;;2;GLO+GAL+QZS+BDS+GPS;NONE;GBR;56.62;-3.94;0;0;NTRIP ESP32_GPS;none;B;N;15200;ESP32_GPS
ENDSOURCETABLE
"""
