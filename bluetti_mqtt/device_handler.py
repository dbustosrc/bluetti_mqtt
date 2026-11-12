import asyncio
from bleak import BleakError
import logging
import time
from typing import Dict, List, cast
from bluetti_mqtt.bluetooth import BadConnectionError, MultiDeviceManager, ModbusError, ParseError, build_device
from bluetti_mqtt.bus import AvailabilityMessage, CommandMessage, EventBus, ParserMessage
from bluetti_mqtt.core import AC60, BluettiDevice, ReadHoldingRegisters, WriteSingleRegister


class DeviceHandler:
    def __init__(self, addresses: List[str], interval: int, bus: EventBus):
        self.manager = MultiDeviceManager(addresses)
        self.devices: Dict[str, BluettiDevice] = {}
        self.interval = interval
        self.bus = bus
        self.device_availability: Dict[str, bool] = {}  # Track device connectivity
        self.last_data_time: Dict[str, float] = {}  # Track last successful data fetch
        self.data_timeout = 300  # 5 minutes timeout for marking device offline

    async def run(self):
        loop = asyncio.get_running_loop()

        # Start manager
        manager_task = loop.create_task(self.manager.run())

        # Connect to event bus
        self.bus.add_command_listener(self.handle_command)

        # Poll the clients
        logging.info('Starting to poll clients...')
        polling_tasks = [self._poll(a) for a in self.manager.addresses]
        pack_polling_tasks = [self._pack_poll(a) for a in self.manager.addresses]
        health_check_tasks = [self._connection_health_monitor(a) for a in self.manager.addresses]
        await asyncio.gather(*(polling_tasks + pack_polling_tasks + health_check_tasks + [manager_task]))

    async def handle_command(self, msg: CommandMessage):
        device, command = msg.device, msg.command
        if not self.manager.is_ready(device.address):
            return
        logging.debug('Performing command for %s: %s', device.type, command)
        if device.type != 'AC60' or not isinstance(command, WriteSingleRegister):
            await self.manager.perform_nowait(device.address, command)
            return
        try:
            response = await (await self.manager.perform(device.address, command))
            if response != bytes(command):
                logging.warning('AC60 register %d returned an unexpected write echo', command.address)
                return
            read = ReadHoldingRegisters(command.address, 1)
            response = await (await self.manager.perform(device.address, read))
            if len(response) != read.response_size() or response[:3] != b'\x01\x03\x02':
                logging.warning('AC60 register %d returned an invalid readback', command.address)
                return
            body = read.parse_response(response)
            if int.from_bytes(body, 'big') != command.value:
                logging.warning('AC60 register %d did not reach the requested value', command.address)
            await self.bus.put(ParserMessage(device, device.parse(command.address, body)))
        except (BadConnectionError, BleakError, ModbusError, ParseError):
            logging.warning('AC60 register %d could not be confirmed', command.address)

    async def _check_device_availability(self, address: str):
        """Check and update device availability status"""
        is_ready = self.manager.is_ready(address)

        last_data = self.last_data_time.get(address)
        device = self.devices.get(address)
        timeout = AC60.telemetry_timeout(self.interval) if isinstance(device, AC60) else self.data_timeout
        data_timed_out = last_data is None or time.monotonic() - last_data > timeout

        is_available = is_ready and not data_timed_out
        current_status = self.device_availability.get(address, None)

        if current_status != is_available:
            self.device_availability[address] = is_available
            # Only send availability message if we have a device object
            if device is not None:
                logging.info(
                    '%s is %s (BLE ready=%s, telemetry fresh=%s)',
                    device.type, 'online' if is_available else 'offline', is_ready, not data_timed_out,
                )
                await self.bus.put(AvailabilityMessage(device, is_available))

    async def _poll(self, address: str):
        while True:
            # Check and update device availability
            await self._check_device_availability(address)

            if not self.manager.is_ready(address):
                logging.debug(f'Waiting for connection to {address} to start polling...')
                await asyncio.sleep(1)
                continue

            device = self._get_device(address)

            # Send all polling commands
            start_time = time.monotonic()
            for command in device.polling_commands:
                await self._poll_with_command(device, command)
            elapsed = time.monotonic() - start_time

            # Limit polling rate if interval provided
            if self.interval > 0 and self.interval > elapsed:
                await asyncio.sleep(self.interval - elapsed)

    async def _pack_poll(self, address: str):
        while True:
            # Check and update device availability
            await self._check_device_availability(address)

            if not self.manager.is_ready(address):
                logging.debug(f'Waiting for connection to {address} to start pack polling...')
                await asyncio.sleep(1)
                continue

            # Break if there's nothing to poll
            device = self._get_device(address)
            if len(device.pack_logging_commands) == 0:
                break

            start_time = time.monotonic()
            for pack in range(1, device.pack_num_max + 1):
                # Send pack set command if the device supports more than 1 pack
                if device.pack_num_max > 1:
                    command = device.build_setter_command('pack_num', pack)
                    await self.manager.perform_nowait(address, command)
                    await asyncio.sleep(10)  # We need to wait after switching packs for the data to be available

                # Poll
                for command in device.pack_logging_commands:
                    await self._poll_with_command(device, command)
            elapsed = time.monotonic() - start_time

            # Limit polling rate if interval provided
            if self.interval > 0 and self.interval > elapsed:
                await asyncio.sleep(self.interval - elapsed)

    async def _poll_with_command(self, device: BluettiDevice, command: ReadHoldingRegisters):
        response_future = await self.manager.perform(device.address, command)
        try:
            response = cast(bytes, await response_future)
            body = command.parse_response(response)
            parsed = device.parse(command.starting_address, body)
            if parsed:
                await self.bus.put(ParserMessage(device, parsed))
                if device.type != 'AC60' or 'total_battery_percent' in parsed:
                    self.last_data_time[device.address] = time.monotonic()
                    await self._check_device_availability(device.address)
        except ParseError:
            logging.debug('Got a parse exception...')
        except ModbusError as err:
            logging.debug(f'Got an invalid request error for {command}: {err}')
        except (BadConnectionError, BleakError) as err:
            logging.debug(f'Needed to disconnect due to error: {err}')

    def _get_device(self, address: str):
        if address not in self.devices:
            name = self.manager.get_name(address)
            self.devices[address] = build_device(address, name)
        return self.devices[address]

    async def _connection_health_monitor(self, address: str):
        """Monitor connection health and disconnect stuck connections"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds

                # Check if we have a device
                if address not in self.devices:
                    continue

                # Check if connection is stuck (connected but no data for timeout period)
                is_ready = self.manager.is_ready(address)
                last_data = self.last_data_time.get(address, 0)
                time_since_data = time.monotonic() - last_data if last_data > 0 else 0

                if is_ready and last_data > 0 and time_since_data > self.data_timeout:
                    device = self.devices[address]
                    logging.warning(
                        f'Device {device.type}-{device.sn} connection appears stuck '
                        f'(no data for {time_since_data:.0f}s), forcing disconnect'
                    )

                    # Force disconnect the stuck connection
                    try:
                        client = self.manager.clients.get(address)
                        if client:
                            await client.client.disconnect()
                    except Exception as e:
                        logging.debug(f'Error disconnecting stuck client: {e}')

                    # The manager should automatically try to reconnect

            except Exception as e:
                logging.error(f'Error in connection health monitor for {address}: {e}')
                await asyncio.sleep(30)
