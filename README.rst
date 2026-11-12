============
bluetti_mqtt
============

This tool provides an MQTT interface to Bluetti power stations. State will be
published to the ``bluetti/state/[DEVICE NAME]/[PROPERTY]`` topic, and commands
can be sent to the ``bluetti/command/[DEVICE NAME]/[PROPERTY]`` topic.



Supported Devices
-----------------
- AC60
- AC70
- AC180
- AC200L
- AC200M
- AC300
- AC500
- EB3A
- EP500
- EP500P
- EP600


Installation
------------

.. code-block:: bash

    $ pip install .

Home Assistant app
~~~~~~~~~~~~~~~~~~

Add ``https://github.com/dbustosrc/bluetti_mqtt`` to the Home Assistant app
store and install **Bluetti to MQTT**. The app supports the models listed under
`Supported Devices`_, with expanded telemetry and control support for the
AC60. The app builds the Python package on AMD64 and ARM64. Python
dependencies have minimum versions and resolve for the app's runtime.

The app starts manually by default. Set ``bt_mac`` to the station address, or
enable ``scan`` for a one-time search. Clear ``scan`` to start MQTT polling.
Leave ``mqtt_host`` empty to use the Supervisor MQTT service. An explicit
broker uses the credentials supplied in the app settings.

Stop the existing Bluetooth bridge before starting this app with the same
station. Existing MQTT discovery topics and unique IDs let Home Assistant
reuse the registered entities.

Usage
-----

.. code-block:: bash

    $ bluetti-mqtt --scan
    Found AC3001234567890123: address 00:11:22:33:44:55
    $ bluetti-mqtt --broker [MQTT_BROKER_HOST] 00:11:22:33:44:55

If your MQTT broker has a username and password, you can pass those in.

.. code-block:: bash

    $ bluetti-mqtt --broker [MQTT_BROKER_HOST] --username username --password pass 00:11:22:33:44:55

By default the device is polled as quickly as possible, but if you'd like to
collect less data, the polling interval can be adjusted.

.. code-block:: bash

    # Poll every 60s
    $ bluetti-mqtt --broker [MQTT_BROKER_HOST] --interval 60 00:11:22:33:44:55

If you have multiple devices within bluetooth range, you can monitor all of
them with just a single command. We can only talk to one device at a time, so
you may notice some irregularity in the collected data, especially if you have
not set an interval.

.. code-block:: bash

    $ bluetti-mqtt --broker [MQTT_BROKER_HOST] 00:11:22:33:44:55 00:11:22:33:44:66

Background Service
------------------

If you are running on a platform with systemd, you can use the following as a
template. It should be placed in ``/etc/systemd/system/bluetti-mqtt.service``.
Once you've written the file, you'll need to run
``sudo systemctl start bluetti-mqtt``. If you want it to run automatically after
rebooting, you'll also need to run ``sudo systemctl enable bluetti-mqtt``.

.. code-block:: bash

    [Unit]
    Description=Bluetti MQTT
    After=network.target
    StartLimitIntervalSec=0

    [Service]
    Type=simple
    Restart=always
    RestartSec=30
    TimeoutStopSec=15
    User=your_username_here
    ExecStart=/home/your_username_here/.local/bin/bluetti-mqtt --broker [MQTT_BROKER_HOST] 00:11:22:33:44:55

    [Install]
    WantedBy=multi-user.target



Home Assistant Integration
--------------------------

If you have configured Home Assistant to use the same MQTT broker, then by
default most data and switches will be automatically configured there. This is
possible thanks to Home Assistant's support for automatic MQTT discovery, which
is enabled by default with the discovery prefix of ``homeassistant``.

This can be controlled with the ``--ha-config`` flag, which defaults to
configuring most fields ("normal"). Home Assistant MQTT discovery can also be
disabled, or additional internal device fields can be configured with the
"advanced" option.

AC60 improvements
~~~~~~~~~~~~~~~~~

The default discovery mode exposes the DC input total, three DC channels,
AC input and output measurements, ECO thresholds and timeouts, and battery
telemetry. Channel 1 is the station input. Channels 2 and 3 are expansion
inputs in device register order. The original DC total and channel 1 MQTT
topics and discovery IDs are preserved.

