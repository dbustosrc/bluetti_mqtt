import asyncio
from contextlib import suppress
from dataclasses import dataclass, replace
from enum import auto, Enum, unique
import json
import logging
import re
from typing import List, Optional
from aiomqtt import Client, MqttError, Will
from paho.mqtt.client import MQTTMessage
from bluetti_mqtt.bus import AvailabilityMessage, CommandMessage, EventBus, ParserMessage
from bluetti_mqtt.core import AC60, BluettiDevice


@unique
class MqttFieldType(Enum):
    NUMERIC = auto()
    BOOL = auto()
    ENUM = auto()
    BUTTON = auto()


@dataclass(frozen=True)
class MqttFieldConfig:
    type: MqttFieldType
    setter: bool
    advanced: bool  # Do not export by default to Home Assistant
    home_assistant_extra: dict
    id_override: Optional[str] = None  # Used to override Home Assistant field id


COMMAND_TOPIC_RE = re.compile(r'^bluetti/command/(\w+)-(\d+)/([a-z_]+)$')
NORMAL_DEVICE_FIELDS = {
    'dc_input_power': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'DC Input Power',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'ac_input_power': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'AC Input Power',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'ac_output_power': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'AC Output Power',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'dc_output_power': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'DC Output Power',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'dc_usb_output_power': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'DC USB Output Power',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'dc_12v_output_power': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'DC 12V Output Power',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'power_generation': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'Total Power Generation',
            'unit_of_measurement': 'kWh',
            'device_class': 'energy',
            'state_class': 'total_increasing',
        }
    ),
    'total_battery_percent': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'Total Battery Percent',
            'unit_of_measurement': '%',
            'device_class': 'battery',
            'state_class': 'measurement',
        }
    ),
    'ac_output_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'AC Output',
            'device_class': 'outlet',
        }
    ),
    'dc_output_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'DC Output',
            'device_class': 'outlet',
        }
    ),
    'ac_output_mode': MqttFieldConfig(
        type=MqttFieldType.ENUM,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'AC Output Mode',
        }
    ),
    'ac_input_current': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'AC Input Current',
            'unit_of_measurement': 'A',
            'device_class': 'current',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'internal_ac_voltage': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Internal AC Voltage',
            'unit_of_measurement': 'V',
            'device_class': 'voltage',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'internal_current_one': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Internal Current Sensor 1',
            'unit_of_measurement': 'A',
            'device_class': 'current',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'internal_power_one': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Internal Power Sensor 1',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'internal_ac_frequency': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Internal AC Frequency',
            'unit_of_measurement': 'Hz',
            'device_class': 'frequency',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'internal_current_two': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Internal Current Sensor 2',
            'unit_of_measurement': 'A',
            'device_class': 'current',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'internal_power_two': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Internal Power Sensor 2',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'ac_input_voltage': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'AC Input Voltage',
            'unit_of_measurement': 'V',
            'device_class': 'voltage',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'internal_current_three': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Internal Current Sensor 3',
            'unit_of_measurement': 'A',
            'device_class': 'current',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'internal_power_three': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Internal Power Sensor 3',
            'unit_of_measurement': 'W',
            'device_class': 'power',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'ac_input_frequency': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'AC Input Frequency',
            'unit_of_measurement': 'Hz',
            'device_class': 'frequency',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'total_battery_voltage': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Total Battery Voltage',
            'unit_of_measurement': 'V',
            'device_class': 'voltage',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'total_battery_current': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=True,
        home_assistant_extra={
            'name': 'Total Battery Current',
            'unit_of_measurement': 'A',
            'device_class': 'current',
            'state_class': 'measurement',
            'force_update': True,
        }
    ),
    'ups_mode': MqttFieldConfig(
        type=MqttFieldType.ENUM,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'UPS Working Mode',
            'options': ['CUSTOMIZED', 'PV_PRIORITY', 'STANDARD', 'TIME_CONTROL'],
        }
    ),
    'split_phase_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=False,  # For safety purposes, I'm not exposing this as a setter
        advanced=False,
        home_assistant_extra={
            'name': 'Split Phase',
        }
    ),
    'split_phase_machine_mode': MqttFieldConfig(
        type=MqttFieldType.ENUM,
        setter=False,  # For safety purposes, I'm not exposing this as a setter
        advanced=False,
        home_assistant_extra={
            'name': 'Split Phase Machine',
        }
    ),
    'grid_charge_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'Grid Charge',
        }
    ),
    'time_control_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'Time Control',
        }
    ),
    'battery_range_start': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'Battery Range Start',
            'step': 1,
            'min': 0,
            'max': 100,
            'unit_of_measurement': '%',
        }
    ),
    'battery_range_end': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'Battery Range End',
            'step': 1,
            'min': 0,
            'max': 100,
            'unit_of_measurement': '%',
        }
    ),
    'led_mode': MqttFieldConfig(
        type=MqttFieldType.ENUM,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'LED Mode',
            'icon': 'mdi:lightbulb',
            'options': ['LOW', 'HIGH', 'SOS', 'OFF'],
        }
    ),
    'power_off': MqttFieldConfig(
        type=MqttFieldType.BUTTON,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'Power Off',
            'payload_press': 'ON',
        }
    ),
    'auto_sleep_mode': MqttFieldConfig(
        type=MqttFieldType.ENUM,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'Screen Auto Sleep Mode',
            'icon': 'mdi:sleep',
            'options': ['THIRTY_SECONDS', 'ONE_MINUTE', 'FIVE_MINUTES', 'NEVER'],
        }
    ),
    'eco_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'ECO',
            'icon': 'mdi:sprout',
        }
    ),
    'dc_eco_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'DC ECO',
            'icon': 'mdi:sprout',
        }
    ),
    'ac_eco_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'AC ECO',
            'icon': 'mdi:sprout',
        }
    ),
    'eco_shutdown': MqttFieldConfig(
        type=MqttFieldType.ENUM,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'ECO Shutdown',
            'icon': 'mdi:sprout',
            'options': ['ONE_HOUR', 'TWO_HOURS', 'THREE_HOURS', 'FOUR_HOURS'],
        }
    ),
    'charging_mode': MqttFieldConfig(
        type=MqttFieldType.ENUM,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'Charging Mode',
            'icon': 'mdi:battery-charging',
            'options': ['STANDARD', 'SILENT', 'TURBO'],
        }
    ),
    'power_lifting_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'Power Lifting',
            'icon': 'mdi:arm-flex',
        }
    ),
    'grid_enhancement_mode_on': MqttFieldConfig(
        type=MqttFieldType.BOOL,
        setter=True,
        advanced=False,
        home_assistant_extra={
            'name': 'Grid Enhancement Mode',
            'icon': 'mdi:transmission-tower',
        }
    ),
    'estimated_time_min': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'Estimated Charge/Run Time',
            'unit_of_measurement': 'min',
            'icon': 'mdi:update',
        }
    ),
    'estimated_time_hr': MqttFieldConfig(
        type=MqttFieldType.NUMERIC,
        setter=False,
        advanced=False,
        home_assistant_extra={
            'name': 'Estimated Charge/Run Time',
            'unit_of_measurement': 'h',
            'icon': 'mdi:update',
        }
    ),
}


