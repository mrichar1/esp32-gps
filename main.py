import time
import sys
from gps import GPS
from blue import Blue
from net import Wifi
import config as cfg

if cfg.WIFI_SSID and cfg.WIFI_PASSWORD:
    Wifi(ssid=cfg.WIFI_SSID, key=cfg.WIFI_PASSWORD)

class ESP32GPS():

    def __init__(self):
        # ESP32 has no clock so store time taken from $GPRMC messages
        self.gps = GPS(baudrate=cfg.GPS_BAUD_RATE, tx=cfg.ESP32_TX_PIN, rx=cfg.ESP32_RX_PIN)
        self.ble = None
        if cfg.ENABLE_BLUETOOTH:
            self.ble = Blue(name=cfg.DEVICE_NAME)
            # Set custom BLE write callback
            self.ble.write_callback = self.esp32_write_data
        self.gps_read_data()

    def gps_read_data(self):
        buffer = b""
        while True:
            while cfg.ENABLE_USB_SERIAL_CLIENT or (self.ble and self.ble.is_connected()):
                buffer += self.gps.uart.read(self.gps.uart.any())
                while b"\r\n" in buffer:
                    line, buffer = buffer.split(b"\r\n", 1)
                    if line.startswith(b"$"):
                        if cfg.PQTMEPE_TO_GGST:
                            if line.startswith(b"$GNRMC"):
                                # Extract UTC_TIME (as str) for use in GST sentence creation
                                self.gps.utc_time = line.split(b',',2)[1].decode('UTF-8')
                            if line.startswith(b"$PQTMEPE"):
                                line = self.gps.pqtmepe_to_gst(line)
                        line += b"\r\n"
                        try:
                            if cfg.ENABLE_USB_SERIAL_CLIENT:
                                sys.stdout.write(line)
                        except Exception as e:
                            pass
                        try:
                            if cfg.ENABLE_BLUETOOTH and self.ble.is_connected():
                                self.ble.send(line)
                        except Exception as e:
                            pass
            time.sleep_ms(100)

    def esp32_write_data(self, value):
        """Callback to run if device is written to (BLE, Serial)"""
        self.gps.uart.write(value)

if __name__ == "__main__":
    e32gps = ESP32GPS()
