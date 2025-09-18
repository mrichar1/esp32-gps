import asyncio
import aioespnow
import network
import sys
import time
from devices import Logger
try:
    from debug import DEBUG
except ImportError:
    DEBUG=False

log = Logger.getLogger().log

class Net():

    def __init__(self, txpower=None):
        self._buffer = b""
        self.espnow = None
        self.espnow_peers = []
        self.wifi_connected = False
        self.espnow_connected = False
        # Get a handle to wifi interfaces
        self.wlan = network.WLAN(network.WLAN.IF_STA)
        self.wlan.active(True)
        # Some boards (e.g. C3) have more stable connections with lower txpower (5)
        if txpower:
            self.wlan.config(txpower=txpower)
        # Chek if wifi has been set up already (e.g. in boot.py)
        if self.wlan.isconnected():
            self.wifi_connected = True


    def enable_espnow(self, peers=""):
        # Disable power management
        self.wlan.config(pm=network.WLAN.PM_NONE)
        log(f"ESP-Now MAC address: {self.wlan.config('mac')}")
        self.espnow_peers = peers
        self.esp = aioespnow.AIOESPNow()
        self.esp.active(False)
        time.sleep(0.5)
        self.esp.active(True)
        # Increase buffer to hold 10 messages
        self.esp.config(rxbuf=2800)
        for mac in self.espnow_peers:
            # Ensure MAC is in bytes
            mac.encode("utf-8") if isinstance(mac, str) else mac
            self.esp.add_peer(mac)
        self.espnow_connected = True
        log(f"ESP-Now active. Peers: {self.espnow_peers}")

    def enable_wifi(self, ssid, key):
        """Connect to wifi if not already connected."""
        if self.wifi_connected == False or ssid != self.wlan.config('ssid'):
            self.wlan.disconnect()
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
            log(f"WLAN connected, SSID: {self.wlan.config('ssid')}, IP: {self.wlan.ifconfig()[0]}, mac: {self.wlan.config('mac')}, channel: {self.wlan.config("channel")}")

    async def espnow_broadcast(self):
        """Regularly announce presence to other peers via broadcast."""

        broadcast = b"\xff" * 6
        self.esp.add_peer(broadcast)

        while True:
            log("BCast")
            self.esp.send(broadcast, "ESP32-GPS")
            await asyncio.sleep(10)

    async def espnow_find_peers(self):
        """Wrapper around recv to look for peers on sender (which otherwise doesn't recv)"""

        while True:
            # Timeout in recv means we won't tight-loop
            await self.espnow_recv(timeout=10000, discover_peers=True)


    async def espnow_send(self, peer, msg):
        """Send to a specific peer."""
        try:
            await self.esp.asend(peer, msg)
        except OSError:
            pass

    async def espnow_sendall(self, msg):
        """Send to all peers. Split into max 250 byte chunks."""
        # ESP-Now has a 250 byte max message size
        # FIXME: Ideally we can switch to 1024 if this PR is accepted:
        # https://github.com/micropython/micropython/pull/16737
        chunk_size = 250

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

    async def espnow_recv(self, timeout=200, discover_peers=False):
        """Wrapper around read to handle errors."""
        try:
            # A sub-1Hz timeout is sensible for most GPS devices
            data = await asyncio.wait_for_ms(self.esp.airecv(), timeout)
            if data:
                # Check if data is from a known peer
                if data[0] not in self.espnow_peers:
                    # If the message is a 'discovery broadcast' add to peers list
                    if discover_peers and data[0] != self.wlan.config('mac') and data[1] == b"ESP32-GPS":
                        log(f"ESP-Now discovered peer: {data[0]}")
                        self.espnow_peers.append(data[0])
                        self.esp.add_peer(data[0])
                    else:
                        # Drop message
                        return
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
