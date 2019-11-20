import oci

import os
import subprocess
from time import sleep
from sys import platform
import ctypes

from cloudmesh.abstractclass.ComputeNodeABC import ComputeNodeABC
from cloudmesh.common.Printer import Printer
from cloudmesh.common.console import Console
from cloudmesh.common.parameter import Parameter
from cloudmesh.common.util import banner
from cloudmesh.common.util import path_expand
from cloudmesh.common.variables import Variables
from cloudmesh.common3.DictList import DictList
from cloudmesh.configuration.Config import Config
from cloudmesh.mongo.CmDatabase import CmDatabase
from cloudmesh.provider import ComputeProviderPlugin
from cloudmesh.secgroup.Secgroup import Secgroup, SecgroupRule
from cloudmesh.common3.DateTime import DateTime
from cloudmesh.common.debug import VERBOSE
from cloudmesh.image.Image import Image

class Provider(ComputeNodeABC, ComputeProviderPlugin):
    kind = "oracle"

    vm_state = [
        'STARTING',
        'RUNNING',
        'STOPPING',
        'STOPPED',
        'UNKNOWN'
    ]

    output = {
        "status": {
            "sort_keys": ["cm.name"],
            "order": ["cm.name",
                      "cm.cloud",
                      "vm_state",
                      "status",
                      "task_state"],
            "header": ["Name",
                       "Cloud",
                       "State",
                       "Status",
                       "Task"]
        },
        "vm": {
            "sort_keys": ["cm.name"],
            "order": ["cm.name",
                      "cm.cloud",
                      "_lifecycle_state",
                      "_lifecycle_state",
                      "task_state",
                      "_image",
                      "_shape",
                      "ip_public",
                      "ip_private",
                      "project_id",
                      "cm.created",
                      "cm.kind"],
            "header": ["Name",
                       "Cloud",
                       "State",
                       "Status",
                       "Task",
                       "Image",
                       "Flavor",
                       "Public IPs",
                       "Private IPs",
                       "Project ID",
                       "Started at",
                       "Kind"],
            "humanize": ["launched_at"]
        },
        "image": {
            "sort_keys": ["cm.name",
                          "extra.minDisk"],
            "order": ["cm.name",
                      "size_in_mbs",
                      "size_in_mbs",
                      "min_ram",
                      "lifecycle_state",
                      "cm.driver"],
            "header": ["Name",
                       "Size (Bytes)",
                       "MinDisk (GB)",
                       "MinRam (MB)",
                       "Status",
                       "Driver"]
        },
        "flavor": {
            "sort_keys": ["cm.name",
                          "vcpus",
                          "disk"],
            "order": ["cm.name",
                      "vcpus",
                      "ram",
                      "disk"],
            "header": ["Name",
                       "VCPUS",
                       "RAM",
                       "Disk"]
        },
        "key": {
            "sort_keys": ["name"],
            "order": ["name",
                      "type",
                      "format",
                      "fingerprint",
                      "comment"],
            "header": ["Name",
                       "Type",
                       "Format",
                       "Fingerprint",
                       "Comment"]
        },
        "secrule": {
            "sort_keys": ["name"],
            "order": ["name",
                      "tags",
                      "direction",
                      "ethertype",
                      "port_range_max",
                      "port_range_min",
                      "protocol",
                      "remote_ip_prefix",
                      "remote_group_id"
                      ],
            "header": ["Name",
                       "Tags",
                       "Direction",
                       "Ethertype",
                       "Port range max",
                       "Port range min",
                       "Protocol",
                       "Range",
                       "Remote group id"]
        },
        "secgroup": {
            "sort_keys": ["name"],
            "order": ["name",
                      "tags",
                      "description",
                      "rules"
                      ],
            "header": ["Name",
                       "Tags",
                       "Description",
                       "Rules"]
        },
        "ip": {
            "order": ["name", 'floating_ip_address', 'fixed_ip_address'],
            "header": ["Name", 'Floating', 'Fixed']
        },
    }

    # noinspection PyPep8Naming
    def Print(self, data, output=None, kind=None):

        if output == "table":
            if kind == "secrule":
                # this is just a temporary fix, both in sec.py and here the secgruops and secrules should be separated
                result = []
                for group in data:
                    # for rule in group['security_group_rules']:
                    #     rule['name'] = group['name']
                    result.append(group)
                data = result

            order = self.output[kind]['order']  # not pretty
            header = self.output[kind]['header']  # not pretty
            # humanize = self.output[kind]['humanize']  # not pretty

            print(Printer.flatwrite(data,
                                    sort_keys=["name"],
                                    order=order,
                                    header=header,
                                    output=output,
                                    # humanize=humanize
                                    )
                  )
        else:
            print(Printer.write(data, output=output))

    @staticmethod
    def _get_credentials(config):
        """
        Internal function to create a dict for the oraclesdk credentials.

        :param config: The credentials from the cloudmesh yaml file
        :return: the dict for the oraclesdk
        """

        d = {'version': '1',
             'user': config['user'],
             'fingerprint': config['fingerprint'],
             'key_file': config['key_file'],
             'pass_phrase': config['pass_phrase'],
             'tenancy': config['tenancy'],
             'compartment_id': config['compartment_id'],
             'region': config['region']}
        return d

    def __init__(self, name=None, configuration="~/.cloudmesh/cloudmesh.yaml"):
        """
        Initializes the provider. The default parameters are read from the
        configuration file that is defined in yaml format.

        :param name: The name of the provider as defined in the yaml file
        :param configuration: The location of the yaml configuration file
        """

        self.config = Config(config_path=configuration)

        conf = Config(config_path=configuration)["cloudmesh"]
        super().__init__(name, conf)

        self.user = self.config["cloudmesh.profile.user"]
        self.spec = conf["cloud"][name]
        self.cloud = name

        self.default = self.spec["default"]
        self.cloudtype = self.spec["cm"]["kind"]

        self.cred = self.config[f"cloudmesh.cloud.{name}.credentials"]

        fields = ["user",
                  "fingerprint",
                  "key_file",
                  "pass_phrase",
                  "tenancy",
                  "compartment_id",
                  "region"]

        for field in fields:
            if self.cred[field] == 'TBD':
                Console.error(
                    f"The credential for Oracle cloud is incomplete. {field} must not be TBD")
        self.credential = self._get_credentials(self.cred)

        self.compute = oci.core.ComputeClient(self.credential)
        self.virtual_network = oci.core.VirtualNetworkClient(self.credential)
        self.identity_client = oci.identity.IdentityClient(self.credential)
        self.compartment_id = self.credential["compartment_id"]

        # self.default_image = deft["image"]
        # self.default_size = deft["size"]
        # self.default.location = cred["datacenter"]

        try:
            self.public_key_path = conf["profile"]["publickey"]
            self.key_path = path_expand(
                Config()["cloudmesh"]["profile"]["publickey"])
            f = open(self.key_path, 'r')
            self.key_val = f.read()
        except:
            raise ValueError("the public key location is not set in the "
                             "profile of the yaml file.")

    def update_dict(self, elements, kind=None):
        """
        This function adds a cloudmesh cm dict to each dict in the list
        elements.
        Libcloud
        returns an object or list of objects With the dict method
        this object is converted to a dict. Typically this method is used
        internally.

        :param elements: the list of original dicts. If elements is a single
                         dict a list with a single element is returned.
        :param kind: for some kinds special attributes are added. This includes
                     key, vm, image, flavor.
        :return: The list with the modified dicts
        """

        if elements is None:
            return None
        elif type(elements) == list:
            _elements = elements
        else:
            _elements = [elements]
        d = []
        for entry in _elements:
            if "cm" not in entry:
                entry['cm'] = {}

            if kind == 'ip':
                entry['name'] = entry['_ip_address']

            entry["cm"].update({
                "kind": kind,
                "driver": self.cloudtype,
                "cloud": self.cloud
            })

            if kind == 'key':
                try:
                    entry['comment'] = entry['public_key'].split(" ", 2)[2]
                except:
                    entry['comment'] = ""
                entry['format'] = \
                    entry['public_key'].split(" ", 1)[0].replace("ssh-", "")

            elif kind == 'vm':
                entry['name'] = entry["cm"]["name"] = entry["_display_name"]
                entry['_image'] = self.compute.get_image(
                    entry['_image_id']).data.display_name

                vnic = self.compute.list_vnic_attachments(
                    self.compartment_id, instance_id=entry['_id']).data[0]
                private = self.virtual_network.list_private_ips(
                    subnet_id=vnic.subnet_id).data[0]
                details = oci.core.models.GetPublicIpByPrivateIpIdDetails(
                    private_ip_id=private.id)
                public = self.virtual_network.get_public_ip_by_private_ip_id(
                    details).data

                if public:
                    entry['ip_public'] = public.ip_address
                entry['ip_private'] = private.ip_address
                entry["cm"]["updated"] = str(DateTime.now())
                entry["cm"]["created"] = str(entry["_time_created"])
                entry["cm"]["status"] = str(entry["_lifecycle_state"])
                entry['_launch_options'] = entry['_launch_options'].__dict__
                entry['_source_details'] = entry['_source_details'].__dict__
                entry['_agent_config'] = entry['_agent_config'].__dict__

            elif kind == 'flavor':
                entry['name'] = entry["cm"]["name"] = entry["_shape"]
                entry["cm"]["created"] = entry["updated"] = str(
                    DateTime.now())

            elif kind == 'image':
                entry['name'] = entry["cm"]["name"] = entry["_display_name"]
                entry["cm"]["created"] = entry["updated"] = str(
                    DateTime.now())
                entry['_launch_options'] = entry['_launch_options'].__dict__

            d.append(entry)
        return d

    def find(self, elements, name=None):
        """
        Finds an element in elements with the specified name.

        :param elements: The elements
        :param name: The name to be found
        :return:
        """

        for element in elements:
            if element["name"] == name or element["cm"]["name"] == name:
                return element
        return None

    def get_instance(self, name):
        vm_instance = self.compute.list_instances(self.compartment_id,
                                                  display_name=name).data
        if vm_instance:
            return vm_instance[0]
        else:
            return None

    def keys(self):
        """
        Lists the keys on the cloud

        :return: dict
        """
        ### TODO: THIS HAS TO BE CHANGED

        return self.get_list(self.cloudman.list_keypairs(),
                             kind="key")

    def key_upload(self, key=None):
        """
        uploads the key specified in the yaml configuration to the cloud
        :param key:
        :return:
        """

        name = key["name"]
        cloud = self.cloud
        Console.msg(f"upload the key: {name} -> {cloud}")
        try:
            ### TODO: THIS HAS TO BE CHANGED

            r = self.cloudman.create_keypair(name, key['public_key'])
        except:  # openstack.exceptions.ConflictException:
            raise ValueError(f"key already exists: {name}")

        return r

    def key_delete(self, name=None):
        """
        deletes the key with the given name
        :param name: The name of the key
        :return:
        """

        cloud = self.cloud
        Console.msg(f"delete the key: {name} -> {cloud}")
        ### TODO: THIS HAS TO BE CHANGED

        r = self.cloudman.delete_keypair(name)

        return r

    def list_secgroups(self, name=None):
        """
        List the named security group

        :param name: The name of the group, if None all will be returned
        :return:
        """
        groups = self.virtual_network.list_network_security_groups(
            self.compartment_id, display_name=name).data

        return self.get_list(
            groups,
            kind="secgroup")

    def list_secgroup_rules(self, name='default'):
        """
        List the named security group

        :param name: The name of the group, if None all will be returned
        :return:
        """
        return self.list_secgroups(name=name)

    def add_secgroup(self, name=None, description=None, vcn_id=None):
        """
        Adds the
        :param name: Name of the group
        :param description: The description
        :return:
        """

        if description is None:
            description = name
        try:
            details = oci.core.models.CreateNetworkSecurityGroupDetails(
                compartment_id=self.compartment_id, display_name=name,
                vcn_id=vcn_id)
            secgroup = self.virtual_network.create_network_security_group(
                details)
            return secgroup.data
        except:
            Console.warning(f"secgroup {name} already exists in cloud. "
                            f"skipping.")

    def add_secgroup_rule(self,
                          name=None,  # group name
                          port=None,
                          protocol=None,
                          ip_range=None):
        """
        Adds the
        :param name: Name of the group
        :param description: The description
        :return:
        """

        try:
            portmin, portmax = port.split(":")
        except:
            portmin = None
            portmax = None

        sec_group = self.list_secgroups(name).id
        rule_details = oci.core.models.AddSecurityRuleDetails(
            direction='ingress', protocol=protocol)
        details = oci.core.models.AddNetworkSecurityGroupSecurityRulesDetails(
            [].append(rule_details))
        self.virtual_network.add_network_security_group_security_rules(
            sec_group, details)

        '''
        self.virtual_network.add_network_security_group_security_rules(
                sec_group, details, 
                port_range_min=portmin,
                port_range_max=portmax,
                
                remote_ip_prefix=ip_range,
                remote_group_id=None,
                
                ethertype='IPv4',
                project_id=None)
        '''

    def remove_secgroup(self, name=None):
        """
        Delete the names security group

        :param name: The name
        :return:
        """
        sec_group = self.list_secgroups(name).data
        self.virtual_network.delete_network_security_group(sec_group.id)
        sec_group = self.list_secgroups(name)
        return len(sec_group) == 0

    def upload_secgroup(self, name=None):
        ### TODO: THIS HAS TO BE CHANGED

        cgroups = self.list_secgroups(name)
        group_exists = False
        if len(cgroups) > 0:
            print("Warning group already exists")
            group_exists = True

        groups = Secgroup().list()
        rules = SecgroupRule().list()

        # pprint (rules)
        data = {}
        for rule in rules:
            data[rule['name']] = rule

        # pprint (groups)

        for group in groups:
            if group['name'] == name:
                break
        print("upload group:", name)

        if not group_exists:
            self.add_secgroup(name=name, description=group['description'])

            for r in group['rules']:
                if r != 'nothing':
                    found = data[r]
                    print("    ", "rule:", found['name'])
                    self.add_secgroup_rule(
                        name=name,
                        port=found["ports"],
                        protocol=found["protocol"],
                        ip_range=found["ip_range"])

        else:

            for r in group['rules']:
                if r != 'nothing':
                    found = data[r]
                    print("    ", "rule:", found['name'])
                    self.add_rules_to_secgroup(
                        name=name,
                        rules=[found['name']])

    # ok
    def add_rules_to_secgroup(self, name=None, rules=None):

        if name is None and rules is None:
            raise ValueError("name or rules are None")

        cgroups = self.list_secgroups(name)
        if len(cgroups) == 0:
            raise ValueError("group does not exist")

        groups = DictList(Secgroup().list())
        rules_details = DictList(SecgroupRule().list())

        try:
            group = groups[name]
        except:
            raise ValueError("group does not exist")

        for rule in rules:
            try:
                found = rules_details[rule]
                self.add_secgroup_rule(name=name,
                                       port=found["ports"],
                                       protocol=found["protocol"],
                                       ip_range=found["ip_range"])
            except:
                ValueError("rule can not be found")

    # not tested
    def remove_rules_from_secgroup(self, name=None, rules=None):
        ### TODO: THIS HAS TO BE CHANGED

        if name is None and rules is None:
            raise ValueError("name or rules are None")

        cgroups = self.list_secgroups(name)
        if len(cgroups) == 0:
            raise ValueError("group does not exist")

        groups = DictList(Secgroup().list())
        rules_details = DictList(SecgroupRule().list())

        try:
            group = groups[name]
        except:
            raise ValueError("group does not exist")

        for rule in rules:
            try:
                found = rules_details[rule]
                try:
                    pmin, pmax = rules['ports'].split(":")
                except:
                    pmin = None
                    pmax = None
            except:
                ValueError("rule can not be found")

            for r in cgroups['security_group_rules']:

                test = \
                    r["port_range_max"] == pmin and \
                    r["port_range_min"] == pmax and \
                    r["protocol"] == found["protocol"] and \
                    r["remote_ip_prefix"] == found["ports"]
                # r["direction"] == "egress" \
                # r["ethertype"] == "IPv6" \
                # r["id"] == "1234e4e3-ba72-4e33-9844-..." \
                # r["remote_group_id"]] == null \
                # r["tenant_id"]] == "CH-12345"

                if test:
                    id = r["security_group_id"]
                    self.cloudman.delete_security_group_rule(id)

    def get_list(self, d, kind=None, debug=False, **kwargs):
        """
        Lists the dict d on the cloud
        :return: dict or libcloud object
        """

        if self.compute:
            entries = []
            for entry in d:
                entries.append(entry.__dict__)
            return self.update_dict(entries, kind=kind)
        return None

    def images(self, **kwargs):
        """
        Lists the images on the cloud
        :return: dict object
        """
        d = self.compute.list_images(self.compartment_id).data
        return self.get_list(d, kind="image")

    def image(self, name=None):
        """
        Gets the image with a given name
        :param name: The name of the image
        :return: the dict of the image
        """

        img = self.compute.list_images(self.compartment_id, display_name=name)
        return img.data[0]

    def flavors(self):
        """
        Lists the flavors on the cloud

        :return: dict of flavors
        """
        flavor_list = self.compute.list_shapes(self.compartment_id).data
        return self.get_list(flavor_list, kind="flavor")

    def flavor(self, name=None):
        """
        Gets the flavor with a given name
        :param name: The name of the flavor
        :return: The dict of the flavor
        """

        return self.find(self.flavors(), name=name)

    def start(self, name=None):
        """
        Start a server with the given name

        :param name: A list of node name
        :return:  A list of dict representing the nodes
        """

        vm_instance = self.get_instance(name)
        if self.compute.get_instance(
                vm_instance.id).data.lifecycle_state in 'STOPPED':
            self.compute.instance_action(vm_instance.id, 'START')

    def stop(self, name=None):
        """
        Stop a list of nodes with the given name

        :param name: A list of node name
        :return:  A list of dict representing the nodes
        """

        vm_instance = self.get_instance(name)
        if self.compute.get_instance(
                vm_instance.id).data.lifecycle_state in 'RUNNING':
            self.compute.instance_action(vm_instance.id, 'SOFTSTOP')

    def pause(self, name=None):
        """
        Start a server with the given name

        :param name: A list of node name
        :return:  A list of dict representing the nodes
        """
        print("Pause is not supported in Oracle")

    def unpause(self, name=None):
        """
        Stop a list of nodes with the given name

        :param name: A list of node name
        :return:  A list of dict representing the nodes
        """
        print("Un-Pause is not supported in Oracle")

    def info(self, name=None):
        """
        Gets the information of a node with a given name

        :param name: The name of the virtual machine
        :return: The dict representing the node including updated status
        """
        data = self.get_instance(name)

        if data is None:
            raise ValueError(f"vm not found {name}")

        r = self.update_dict([data], kind="vm")
        return r

    def status(self, name=None):

        vm_instance = self.get_instance(name)
        r = self.compute.get_instance(vm_instance.id).data
        return r.lifecycle_state

    def suspend(self, name=None):
        """
        NOT YET IMPLEMENTED.

        suspends the node with the given name.

        :param name: the name of the node
        :return: The dict representing the node
        """
        # UNTESTED
        ### TODO: THIS HAS TO BE CHANGED

        server = self.cloudman.get_server(name)['id']
        r = self.cloudman.compute.suspend_server(server)

        return r

    def resume(self, name=None):
        """
        resume a stopped node.

        :param name: the name of the node
        :return: the dict of the node
        """
        vm_instance = self.get_instance(name)
        res = self.compute.instance_action(vm_instance.id, 'START')
        return res

    def list(self):
        """
        Lists the vms on the cloud

        :return: dict of vms
        """
        vm_list = self.compute.list_instances(self.compartment_id).data
        return self.get_list(vm_list, kind="vm")

    def destroy(self, name=None):
        """
        Destroys the node
        :param name: the name of the node
        :return: the dict of the node
        """
        vm_instance = self.get_instance(name)
        r = self.compute.terminate_instance(vm_instance.id)

        servers = self.update_dict([vm_instance], kind='vm')
        return servers

    def reboot(self, name=None):
        """
        Reboot a list of nodes with the given name

        :param name: A list of node name
        :return:  A list of dict representing the nodes
        """

        vm_instance = self.get_instance(name)
        res = self.compute.instance_action(vm_instance.id, 'SOFTRESET')
        return res

    def set_server_metadata(self, name, cm):
        """
        Sets the server metadata from the cm dict

        :param name: The name of the vm
        :param cm: The cm dict
        :return:
        """

        data = {'cm': str(cm)}
        vm_instance = self.get_instance(name)
        self.compute.get_instance(vm_instance.id).data.metadata = data

    def get_server_metadata(self, name):
        vm_instance = self.get_instance(name)
        return vm_instance.metadata

    def delete_server_metadata(self, name, key):
        vm_instance = self.get_instance(name)
        vm_instance.metadata = {}
        return vm_instance.metadata

    def get_availability_domain(self):
        availability_domain = \
            self.identity_client.list_availability_domains(
                self.compartment_id).data[0]
        return availability_domain

    def create_vcn_and_subnet(self, virtual_network, availability_domain):
        try:
            # Create a VCN
            vcn_name = 'test_vcn'
            cidr_block = "11.0.0.0/16"
            '''
            result = virtual_network.list_vcns(self.compartment_id,
                                               display_name=vcn_name).data
    
            if not result:
            '''
            vcn_details = oci.core.models.CreateVcnDetails(
                cidr_block=cidr_block, display_name=vcn_name,
                compartment_id=self.compartment_id)
            result = virtual_network.create_vcn(vcn_details).data
            # else:
            # result = result[0]

            vcn = oci.wait_until(
                virtual_network,
                virtual_network.get_vcn(result.id),
                'lifecycle_state',
                'AVAILABLE',
                max_wait_seconds=300
            ).data
            print('Created VCN')

            # Create a subnet
            subnet_name = 'test_subnet'
            subnet_cidr_block1 = "11.0.0.0/25"
            # result_subnet = virtual_network.list_subnets(self.compartment_id, vcn.id,
            #                                             display_name=subnet_name).data
            # if not result_subnet:
            result_subnet = virtual_network.create_subnet(
                oci.core.models.CreateSubnetDetails(
                    compartment_id=self.compartment_id,
                    availability_domain=availability_domain,
                    display_name=subnet_name,
                    vcn_id=vcn.id,
                    cidr_block=subnet_cidr_block1
                )
            ).data
            # else:
            # result_subnet = result_subnet[0]

            subnet = oci.wait_until(
                virtual_network,
                virtual_network.get_subnet(result_subnet.id),
                'lifecycle_state',
                'AVAILABLE',
                max_wait_seconds=300
            ).data
            print('Created subnet')

            # Create an internet gateway
            result_gateway = virtual_network.create_internet_gateway(
                oci.core.models.CreateInternetGatewayDetails(
                    compartment_id=self.compartment_id,
                    display_name='test_gateway',
                    is_enabled=True,
                    vcn_id=vcn.id
                )
            ).data

            gateway = oci.wait_until(
                virtual_network,
                virtual_network.get_internet_gateway(result_gateway.id),
                'lifecycle_state',
                'AVAILABLE',
                max_wait_seconds=300
            ).data
            print('Created gateway')

            route_rules = []
            route_rules.append(oci.core.models.RouteRule(
                destination='0.0.0.0/0', network_entity_id=result_gateway.id))

            new_vcn = virtual_network.get_vcn(vcn.id).data
            route_table_id = new_vcn.default_route_table_id
            route_table = virtual_network.get_route_table(route_table_id).data
            virtual_network.update_route_table(route_table.id,
                                               oci.core.models.UpdateRouteTableDetails(
                                                   route_rules=route_rules
                                               ))

            return {'vcn': vcn, 'subnet': subnet}

        except:
            if subnet is not None:
                virtual_network.delete_subnet(subnet.id)
            if gateway is not None:
                virtual_network.delete_internet_gateway(gateway.id)
            if vcn is not None:
                virtual_network.delete_vcn(vcn.id)

    def create(self,
               name=None,
               image=None,
               size=None,
               location=None,
               timeout=360,
               key=None,
               secgroup=None,
               ip=None,
               user=None,
               public=True,
               group=None,
               metadata=None,
               cloud=None,
               **kwargs):
        """
        creates a named node


        :param group: the list of groups the vm belongs to
        :param name: the name of the node
        :param image: the image used
        :param size: the size of the image
        :param timeout: a timeout in seconds that is invoked in case the image
                        does not boot. The default is set to 3 minutes.
        :param kwargs: additional arguments HEADING(c=".")ed along at time of
                       boot
        :return:
        """

        # user is 'opc' for oracle linux and windows based systems and
        # otherwise ubuntu
        if user is None:
            user = Image.guess_username(image)

        '''
        # get IP - no way to assign while creating instance in oracle
        if ip is not None:
            entry = self.list_public_ips(ip=ip, available=True)
            if len(entry) == 0:
                print("ip not available")
                raise ValueError(f"The ip can not be assigned {ip}")
        '''

        if type(group) == str:
            groups = Parameter.expand(group)
        else:
            groups = None

        banner("Create Server")
        print("    Name:    ", name)
        print("    User:    ", user)
        print("    IP:      ", ip)
        print("    Image:   ", image)
        print("    Size:    ", size)
        print("    Public:  ", public)
        print("    Key:     ", key)
        print("    location:", location)
        print("    timeout: ", timeout)
        print("    secgroup:", secgroup)
        print("    group:   ", group)
        print("    groups:  ", groups)
        print()

        try:
            create_instance_details = oci.core.models.LaunchInstanceDetails()
            create_instance_details.compartment_id = self.compartment_id
            availability_domain = self.get_availability_domain()

            vcn_and_subnet = self.create_vcn_and_subnet(self.virtual_network,
                                                        availability_domain.name)

            if secgroup is not None:
                # s = self.list_secgroups(secgroup)
                # if (len(s) == 0):
                s = self.add_secgroup(secgroup, secgroup,
                                      vcn_and_subnet['vcn'].id)
                s_id = s.id
            # else:
            # s_id = s[0]['_id']

            create_instance_details.availability_domain = availability_domain.name
            create_instance_details.display_name = name

            if (secgroup is not None):
                nsgs = []
                nsgs.append(s_id)
            else:
                nsgs = None

            subnet = vcn_and_subnet['subnet']
            create_instance_details.create_vnic_details = oci.core.models.CreateVnicDetails(
                nsg_ids=nsgs,
                subnet_id=subnet.id,
                assign_public_ip=public
            )

            create_instance_details.image_id = self.image(image).id
            create_instance_details.shape = size

            key_file = open(key, "r")
            create_instance_details.metadata = {
                "ssh_authorized_keys": key_file.read()}

            result = self.compute.launch_instance(create_instance_details)
            instance_ocid = result.data.id

            get_instance_response = oci.wait_until(
                self.compute,
                self.compute.get_instance(instance_ocid),
                'lifecycle_state',
                'RUNNING',
                max_wait_seconds=600
            )
            print('Launched instance')

            variables = Variables()
            variables['vm'] = name

        except Exception as e:
            Console.error("Problem starting vm", traceflag=True)
            print(e)
            raise RuntimeError

        vm_instance = self.compute.get_instance(instance_ocid).data.__dict__;
        return self.update_dict(vm_instance, kind="vm")[0]

    # ok
    def list_public_ips(self,
                        ip=None,
                        available=False):

        ips = self.virtual_network.list_public_ips("REGION",
                                                   self.compartment_id).data
        if ip is not None:
            for ip_names in ips:
                if ip_names.display_name == ip:
                    ips = [ip_names]
                    break

        if available:
            available_lists = []
            for ip_names in ips:
                if ip_names.lifecycle_state == 'AVAILABLE':
                    available_lists.append(ip_names)
            ips = available_lists

        return self.get_list(ips, kind="ip")

    # ok
    def delete_public_ip(self, ip=None):
        try:
            ips = self.list_public_ips(ip)

            for _ip in ips:
                r = self.virtual_network.delete_public_ip(ip['id'])
        except:
            pass

    # ok
    def create_public_ip(self):
        details = oci.core.models.CreatePublicIpDetails(
            compartment_id=self.compartment_id, display_name="test_ip",
            lifetime="RESERVED")
        return self.virtual_network.create_public_ip(details)

    # ok
    def find_available_public_ip(self):
        ips = self.virtual_network.list_public_ips("REGION",
                                                   self.compartment_id).data
        available = None
        for ip_names in ips:
            if ip_names.lifecycle_state == 'AVAILABLE':
                available = ip_names.ip_address
                break;

        return available

    # ok
    def attach_public_ip(self, name=None, ip=None):
        ### TODO: THIS HAS TO BE CHANGED
        server = self.get_instance(name)
        self.virtual_network.update_vnic()
        self.compute.attach_vnic()
        print(server)
        server.vnic.create_public_ip = False

    # ok
    def detach_public_ip(self, name=None, ip=None):
        ### TODO: THIS HAS TO BE CHANGED

        server = self.cloudman.get_server(name)['id']
        data = self.cloudman.list_floating_ips({'floating_ip_address': ip})[0]
        ip_id = data['id']
        return self.cloudman.detach_ip_from_server(server_id=server,
                                                   floating_ip_id=ip_id)

    # ok
    def get_public_ip(self,
                      server=None,
                      name=None):
        if not server:
            server = self.info(name=name)
        ip = None
        return ip

    # ok
    def get_private_ip(self,
                       server=None,
                       name=None):
        ### TODO: THIS HAS TO BE CHANGED

        if not server:
            server = self.info(name=name)
        ip = None
        ips = server['addresses']
        first = list(ips.keys())[0]
        addresses = ips[first]

        found = []
        for address in addresses:
            if address['OS-EXT-IPS:type'] == 'fixed':
                ip = address['addr']
                found.append(ip)
        return found

    def console(self, vm=None):
        return self.log(server=vm)

    def log(self, vm=None):
        instance = self.get_instance(vm)
        details = oci.core.models.CaptureConsoleHistoryDetails(
            instance_id=instance.id)
        captured_history = self.compute.capture_console_history(details).data
        oci.wait_until(
            self.compute,
            self.compute.get_console_history(captured_history.id),
            'lifecycle_state',
            'SUCCEEDED',
            max_wait_seconds=600
        )
        return self.compute.get_console_history_content(
            captured_history.id).data

    def rename(self, name=None, destination=None):
        """
        rename a node. NOT YET IMPLEMENTED.

        :param destination
        :param name: the current name
        :return: the dict with the new name
        """
        details = oci.core.models.UpdateInstanceDetails()
        details.display_name = name
        vm_instance = self.get_instance(name)
        self.compute.update_instance(vm_instance.id, details)

    def ssh(self, vm=None, command=None):
        ip = vm['ip_public']
        key_name = vm['name']
        image = vm['_image']
        user = Image.guess_username(image)
        print(key_name)

        cm = CmDatabase()

        keys = cm.find_all_by_name(name=key_name, kind="key")
        print("KEYS: ", keys)
        for k in keys:
            if 'location' in k.keys():
                if 'private' in k['location'].keys():
                    key = k['location']['private']
                    break

        cm.close_client()

        if command is None:
            command = ""

        if user is None:
            location = ip
        else:
            location = user + '@' + ip
        cmd = "ssh " \
              "-o StrictHostKeyChecking=no " \
              "-o UserKnownHostsFile=/dev/null " \
              f"-i {key} {location} {command}"
        cmd = cmd.strip()
        # VERBOSE(cmd)
        if command == "":
            if platform.lower() == 'win32':
                class disable_file_system_redirection:
                    _disable = ctypes.windll.kernel32.Wow64DisableWow64FsRedirection
                    _revert = ctypes.windll.kernel32.Wow64RevertWow64FsRedirection

                    def __enter__(self):
                        self.old_value = ctypes.c_long()
                        self.success = self._disable(
                            ctypes.byref(self.old_value))

                    def __exit__(self, type, value, traceback):
                        if self.success:
                            self._revert(self.old_value)

                with disable_file_system_redirection():
                    os.system(cmd)
            else:
                os.system(cmd)
        else:
            if platform.lower() == 'win32':
                class disable_file_system_redirection:
                    _disable = ctypes.windll.kernel32.Wow64DisableWow64FsRedirection
                    _revert = ctypes.windll.kernel32.Wow64RevertWow64FsRedirection

                    def __enter__(self):
                        self.old_value = ctypes.c_long()
                        self.success = self._disable(
                            ctypes.byref(self.old_value))

                    def __exit__(self, type, value, traceback):
                        if self.success:
                            self._revert(self.old_value)

                with disable_file_system_redirection():
                    ssh = subprocess.Popen(cmd,
                                           shell=True,
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE)
            else:
                ssh = subprocess.Popen(cmd,
                                       shell=True,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            result = ssh.stdout.read().decode("utf-8")
            if not result:
                error = ssh.stderr.readlines()
                print("ERROR: %s" % error)
            else:
                return result

    def wait(self,
             vm=None,
             interval=None,
             timeout=None):
        name = vm['name']
        if interval is None:
            # if interval is too low, OS will block your ip (I think)
            interval = 10
        if timeout is None:
            timeout = 360
        Console.info(
            f"waiting for instance {name} to be reachable: Interval: {interval}, Timeout: {timeout}")
        timer = 0
        while timer < timeout:
            sleep(interval)
            timer += interval
            try:
                r = self.list()
                r = self.ssh(vm=vm, command='echo IAmReady').strip()
                if 'IAmReady' in r:
                    return True
            except:
                pass

        return False
