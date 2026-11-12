# Bluetti to MQTT

## Setup

1. Set up the [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) in Home Assistant with the broker the app will use.
2. Enter your Bluetti Bluetooth MAC address under **Address(es)**. If you need to find it, enable **Scan**, start the app, and copy the address from the **Log** tab. Then turn off **Scan** and save.
3. Stop any other Bluetooth bridge connected to the same station. Start **Bluetti to MQTT** and check the **Log** tab for Bluetooth and MQTT connections.

## Configuration

| Field | Setting | Description |
| --- | --- | --- |
| MQTT username | `mqtt_username` | Username for a broker you configure manually. |
| MQTT password | `mqtt_password` | Password for a broker you configure manually. |
| MQTT host | `mqtt_host` | Broker hostname or IP address. Leave blank to use the MQTT service provided by Supervisor, such as the Mosquitto app. |
| MQTT port | `mqtt_port` | Optional override for the broker port. A manually configured broker defaults to `1883`. |
| HA Config Level | `ha_config` | `normal` discovers the standard entities, `none` disables Home Assistant MQTT discovery, and `advanced` also discovers supported internal measurements. |
| Address(es) | `bt_mac` | Bluetooth MAC addresses of the stations. Separate multiple addresses with one space. |
| Poll Interval | `poll_sec` | Time between polling cycles in seconds. The default is `15`. |
| Scan | `scan` | Run a one-time Bluetooth scan and list devices in **Log**. Turn it off for regular polling. |
| Debug Mode | `debug` | Include detailed diagnostic messages in **Log**. |

## AC60 telemetry

The AC60 exposes three DC inputs, battery state of charge, AC measurements, and supported controls. Use either the station's total solar energy or the individual channel counters in the Energy dashboard to avoid counting the same production twice. For battery energy, Home Assistant requires separate energy measurements for charging and discharging.

The [project README](https://github.com/dbustosrc/bluetti_mqtt/blob/main/README.rst) covers the CLI tools, including `bluetti-discovery` and `bluetti-logger`, and links to the source and license.
