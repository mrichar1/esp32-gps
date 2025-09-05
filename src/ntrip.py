"""Provide simple NTRIP Client, Server and Caster functionality."""

import select
import socket
import sys
import time
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
        self.socket = None

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

    def caster_connect(self):
        while True:
            try:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(10)
                log(f"[{self.name}] Connecting to {self.host}:{self.port}...")
                self.socket.connect(socket.getaddrinfo(self.host, self.port)[0][-1])
                break
            except OSError as err:
                log(f"[{self.name}] Connection error: {err}")
                time.sleep(3)

        # Initial login - check response
        login_ok = False
        self.socket.sendall(self.request_headers)
        headers = self.socket.recv(2048).split(b"\r\n")
        for line in headers:
            if line.endswith(b"200 OK"):
                login_ok = True
        if not login_ok:
            self.socket.close()
            raise ValueError(headers)


class Client(Base):

    def __init__(self, *args, **kwargs):
        """Defaults to centipede NTRIP service"""
        super().__init__(*args, **kwargs)
        self.name = "Client"

    def run(self):
        self.request_headers = self.build_headers(method="GET")
        self.caster_connect()
        self.socket.setblocking(False)

    def iter_data(self):
        while True:
            try:
                data = self.socket.recv(128)
                if data:
                    yield data
                else:
                    # Socket closed
                    log(f"[{self.name}] Connection error. Reconnecting...")
                    try:
                        self.socket.close()
                    except:
                        pass
                    time.sleep(1)
                    self.caster_connect()
            except OSError:
                # Would block / timeout
                time.sleep(0.01)
                continue


class Server(Base):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Server"

    def run(self):
        self.request_headers = self.build_headers(method="POST", mount=self.mount)
        self.caster_connect()
        # FIXME: Event loop (use machine sleep?)
        while True:
            time.sleep(1)

    def send_data(self, data):
        if self.socket:
            try:
                self.socket.sendall(data)
            except Exception as e:
                log(f"[{self.name}] Data send error: {e}. Reconnecting...")
                try:
                    self.socket.close()
                except:
                    pass
                time.sleep(1)
                self.caster_connect()


