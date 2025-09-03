"""Provide simple NTRIP Client, Server and Caster functionality."""

import socket
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
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                # # Keepalive pings - after 5 secs, send a poing every 5 secs 6 times, then drop
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 10)
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 3)
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
                self.socket.connect((self.host, self.port))
                break
            except OSError as err:
                log(f"Connection error: {err}")
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
        self.request_headers = self.build_headers(method="GET")
        self.caster_connect()
        self.socket.setblocking(False)

        # FIXME: Take out - send/recv data should be called by importing code
        for chunk in self.iter_data():
            log(f"CH: {chunk}")

    def iter_data(self):
        while True:
            try:
                data = self.socket.recv(128)
                if data:
                    yield data
                else:
                    # Socket closed
                    log(f"Connection error. Reconnecting...")
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
        self.request_headers = self.build_headers(method="POST", mount=self.mount)
        self.caster_connect()
        self.test_sending()

    def test_sending(self):
        # FIXME: Take out - send_data should be called by importing code
        while True:
            # FIXME: slight delay to stay under 115200 baud -should be 0.1!
            time.sleep(1)
            #log("Send")
            self.send_data(example_data)

    def send_data(self, data):
        try:
            self.socket.sendall(data)
        except Exception as e:
            log(f"Data send error: {e}. Reconnecting...")
            try:
                self.socket.close()
            except:
                pass
            time.sleep(1)
            self.caster_connect()


class Caster(Base):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clients = set()
        self.servers = set()
        self.sourcetable = (
            #f"CAS;ESP32_GPS;2101;ESP32_GPS;None;0;{cfg.NTRIP_COUNTRY_CODE};{cfg.NTRIP_BASE_LATITUDE};{cfg.NTRIP_BASE_LONGITUDE};0.0.0.0;0;https://github.com/mrichar1/esp32-gps\r\n"
            f"STR;{self.mount};{cfg.NTRIP_COUNTRY_CODE};RTCM3;1005,1006,1033,1077,1087,1097,1107,1127,1230;2;GLO+GAL+QZS+BDS+GPS;NONE;{cfg.NTRIP_COUNTRY_CODE};{cfg.NTRIP_BASE_LATITUDE};{cfg.NTRIP_BASE_LONGITUDE};0;0;NTRIP ESP32_GPS {cfg.GPS_HARDWARE};none;N;N;15200;{cfg.DEVICE_NAME}\r\n"
            "ENDSOURCETABLE\r\n"
        ).encode()
        self.run()

    def run(self):
        addr = getattr(cfg, "NTRIP_CASTER_ADDRESS", "0.0.0.0")
        port = getattr(cfg, "NTRIP_CASTER_PORT", 2101)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((addr, port))
        self.socket.listen(5)
        self.socket.setblocking(False)

        try:
            while True:
                # Accept new connections
                try:
                    conn, addr = self.socket.accept()
                    conn.setblocking(False)
                    self.handle_connection(conn)
                except OSError:
                    # No new connection
                    pass
                except:
                    self.socket.close()

                # Use a copy of the set to allow removals during iteration
                for server in list(self.servers):
                    try:
                        data = server.recv(1024)
                        if data:
                            # Broadcast to all clients
                            for client in list(self.clients):
                                try:
                                    client.send(data)
                                except:
                                    self.clients.remove(client)
                                    client.close()
                        else:
                            # Empty data = server disconnect
                            self.servers.remove(server)
                            server.close()
                    except OSError:
                        # No server data received
                        pass
                    except:
                        self.servers.remove(server)
                        server.close()

                # Small sleep to allow data settling
                time.sleep(0.01)
        except KeyboardInterrupt as e:
            print(f"EXC: {e}")
        except Exception as e:
            print(f"EXC: {e}")
        finally:
            try:
                self.socket.shutdown(socket.SHUT_WR)
                self.socket.close()
            except:
                pass

    @staticmethod
    def send_headers(conn, sourcetable=False):
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
            "Content-Type: text/plain\r\n"
            f"Connection: {conn_type}\r\n"
            "\r\n"
        ).encode()
        conn.sendall(response_headers)

    def handle_connection(self, conn):
        try:
            req = conn.recv(1024).decode(errors="ignore")
        except OSError:
            return

        try:
            authorised = False
            # Check authorisation
            for line in req.splitlines():
                if line.startswith("Authorization"):
                    auth_val = line.split("Basic ", 1)[1]
                    if auth_val == self.credb64:
                        authorised = True

            if req.startswith("GET / "):
                # Send SOURCETABLE to client, then close
                log(f"[CLIENT] sourcetable")
                self.send_headers(conn, sourcetable=True)
                conn.sendall(self.sourcetable)
                conn.close()
            # SOURCETABLE requests can be unauthorised
            elif not authorised:
                conn.sendall("HTTP/1.1 401 Invalid Username or Password\r\n\r\n".encode())
                conn.close()
            elif req.startswith(f"GET /{self.mount} "):
                # Client downloading RTCM data
                log(f"[CLIENT] subscribed: {req}")
                self.send_headers(conn)
                self.clients.add(conn)
            elif req.startswith("POST"):
                if not req.startswith(f"POST /{self.mount}"):
                    conn.sendall("HTTP/1.1 404 Invalid Mountpoint\r\n\r\n".encode())
                    conn.close()
                    return
                # Server uploading RTCM data
                log(f"[SERVER] subscribed: {req}")
                self.send_headers(conn)
                self.servers.add(conn)
        except Exception as e:
            print("E", e)
            self.socket.close()
