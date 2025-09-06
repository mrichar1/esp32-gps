"""Provide simple NTRIP Client, Server and Caster functionality."""

import asyncio
import gc
import sys
import time
from collections import deque
import config as cfg
from gps_utils import log

try:
    from ubinascii import b2a_base64 as b64encode
except ModuleNotFoundError:
    from base64 import b64encode


example_data = bytes([
    0xD3, 0x00, 0x40, 0x41, 0x2E, 0x06, 0x44, 0x19, 0x1E, 0xF5, 0x00,
    0xA4, 0x00, 0x00, 0x10, 0xB6, 0x11, 0x08, 0xC2, 0xE8, 0x1D, 0x58,
    0x1A, 0x72, 0xC8, 0x46, 0xCD, 0x1A, 0x08, 0xEA, 0x81, 0x2C, 0x3E,
    0xDC, 0x1B, 0xBB, 0xD9, 0x5D, 0x90, 0x61, 0xE8, 0x05, 0x2F, 0xFB,
    0x89, 0x9A, 0x4D, 0xCC, 0xEB, 0xFE, 0x4C, 0x25, 0x28, 0xFB, 0x6C,
    0xDA, 0x7F, 0x61, 0x8E, 0x60, 0x9C, 0xBF, 0xFB, 0x6A, 0x2D, 0x30,
    0x02, 0x19, 0x8F, 0x73
])


class Base():

    def __init__(self, host="", port=2101, mount="ESP32", credentials="c:c"):
        self.name = None
        self.host = host
        self.port = port
        self.mount = mount
        self.credb64 =  b64encode(credentials.encode('ascii')).decode().strip()
        self.useragent = "NTRIP ESP32_GPS Client/1.0"
        self.request_headers = None
        self.reader = None
        self.writer = None
        # Set a very large max-len as never want to hit it
        self.queue = deque([], 128)
        self.event = asyncio.Event()

    def build_headers(self, method, mount=None):
        mount = mount or self.mount
        return (
            f"{method} /{mount} HTTP/1.1\r\n"
            "Ntrip-Version: Ntrip/2.0\r\n"
            f"User-Agent: {self.useragent}\r\n"
            f"Authorization: Basic {self.credb64}\r\n"
            "Connection: keep-alive\r\n"
            "\r\n"
        ).encode()

    async def caster_connect(self):
        while True:
            try:
                log(f"[{self.name}] Connecting to {self.host}:{self.port}...")
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                break
            except OSError as err:
                log(f"[{self.name}] Connection error: {err}")
                time.sleep(3)

        # Initial login - check response
        login_ok = False
        self.writer.write(self.request_headers)
        await self.writer.drain()
        headers = await self.reader.read(1024)
        headers = headers.split(b"\r\n")
        for line in headers:
            if line.endswith(b"200 OK"):
                login_ok = True
        if not login_ok:
            self.writer.close()
            raise ValueError(headers)


class Client(Base):

    def __init__(self, *args, **kwargs):
        """Defaults to centipede NTRIP service"""
        super().__init__(*args, **kwargs)
        self.name = "Client"
        self.request_headers = self.build_headers(method="GET")

    async def iter_data(self):
        """Read data from caster and yield as requested."""
        while True:
            if self.reader:
                try:
                    data = await self.reader.read(128)
                    if data:
                        yield data
                    else:
                        # Stream closed
                        log(f"[{self.name}] Connection error. Reconnecting...")
                        try:
                            self.writer.close()
                            await self.writer.wait_closed()
                        except:
                            pass
                        await asyncio.sleep(1)
                        await self.caster_connect()
                except (OSError, asyncio.IncompleteReadError):
                    # Would block / timeout
                    await asyncio.sleep(0.01)
                    continue
            else:
                # Reader not ready yet...
                await asyncio.sleep(1)

    async def run(self):
        await self.caster_connect()