class Caster(Base):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Caster"
        self.clients = {}
        self.servers = {}
        self.clients_remove = set()
        self.servers_remove = set()
        self.sourcetable = (
            #f"CAS;ESP32_GPS;2101;ESP32_GPS;None;0;{cfg.NTRIP_COUNTRY_CODE};{cfg.NTRIP_BASE_LATITUDE};{cfg.NTRIP_BASE_LONGITUDE};0.0.0.0;0;https://github.com/mrichar1/esp32-gps\r\n"
            f"STR;{self.mount};{cfg.NTRIP_COUNTRY_CODE};RTCM3;1005,1006,1033,1077,1087,1097,1107,1127,1230;2;GLO+GAL+QZS+BDS+GPS;NONE;{cfg.NTRIP_COUNTRY_CODE};{cfg.NTRIP_BASE_LATITUDE};{cfg.NTRIP_BASE_LONGITUDE};0;0;NTRIP ESP32_GPS {cfg.GPS_HARDWARE};none;N;N;15200;{cfg.DEVICE_NAME}\r\n"
            "ENDSOURCETABLE\r\n"
        ).encode()

    @staticmethod
    def rtcm_parser(buffer=b""):
        """Process a bytearray buffer, extracting RTCM messages.
        Returns a list of complete messages, and any leftover buffer."""
        messages = []
        offset = 0

        while offset < len(buffer):
            # Header is min 3 bytes
            if len(buffer) < 3:
                break

            if buffer[0] != 0xD3:
                # Check for RTCM3 preamble byte
                offset += 1
                continue

            length = ((buffer[offset + 1] & 0x03) << 8) | buffer[offset + 2]
            total_len = 3 + length + 3  # header + payload + CRC

            if len(buffer) - offset < total_len:
                break  # Incomplete message

            # Append slice of bytearray directly
            messages.append(buffer[offset:offset + total_len])
            offset += total_len

            # Return messages and remaining buffer as slice
            return messages, buffer[offset:]


    def drop_connection(self, conn, addr, conn_type="client"):
        # Micropython str has no title() attribute
        title = conn_type[0].upper() + conn_type[1:]
        log(f"[{self.name}] {title} disconnected: {addr}")
        try:
            conn.close()
        except:
            pass
        if conn_type == "client":
            self.clients_remove.add(conn)
        else:
            self.servers_remove.add(conn)

    def run(self):
        addr = cfg.NTRIP_CASTER_BIND_ADDRESS or "0.0.0.0"
        port = cfg.NTRIP_CASTER_BIND_PORT or 2101
        log(f"[{self.name}] Listening on {addr}:{port}")
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((addr, port))
        self.socket.listen(5)
        self.socket.setblocking(False)

        try:
            while True:
                self.servers_remove = set()
                self.clients_remove = set()
                # Only watch servers if there are clients to send to
                server_conns = [conn for conn in self.servers] if self.clients else []
                client_conns = [conn for conn in self.clients]
                read_list = [self.socket] + server_conns + client_conns
                write_list = server_conns

                readable, writeable, _ = select.select(read_list, write_list, [], 0.1)

                for sock in readable:
                    # Caster listening socket
                    if sock is self.socket:
                        conn, addr = self.socket.accept()
                        log(f"[{self.name}] Connection from: {addr}")
                        conn.setblocking(False)
                        self.handle_connection(conn, addr)
                    # Server socket
                    elif sock in self.servers:
                        # Handle server/client sockets
                        buffer = bytearray()
                        s_conn, s_addr = self.servers[sock]
                        try:
                            chunk = s_conn.recv(1024)
                        except OSError:
                            # No server data received (but still connected)
                            continue
                        except Exception as e:
                            log(f"[{self.name}] Server error: {sys.print_exception(e)}")
                            self.drop_connection(s_conn, s_addr, conn_type="server")
                            continue
                        if not chunk:
                            # Empty data = server disconnect
                            self.drop_connection(s_conn, s_addr, conn_type="server")
                            continue
                        buffer.extend(chunk)
                        msgs, buffer = self.rtcm_parser(buffer)
                        # Broadcast to all clients
                        for client in self.clients:
                            c_conn, c_addr = self.clients[client]
                            for msg in msgs:
                                try:
                                    c_conn.sendall(msg)
                                except Exception as e:
                                    log(f"[{self.name}] Client error: {sys.print_exception(e)}")
                                    self.drop_connection(c_conn, c_addr, conn_type="client")
                                    # Skip remaining messages for this client
                                    break
                    else:
                        # Client socket
                        c_conn, c_addr = self.clients[sock]
                        try:
                            c_conn.recv(1)
                        except OSError:
                            # No client data received (but still connected)
                            pass
                        except:
                            self.drop_connection(c_conn, c_addr, conn_type="client")
                for sock in writeable:
                    s_conn, s_addr = self.servers[sock]
                    try:
                        s_conn.send(b"")
                    except OSError:
                        # No server data read (but still connected)
                        pass
                    except:
                        self.drop_connection(s_conn, s_addr, conn_type="server")

                # Remove disconnected clients/servers
                for client in self.clients_remove:
                    self.clients.pop(client, None)
                for server in self.servers_remove:
                    self.servers.pop(server, None)

        except KeyboardInterrupt as e:
            pass
        except Exception as e:
            log(f"[{self.name} Exception: {sys.print_exception(e)}")
        finally:
            try:
                self.socket.shutdown(socket.SHUT_WR)
                self.socket.close()
            except:
                pass

    @staticmethod
    def send_headers(conn, content_type="text/plain", sourcetable=False):
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
        conn.sendall(response_headers)

    def handle_connection(self, conn, addr):
        try:
            req = conn.recv(1024).decode()
        except OSError:
            return

        authorised = False
        # Check authorisation
        for line in req.splitlines():
            if line.startswith("Authorization"):
                auth_val = line.split("Basic ", 1)[1]
                if auth_val == self.credb64:
                    authorised = True

        if req.startswith("GET / "):
            # Send SOURCETABLE to client, then close
            log(f"[{self.name}] Client requested Sourcetable")
            self.send_headers(conn, sourcetable=True)
            conn.sendall(self.sourcetable)
            conn.close()
        # SOURCETABLE requests can be unauthorised
        elif not authorised:
            conn.sendall("HTTP/1.1 401 Invalid Username or Password\r\n\r\n".encode())
            conn.close()
        elif req.startswith(f"GET /{self.mount} "):
            # Client downloading RTCM data
            log(f"[{self.name}] Client subscribed: {addr}")
            self.send_headers(conn, content_type="gnss/data")
            self.clients[conn] = (conn, addr)
        elif req.startswith("POST"):
            if not req.startswith(f"POST /{self.mount}"):
                conn.sendall("HTTP/1.1 404 Invalid Mountpoint\r\n\r\n".encode())
                conn.close()
                return
            # Server uploading RTCM data
            log(f"[{self.name}] Server subscribed: {addr}")
            self.send_headers(conn)
            self.servers[conn] = (conn, addr)