The optional `solar channels package <examples/home_assistant/ac60_solar_channels.yaml>`_
defines three Home Assistant Integral helpers in kWh. Include it with your
Home Assistant packages after all three DC input power sensors appear. Match
the package's source IDs to your registry if you renamed any of those sensors.
Use either the station total or the three channel counters in the Energy
dashboard to keep each watt-hour counted once. The existing total remains
available for aggregate history.

The station reports total battery state of charge, voltage, and current.
The Home Assistant Energy dashboard requires separate energy readings for
charging and discharging.

The battery pack sensors read one pack at register 6100. The station reports
the number of connected packs separately. ECO thresholds and timeouts are
read-only.

AC60 controls are confirmed by a register read after writing. MQTT sensors
expire after three polling intervals, with a minimum of 30 seconds.

Run the offline regression tests with ``python -m unittest discover -s tests``.

Reverse Engineering
-------------------

For research purposes you can also use the ``bluetti-logger`` command to poll
the device and log in a standardised format.

.. code-block:: bash

    $ bluetti-logger --log the-log-file.log 00:11:22:33:44:55

While the logger is running, change settings on the device and take note of the
time when you made the change, waiting ~ 1 minute between changes. Note that
not every setting that can be changed on the device can be changed over
bluetooth.

If you're looking to add support to control something that the app can change
but cannot be changed directly from the device screen, both iOS and Android
support collecting bluetooth logs from running apps. Additionally, with the
correct hardware Wireshark can be used to collect logs. With these logs and a
report of what commands were sent at what times, this data can be used to
reverse engineer support.

For supporting new devices, the ``bluetti-discovery`` command is provided. It
will scan from 0 to 12500 assuming MODBUS-over-Bluetooth. This will take a
while and requires that the scanned device be in close Bluetooth range for
optimal performance.

.. code-block:: bash

    $ bluetti-discovery --scan
    Found AC3001234567890123: address 00:11:22:33:44:55
    $ bluetti-discovery --log the-log-file.log 00:11:22:33:44:55

Credits
-------

- `warhammerkid/bluetti_mqtt <https://github.com/warhammerkid/bluetti_mqtt>`_
  for the original BLE-to-MQTT bridge.
- `ftrueck/bluetti_mqtt <https://github.com/ftrueck/bluetti_mqtt>`_ and
  `bxm6306's AC60 contribution <https://github.com/warhammerkid/bluetti_mqtt/pull/79>`_
  for the AC60 register map and the MQTT fields inherited by this fork.
- `adamjacobmuller/bluetti_mqtt <https://github.com/adamjacobmuller/bluetti_mqtt>`_
  for the fork base and its bridge and per-device MQTT availability.
- `Joihnny579/bluettiB <https://github.com/Joihnny579/bluettiB>`_ for the
  Grid Enhancement register and the control readback pattern.
- `Patrick762/bluetti-bt-lib <https://github.com/Patrick762/bluetti-bt-lib>`_,
  `bluetti-community/bluetti-registers <https://github.com/bluetti-community/bluetti-registers>`_,
  and `thatguy-za/esp32-nut-bluetti <https://github.com/thatguy-za/esp32-nut-bluetti>`_
  for corroborating the AC60 power registers and AC input voltage scale.
- `j4m3z0r/bluetti-monitor <https://github.com/j4m3z0r/bluetti-monitor>`_ for
  the signed battery-current format and the write-echo verification pattern.
- `ftrueck/bluetti2mqtt <https://github.com/ftrueck/bluetti2mqtt>`_,
  `semitop7/bluetti2mqtt <https://github.com/semitop7/bluetti2mqtt>`_, and
  `DuBistMutig/bluetti2mqtt <https://github.com/DuBistMutig/bluetti2mqtt>`_
  for Home Assistant add-on packaging and compatibility references.
- The Home Assistant app icon comes from ftrueck/bluetti2mqtt and is licensed
  under Apache-2.0. See `LICENSE-icon <LICENSE-icon>`_.
- `Ellmondo/bluetti-bt-connect-lib <https://github.com/Ellmondo/bluetti-bt-connect-lib>`_
  for documenting an expansion-pack current register on the EP2000.