def measurement(name, unit=None, device_class=None, *, force_update=False):
    config = {'name': name, 'state_class': 'measurement'}
    if unit:
        config['unit_of_measurement'] = unit
    if device_class:
        config['device_class'] = device_class
    if force_update:
        config['force_update'] = True
    return MqttFieldConfig(MqttFieldType.NUMERIC, False, False, config)


DC_INPUT_FIELDS = {
    f'{source}_{metric}': replace(
        measurement(f'DC Input {metric.title()} {channel}', unit, metric, force_update=True),
        id_override=f'dc_input_{metric}{channel}',
    )
    for channel, source in enumerate(('internal_dc_input', 'pack_dc_input', 'pack2_dc_input'), 1)
    for metric, unit in (('voltage', 'V'), ('power', 'W'), ('current', 'A'))
}
LEGACY_DC_INPUT_FIELDS = {
    name: field for name, field in DC_INPUT_FIELDS.items() if name.startswith('internal_dc_input_')
}
AC60_FIELDS = {
    **NORMAL_DEVICE_FIELDS,
    **{
        name: replace(NORMAL_DEVICE_FIELDS[name], advanced=False)
        for name in ('ac_input_voltage', 'ac_input_frequency', 'total_battery_voltage')
    },
    'battery_current': measurement('Battery Current', 'A', 'current'),
    'battery_status': MqttFieldConfig(MqttFieldType.NUMERIC, False, False, {
        'name': 'Battery Status',
        'device_class': 'enum',
        'options': ['idle', 'charging', 'discharging'],
        'value_template': '{{ ["idle", "charging", "discharging"][value | int] }}',
    }),
    'battery_charging_power': measurement('Battery Charging Power', 'W', 'power', force_update=True),
    'battery_discharging_power': measurement('Battery Discharging Power', 'W', 'power', force_update=True),
    'num_packs_connected': measurement('Connected Battery Packs'),
    'ac_output_voltage': measurement('AC Output Voltage', 'V', 'voltage'),
    'ac_output_amps': measurement('AC Output Current', 'A', 'current'),
    'ac_output_frequency': measurement('AC Output Frequency', 'Hz', 'frequency'),
    'ac_output_uptime_minutes': measurement('AC Output Uptime', 'min', 'duration'),
    'dc_output_uptime_minutes': measurement('DC Output Uptime', 'min', 'duration'),
    'ac_eco_hours': measurement('AC ECO Timeout', 'h', 'duration'),
    'dc_eco_hours': measurement('DC ECO Timeout', 'h', 'duration'),
    'ac_eco_watts': measurement('AC ECO Threshold', 'W', 'power'),
    'dc_eco_watts': measurement('DC ECO Threshold', 'W', 'power'),
    **{
        field: MqttFieldConfig(MqttFieldType.BOOL, False, False, {'name': f'DC Input {channel} Active'})
        for channel, field in enumerate(
            ('charging_from_internal_dc', 'charging_from_pack_dc', 'charging_from_pack2_dc'), 1
        )
    },
}


