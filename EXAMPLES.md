# Example Uses

This is a work in progress...

## Serial GPS with message filtering/rewriting


## Bluetooth GPS


## NTRIP

#### Server: Sending Corrections to a Caster

This is the most common reason for running a NTRIP server.

Corrections are read from the Base Station GPS device, and sent to a Caster (local or remote). These can then be fetched by the Rover running an NTRIP client.

#### Server: Sending 'Survey-in' data to a Caster for later PPP/PPK

If your GPS device can send raw RTCM data, you can send this to the Caster instead of just corrections. You can then log this data and use it for PPP or PPK analysis, either via the NRCAN service, or using RTKPost.

Once a fix has been obtained, you can switch your GPS to sending corrections.

**NOTE:** While the esp32-gps` Caster will accept raw RTCM data to forward on, some Caster services may only accept correction data. Check with your provider before use.


#### Client

The NTRIP client will connect to a Caster, read correction data, and then write this to the GPS serial device. The Caster can optionally be running locally or remotely.

#### Caster

The commonest option is to run the Caster and Server on the same Base Station device, using a wifi connection for the Client to connect remotely. 

However the Caster can also run independently, receiving data from one or more Servers on other devices.

#### ESPNow

If wifi isn't available, ESPNow can be used instead for transferring data.

The Base Station device is set up with GPS, ESPNow Sender and NTRIP Server.

A receiver then runs ESPNow Receiver and NTRIP Caster (this device can also run NTRIP Client to read from the local Caster and write to the Rover device).

