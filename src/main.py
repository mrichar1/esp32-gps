import asyncio
from machine import UART, reset
import sys
import time
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
        self.blue = None
        self.gps = None
        self.irq_event = asyncio.ThreadSafeFlag()
        self.espnow_event = asyncio.ThreadSafeFlag()
        self.shutdown_event = asyncio.Event()
        self.serial = None
        self.ntrip_caster = None
        self.ntrip_server = None
        self.ntrip_client = None

    def setup_gps(self):
        log("Enabling GPS device.")
        try:
            self.gps = GPS(uart=cfg.GPS_UART, baudrate=cfg.GPS_BAUD_RATE, tx=cfg.GPS_TX_PIN, rx=cfg.GPS_RX_PIN)
        except (AttributeError, ValueError, OSError) as e:
            log(f"Error setting up GPS: {e}")
            return
        if hasattr(self.gps, "uart"):
            if (cmds := getattr(cfg, "GPS_SETUP_COMMANDS", None)):
                # Prefix used to filter response messages
                prefix = getattr(cfg, "GPS_SETUP_RESPONSE_PREFIX", "")
                for cmd in cmds:
                    self.gps.write_nmea(cmd, prefix)

            # Set up GPS read irq callback
            self.gps.uart.irq(self.uart_read_handler, UART.IRQ_RXIDLE)


    def setup_serial(self):
        log_serial = getattr(cfg, "LOG_TO_SERIAL", False)
        try:
            self.serial = Serial(uart=cfg.SERIAL_UART, baudrate=cfg.SERIAL_BAUD_RATE, tx=cfg.SERIAL_TX_PIN, rx=cfg.SERIAL_RX_PIN, log_serial=log_serial)
        except AttributeError:
            # No config options passed in
            pass


    def setup_networks(self):
        txpower = getattr(cfg, "WIFI_TXPOWER", None)
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
        if (
            "server" in getattr(cfg, "NTRIP_MODE", []) or
            getattr(cfg, "ESPNOW_MODE", None) == "sender" or
            hasattr(cfg, "ENABLE_SERIAL_CLIENT") or
            (self.blue and self.blue.is_connected())
        ):
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
        self.tasks = []

        # Start serial early, as logs may be redirected to it.
        if getattr(cfg, "ENABLE_SERIAL_CLIENT", None):
            self.setup_serial()
            if hasattr(self.serial, 'uart'):
                log(f"Serial output enabled (UART{self.serial.id})")
            else:
                # Serial setup didn't create uart for some reason, so turn off serial logging
                cfg.ENABLE_SERIAL_CLIENT = False

        # Set up wifi
        self.setup_networks()

        # Expect to receive gps data (from device, or ESPNOW)
        src_data = True
        espnow_mode = getattr(cfg, "ESPNOW_MODE", None)
        if cfg.ENABLE_GPS:
            self.setup_gps()
            # sender goes with GPS device
            if espnow_mode == "sender":
                log("ESPNow: sender mode.")
        elif espnow_mode == "receiver":
            log("ESPNow: receiver mode.")
            self.tasks.append(self.espnow_reader())
        else:
            log("No GPS source available. Serial, Bluetooth and NTRIP server output will be disabled.")
            src_data = False


        # No point enabling bluetooth if no GPS data to send
        if src_data and cfg.ENABLE_BLUETOOTH:
            log("Enabling Bluetooth")
            if self.net.wifi_connected:
                log("WARNING: Many ESP32 devices have insufficient RAM to run Wifi, Bluetooth and ESP32-GPS at the same time!")
            self.blue = Blue(name=cfg.DEVICE_NAME)
            # Set custom BLE write callback
            self.blue.write_callback = self.esp32_write_data

        # NTRIP needs a network connection
        if self.net.wifi_connected:
            if 'caster' in cfg.NTRIP_MODE:
                self.ntrip_caster = ntrip.Caster(cfg.NTRIP_CASTER_BIND_ADDRESS, cfg.NTRIP_CASTER_BIND_PORT, cfg.NTRIP_SOURCETABLE, cfg.NTRIP_CLIENT_CREDENTIALS, cfg.NTRIP_SERVER_CREDENTIALS)
                self.tasks.append(asyncio.create_task(self.ntrip_caster.run()))
                # Allow Caster to start before Server/Client
                await asyncio.sleep(2)
            if src_data and 'server' in cfg.NTRIP_MODE:
                self.ntrip_server = ntrip.Server(cfg.NTRIP_CASTER, cfg.NTRIP_PORT, cfg.NTRIP_MOUNT, cfg.NTRIP_CLIENT_CREDENTIALS)
                self.tasks.append(asyncio.create_task(self.ntrip_server.run()))
            if cfg.ENABLE_GPS and 'client' in cfg.NTRIP_MODE:
                self.ntrip_client = ntrip.Client(cfg.NTRIP_CASTER, cfg.NTRIP_PORT, cfg.NTRIP_MOUNT, cfg.NTRIP_CLIENT_CREDENTIALS)
                self.tasks.append(asyncio.create_task(self.ntrip_client.run()))
                self.tasks.append(self.ntrip_client_read())

        # Wait for shutdown_event signal
        await self.shutdown_event.wait()

    async def shutdown(self):
        """Clean up background processes, handlers etc on exit."""
        # Stop gps irq handling
        if hasattr(self.gps, 'uart'):
            self.gps.uart.irq(None)

        # Stop bluetooth irq handling
        if hasattr(self.blue, 'ble'):
            self.blue.ble.irq(None)

        # Signal ntrip_caster to cleanup
        if hasattr(self.ntrip_caster, "cleanup"):
            await self.ntrip_caster.cleanup()

        # Clean up self
        for task in self.tasks:
            try:
                task.cancel()
            except:
                pass

        # Wait for tasks to exit
        await asyncio.gather(*self.tasks, return_exceptions=True)

if __name__ == "__main__":
    e32gps = ESP32GPS()
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(e32gps.run())

        # The background tasks in e32gps should run forever (or raise exceptions).
        # We only reach here if the event loop exits cleanly - i.e no background tasks.
        log("Exited - nothing to do.")
        log("Enable at least one long-running process in your configuration: (GPS, ESPNow Receiver, NTRIP)")

        # Clean up hanging IRQ etc
        loop.run_until_complete(e32gps.shutdown())

    except (KeyboardInterrupt, Exception) as e:
        e32gps.shutdown_event.set()
        loop.run_until_complete(e32gps.shutdown())
        if isinstance(e, KeyboardInterrupt):
            log("Ctrl-C received - shutting down.")
        else:
            log("Unhandled exception - shutting down.")
            sys.print_exception(e)
            if getattr(cfg, "CRASH_RESET", None):
                log("Hard resetting due to crash...")
                # Delay (to prevent restart tight loop, and give time to read the exception)
                time.sleep(5)
                reset()
