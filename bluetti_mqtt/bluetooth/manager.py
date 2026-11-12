import asyncio
import logging
from typing import Dict, List
from bleak import BleakScanner
from bluetti_mqtt.core import DeviceCommand
from .client import BluetoothClient


class MultiDeviceManager:
    clients: Dict[str, BluetoothClient]

    def __init__(self, addresses: List[str]):
        self.addresses = addresses
        self.clients = {}

    async def run(self):
        logging.info(f'Connecting to clients: {self.addresses}')

        # Reuse discovered devices so Bleak does not scan again when connecting.
        devices = {d.address.lower(): d for d in await BleakScanner.discover()}

        # Start client loops
        self.clients = {a: BluetoothClient(devices.get(a.lower(), a)) for a in self.addresses}
        await asyncio.gather(*[c.run() for c in self.clients.values()])

    def is_ready(self, address: str):
        if address in self.clients:
            return self.clients[address].is_ready
        else:
            return False

    def get_name(self, address: str):
        if address in self.clients:
            return self.clients[address].name
        else:
            raise Exception('Unknown address')

    async def perform(self, address: str, command: DeviceCommand):
        if address in self.clients:
            return await self.clients[address].perform(command)
        else:
            raise Exception('Unknown address')

    async def perform_nowait(self, address: str, command: DeviceCommand):
        if address in self.clients:
            await self.clients[address].perform_nowait(command)
        else:
            raise Exception('Unknown address')
