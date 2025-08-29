""" Config variables - accessed as config.X in main.py"""

DEVICE_NAME = "ESP32_GPS"           # Used as Bluetooth device name
ESP32_TX_PIN = 0                    # Connected to GPS RX pin
ESP32_RX_PIN = 1                    # Connected to GPS TX pin
GPS_BAUD_RATE = 115200              # For LC29HEA - set to 115200 for most other models
PQTMEPE_TO_GGST = True              # Convert PQTMEPE messages to GGST (for accuracy info)
ENABLE_BLUETOOTH = True             # Output via bluetooth device
ENABLE_USB_SERIAL_CLIENT = True     # Output via usb serial using sys.stdout as UART(0) is taken by REPL
WIFI_SSID = ""                      # SSID for Wifi Access Point
WIFI_PASSWORD = ""                  # Password for Wifi Access Point
