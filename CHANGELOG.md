# Change Log

## 0.16.6

* Include BlueZ tools and run the Home Assistant bridge as an S6 service.
* Reuse scanned Bluetooth devices when connecting to avoid redundant discovery.

## 0.16.5

* Add AC60 battery flow status and charging and discharging power calculated from battery voltage and current.
* Provide a Home Assistant package for separate battery energy totals in the Energy dashboard.

## 0.16.4

* Documentation update for Home Assistant, including the Info page, logo, and configuration help.

## 0.16.3

* Provide the Bluetti to MQTT app for Home Assistant on AMD64 and ARM64, with support for the models listed in the README.
* Publish individual AC60 DC inputs and the voltage and state of charge from the mapped battery pack.
* Expose AC60 battery current, AC measurements, output runtime, and ECO settings.
* Correct AC60 input voltage scaling and use one register each for AC output power and switch state.
* Enable AC60 Grid Enhancement control and verify AC60 control writes by reading back the register.
* Expire stale AC60 measurements and preserve MQTT discovery identities across upgrades.
* Resolve compatible dependency versions at install time and support CLI startup on Python 3.14.
* Provide an optional Home Assistant package for per-input AC60 solar energy.

## 0.15.0

* Add additional battery pack details for AC200M, AC300, EP500(P), and AC500
* Add initial logging support for AC60 (and very basic polling)

## 0.14.0

* BREAKING: The internal API has changed to better reflect standard MODBUS terminology
* Out-of-range internal_current_three values are no longer reported for AC300
* No longer checks if it can connect to all listed devices when logging

## 0.13.0

* Add initial logging support for EP600 (and very basic polling)

## 0.12.0

* Add a bluetti-discovery command that can collect information from unsupported Bluetti devices
* Out-of-range DC input current values are no longer reported

## 0.11.1

* Fix bug where attempting to set numeric fields would cause a crash

## 0.11.0

* Re-write MQTT client to make Home Assistant config easier, and add most fields to Home Assistant config
* Add new command line flag to control what fields get configured in Home Assistant
* Add power_off control to AC200M (@slash5k1)

## 0.10.0

* Update AC500 support
* Add split phase parsing support
* Remove unsupported power_generation field from EB3A
* Improved error reporting

## 0.9.2

* Update EB3A support

## 0.9.1

* Fix decimal conversion factors for DC inputs on the AC200Max

## 0.9.0

* Add LED status and setting to homeassistant for EB3A (@ray0711)
* Fix crash with failed bluetooth connection
* Add beta support for AC500

## 0.8.3

* Fix a bug with `dc_input_power` reporting

## 0.8.2

* More bug fixes...

## 0.8.1

* Fix build issue

## 0.8.0

* Add support for reporting details for multiple battery packs
* Re-architect internals for a better logical separation into layers (core, bluetooth, and the polling + MQTT app)

## 0.7.1

* Fix crash with EB3A logging (@jretz)

## 0.7.0

* Add support for Home Assistant discovery (@lbossle)
* Re-architect parsing to support device-specific customization
* Add beta support for EB3A
* Fix bug with automatic bluetooth reconnect

## 0.6.3

* Fix bug with scanning unnamed devices for WinRT bluetooth backend
* Fix bug with converting commands to bytes for WinRT & macOS blueooth backend
* Fix issue with using an unsupported event loop on Windows for asyncio-mqtt

## 0.6.2

* Fix bug in logging multiple batteries where the last slot was skipped.
* Automatically reconnect to broker if disconnected

## 0.6.1

* Added support for paging through batteries in the logger to collect more information about how things work.

## 0.6.0

* Added support for configuring username / password / port for MQTT broker
* Added proper signal handling. It now correctly shuts down when sent SIGTERM or SIGINT.

## 0.5.1

* Added a `DEBUG` environment variable that turns on more logging

## 0.5.0

* Started parsing out more fields from the device
* Added support for handling invalid request errors

## 0.4.0

* Added an `--interval` command line flag to change the polling rate

## 0.3.0

* Added support for sending commands to the device over MQTT
