import bluetooth
import errno
import time
from micropython import const

# Set constants
IRQ_CENTRAL_CONNECT = const(1)
IRQ_CENTRAL_DISCONNECT = const(2)
IRQ_GATTS_WRITE = const(3)

FLAG_READ = const(0x0002)
FLAG_WRITE_NO_RESPONSE = const(0x0004)
FLAG_WRITE = const(0x0008)
FLAG_NOTIFY = const(0x0010)

# Nordic UART Service (NUS)
UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
UART_TX = (
    bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"),
    FLAG_READ | FLAG_NOTIFY,
)
UART_RX = (
    bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"),
    FLAG_WRITE | FLAG_WRITE_NO_RESPONSE,
)
UART_SERVICE = (
    UART_UUID,
    (UART_TX, UART_RX),
)

class Blue():

    def __init__(self, name="ESP32_GPS"):
        self.name = name
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self.irq)
        ((self.handle_tx, self.handle_rx),) = self.ble.gatts_register_services((UART_SERVICE,))
        self.ble.gatts_set_buffer(self.handle_tx, 1024, True)
        self.connections = set()
        self.write_callback = None
        self.advertise()

    def advertise(self):
        interval_us = 500000
        payload = b'\x02\x01\x06' + bytes([len(self.name) + 1, 0x09]) + self.name
        self.ble.gap_advertise(interval_us, adv_data=payload)

    def irq(self, event, data):
        # Track connections so we can send notifications.
        if event == IRQ_CENTRAL_CONNECT:
            conn, _, _ = data
            self.connections.add(conn)
        elif event == IRQ_CENTRAL_DISCONNECT:
            conn, _, _ = data
            self.connections.remove(conn)
            self.advertise()
        elif event == IRQ_GATTS_WRITE:
            _, value_handle = data
            value = self.ble.gatts_read(value_handle)
            if value_handle == self.handle_rx and self.write_callback:
                self.write_callback(value)

    def is_connected(self):
        return len(self.connections) > 0

    def send(self, data):
        self.ble.gatts_write(self.handle_tx, data)
        for conn in self.connections:
            while True:
                try:
                    self.ble.gatts_notify(conn, self.handle_tx)
                    self.buf_len = 0
                    break
                except OSError as e:
                    if e.errno == errno.ENOMEM:
                        # Retry notify once stack has drained
                        time.sleep_ms(5)
                    else:
                        raise
