import asyncio
import aioespnow
import network
import sys
import time
from gps_utils import log

class Net():

    def __init__(self):
        self._buffer = b""
        self.espnow = None
        self.espnow_peers = []
        self.wifi_connected = False
        self.espnow_connected = False
        # Get a handle to wifi interfaces
        self.wlan = network.WLAN(network.WLAN.IF_STA)
        self.wlan.active(True)

    def enable_espnow(self, peers):
        # Try to maximise wifi efficiency
        # Set power as high as possible
        self.wlan.config(txpower(85))
        # Disable power management
        self.wlan.config(pm=network.WLAN.PM_NONE)
        self.espnow_peers = peers
        self.esp = aioespnow.AIOESPNow()
        self.esp.active(False)
        time.sleep(0.5)
        self.esp.active(True)
        # Increase buffer to hold 10 messages
        self.esp.config(rxbuf=2800)
        broadcast = b"\xff" * 6
        self.esp.add_peer(broadcast)
        for mac in self.espnow_peers:
            # Ensure MAC is in bytes
            mac.encode("utf-8") if isinstance(mac, str) else mac
            self.esp.add_peer(mac)
        self.espnow_connected = True
        log("ESPNow active.")

    def enable_wifi(self, ssid, key):
        """Connect to wifi if not already connected."""
        self.wifi_connected = False
        if self.wlan.config('ssid') == ssid and self.wlan.isconnected():
            self.wifi_connected = True
        else:
            # Suggested to improve connection success on some ESP32 C3 devices
            self.wlan.config(txpower(5))
            self.wlan.connect(ssid, key)
            log("Wifi connecting...(allowing up to 20 seconds to complete)")
            for i in range(20):
                time.sleep(1)
                if self.wlan.isconnected():
                    self.wifi_connected = True
                    break
            if not self.wlan.isconnected():
                log("WLAN Connection failed.")

        if self.wifi_connected:
            log(f"WLAN connected, IP: {self.wlan.ifconfig()[0]}, channel: {self.wlan.config("channel")}")


    async def espnow_send(self, peer, msg):
        """Send to a specific peer."""
        try:
            await self.esp.asend(peer, msg)
        except OSError:
            pass

    async def espnow_sendall(self, msg):
        """Send to all peers. Split into max 250 byte chunks."""
        # ESPNow has a 250 byte max message size
        chunk_size = 1024

        data = self._buffer + msg

        # Push short messages to buffer
        if len(data) < chunk_size:
            self._buffer = data
            return
        i = 0
        while i + chunk_size < len(data):
            try:
                chunk = data[i:i+chunk_size]
                await self.esp.asend(chunk)
            except OSError as e:
                pass
            i += chunk_size

        # Push leftover bytes to buffer
        if i < len(data):
            self._buffer = data[i:]

    async def espnow_recv(self, timeout=200):
        """Wrapper around read to handle errors."""
        try:
            # A sub-1Hz timeout is sensible for most GPS devices
            data = await asyncio.wait_for_ms(self.esp.airecv(), timeout)
            if data and data[0] in self.espnow_peers:
                return data[1]
        except asyncio.TimeoutError:
            return None
        except ValueError:
            # BUG: buffer errors need espnow reinitialised
            self.esp.active(False)
            self.esp.active(True)
        except Exception as e:
            sys.print_exception(e)


    @staticmethod
    def reset():
        """Reset network interfaces."""
        self.wlan.active(False)
        time.sleep(0.5)
        self.wlan.active(True)
        self.wlan.disconnect()
        # Setting txpower fixes ESP32 c3 supermini connection issues
        self.wlan.config(txpower=5)
