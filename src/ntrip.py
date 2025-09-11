"""Provide simple NTRIP Client, Server and Caster functionality."""

import asyncio
import gc
import sys
import time
from collections import deque
from gps_utils import log

DEBUG=True

try:
    from ubinascii import b2a_base64 as b64encode
except ModuleNotFoundError:
    from base64 import b64encode

# Exception to raise for Caster authentication errors
class AuthError(Exception):
    pass


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
        # Assuming avg RTCM message is 200 bytes, queue around 2048bytes of them
        # (in usual operation, queue never grows to more than 2 with clients reading from caster)
        self.queue = deque([], 10)
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
                self.writer.write(self.request_headers)
                await self.writer.drain()
                headers = await self.reader.read(1024)
                headers = headers.split(b"\r\n")
                for line in headers:
                    if line.endswith(b"200 OK"):
                        break
                else:
                    # Not valid login
                    raise ValueError(headers)
                break
            except (OSError, ValueError) as err:
                log(f"[{self.name}] Connection error: {err}")
                try:
                    self.writer.close()
                except:
                    pass
                # Wait before trying to reconnect
                asyncio.sleep(3)

            # Initial login - check response
            except OSError:
                pass

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
                        except Exception as e:
                            if DEBUG:
                                sys.print_exception(e)
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
                        try:
                            self.writer.write(self.queue[0])
                            await self.writer.drain()
                            self.queue.popleft()
                        except Exception as e:
                            log(f"[{self.name}] Data send failed: {e}. Reconnecting...")
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


