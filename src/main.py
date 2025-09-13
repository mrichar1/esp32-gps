import asyncio
import sys
from machine import UART
from blue import Blue
from net import Net
import config as cfg
from devices import GPS, Logger, Serial
import ntrip
try:
    from debug import DEBUG
except ImportError:
    DEBUG=False

log = Logger.getLogger().log

class ESP32GPS():

    def __init__(self):
        self.net = None
        self.irq_event = asyncio.ThreadSafeFlag()
        self.espnow_event = asyncio.ThreadSafeFlag()
        self.serial = None
        self.ntrip_caster = None
        self.ntrip_server = None
        self.ntrip_client = None

    def setup_gps(self):
        log("Enabling GPS device.")
        self.gps = GPS(uart=cfg.GPS_UART, baudrate=cfg.GPS_BAUD_RATE, tx=cfg.GPS_TX_PIN, rx=cfg.GPS_RX_PIN)
        if hasattr(cfg, "GPS_SETUP_COMMANDS"):
            for cmd in cfg.GPS_SETUP_COMMANDS:
                self.gps.write_nmea(cmd)
        # Set up GPS read irq callback
        self.gps.uart.irq(self.uart_read_handler, UART.IRQ_RXIDLE)


    def setup_serial(self):
        log_serial = False
        if hasattr(cfg, "LOG_TO_SERIAL") and cfg.LOG_TO_SERIAL:
            log_serial = True
        self.serial = Serial(uart=cfg.SERIAL_UART, baudrate=cfg.SERIAL_BAUD_RATE, tx=cfg.SERIAL_TX_PIN, rx=cfg.SERIAL_RX_PIN, log_serial=log_serial)


    def setup_networks(self):
        txpower=None
        if hasattr(cfg, "WIFI_TXPOWER"):
            txpower = cfg.WIFI_TXPOWER
        self.net = Net(txpower=txpower)
        # Note: We start wifi first, as this will define the channel to be used.
        # Wifi connections also enable power management, which espnow startup will later disable.
        # See: https://docs.micropython.org/en/latest/library/espnow.html#espnow-and-wifi-operation
        try:
            self.net.enable_wifi(ssid=cfg.WIFI_SSID, key=cfg.WIFI_PSK)
        except AttributeError:
            pass
        # Start ESPNow if peers provided
        try:
            if cfg.ESPNOW_MODE:
                self.net.enable_espnow(peers=cfg.ESPNOW_PEERS)
        except AttributeError:
            # No ESPNOW peers provided - skip activating ESPNOW
            pass


    def esp32_write_data(self, value):
        """Callback to run if device is written to (BLE, Serial)"""
        self.gps.uart.write(value)

    async def ntrip_client_read(self):
        """Read data from NTRIP client and write to GPS device."""
        while True:
            async for data in ntrip_client.iter_data():
                self.esp32_write_data(data)

    async def espnow_reader(self):
        """Read from ESPNow in async loop, and send for outputting."""
        while True:
            try:
                data = await self.net.espnow_recv()
                if data:
                    await self.gps_data(data)
            except Exception as e:
                sys.print_exception(e)

    def uart_read_handler(self, u):
        """Callback to run if GPS has data ready for reading."""
        # Ignore UART unless there is an output to recv data
        if "server" in cfg.NTRIP_MODE or cfg.ESPNOW_MODE == "sender" or cfg.ENABLE_SERIAL_CLIENT or (self.blue and self.blue.is_connected()):
            data = self.gps.uart.read()
            if data:
                # We mustn't block here, so schedule an async task to handle the data
                asyncio.get_event_loop().create_task(self.gps_data(data))

    async def gps_data(self, line):
        """Read GPS data and send to configured outputs.

        All exceptions are caught and logged to avoid crashing the main thread.

        NMEA sentences are sent to (if enabled): USB serial, Bluetooth, ESPNow and NTRIP server (only non-NMEA data).
        """
        if not line:
            return
        isNMEA= False
        # Handle NMEA sentences
        if line.startswith(b"$") and line.endswith(b"\r\n"):
            isNMEA = True
            if cfg.ENABLE_GPS and cfg.PQTMEPE_TO_GGST:
                if line.startswith(b"$GNRMC"):
                    # Extract UTC_TIME (as str) for use in GST sentence creation
                    self.gps.utc_time = line.split(b',',2)[1].decode('UTF-8')
                if line.startswith(b"$PQTMEPE"):
                    line = self.gps.pqtmepe_to_gst(line)
        try:
            if cfg.ENABLE_SERIAL_CLIENT:
                # Only send a line if the last transmit completed - avoid buffer overflow
                if self.serial.uart.txdone():
                    self.serial.uart.write(line)
        except Exception as e:
            log(f"[GPS DATA] USB serial send exception: {sys.print_exception(e)}")
        try:
            if cfg.ENABLE_BLUETOOTH and self.blue.is_connected():
                self.blue.send(line)
        except Exception as e:
            log(f"[GPS DATA] BT send exception: {sys.print_exception(e)}")
        try:
            if self.net.espnow_connected and cfg.ESPNOW_MODE == "sender":
                await self.net.espnow_sendall(line)
        except Exception as e:
            log(f"[GPS DATA] ESPNow send exception: {sys.print_exception(e)}")
        try:
            # Don't sent NMEA sentences to NTRIP server
            if not isNMEA and self.ntrip_server:
                await self.ntrip_server.send_data(line)
        except Exception as e:
            log(f"[GPS DATA] NTRIP server send exception: {sys.print_exception(e)}")
        # Settle
        asyncio.sleep(0)

    async def run(self):
        """Start various long-running async processes.

        There are 2 conditions which affect which services to start:
        1. GPS data, sourced either from a GPS device, or ESPNOW receiver.
        2. Wifi connection.

        Data source is needed for:
        a. Bluetooth.
        b. Serial output
        c. NTRIP Server.

        Wifi is needed for:
        a. NTRIP services (caster, server, client)
        """
        tasks = []

        self.setup_serial()
        self.setup_networks()

        # Expect to receive gps data (from device, or ESPNOW)
        src_data = True
        if cfg.ENABLE_GPS:
            self.setup_gps()
            # sender goes with GPS device
            if hasattr(cfg, "ESPNOW_MODE") and cfg.ESPNOW_MODE == "sender":
                log("ESPNow: sender mode.")
        elif hasattr(cfg, "ESPNOW_MODE") and cfg.ESPNOW_MODE == "receiver":
            log("ESPNow: receiver mode.")
            tasks.append(self.espnow_reader())
        else:
            log("No GPS source available. Serial, Bluetooth and NTRIP server output will be disabled.")
            src_data = False

        self.blue = None
        # No point enabling bluetooth if no GPS data to send
        if src_data and cfg.ENABLE_BLUETOOTH:
            self.blue = Blue(name=cfg.DEVICE_NAME)
            # Set custom BLE write callback
            self.blue.write_callback = self.esp32_write_data

        # NTRIP needs a network connection
        if self.net.wifi_connected:
            if 'caster' in cfg.NTRIP_MODE:
                self.ntrip_caster = ntrip.Caster(cfg.NTRIP_CASTER_BIND_ADDRESS, cfg.NTRIP_CASTER_BIND_PORT, cfg.NTRIP_SOURCETABLE, cfg.NTRIP_CLIENT_CREDENTIALS, cfg.NTRIP_SERVER_CREDENTIALS)
                tasks.append(asyncio.create_task(self.ntrip_caster.run()))
                # Allow Caster to start before Server/Client
                await asyncio.sleep(2)
            if src_data and 'server' in cfg.NTRIP_MODE:
                self.ntrip_server = ntrip.Server(cfg.NTRIP_CASTER, cfg.NTRIP_PORT, cfg.NTRIP_MOUNT, cfg.NTRIP_CLIENT_CREDENTIALS)
                tasks.append(asyncio.create_task(self.ntrip_server.run()))
            if cfg.ENABLE_GPS and 'client' in cfg.NTRIP_MODE:
                self.ntrip_client = ntrip.Client(cfg.NTRIP_CASTER, cfg.NTRIP_PORT, cfg.NTRIP_MOUNT, cfg.NTRIP_CLIENT_CREDENTIALS)
                tasks.append(asyncio.create_task(self.ntrip_client.run()))
                tasks.append(self.ntrip_client_read())

        await asyncio.gather(*tasks)

        # keep the loop alive
        while True:
            await asyncio.sleep(1)


if __name__ == "__main__":
    e32gps = ESP32GPS()
    asyncio.run(e32gps.run())
