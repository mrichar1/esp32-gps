import asyncio
from devices import Logger
try:
    from debug import DEBUG
except ImportError:
    DEBUG=False

log = Logger.getLogger().log

class Shell():

    def __init__(self, callbacks={}, bind_address="0.0.0.0", bind_port=51716, password=""):
        self.name = "Remote Shell"
        self.callbacks = callbacks
        self.bind_address = bind_address
        self.bind_port = bind_port
        self.password = password
        self.shutdown_event = asyncio.Event()


    async def handle_connection(self, reader, writer):
        addr = writer.get_extra_info('peername')
        log(f"[{self.name}] Connection from: {addr}")
        writer.write(b">>> ESP32-GPS Remote Shell <<<\n")
        if self.password:
            writer.write(b">>> Enter password: ")
            try:
                req = await reader.read(1024)
                if req == b"":
                    log(f"[{self.name}] Client {addr} disconnected.")
                    writer.close()
                    return
                elif req.strip().decode() != self.password:
                    log(f"[{self.name}] Invalid password.")
                    writer.write(b"Invalid password! Closing connection...\n")
                    writer.close()
                    return
            except OSError:
                return
        while True:
            try:
                writer.write(b"> ")
                req = await reader.read(1024)
                req = req.decode().strip()
                if req == "":
                    log(f"[{self.name}] Client {addr} disconnected.")
                    writer.close()
                    return
                cmd = req
                opts = ""
                try:
                    cmd, opts = req.split(None, 1)
                except ValueError:
                    # No options provided
                    pass
                resp = self.exec_command(cmd, opts)
                if resp:
                    if not isinstance(resp, bytes):
                        resp = resp.encode()
                    if not resp.endswith(b"\n"):
                        resp += b"\n"
                    writer.write(resp)
            except OSError:
                writer.close()
                return
            await asyncio.sleep(0.1)

    def exec_command(self, cmd, opts):
        if DEBUG:
            log(f"Shell command: {repr(cmd)} {opts}")
        if cmd in self.callbacks:
            return self.callbacks[cmd](opts)
        else:
            return("Invalid command.")


    async def write(self):
        pass

    async def read(self):
        pass

    async def run(self):
        log(f"[{self.name}] Listening on {self.bind_address}:{self.bind_port}")
        server = await asyncio.start_server(self.handle_connection, self.bind_address, self.bind_port)

        # Wait for shutdown signal
        await self.shutdown_event.wait()
        # shutdown server
        server.close()
        await server.wait_closed()


    async def shutdown(self):
        """Cleanup background tasks."""
        # Clean up all background tasks
        self.shutdown_event.set()
        for task in self.tasks:
            try:
                task.cancel()
            except:
                pass
        await asyncio.gather(*self.tasks, return_exceptions=True)
