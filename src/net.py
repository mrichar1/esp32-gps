import network
import time

class Wifi():

    def __init__(self, ssid, key):
        wlan = network.WLAN(network.WLAN.IF_STA)
        wlan.active(True)
        wlan.connect(ssid, key)
        for i in range(20):
            if wlan.isconnected():
                break
            time.sleep(1)
        if not wlan.isconnected():
            print("WLAN Connection failed.")