class Caster():

    def __init__(self, bind_address="0.0.0.0", bind_port=2101, sourcetable="", cli_creds="c:c", srv_creds="c:c"):
        self.name = "Caster"
        self.bind_address = bind_address
        self.bind_port = bind_port
        self.sourcetable = sourcetable.replace("\n", "\r\n").encode() or "STR;ESP32;ESP32_GPS;RTCM 3.3;;2;GPS;;GB;51.476;0.00;0;0;;none;B;;9600;\r\n"
        self.cli_credb64 =  b64encode(cli_creds.encode('ascii')).decode().strip()
        self.srv_credb64 =  b64encode(srv_creds.encode('ascii')).decode().strip()
        # { MNT: { clients: {(r, w)}, servers: {(r, w)}}}
        self.allowed_mounts = set()
        self.mounts = {}
        self.server_tasks = {}

    def get_allowed_mounts(self):
        """Populate allowed_mounts dict with all mountpoints in SOURCETABLE."""
        for line in self.sourcetable.split(b"\r\n"):
            if line.startswith(b"STR"):
                self.allowed_mounts.add(line.split(b";")[1].decode())

    @staticmethod
    async def send_headers(writer, content_type="text/plain", status="200"):
        status_line = "HTTP/1.1 200 OK"
        conn_type = "keep-alive"
        # If True, close connection after sending headers
        close_conn = False
        if status == "404":
            status_line = "HTTP/1.1 404 Invalid Mountpoint\r\n\r\n"
            conn_type = "close"
            close_conn = True
        elif status == "409":
            status_line = "HTTP/1.1 409 Mountpoint Conflict\r\n\r\n"
            conn_type = "close"
            close_conn = True
        elif status == "503":
            status_line = "HTTP/1.1 503 Mountpoint Unavailable\r\n\r\n"
            conn_type = "close"
            close_conn = True
        elif status == "sourcetable":
            status_line = "SOURCETABLE 200 OK"
            conn_type = "close"

        response_headers = (
            f"{status_line}\r\n"
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

        if close_conn:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                if DEBUG:
                    sys.print_exception(e)

    async def drop_connection(self, mount, writer, conn_type="client"):
        """Close stale connections and remove from the list."""

        conn_dict = self.mounts[mount]["servers"] if conn_type == "server" else self.mounts[mount]["clients"]

        addr = writer.get_extra_info('peername')
        title = conn_type[0].upper() + conn_type[1:]
        log(f"[{self.name}] {title} disconnected: {addr}")
        try:
            conn_dict.pop(writer)
        except KeyError:
            pass
        if conn_type == "server":
            # cancel asyncio background server task
            task = self.server_tasks.pop((mount, writer), None)
            if task and task is not asyncio.current_task():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            if DEBUG:
                sys.print_exception(e)
        if conn_type == "server":
            # Remove all associated clients and delete mount
            for client in self.mounts[mount]["clients"]:
                try:
                    client.write("Mountpoint unavailable. Please try again later.\r\n".encode())
                    client.close()
                    await client.wait_closed()
                except Exception as e:
                    # Client already gone
                    if DEBUG:
                        sys.print_exception(e)
            del self.mounts[mount]

    async def probe_connections(self):
        """Probe clients and servers
        evry N seconds to check still connected."""

        # Seconds to sleep between probe attempts
        probe_cycle = 5

        while True:
            # Sleep if no servers and no clients
            if not any(d.get("clients") or d.get("servers") for d in self.mounts.values()):
                await asyncio.sleep(probe_cycle)
                continue

            for mount, conns in self.mounts.items():
                for s_writer, s_reader in list(conns["servers"].items()):
                    try:
                        s_writer.write(b"")
                        await s_writer.drain()
                    except OSError:
                        await self.drop_connection(mount, s_writer, conn_type="server")
                        try:
                            s_writer.close()
                            await s_writer.wait_closed()
                        except Exception as e:
                            if DEBUG:
                                sys.print_exception(e)
                    except Exception as e:
                        if DEBUG:
                            sys.print_exception(e)
                for c_writer, c_reader in list(conns["clients"].items()):
                    try:
                        probe = await c_reader.read(128)
                        if not probe:
                            await self.drop_connection(mount, c_writer)
                            try:
                                c_writer.close()
                                await c_writer.wait_closed()
                            except Exception as e:
                                if DEBUG:
                                    sys.print_exception(e)
                    except OSError:
                        await self.drop_connection(mount, c_writer)
                        try:
                            c_writer.close()
                            await c_writer.wait_closed()
                        except Exception as e:
                            if DEBUG:
                                sys.print_exception(e)

            gc.collect()
            await asyncio.sleep(probe_cycle)

    async def server_loop(self, mount, conns, s_writer, s_reader):
        """Loop reading from server and writing to client(s)"""
        try:
            while True:
                if mount not in self.mounts or not len(conns["clients"]):
                    # No server or clients associated with this mount any more.
                    break
                try:
                    # Max msg length for RTCM is 1023
                    data = await s_reader.read(1024)
                    if not data:
                        # Empty data = server disconnect
                        raise OSError
                except OSError:
                    await self.drop_connection(mount, s_writer, conn_type="server")
                    break
                cli_remove = []
                for c_writer, _ in conns["clients"].items():
                    try:
                        c_writer.write(data)
                        await c_writer.drain()
                    except OSError:
                        # Flag client for removal at end of loop
                        cli_remove.append(c_writer)
                        # Don't send more messages
                        break
                for c_writer in cli_remove:
                    await self.drop_connection(mount, c_writer)

                # Yield control
                await asyncio.sleep_ms(1)

        except Exception as e:
            if DEBUG:
                sys.print_exception(e)
            await self.drop_connection(mount, s_writer, conn_type="server")



    async def handle_data(self):
        # Do nothing if no clients or servers connected
        while True:
            # Sleep unless a mount point has both client and server connections
            if not any(d.get("clients") and d.get("servers") for d in self.mounts.values()):
                await asyncio.sleep(0.1)
                continue

            for mount, conns in self.mounts.items():
                # Only continue if there are clients to receive data
                if len(conns["clients"]):
                    for s_writer, s_reader in list(conns["servers"].items()):
                        key = (mount, s_writer)
                        if key not in self.server_tasks:
                            task = asyncio.create_task(self.server_loop(mount, conns, s_writer, s_reader))
                            self.server_tasks[key] = task
            await asyncio.sleep(0.1)



    async def handle_connection(self, reader, writer):
        addr = writer.get_extra_info('peername')
        log(f"[{self.name}] Connection from: {addr}")
        try:
            req = await reader.read(1024)
            req = req.decode()

        except OSError:
            return

        # Get client's password from headers
        password = None
        for line in req.splitlines():
            if line.startswith("Authorization"):
                password = line.split("Basic ", 1)[1]
        try:
            method, mount, _ = req.split(None,2)
            if mount == "/":
                # Send SOURCETABLE to client, then close
                log(f"[{self.name}] Client requested Sourcetable")
                await self.send_headers(writer, status="sourcetable")
                try:
                    writer.write(self.sourcetable)
                    await writer.drain()
                except OSError as e:
                    pass
                finally:
                    writer.close()
                    await writer.wait_closed()
                    return

            mount = mount.lstrip("/")
            if method == "GET":
                # Client downloading RTCM data
                if not password == self.cli_credb64:
                    raise AuthError
                if mount not in self.mounts:
                    # No Server is supplying data for that mountpoint
                    status = "503"
                    if mount not in self.allowed_mounts:
                        # Mount not in sourcetable at all
                        status = "404"
                    await self.send_headers(writer, status=status)
                    return
                log(f"[{self.name}] Client subscribed: {addr}")
                await self.send_headers(writer, content_type="gnss/data")
                self.mounts[mount]["clients"][writer] = reader
                return
            elif method == "POST":
                # Server uploading RTCM data
                if not password == self.srv_credb64:
                    raise AuthError
                if mount not in self.allowed_mounts:
                    # Mount not in sourcetable
                    await self.send_headers(writer, status="404")
                    return
                if mount in self.mounts:
                    # Another server is supplying this mountpoint
                    await self.send_headers(writer, status="409")
                    return
                log(f"[{self.name}] Server subscribed: {addr}")
                await self.send_headers(writer)
                self.mounts[mount] = {"servers": {writer: reader}, "clients": {}}
        except AuthError:
            writer.write("HTTP/1.1 401 Invalid Username or Password\r\n\r\n".encode())
            writer.close()
            await writer.wait_closed()
        except:
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass
        asyncio.sleep(0)


    async def run(self):
        self.get_allowed_mounts()

        # Background tasks
        asyncio.create_task(self.handle_data())
        asyncio.create_task(self.probe_connections())

        log(f"[{self.name}] Listening on {self.bind_address}:{self.bind_port}")
        await asyncio.start_server(self.handle_connection, self.bind_address, self.bind_port)
