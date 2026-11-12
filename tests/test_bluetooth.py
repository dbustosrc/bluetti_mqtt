import unittest
from unittest.mock import AsyncMock, Mock, patch

from bleak import BleakError
from bleak.backends.device import BLEDevice

from bluetti_mqtt.bluetooth.client import BluetoothClient, ClientState
from bluetti_mqtt.bluetooth.manager import MultiDeviceManager


class BluetoothTests(unittest.IsolatedAsyncioTestCase):
    async def test_manager_reuses_discovered_device_and_keeps_address_fallback(self):
        found = BLEDevice('AA:BB:CC:DD:EE:FF', 'AC60123', {})
        addresses = ['aa:bb:cc:dd:ee:ff', '00:11:22:33:44:55']
        clients = [Mock(run=AsyncMock()), Mock(run=AsyncMock())]
        with patch('bluetti_mqtt.bluetooth.manager.BleakScanner.discover',
                   new=AsyncMock(return_value=[found])) as discover, \
                patch('bluetti_mqtt.bluetooth.manager.BluetoothClient', side_effect=clients) as factory:
            manager = MultiDeviceManager(addresses)
            await manager.run()
        discover.assert_awaited_once()
        self.assertIs(factory.call_args_list[0].args[0], found)
        self.assertEqual(factory.call_args_list[1].args[0], addresses[1])
        self.assertEqual(list(manager.clients), addresses)
        for client in clients:
            client.run.assert_awaited_once()

    async def test_client_preserves_device_details_and_retries_failed_discovery(self):
        found = BLEDevice('AA:BB:CC:DD:EE:FF', 'AC60123', {})
        backend = Mock(connect=AsyncMock(side_effect=[
            BleakError('failed to discover services, device disconnected'), None,
        ]))
        with patch('bluetti_mqtt.bluetooth.client.BleakClient', return_value=backend) as factory:
            client = BluetoothClient(found)
        factory.assert_called_once_with(found)
        self.assertEqual(client.address, found.address)
        with patch('bluetti_mqtt.bluetooth.client.asyncio.sleep', new=AsyncMock()) as sleep:
            with self.assertLogs(level='ERROR'):
                await client._connect()
            self.assertEqual(client.state, ClientState.NOT_CONNECTED)
            sleep.assert_awaited_once_with(1)
            await client._connect()
        self.assertEqual(client.state, ClientState.CONNECTED)
        self.assertEqual(backend.connect.await_count, 2)

    async def test_client_still_accepts_an_address(self):
        with patch('bluetti_mqtt.bluetooth.client.BleakClient') as factory:
            client = BluetoothClient('00:11:22:33:44:55')
        self.assertEqual(client.address, '00:11:22:33:44:55')
        factory.assert_called_once_with(client.address)