def battery_pack_fields(pack: int):
    return {
        'pack_status': MqttFieldConfig(
            type=MqttFieldType.ENUM,
            setter=False,
            advanced=True,
            home_assistant_extra={
                'name': f'Battery Pack {pack} Status',
                'value_template': '{{ value_json.status }}'
            },
            id_override=f'pack_status{pack}'
        ),
        'pack_voltage': MqttFieldConfig(
            type=MqttFieldType.NUMERIC,
            setter=False,
            advanced=True,
            home_assistant_extra={
                'name': f'Battery Pack {pack} Voltage',
                'unit_of_measurement': 'V',
                'device_class': 'voltage',
                'state_class': 'measurement',
                'force_update': True,
                'value_template': '{{ value_json.voltage }}'
            },
            id_override=f'pack_voltage{pack}'
        ),
        'pack_battery_percent': MqttFieldConfig(
            type=MqttFieldType.NUMERIC,
            setter=False,
            advanced=False,
            home_assistant_extra={
                'name': f'Battery Pack {pack} Percent',
                'unit_of_measurement': '%',
                'device_class': 'battery',
                'state_class': 'measurement',
                'value_template': '{{ value_json.percent }}'
            },
            id_override=f'pack_percent{pack}'
        ),
    }


class MQTTClient:
    devices: List[BluettiDevice]
    message_queue: Optional[asyncio.Queue]

    def __init__(
        self,
        bus: EventBus,
        hostname: str,
        home_assistant_mode: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        poll_interval: int = 0,
    ):
        self.bus = bus
        self.hostname = hostname
        self.port = port
        self.username = username
        self.password = password
        self.home_assistant_mode = home_assistant_mode
        self.sensor_expiry = AC60.telemetry_timeout(poll_interval)
        self.devices = []
        self.message_queue = None
        self.device_availability = {}

    async def run(self):
        self.bus.add_parser_listener(self.handle_message)
        self.bus.add_availability_listener(self.handle_availability)
        while True:
            logging.info('Connecting to MQTT broker...')
            try:
                async with Client(
                    hostname=self.hostname,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    will=Will(
                        topic='bluetti/bridge/status',
                        payload='offline',
                        qos=1,
                        retain=True
                    )
                ) as client:
                    logging.info('Connected to MQTT broker')

                    await self._publish_availability(client, True)
                    await self._publish_known_availability(client)

                    self.message_queue = asyncio.Queue()
                    tasks = [
                        asyncio.create_task(self._handle_commands(client)),
                        asyncio.create_task(self._handle_messages(client)),
                        asyncio.create_task(self._periodic_availability_refresh(client)),
                    ]
                    try:
                        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    finally:
                        self.message_queue = None
                        for task in tasks:
                            task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                        with suppress(MqttError):
                            await self._publish_availability(client, False)
            except MqttError:
                logging.exception('MQTT error:')
                await asyncio.sleep(5)

    async def handle_message(self, msg: ParserMessage):
        if self.message_queue is not None:
            self.message_queue.put_nowait(msg)

    async def handle_availability(self, msg: AvailabilityMessage):
        self.device_availability[msg.device.sn] = msg.available
        if self.message_queue is not None:
            self.message_queue.put_nowait(msg)

    async def _publish_availability(self, client: Client, available: bool):
        payload = 'online' if available else 'offline'
        await client.publish('bluetti/bridge/status', payload.encode(), qos=1, retain=True)

    async def _publish_device_availability(self, client: Client, device: BluettiDevice, available: bool):
        topic = f'bluetti/status/{device.type}-{device.sn}/availability'
        payload = 'online' if available else 'offline'
        await client.publish(topic, payload.encode(), qos=1, retain=True)

    async def _publish_known_availability(self, client: Client):
        for device in self.devices:
            await self._publish_device_availability(
                client, device, self.device_availability.get(device.sn, False)
            )

    async def _periodic_availability_refresh(self, client: Client):
        while True:
            await asyncio.sleep(60)
            await self._publish_availability(client, True)
            await self._publish_known_availability(client)

    async def _handle_commands(self, client: Client):
        await client.subscribe('bluetti/command/#')
        async for mqtt_message in client.messages:
            await self._handle_command(mqtt_message)

    async def _handle_messages(self, client: Client):
        queue = self.message_queue
        while True:
            msg = await queue.get()
            if isinstance(msg, ParserMessage):
                if msg.device not in self.devices:
                    await self._init_device(msg.device, client)
                    self.devices.append(msg.device)
                    if msg.device.sn in self.device_availability:
                        await self._publish_device_availability(
                            client, msg.device, self.device_availability[msg.device.sn]
                        )
                await self._handle_message(client, msg)
            elif isinstance(msg, AvailabilityMessage):
                await self._publish_device_availability(client, msg.device, msg.available)
            queue.task_done()

    async def _init_device(self, device: BluettiDevice, client: Client):
        # Skip announcing device to Home Assistant if disabled
        if self.home_assistant_mode == 'none':
            return

        def payload(id: str, component: str, field: MqttFieldConfig) -> str:
            ha_id = id if not field.id_override else field.id_override
            payload_dict = {
                'state_topic': f'bluetti/state/{device.type}-{device.sn}/{id}',
                'device': {
                    'identifiers': [
                        f'{device.sn}'
                    ],
                    'manufacturer': 'Bluetti',
                    'name': f'{device.type} {device.sn}',
                    'model': device.type
                },
                'unique_id': f'{device.sn}_{ha_id}',
                'default_entity_id': f'{component}.{device.type.lower()}_{ha_id}',
            }
            if field.setter:
                payload_dict['command_topic'] = f'bluetti/command/{device.type}-{device.sn}/{id}'
            # Use both bridge and device availability topics
            payload_dict['availability'] = [
                {
                    'topic': 'bluetti/bridge/status',
                    'payload_available': 'online',
                    'payload_not_available': 'offline'
                },
                {
                    'topic': f'bluetti/status/{device.type}-{device.sn}/availability',
                    'payload_available': 'online',
                    'payload_not_available': 'offline'
                }
            ]
            payload_dict['availability_mode'] = 'all'
            payload_dict.update(field.home_assistant_extra)
            if device.type == 'AC60' and component == 'sensor':
                payload_dict['expire_after'] = self.sensor_expiry

            return json.dumps(payload_dict, separators=(',', ':'))

        # Publish normal fields
        fields = AC60_FIELDS if device.type == 'AC60' else NORMAL_DEVICE_FIELDS
        for name, field in fields.items():
            # Skip fields not supported by the device
            if not device.has_field(name):
                continue

            # Skip advanced fields if not enabled
            if field.advanced and self.home_assistant_mode != 'advanced':
                continue

            # Figure out Home Assistant type
            if field.type == MqttFieldType.NUMERIC:
                component = 'number' if field.setter else 'sensor'
            elif field.type == MqttFieldType.BOOL:
                component = 'switch' if field.setter else 'binary_sensor'
            elif field.type == MqttFieldType.ENUM:
                component = 'select' if field.setter else 'sensor'
            elif field.type == MqttFieldType.BUTTON:
                component = 'button'

            # Publish config
            await client.publish(
                f'homeassistant/{component}/{device.sn}_{name}/config',
                payload=payload(name, component, field).encode(),
                retain=True
            )

        # Publish battery pack configs
        for pack in range(1, device.pack_num_max + 1):
            fields = battery_pack_fields(pack)
            for name, field in fields.items():
                # Skip fields not supported by the device
                if not device.has_field(name):
                    continue

                # Publish config
                await client.publish(
                    f'homeassistant/sensor/{device.sn}_{field.id_override}/config',
                    payload=payload(f'pack_details{pack}', 'sensor', field).encode(),
                    retain=True
                )

        # Publish DC input config
        if device.has_field('internal_dc_input_voltage'):
            dc_fields = DC_INPUT_FIELDS if device.type == 'AC60' else LEGACY_DC_INPUT_FIELDS
            for field in dc_fields.values():
                name = field.id_override
                await client.publish(
                    f'homeassistant/sensor/{device.sn}_{name}/config',
                    payload=payload(name, 'sensor', field).encode(),
                    retain=True
                )

        logging.info(f'Sent discovery message of {device.type}-{device.sn} to Home Assistant')

    async def _handle_command(self, mqtt_message: MQTTMessage):
        # Parse the mqtt_message.topic
        m = COMMAND_TOPIC_RE.match(str(mqtt_message.topic))
        if not m:
            logging.warn(f'unknown command topic: {mqtt_message.topic}')
            return

        # Find the matching device for the command
        device = next((d for d in self.devices if d.type == m[1] and d.sn == m[2]), None)
        if not device:
            logging.warn(f'unknown device: {m[1]} {m[2]}')
            return

        # Check if the device supports setting this field
        if not device.has_field_setter(m[3]):
            logging.warn(f'Received command for unknown topic: {m[3]} - {mqtt_message.topic}')
            return

        field = NORMAL_DEVICE_FIELDS.get(m[3])
        if field is None:
            logging.warning('Received command for unhandled field: %s', m[3])
            return
        if device.type == 'AC60' and mqtt_message.retain:
            logging.warning('Ignoring retained AC60 command for %s', m[3])
            return
        try:
            if field.type == MqttFieldType.ENUM:
                value = mqtt_message.payload.decode('ascii')
            elif field.type == MqttFieldType.BOOL or field.type == MqttFieldType.BUTTON:
                if device.type == 'AC60' and mqtt_message.payload not in (b'ON', b'OFF'):
                    raise ValueError('expected ON or OFF')
                value = mqtt_message.payload == b'ON'
            elif field.type == MqttFieldType.NUMERIC:
                value = int(mqtt_message.payload.decode('ascii'))
            else:
                raise AssertionError(f'unexpected enum type: {field.type}')
            cmd = device.build_setter_command(m[3], value)
        except (KeyError, ValueError):
            logging.warning('Ignoring invalid command value for %s', m[3])
            return

        await self.bus.put(CommandMessage(device, cmd))

    async def _handle_message(self, client: Client, msg: ParserMessage):
        logging.debug(f'Got a message from {msg.device}: {msg.parsed}')
        topic_prefix = f'bluetti/state/{msg.device.type}-{msg.device.sn}/'

        # Publish normal fields
        fields = AC60_FIELDS if msg.device.type == 'AC60' else NORMAL_DEVICE_FIELDS
        for name, value in msg.parsed.items():
            # Skip unconfigured fields
            if name not in fields:
                continue

            # Build payload string
            field = fields[name]
            if field.type == MqttFieldType.NUMERIC:
                payload = str(value)
            elif field.type == MqttFieldType.BOOL or field.type == MqttFieldType.BUTTON:
                payload = 'ON' if value else 'OFF'
            elif field.type == MqttFieldType.ENUM:
                payload = value.name
            else:
                assert False, f'Unhandled field type: {field.type.name}'

            await client.publish(topic_prefix + name, payload=payload.encode())

        # Publish battery pack data
        pack_details = self._build_pack_details(msg.parsed)
        if 'pack_num' in msg.parsed and len(pack_details) > 0:
            await client.publish(
                topic_prefix + f'pack_details{msg.parsed["pack_num"]}',
                payload=json.dumps(pack_details, separators=(',', ':')).encode()
            )

        # Publish DC input data
        dc_fields = DC_INPUT_FIELDS if msg.device.type == 'AC60' else LEGACY_DC_INPUT_FIELDS
        for name, field in dc_fields.items():
            if name in msg.parsed:
                await client.publish(topic_prefix + field.id_override, payload=str(msg.parsed[name]).encode())

    def _build_pack_details(self, parsed: dict):
        details = {}
        if 'pack_status' in parsed:
            details['status'] = parsed['pack_status'].name
        if 'pack_battery_percent' in parsed:
            details['percent'] = parsed['pack_battery_percent']
        if 'pack_voltage' in parsed:
            details['voltage'] = float(parsed['pack_voltage'])
        if 'cell_voltages' in parsed:
            details['voltages'] = [float(d) for d in parsed['cell_voltages']]
        return details
