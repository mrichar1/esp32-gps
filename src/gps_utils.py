"""Handle GPS serial access via UART, and provide helper functions."""
import sys

def nmea_checksum(sentence):
    """Calculate NMEA 0183 checksum for a sentence."""
    cksum = 0
    for c in sentence:
        cksum ^= ord(c)
    return f"{cksum:02X}"

def log(msg=""):
    """Write log messages as proprietary NMEA sentences.

    This allows log messages to be intermised with GPS data if using USB serial output.
    """
    chksum = nmea_checksum(msg)
    # Escape any literal newlines/special chars in the message
    msg_str = msg.encode('unicode_escape').decode()
    # sys.stdout is USB serial on ESP32 devices
    sys.stdout.write(f"$PLOG,{msg_str}*{chksum}\r\n")
    sys.stdout.flush()


class GPS():

    def pqtmepe_to_gst(self, pqtmepe):
        """
        Convert a $PQTMEPE sentence to a $GPGST sentence.

        PQTMEPE format:
        $PQTMEPE,<ver>,<epe_north>,<epe_east>,<epe_down>,<epe_2d>,<epe_3d>*CS

        GST format:
        $GPGST,hhmmss.sss,rms,maj,smin,ori,lat_err,lon_err,alt_err*CS
        """

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

    def __init__(self, baudrate=115200, tx=0, rx=1):
         # Lazy-import to allow non-class functions to be used without needing UART support
         from machine import UART
         self.utc_time = "00:00:00"
         self.uart = UART(1,baudrate=baudrate, tx=tx, rx=rx)
