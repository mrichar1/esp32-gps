import time
import sys
from gps import GPS
from blue import Blue

# Config variables
DEVICE_NAME = "ESP32_GPS" # Used as Bluetooth device name
ESP32_TX_PIN = 0 # Connected to GPS RX pin
ESP32_RX_PIN = 1 # Connected to GPS TX pin
GPS_BAUD_RATE = 460800 # For LC29HEA - set to 115200 for most other models
PQTMEPE_TO_GGST = True # Convert PQTMEPE messages to GGST (for accuracy info)
ENABLE_BLUETOOTH = True # Output via bluetooth device
ENABLE_USB_SERIAL_CLIENT = True # Output via usb serial using sys.stdout as UART(0) is taken by REPL


class ESP32GPS():

    def __init__(self):
        # ESP32 has no clock so store time taken from $GPRMC messages
        self.gps = GPS(baudrate=GPS_BAUD_RATE, tx=ESP32_TX_PIN, rx=ESP32_RX_PIN)
        self.ble = None
        if ENABLE_BLUETOOTH:
            self.ble = Blue(name=DEVICE_NAME)
            # Set custom BLE write callback
            self.ble.write_callback = self.esp32_write_data
        self.gps_read_data()

    def gps_read_data(self):
        buffer = b""
        while True:
            while ENABLE_USB_SERIAL_CLIENT or (self.ble and self.ble.is_connected()):
                buffer += self.gps.uart.read(self.gps.uart.any())
                while b"\r\n" in buffer:
                    line, buffer = buffer.split(b"\r\n", 1)
                    if line.startswith(b"$"):
                        if PQTMEPE_TO_GGST:
                            if line.startswith(b"$GNRMC"):
                                # Extract UTC_TIME (as str) for use in GST sentence creation
                                self.gps.utc_time = line.split(b',',2)[1].decode('UTF-8')
                            if line.startswith(b"$PQTMEPE"):
                                line = self.gps.pqtmepe_to_gst(line)
                        try:
                            line += b"\r\n"
                            if ENABLE_USB_SERIAL_CLIENT:
                                sys.stdout.write(line)
                                sys.stdout.flush()
                            if ENABLE_BLUETOOTH:
                                self.ble.send(line)
                        except Exception as e:
                            pass
            time.sleep_ms(100)

    def esp32_write_data(self, value):
        """Callback to run if device is written to (BLE, Serial)"""
        self.gps.uart.write(value)

if __name__ == "__main__":
    e32gps = ESP32GPS()
