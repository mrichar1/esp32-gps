""" Config variables - accessed as config.X in main.py"""

# GPS device configuration
GPS_HARDWARE = "F9P"                # Text description of GPS hardware device
ESP32_TX_PIN = 0                    # Connected to GPS RX pin
ESP32_RX_PIN = 1                    # Connected to GPS TX pin
GPS_BAUD_RATE = 115200              # For LC29HEA - set to 115200 for most other models

# NMEA/Data configuration
PQTMEPE_TO_GGST = False             # Convert PQTMEPE messages to GGST (for accuracy info from Quectel devices)

# USB serial configuration
ENABLE_USB_SERIAL_CLIENT = True     # Output via usb serial using sys.stdout as UART(0) is taken by REPL

# Bluetooth configuration
DEVICE_NAME = "ESP32_GPS"           # Used as Bluetooth device name
ENABLE_BLUETOOTH = True             # Output via bluetooth device

# Wifi credentials - needed for NTRIP services
WIFI_SSID = ""                      # SSID for Wifi Access Point
WIFI_PSK = ""                       # PSK for Wifi Access Point

# NTRIP configuration
# Common config
NTRIP_MODE = "client"               # To enable NTRIP services, comma-separated list of: client (pull NTRIP data from caster), server (upload NTRIP data to a caster), caster (read/write to servers/clients)
NTRIP_CASTER = "crtk.net"           # NTRIP caster address (for server and client modes).
NTRIP_PORT = 2101                   # NTRIP port (for all modes)
NTRIP_CREDENTIALS = "c:c"           # NTRIP credentials (in form user:pass). Centipede: "c:c". rtk2go: "your@email.com:none" (for all modes)
NTRIP_MOUNT = "ESP32"               # NTRIP mount (for all modes). Note there is no support for NEAR/GGA automatic mountpoints.

# Caster config
# NOTE: The caster only currently supports a single server, mounted at NTRIP_MOUNT, so these values can be fixed in the SOURCETABLE
NTRIP_CASTER_BIND_ADDRESS = "0.0.0.0"  # Address to bind the NTRIP caster
NTRIP_CASTER_BIND_PORT = 2101       # Port to bind the NTRIP caster
NTRIP_BASE_LATITUDE = "56.62"       # Latitude of NTRIP server (mount)
NTRIP_BASE_LONGITUDE = "-3.94"      # Longitude of NTRIP server (mount)
NTRIP_COUNTRY_CODE = "GBR"          # Country code of NTRIP server (mount) e.g. United Kingdom = GBR
