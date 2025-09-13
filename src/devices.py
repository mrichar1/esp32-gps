"""Handle GPS & Serial devices via UART, and provide helper functions."""
import sys
try:
    from machine import UART
except ImportError:
    pass
try:
    from debug import DEBUG
except ImportError:
    DEBUG=False

# Maximum length of an NMEA sentence is 82, minus 10 for $PLOG,<payload>*XX\r\n
NMEA_LEN = 72

def nmea_checksum(sentence):
    """Calculate NMEA 0183 checksum for a sentence."""
    sentence = sentence.lstrip("$")
    cksum = 0
    for c in sentence:
        cksum ^= ord(c)
    return f"{cksum:02X}"


class GPS():

    def __init__(self, uart=1, baudrate=115200, tx=0, rx=1):
        self.utc_time = "00:00:00"
        try:
            self.uart = UART(uart,baudrate=baudrate, tx=tx, rx=rx)
        except Exception as e:
            sys.print_exception(e)
        logging = Logger.getLogger()
        self.log = logging.log


    def write_nmea(self, msg):
        """Write NMEA sentence to the GPS (adding $ and checksum)."""
        msg =msg.lstrip("$")
        if not "*" in msg:
            chksum = nmea_checksum(msg)
            msg = f"{msg}*{chksum}"
        self.log(f"Sent GPS Cmd: {msg}")
        self.uart.write(f"${msg}\r\n")

    def pqtmepe_to_gst(self, pqtmepe):
        """
        Convert a $PQTMEPE sentence to a $GPGST sentence.

        PQTMEPE format:
        $PQTMEPE,<ver>,<epe_north>,<epe_east>,<epe_down>,<epe_2d>,<epe_3d>*CS

        GST format:
        $GPGST,hhmmss.sss,rms,maj,smin,ori,lat_err,lon_err,alt_err*CS
        """

        try:
            # Strip leading $, trailing checksum
            body = pqtmepe.strip()[1:]
            fields, _ = body.split(b"*")
            parts = fields.split(b",")

            if parts[0] != b"PQTMEPE":
                # Return a 'null' sentence
                return b"\r\n"

            # Extract values
            epe_north = float(parts[2])
            epe_east  = float(parts[3])
            epe_down  = float(parts[4])
            epe_2d    = float(parts[5])
        except (IndexError, ValueError):
            return b"\r\n"

        # Approximate mapping
        rms     = epe_2d
        maj     = epe_2d
        smin    = min(epe_north, epe_east)
        ori     = 0.0
        lat_err = epe_north
        lon_err = epe_east
        alt_err = epe_down

        gst_body = f"GPGST,{self.utc_time},{rms:.4f},{maj:.4f},{smin:.4f},{ori:.1f},{lat_err:.4f},{lon_err:.4f},{alt_err:.4f}"
        cs = nmea_checksum(gst_body)
        return f"${gst_body}*{cs}".encode()

class Logger:
    """Log to stdout, or via a handler."""
    _handler = sys.stdout

    def getLogger():
        return Logger()

    @classmethod
    def setHandler(cls, handler):
        """Set handler (must have .write(str) method)."""
        cls._handler = handler

    def log(self, msg):
        if not msg.endswith("\n"):
            msg = msg + "\n"
        Logger._handler.write(str(msg))


class Serial():

    def __init__(self, uart, baudrate=115200, tx=3, rx=4, log_serial=True):
        """Try to set up serial for GPS messages (and optionally logging)."""
        logging = Logger()
        log = Logger.getLogger().log
        # Store the UART id as not queryable from the UART instance
        self.id = uart
        if uart:
            try:
                self.uart = UART(uart,baudrate=baudrate, tx=tx, rx=rx)
                if log_serial:
                    log("Redirecting logging to serial device.")
                    # Send log messages to serial output
                    logging.setHandler(self.SerialHandler(self.uart))
            except Exception as e:
                log(f"ERROR: Unable to open UART ({uart}) device.. Serial output disabled.")


    class SerialHandler():
        """A handler for logging which logs proprietary NMEA sentences to uart or stdout.

        This allows log messages to be intermixed with GPS data if using USB serial output.
        """
        def __init__(self, uart):
            self.uart = uart

        def write(self, msg):
            msg = str(msg)
            try:
                # Split messages on newline (for long debug tracebacks)
                for line in msg.split("\n"):
                    # Chunk messages to stay under NMEA sentence length limit
                    for i in range(0, len(line), NMEA_LEN):
                        # Escape any literal newlines/special chars in the message
                        msg_str = line[i:i+NMEA_LEN].encode('unicode_escape').decode()
                        chksum = nmea_checksum(msg_str)
                        self.uart.write(f"$PLOG,{msg_str}*{chksum}\r\n")
            except Exception as e:
                sys.print_exception(e)