class Server(Base):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Server"
        self.request_headers = self.build_headers(method="POST", mount=self.mount)

    async def send_data(self, data):
        """Push data to be sent onto the queue."""
        self.queue.append(data)
        self.event.set()
        await asyncio.sleep(0)

    async def run(self):
        """Connect to caster, then send queued event data in a loop."""
        while True:
            await self.caster_connect()

            try:
                while True:
                    while not self.queue:
                        self.event.clear()
                        await self.event.wait()

                    while self.queue:
                        data = self.queue.popleft()
                        try:
                            self.writer.write(data)
                            await self.writer.drain()
                        except Exception as e:
                            log(f"[{self.name}] Data send failed: {e}. Reconnecting...")
                            # put the data back so it isn’t lost
                            self.queue.appendleft(data)
                            try:
                                if self.writer:
                                    self.writer.close()
                                    await self.writer.wait_closed()
                            except Exception:
                                pass
                            # Delay before reconnecting
                            await asyncio.sleep(3)
                            # End inner loop, triggering reconnect
                            break
                    # yield to the event loop
                    await asyncio.sleep(0)
            except asyncio.CancelledError:
                break


class Caster(Base):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Caster"
        self.clients = {}
        self.servers = {}
        self.sourcetable = (
            #f"CAS;ESP32_GPS;2101;ESP32_GPS;None;0;{cfg.NTRIP_COUNTRY_CODE};{cfg.NTRIP_BASE_LATITUDE};{cfg.NTRIP_BASE_LONGITUDE};0.0.0.0;0;https://github.com/mrichar1/esp32-gps\r\n"
            f"STR;{self.mount};{cfg.NTRIP_COUNTRY_CODE};RTCM3;1005,1006,1033,1077,1087,1097,1107,1127,1230;2;GLO+GAL+QZS+BDS+GPS;NONE;{cfg.NTRIP_COUNTRY_CODE};{cfg.NTRIP_BASE_LATITUDE};{cfg.NTRIP_BASE_LONGITUDE};0;0;NTRIP ESP32_GPS {cfg.GPS_HARDWARE};none;N;N;15200;{cfg.DEVICE_NAME}\r\n"
            "ENDSOURCETABLE\r\n"
        ).encode()

    @staticmethod
    def rtcm_parser(buffer):
        """
        Parse a bytearray buffer for RTCM3 messages.
        Returns a list of slices (start, end) into the buffer,
        and a trimmed buffer containing only leftover bytes.
        """
        messages = []
        offset = 0
        buf_len = len(buffer)

        while offset + 3 <= buf_len:
            # Skip until we find RTCM preamble
            if buffer[offset] != 0xD3:
                offset += 1
                continue

            # Read payload length
            length = ((buffer[offset + 1] & 0x03) << 8) | buffer[offset + 2]
            total_len = 3 + length + 3

            if offset + total_len > buf_len:
                # incomplete message
                break

            messages.append(buffer[offset:offset + total_len])
            offset += total_len

        # Return messages and remaining buffer
        return messages, buffer[offset:]

    @staticmethod
    async def send_headers(writer, content_type="text/plain", sourcetable=False):
        conn_type = "keep-alive"
        proto = "HTTP/1.1"
        if sourcetable:
            # Close connection once sent
            conn_type = "close"
            # Some clients seem to always want SOURCETABLE line, even for v2
            proto = "SOURCETABLE"

        response_headers = (
            f"{proto} 200 OK\r\n"
            "Server: NTRIP ESP32_GPS/2.0\r\n"
            "Ntrip-Version: Ntrip/2.0\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Connection: {conn_type}\r\n"
            "\r\n"
        ).encode()
        try:
            writer.write(response_headers)
            await writer.drain()
        except OSError as e:
            writer.close()
            await writer.wait_closed()

    async def drop_connection(self, writer, conn_type="client"):
        """Close stale connections and remove from the list."""

        conn_dict = self.servers if conn_type == "server" else self.clients

        addr = writer.get_extra_info('peername')
        title = conn_type[0].upper() + conn_type[1:]
        log(f"[{self.name}] {title} disconnected: {addr}")
        conn_dict.pop(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except:
            pass

    async def probe_connections(self):
        """Probe clients and servers evry 10 seconds to check still connected."""

        while True:
            # If no servers and no clients, sleep
            if not self.servers and not self.clients:
                await asyncio.sleep(10)

            for s_reader, s_writer in list(self.servers.values()):
                try:
                    probe = s_writer.write(b"")
                    await s_writer.drain()
                except OSError:
                    # No server data written (but still connected)
                    pass
                except Exception as e:
                    log(f"Exception: {sys.print_exception(e)}")
                    await self.drop_connection(s_writer, conn_type="server")
                    try:
                        s_writer.close()
                        await s_writer.wait_closed()
                    except:
                        pass
            for c_reader, c_writer in self.clients.values():
                try:
                    probe = await c_reader.read(1)
                except OSError:
                    # No client data received (but still connected)
                    pass
                except:
                    await self.drop_connection(c_writer)
                    try:
                        c_writer.close()
                        await c_writer.wait_closed()
                    except:
                        pass

            gc.collect()
            # Wait 10 secs
            await asyncio.sleep(10)

    async def handle_data(self):
        # Do nothing if no clients or servers connected
        while True:
            if not self.servers or not self.clients:
                await asyncio.sleep(0.1)
                continue

            for s_reader, s_writer in list(self.servers.values()):
                buffer = bytearray()
                try:
                    data = await s_reader.read(512)
                    if not data:
                        # Empty data = server disconnect
                        await self.drop_connection(s_writer, conn_type="server")
                        continue
                    buffer.extend(data)
                    # Write to all clients
                    msgs, buffer = self.rtcm_parser(buffer)
                    for c_reader, c_writer in self.clients.values():
                        for msg in msgs:
                            try:
                                c_writer.write(msg)
                                await c_writer.drain()
                            except:
                                await self.drop_connection(c_writer)
                                # Don't send more messages
                                break
                except:
                    await self.drop_connection(s_writer, conn_type="server")

    async def handle_connection(self, reader, writer):
        addr = writer.get_extra_info('peername')
        log(f"[{self.name}] Connection from: {addr}")
        try:
            req = await reader.read(1024)
            req = req.decode()

        except OSError:
            return

        authorised = False
        # Check authorisation
        for line in req.splitlines():
            if line.startswith("Authorization"):
                auth_val = line.split("Basic ", 1)[1]
                if auth_val == self.credb64:
                    authorised = True
                else:
                    log(f"[{self.name}] Authorisation failed: {addr}")

        if req.startswith("GET / "):
            # Send SOURCETABLE to client, then close
            log(f"[{self.name}] Client requested Sourcetable")
            await self.send_headers(writer, sourcetable=True)
            try:
                writer.write(self.sourcetable)
                await writer.drain()
            except OSError as e:
                pass
            finally:
                writer.close()
                await writer.wait_closed()
        # SOURCETABLE requests can be unauthorised
        elif not authorised:
            writer.write("HTTP/1.1 401 Invalid Username or Password\r\n\r\n".encode())
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        elif req.startswith(f"GET /{self.mount} "):
            # Client downloading RTCM data
            log(f"[{self.name}] Client subscribed: {addr}")
            await self.send_headers(writer, content_type="gnss/data")
            self.clients[writer] = (reader, writer)
        elif req.startswith("POST"):
            if not req.startswith(f"POST /{self.mount}"):
                writer.write("HTTP/1.1 404 Invalid Mountpoint\r\n\r\n".encode())
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            # Server uploading RTCM data
            log(f"[{self.name}] Server subscribed: {addr}")
            await self.send_headers(writer)
            self.servers[writer] = (reader, writer)

    async def run(self):
        addr = cfg.NTRIP_CASTER_BIND_ADDRESS or "0.0.0.0"
        port = cfg.NTRIP_CASTER_BIND_PORT or 2101

        # Background tasks
        asyncio.create_task(self.handle_data())
        asyncio.create_task(self.probe_connections())

        log(f"[{self.name}] Listening on {addr}:{port}")
        await asyncio.start_server(self.handle_connection, addr, port, backlog=10)
