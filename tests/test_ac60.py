import asyncio
from decimal import Decimal
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from paho.mqtt.client import MQTTMessage

from bluetti_mqtt.bus import AvailabilityMessage, CommandMessage, EventBus, ParserMessage
from bluetti_mqtt.core import AC60, AC70, ReadHoldingRegisters, WriteSingleRegister
from bluetti_mqtt.core.utils import modbus_crc
from bluetti_mqtt.device_handler import DeviceHandler
from bluetti_mqtt.mqtt_client import MQTTClient, MqttError
from bluetti_mqtt.server_cli import CommandLineHandler


def registers(start, count, values):
    block = bytearray(2 * count)
    for address, value in values.items():
        offset = 2 * (address - start)
        block[offset:offset + 2] = (value & 0xFFFF).to_bytes(2, 'big')
    return bytes(block)


def read_reply(data):
    body = bytes((1, 3, len(data))) + data
    return body + modbus_crc(body).to_bytes(2, 'little')


class AppPasswordTests(unittest.TestCase):
    def test_app_password_defaults_to_environment_and_cli_can_override_it(self):
        args = ['bluetti-mqtt', '--broker', 'broker', '00:11:22:33:44:55']
        with patch.dict(os.environ, {'BLUETTI_MQTT_PASSWORD': 'test pass'}), \
                patch('bluetti_mqtt.server_cli.sys', SimpleNamespace(platform='linux')), \
                patch.object(CommandLineHandler, 'start') as start:
            CommandLineHandler(args).execute()
            self.assertEqual(start.call_args.args[0].password, 'test pass')
            CommandLineHandler([*args, '--password', 'manual']).execute()
            self.assertEqual(start.call_args.args[0].password, 'manual')


