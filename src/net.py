import network
import time
import log

class Wifi():

    def __init__(self, ssid, key):
        # Maximise frequency range/power
        network.country("US")
        wlan = network.WLAN(network.WLAN.IF_STA)
        if not wlan.isconnected():
            # turn off an on to reset and hardware glitches
            time.sleep(0.5)
            wlan.active(False)
            time.sleep(0.5)
            wlan.active(True)
            time.sleep(0.5)
            wlan.disconnect()
            # Setting txpower fixes ESP32 c3 supermini connection issues
            wlan.config(txpower=5)
            time.sleep(0.5)
            wlan.connect(ssid, key)
            for i in range(120):
                if wlan.isconnected():
                    log(f"WLAN connected, IP: {wlan.ifconfig()[0]}")
                    break
                time.sleep(1)
            if not wlan.isconnected():
                log("WLAN Connection failed.")
        else:
            log(f"WLAN connected, IP: {wlan.ifconfig()[0]}")
