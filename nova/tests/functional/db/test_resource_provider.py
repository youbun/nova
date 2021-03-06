#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from nova import context
from nova import exception
from nova import objects
from nova.objects import fields
from nova import test
from nova.tests import fixtures
from nova.tests import uuidsentinel

DISK_INVENTORY = dict(
    total=200,
    reserved=10,
    min_unit=2,
    max_unit=5,
    step_size=1,
    allocation_ratio=1.0
)


class ResourceProviderTestCase(test.NoDBTestCase):
    """Test resource-provider objects' lifecycles."""

    USES_DB_SELF = True

    def setUp(self):
        super(ResourceProviderTestCase, self).setUp()
        self.useFixture(fixtures.Database())
        self.useFixture(fixtures.Database(database='api'))
        self.context = context.RequestContext('fake-user', 'fake-project')

    def test_create_resource_provider_requires_uuid(self):
        resource_provider = objects.ResourceProvider(
            context = self.context)
        self.assertRaises(exception.ObjectActionError,
                          resource_provider.create)

    def test_create_resource_provider(self):
        created_resource_provider = objects.ResourceProvider(
            context=self.context,
            uuid=uuidsentinel.fake_resource_provider,
            name=uuidsentinel.fake_resource_name,
        )
        created_resource_provider.create()
        self.assertIsInstance(created_resource_provider.id, int)

        retrieved_resource_provider = objects.ResourceProvider.get_by_uuid(
            self.context,
            uuidsentinel.fake_resource_provider
        )
        self.assertEqual(retrieved_resource_provider.id,
                         created_resource_provider.id)
        self.assertEqual(retrieved_resource_provider.uuid,
                         created_resource_provider.uuid)
        self.assertEqual(retrieved_resource_provider.name,
                         created_resource_provider.name)
        self.assertEqual(0, created_resource_provider.generation)
        self.assertEqual(0, retrieved_resource_provider.generation)

    def test_save_resource_provider(self):
        created_resource_provider = objects.ResourceProvider(
            context=self.context,
            uuid=uuidsentinel.fake_resource_provider,
            name=uuidsentinel.fake_resource_name,
        )
        created_resource_provider.create()
        created_resource_provider.name = 'new-name'
        created_resource_provider.save()
        retrieved_resource_provider = objects.ResourceProvider.get_by_uuid(
            self.context,
            uuidsentinel.fake_resource_provider
        )
        self.assertEqual('new-name', retrieved_resource_provider.name)

    def test_create_inventory_with_uncreated_provider(self):
        resource_provider = objects.ResourceProvider(
            context=self.context,
            uuid=uuidsentinel.inventory_resource_provider
        )
        resource_class = fields.ResourceClass.DISK_GB
        disk_inventory = objects.Inventory(
            context=self.context,
            resource_provider=resource_provider,
            resource_class=resource_class,
            **DISK_INVENTORY
        )
        self.assertRaises(exception.ObjectActionError,
                          disk_inventory.create)

    def test_create_and_update_inventory(self):
        resource_provider = objects.ResourceProvider(
            context=self.context,
            uuid=uuidsentinel.inventory_resource_provider,
            name='foo',
        )
        resource_provider.create()
        resource_class = fields.ResourceClass.DISK_GB
        disk_inventory = objects.Inventory(
            context=self.context,
            resource_provider=resource_provider,
            resource_class=resource_class,
            **DISK_INVENTORY
        )
        disk_inventory.create()

        self.assertEqual(resource_class, disk_inventory.resource_class)
        self.assertEqual(resource_provider,
                         disk_inventory.resource_provider)
        self.assertEqual(DISK_INVENTORY['allocation_ratio'],
                         disk_inventory.allocation_ratio)
        self.assertEqual(DISK_INVENTORY['total'],
                         disk_inventory.total)

        disk_inventory.total = 32
        disk_inventory.save()

        inventories = objects.InventoryList.get_all_by_resource_provider_uuid(
            self.context, resource_provider.uuid)

        self.assertEqual(1, len(inventories))
        self.assertEqual(32, inventories[0].total)

        inventories[0].total = 33
        inventories[0].save()
        reloaded_inventories = (
            objects.InventoryList.get_all_by_resource_provider_uuid(
            self.context, resource_provider.uuid))
        self.assertEqual(33, reloaded_inventories[0].total)

    def test_provider_set_inventory(self):
        rp = objects.ResourceProvider(context=self.context,
                                      uuid=uuidsentinel.rp_uuid,
                                      name=uuidsentinel.rp_name)
        rp.create()
        saved_generation = rp.generation

        disk_inv = objects.Inventory(
                resource_provider=rp,
                resource_class=fields.ResourceClass.DISK_GB,
                total=1024,
                reserved=15,
                min_unit=10,
                max_unit=100,
                step_size=10,
                allocation_ratio=1.0)

        vcpu_inv = objects.Inventory(
                resource_provider=rp,
                resource_class=fields.ResourceClass.VCPU,
                total=12,
                reserved=0,
                min_unit=1,
                max_unit=12,
                step_size=1,
                allocation_ratio=16.0)

        # set to new list
        inv_list = objects.InventoryList(objects=[disk_inv, vcpu_inv])
        rp.set_inventory(inv_list)

        # generation has bumped
        self.assertEqual(saved_generation + 1, rp.generation)
        saved_generation = rp.generation

        new_inv_list = objects.InventoryList.get_all_by_resource_provider_uuid(
                self.context, uuidsentinel.rp_uuid)
        self.assertEqual(2, len(new_inv_list))
        resource_classes = [inv.resource_class for inv in new_inv_list]
        self.assertIn(fields.ResourceClass.VCPU, resource_classes)
        self.assertIn(fields.ResourceClass.DISK_GB, resource_classes)

        # reset list to just disk_inv
        inv_list = objects.InventoryList(objects=[disk_inv])
        rp.set_inventory(inv_list)

        # generation has bumped
        self.assertEqual(saved_generation + 1, rp.generation)
        saved_generation = rp.generation

        new_inv_list = objects.InventoryList.get_all_by_resource_provider_uuid(
                self.context, uuidsentinel.rp_uuid)
        self.assertEqual(1, len(new_inv_list))
        resource_classes = [inv.resource_class for inv in new_inv_list]
        self.assertNotIn(fields.ResourceClass.VCPU, resource_classes)
        self.assertIn(fields.ResourceClass.DISK_GB, resource_classes)
        self.assertEqual(1024, new_inv_list[0].total)

        # update existing disk inv to new settings
        disk_inv = objects.Inventory(
                resource_provider=rp,
                resource_class=fields.ResourceClass.DISK_GB,
                total=2048,
                reserved=15,
                min_unit=10,
                max_unit=100,
                step_size=10,
                allocation_ratio=1.0)
        inv_list = objects.InventoryList(objects=[disk_inv])
        rp.set_inventory(inv_list)

        # generation has bumped
        self.assertEqual(saved_generation + 1, rp.generation)
        saved_generation = rp.generation

        new_inv_list = objects.InventoryList.get_all_by_resource_provider_uuid(
                self.context, uuidsentinel.rp_uuid)
        self.assertEqual(1, len(new_inv_list))
        self.assertEqual(2048, new_inv_list[0].total)

        # fail when generation wrong
        rp.generation = rp.generation - 1
        self.assertRaises(exception.ConcurrentUpdateDetected,
                          rp.set_inventory, inv_list)
