import asyncio
import gc
import sys
import time
from blue import Blue
from net import Wifi
import config as cfg
from gps_utils import GPS, log
import ntrip

try:
    Wifi(ssid=cfg.WIFI_SSID, key=cfg.WIFI_PSK)
except AttributeError:
    # No credentials provided - skip activating wifi
    pass

class ESP32GPS():

    def __init__(self):
        # ESP32 has no clock so store time taken from $GPRMC messages
        self.gps = GPS(baudrate=cfg.GPS_BAUD_RATE, tx=cfg.ESP32_TX_PIN, rx=cfg.ESP32_RX_PIN)
        self.buf = bytearray()
        self.buf_len = 0
        self.start_idx = 0



    async def run(self):
        if hasattr(cfg, "GPS_SETUP_COMMANDS"):
            for cmd in cfg.GPS_SETUP_COMMANDS:
                self.gps.write_nmea(cmd)
        self.blue = None
        if cfg.ENABLE_BLUETOOTH:
            self.blue = Blue(name=cfg.DEVICE_NAME)
            # Set custom BLE write callback
            self.blue.write_callback = self.esp32_write_data

        if 'caster' in cfg.NTRIP_MODE:
            self.ntrip_caster = ntrip.Caster(cfg.NTRIP_CASTER_BIND_ADDRESS, cfg.NTRIP_CASTER_BIND_PORT, cfg.NTRIP_SOURCETABLE, cfg.NTRIP_CLIENT_CREDENTIALS, cfg.NTRIP_SERVER_CREDENTIALS)
            task_cast = asyncio.create_task(self.ntrip_caster.run())
            # Allow Caster to start before Server/Client
            await asyncio.sleep(2)
        if 'server' in cfg.NTRIP_MODE:
            self.ntrip_server = ntrip.Server(cfg.NTRIP_CASTER, cfg.NTRIP_PORT, cfg.NTRIP_MOUNT, cfg.NTRIP_CLIENT_CREDENTIALS)
            task_srv = asyncio.create_task(self.ntrip_server.run())
        if 'client' in cfg.NTRIP_MODE:
            self.ntrip_client = ntrip.Client(cfg.NTRIP_CASTER, cfg.NTRIP_PORT, cfg.NTRIP_MOUNT, cfg.NTRIP_CLIENT_CREDENTIALS)
            task_cli = asyncio.create_task(self.ntrip_client.run())
            await self.ntrip_client_read()

        task_gps = asyncio.create_task(self.gps_data())

        await asyncio.gather(
            task_cast,
            task_srv,
            task_gps
        )

    async def read_uart(self):
        while True:
            data = self.gps.uart.read()
            if data:
                mlen = len(data)
                # Protect against OOM in case of unuusally large messages
                if self.buf_len + mlen > 2048:
                    # Overflow - skip old bytes
                    self.start_idx = 0
                    self.buf_len = 0
                self.buf[self.buf_len:self.buf_len+mlen] = data
                self.buf_len += mlen
            else:
                await asyncio.sleep(0)
                continue

            while self.start_idx < self.buf_len:
                b0 = self.buf[self.start_idx]
                remaining = self.buf_len - self.start_idx

                if b0 == 0xD3 and remaining >= 3:
                    # Extract RTCM Header and Length fields
                    hdr = self.buf[self.start_idx+1:self.start_idx+3]
                    length = ((hdr[0] & 0x03) << 8) | hdr[1]
                    # preamble+header+payload+CRC
                    total_len = 3 + length + 3
                    # Length field must indicate max 1023 bytes
                    if length == 0 or length > 1023:
                        self.start_idx += 1
                        continue
                    if remaining < total_len:
                        # Not got whole msg yet
                        break

                    msg = self.buf[self.start_idx:self.start_idx+total_len]
                    self.start_idx += total_len
                    return bytes(msg)

                elif b0 == ord('$'):
                    #NMEA?
                    # Look for end marker
                    end_idx = self.buf.find(b'\r\n', self.start_idx, self.buf_len)
                    if end_idx == -1:
                        if self.buf_len > 82:
                            # NMEA messages are max 82 bytes long
                            # If longer, and end-marker not found, then false-positive, move on
                            self.start_idx += 1
                            continue
                        else:
                            # Need more data
                            break
                    # Found end marker - build message, move index
                    msg = self.buf[self.start_idx:end_idx+2]
                    self.start_idx = end_idx + 2
                    return bytes(msg)

                else:
                    # Not a marker-byte, move on
                    self.start_idx += 1

            # Periodically compact buffer to avoid growing indefinitely
            if self.start_idx > 512:
                self.buf[:self.buf_len - self.start_idx] = self.buf[self.start_idx:self.buf_len]
                self.buf_len -= self.start_idx
                self.start_idx = 0

    async def ntrip_client_read(self):
        while True:
            async for data in ntrip_client.iter_data():
                self.esp32_write_data(data)

    async def gps_data(self):
        """Read data from GPS and send to configured outputs.

        All exceptions are caught and logged to avoid crashing the main thread.

        NMEA sentences are sent to USB serial (if enabled), Bluetooth (if enabled) and NTRIP server (if enabled, but only non-NMEA data).
        """
        while True:
            while "server" in cfg.NTRIP_MODE or cfg.ENABLE_USB_SERIAL_CLIENT or (self.blue and self.blue.is_connected()):
                isNMEA= False
                line = await self.read_uart()
                if not line:
                    continue
                # Handle NMEA sentences
                if line.startswith(b"$") and line.endswith(b"\r\n"):
                    isNMEA = True
                    if cfg.PQTMEPE_TO_GGST:
                        if line.startswith(b"$GNRMC"):
                            # Extract UTC_TIME (as str) for use in GST sentence creation
                            self.gps.utc_time = line.split(b',',2)[1].decode('UTF-8')
                        if line.startswith(b"$PQTMEPE"):
                            line = self.gps.pqtmepe_to_gst(line)
                try:
                    if cfg.ENABLE_USB_SERIAL_CLIENT:
                        sys.stdout.write(line)
                except Exception as e:
                    log(f"[GPS DATA] USB serial send exception: {sys.print_exception(e)}")
                try:
                    if cfg.ENABLE_BLUETOOTH and self.blue.is_connected():
                        self.blue.send(line)
                except Exception as e:
                    log(f"[GPS DATA] BT send exception: {sys.print_exception(e)}")
                try:
                    if not isNMEA and 'server' in cfg.NTRIP_MODE:
                        # Don't sent NMEA sentences to NTRIP server
                        await self.ntrip_server.send_data(line)
                except Exception as e:
                    log(f"[GPS DATA] NTRIP server send exception: {sys.print_exception(e)}")
            # Wait for one of the outputs to start
            await asyncio.sleep(1)

    def esp32_write_data(self, value):
        """Callback to run if device is written to (BLE, Serial)"""
        self.gps.uart.write(value)

if __name__ == "__main__":
    e32gps = ESP32GPS()
    asyncio.run(e32gps.run())