class AC60Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device = AC60('test', '123')
        self.bus = EventBus()
        self.mqtt = MQTTClient(self.bus, 'test', 'normal', poll_interval=15)
        self.broker = AsyncMock()

    def messages(self):
        return {args[0]: args[1] if len(args) > 1 else kwargs['payload']
                for args, kwargs in self.broker.publish.await_args_list}

    async def test_dc_channels_keep_original_topics_and_discovery_ids(self):
        await self.mqtt._init_device(self.device, self.broker)
        messages = self.messages()
        for channel in range(1, 4):
            for metric in ('power', 'voltage', 'current'):
                name = f'dc_input_{metric}{channel}'
                config = json.loads(messages[f'homeassistant/sensor/123_{name}/config'])
                self.assertEqual(config['unique_id'], f'123_{name}')
                self.assertEqual(config['state_topic'], f'bluetti/state/AC60-123/{name}')
                self.assertEqual(config['default_entity_id'], f'sensor.ac60_{name}')
                self.assertEqual(config['state_class'], 'measurement')
        for name in ('total_battery_percent', 'ac_input_voltage', 'ac_input_frequency',
                     'total_battery_voltage', 'battery_current', 'ac_output_frequency',
                     'ac_output_uptime_minutes', 'dc_eco_hours', 'num_packs_connected'):
            config = json.loads(messages[f'homeassistant/sensor/123_{name}/config'])
            self.assertEqual(config['expire_after'], 45)
            self.assertEqual(config['availability_mode'], 'all')
        config = json.loads(messages['homeassistant/switch/123_ac_output_on/config'])
        self.assertEqual(config['command_topic'], 'bluetti/command/AC60-123/ac_output_on')
        self.assertNotIn('expire_after', config)
        self.assertNotIn('homeassistant/sensor/123_pack_percent2/config', messages)

        self.broker.reset_mock()
        sample = registers(1200, 90, {
            1209: 3, 1210: 1, 1212: 10, 1213: 125, 1214: 8,
            1218: 0, 1220: 0, 1221: 0, 1222: 0,
            1226: 1, 1228: 30, 1229: 200, 1230: 15,
        })
        await self.mqtt._handle_message(self.broker, ParserMessage(self.device, self.device.parse(1200, sample)))
        expected = {
            'dc_input_power1': b'10', 'dc_input_voltage1': b'12.5', 'dc_input_current1': b'0.8',
            'dc_input_power2': b'0', 'dc_input_voltage2': b'0', 'dc_input_current2': b'0',
            'dc_input_power3': b'30', 'dc_input_voltage3': b'20', 'dc_input_current3': b'1.5',
            'charging_from_internal_dc': b'ON', 'charging_from_pack_dc': b'OFF',
            'charging_from_pack2_dc': b'ON', 'num_packs_connected': b'3',
        }
        self.assertEqual(self.messages(), {f'bluetti/state/AC60-123/{key}': val for key, val in expected.items()})

    async def test_ac70_keeps_legacy_discovery(self):
        await self.mqtt._init_device(AC70('test', '456'), self.broker)
        messages = self.messages()
        self.assertIn('homeassistant/sensor/456_dc_input_power1/config', messages)
        self.assertNotIn('homeassistant/sensor/456_dc_input_power2/config', messages)
        self.assertNotIn('homeassistant/sensor/456_ac_input_voltage/config', messages)

    async def test_battery_power_uses_same_sample_voltage_and_status(self):
        await self.mqtt._init_device(self.device, self.broker)
        messages = self.messages()
        status_config = json.loads(messages['homeassistant/sensor/123_battery_status/config'])
        self.assertEqual(status_config['options'], ['idle', 'charging', 'discharging'])
        for name in ('battery_charging_power', 'battery_discharging_power'):
            config = json.loads(messages[f'homeassistant/sensor/123_{name}/config'])
            self.assertEqual(config['unit_of_measurement'], 'W')
            self.assertEqual(config['device_class'], 'power')
            self.assertEqual(config['state_class'], 'measurement')
            self.assertTrue(config['force_update'])
            self.assertEqual(config['expire_after'], 45)
            self.assertFalse(self.device.has_field_setter(name))

        # Samples cover solar surplus, night discharge, idle and signed current.
        for voltage, current, status, charging, discharging in (
            (2331, 62, 1, Decimal('144.522'), Decimal(0)),
            (2282, 42, 2, Decimal(0), Decimal('95.844')),
            (2318, 4, 0, Decimal(0), Decimal(0)),
            (2282, -12, 2, Decimal(0), Decimal('27.384')),
        ):
            with self.subTest(status=status, current=current):
                self.broker.reset_mock()
                parsed = self.device.parse(100, registers(100, 50, {
                    100: voltage, 101: current, 102: 32, 103: status,
                }))
                self.assertEqual(parsed['battery_charging_power'], charging)
                self.assertEqual(parsed['battery_discharging_power'], discharging)
                await self.mqtt._handle_message(self.broker, ParserMessage(self.device, parsed))
                published = self.messages()
                prefix = 'bluetti/state/AC60-123/'
                self.assertEqual(published[prefix + 'battery_status'], str(status).encode())
                self.assertEqual(Decimal(published[prefix + 'battery_charging_power'].decode()), charging)
                self.assertEqual(Decimal(published[prefix + 'battery_discharging_power'].decode()), discharging)

    def test_invalid_or_partial_battery_sample_keeps_other_telemetry(self):
        for voltage, status in ((0, 1), (65535, 2), (2331, 65535)):
            with self.subTest(voltage=voltage, status=status):
                parsed = self.device.parse(100, registers(100, 50, {
                    100: voltage, 101: 62, 102: 32, 103: status,
                }))
                self.assertEqual(parsed['total_battery_percent'], 32)
                self.assertNotIn('battery_charging_power', parsed)
                self.assertNotIn('battery_discharging_power', parsed)
        self.assertNotIn('battery_charging_power', self.device.parse(
            101, registers(101, 3, {101: 62, 102: 32, 103: 1})
        ))
        self.assertNotIn('battery_status', self.device.parse(100, bytes(6)))

    async def test_known_pack_reports_on_existing_topic(self):
        sample = registers(6100, 100, {6111: 2365, 6113: 74})
        parsed = self.device.parse(6100, sample)
        await self.mqtt._handle_message(self.broker, ParserMessage(self.device, parsed))
        self.assertEqual(json.loads(self.messages()['bluetti/state/AC60-123/pack_details1']),
                         {'voltage': 23.65, 'percent': 74})
        self.assertNotIn('pack_num', self.device.parse(6100, bytes(200)))
        invalid = registers(6100, 100, {6111: 2365, 6113: 65535})
        self.assertNotIn('pack_num', self.device.parse(6100, invalid))

    def test_ac_output_uses_one_register_and_input_voltage_is_unscaled(self):
        blocks = {
            100: {101: -12, 102: 55, 142: 100},
            1300: {1300: 600, 1314: 121},
            1400: {1420: 101, 1430: 101, 1424: 42},
            1500: {1500: 600, 1509: 0, 1511: 1209, 1512: 10},
            2000: {2011: 1, 2015: 4, 2016: 5},
        }
        decoded = [self.device.parse(cmd.starting_address, registers(
            cmd.starting_address, cmd.quantity, blocks[cmd.starting_address]
        )) for cmd in self.device.polling_commands if cmd.starting_address in blocks]
        self.assertEqual([data['ac_output_power'] for data in decoded if 'ac_output_power' in data], [100])
        self.assertEqual([data['ac_output_on'] for data in decoded if 'ac_output_on' in data], [True])
        self.assertEqual(decoded[0]['battery_current'], Decimal('-1.2'))
        self.assertEqual(decoded[1]['ac_input_voltage'], 121)
        self.assertEqual(decoded[3]['ac_output_voltage'], Decimal('120.9'))

    async def test_grid_enhancement_write_checks_echo_and_publishes_readback(self):
        handler = DeviceHandler(['test'], 15, self.bus)
        handler.manager.is_ready = lambda _: True
        command = self.device.build_setter_command('grid_enhancement_mode_on', True)
        self.assertEqual(command.address, 2225)
        self.assertFalse(self.device.has_field_setter('ac_eco_hours'))
        reply = read_reply(b'\x00\x00')

        async def exchange(address, request):
            future = asyncio.get_running_loop().create_future()
            future.set_result(bytes(request) if isinstance(request, WriteSingleRegister) else reply)
            return future

        handler.manager.perform = AsyncMock(side_effect=exchange)
        with self.assertLogs(level='WARNING'):
            await handler.handle_command(CommandMessage(self.device, command))
        write, read = (call.args[1] for call in handler.manager.perform.await_args_list)
        self.assertIsInstance(read, ReadHoldingRegisters)
        self.assertEqual(write.address, read.starting_address)
        self.assertEqual((await self.bus.queue.get()).parsed, {'grid_enhancement_mode_on': False})

        future = asyncio.get_running_loop().create_future()
        future.set_result(bytes(WriteSingleRegister(2225, 0)))
        handler.manager.perform = AsyncMock(return_value=future)
        with self.assertLogs(level='WARNING'):
            await handler.handle_command(CommandMessage(self.device, command))
        handler.manager.perform.assert_awaited_once()
        self.assertTrue(self.bus.queue.empty())

    async def test_ac60_ignores_retained_and_invalid_switch_commands(self):
        self.mqtt.devices.append(self.device)
        msg = MQTTMessage(topic=b'bluetti/command/AC60-123/ac_output_on')
        for retain, payload in [(True, b'OFF'), (False, b'toggle')]:
            msg.retain, msg.payload = retain, payload
            with self.assertLogs(level='WARNING'):
                await self.mqtt._handle_command(msg)
        self.assertIsNone(self.bus.queue)
        msg.retain, msg.payload = False, b'ON'
        await self.mqtt._handle_command(msg)
        self.assertEqual((await self.bus.queue.get()).command.address, 2011)

    async def test_availability_tracks_valid_soc_and_connection(self):
        handler = DeviceHandler(['test'], 15, self.bus)
        handler.devices['test'] = self.device
        handler.manager.is_ready = lambda _: True
        handler.last_data_time['test'] = 100
        for now, available in [(120, True), (146, False)]:
            with patch('bluetti_mqtt.device_handler.time.monotonic', return_value=now):
                await handler._check_device_availability('test')
            self.assertEqual(await self.bus.queue.get(), AvailabilityMessage(self.device, available))
        handler.last_data_time['test'] = 150
        with patch('bluetti_mqtt.device_handler.time.monotonic', return_value=150):
            await handler._check_device_availability('test')
        self.assertTrue((await self.bus.queue.get()).available)
        handler.manager.is_ready = lambda _: False
        await handler._check_device_availability('test')
        self.assertFalse((await self.bus.queue.get()).available)

    async def test_mqtt_reconnect_cancels_session_tasks_and_reuses_listeners(self):
        reconnected = asyncio.Event()
        second = AsyncMock()
        first = AsyncMock()
        for broker in (first, second):
            broker.__aenter__.return_value = broker
        self.mqtt.devices.append(self.device)
        await self.mqtt.handle_availability(AvailabilityMessage(self.device, False))

        async def commands(client):
            if client is first:
                raise MqttError('test disconnect')
            reconnected.set()
            await asyncio.Future()

        async def refresh(_):
            await asyncio.Future()

        self.mqtt._handle_commands = commands
        self.mqtt._periodic_availability_refresh = refresh
        with patch('bluetti_mqtt.mqtt_client.Client', side_effect=[first, second]), \
                patch('bluetti_mqtt.mqtt_client.asyncio.sleep', new_callable=AsyncMock):
            task = asyncio.create_task(self.mqtt.run())
            try:
                with self.assertLogs(level='ERROR'):
                    await asyncio.wait_for(reconnected.wait(), timeout=2)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertEqual(len(self.bus.parser_listeners), 1)
        self.assertEqual(len(self.bus.availability_listeners), 1)
        second.publish.assert_any_await('bluetti/status/AC60-123/availability', b'offline', qos=1, retain=True)
        self.assertIsNone(self.mqtt.message_queue)
