import oci
from cloudmesh.configuration.Config import Config
from cloudmesh.oracle.compute.Provider import Provider
from cloudmesh.oracle.storage.Provider import Provider as StorageProvider

# Initialize
config_file = "~/.cloudmesh/cloudmesh.yaml"
config = Config(config_file)["cloudmesh"]["cloud"]["oracle"]["credentials"]
compute = oci.core.ComputeClient(config)
virtual_network = oci.core.VirtualNetworkClient(config)
identity_client = oci.identity.IdentityClient(config)
provider = Provider(name='oracle')
storage_provider = StorageProvider('oracle')


result = storage_provider.list("example-bucket")
print("RESULT:", result)

# Test list public ips
def test_list_ips():
    ips = provider.list_public_ips(ip='test_public_ip',available=True)
    print(ips)

# Test create instance
def test_create_instance():
    provider.create(name='new_instance')

# Test list public ips
def test_list_public_ips():
    x = provider.list_public_ips()
    print(x)

# Get server metadata
def get_instance_metadata(vm_instance):
    info = compute.get_instance("ocid1.instance.oc1.iad.abuwcljtdmuy2f4ftcuo7of5wd3gnqwbidt4e3cqnflnqgdd66pl2jk6lmwq").data
    print(info.metadata)


# Find status of a VM instance
def get_instance_status(vm_instance):
    status = compute.get_instance(vm_instance).data
    print(status.lifecycle_state)


# Find information about a VM instance
def get_instance_status(vm_instance):
    info = compute.get_instance(vm_instance).data
    print(info)


# Lists account users
def list_users():
    identity = oci.identity.IdentityClient(config)
    users = identity.list_users(config["tenancy"]).data
    for user in users:
        print(user.id, user.description)


# Lists all VM instances in a compartment4
def list_instances():
    compartment_id = config["compartment_id"]
    instances = compute.list_instances(compartment_id).data
    for instance in instances:
        print(instance.display_name, instance.lifecycle_state)


# Lists running VM instances in a compartment
def list_running_instances():
    compartment_id = config["compartment_id"]
    instances = compute.list_instances(compartment_id, lifecycle_state="RUNNING").data
    for instance in instances:
        print(instance.display_name, instance.lifecycle_state)


# Lists images in a compartment
def list_images():
    compartment_id = config["compartment_id"]
    images = compute.list_images(compartment_id)
    for image in images.data:
        print(image.display_name)


# Find image with given name
# image_id str
def get_image(image_name):
    compartment_id = config["compartment_id"]
    images = compute.list_images(compartment_id, display_name=image_name)
    return images.data[0]


# List all flavors in a compartment
def list_flavors():
    compartment_id = config["compartment_id"]
    flavors = compute.list_shapes(compartment_id)
    for flavor in flavors.data:
        print(flavor.shape)


# Renames a vm instance
# vm_instance str
def rename(vm_instance, name):
    details = oci.core.models.UpdateInstanceDetails()
    details.display_name = name
    compute.update_instance(vm_instance, details)


# Starts a vm instance
# vm_instance str
def start_instance(vm_instance):
    if compute.get_instance(vm_instance).data.lifecycle_state in 'STOPPED':
        compute.instance_action(vm_instance, 'START')


# Stops a vm instance
# vm_instance str
def stop_instance(vm_instance):
    if compute.get_instance(vm_instance).data.lifecycle_state in 'RUNNING':
        compute.instance_action(vm_instance, 'SOFTSTOP')


# Reboots a vm instance
# vm_instance str
def reboot_instance(vm_instance):
    if compute.get_instance(vm_instance).data.lifecycle_state in 'RUNNING':
        compute.instance_action(vm_instance, 'SOFTRESET')


# Terminate an instance of a vm
# vm_instance_id str
def terminate_instance(vm_instance):
    compute.terminate_instance(vm_instance)


def get_availability_domain(identity_client, compartment_id):
    availability_domain = identity_client.list_availability_domains(compartment_id).data[0]
    return availability_domain


def create_vcn_and_subnet(virtual_network, compartment_id, availability_domain):
    # Create a VCN
    vcn_name = 'test_vcn'
    cidr_block = "10.0.0.0/16"
    result = virtual_network.list_vcns(compartment_id, display_name=vcn_name).data

    if not result:
        vcn_details = oci.core.models.CreateVcnDetails(cidr_block=cidr_block, display_name=vcn_name, compartment_id=compartment_id)
        result = virtual_network.create_vcn(vcn_details).data
    else:
        result = result[0]

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
    subnet_cidr_block1 = "10.0.0.0/25"
    result_subnet = virtual_network.list_subnets(compartment_id, vcn.id, display_name=subnet_name).data
    if not result_subnet:
        result_subnet = virtual_network.create_subnet(
            oci.core.models.CreateSubnetDetails(
                compartment_id=compartment_id,
                availability_domain=availability_domain,
                display_name=subnet_name,
                vcn_id=vcn.id,
                cidr_block=subnet_cidr_block1
            )
        ).data
    else:
        result_subnet = result_subnet[0]

    subnet = oci.wait_until(
        virtual_network,
        virtual_network.get_subnet(result_subnet.id),
        'lifecycle_state',
        'AVAILABLE',
        max_wait_seconds=300
    ).data
    print('Created subnet')

    return {'vcn': vcn, 'subnet': subnet}


def create_instance():
    create_instance_details = oci.core.models.LaunchInstanceDetails()
    compartment_id = config["compartment_id"]
    create_instance_details.compartment_id = compartment_id
    availability_domain = get_availability_domain(identity_client, compartment_id)
    vcn_and_subnet = create_vcn_and_subnet(virtual_network, compartment_id, availability_domain.name)
    create_instance_details.availability_domain = availability_domain.name
    create_instance_details.display_name = 'test_instance'
    subnet = vcn_and_subnet['subnet']
    create_instance_details.create_vnic_details = oci.core.models.CreateVnicDetails(
            subnet_id=subnet.id,
            assign_public_ip=False
        )
    create_instance_details.image_id = get_image('Oracle-Linux-7.7-2019.08.28-0').id
    create_instance_details.shape = 'VM.Standard.E2.1'

    result = compute.launch_instance(create_instance_details)
    instance_ocid = result.data.id

    get_instance_response = oci.wait_until(
        compute,
        compute.get_instance(instance_ocid),
        'lifecycle_state',
        'RUNNING',
        max_wait_seconds=600
    )
    print('Launched instance')

# For storage
def create_file_system():
    file_storage_client = oci.file_storage.FileStorageClient(config)
    compartment_id = config["compartment_id"]
    availability_domain=get_availability_domain(
                identity_client, compartment_id)
    print(availability_domain)
    # Creating File System
    create_response = file_storage_client.create_file_system(
        oci.file_storage.models.CreateFileSystemDetails(
            display_name='py_sdk_example_fs',
            compartment_id=compartment_id,
            availability_domain=availability_domain.name,
            freeform_tags={"foo": "value"}
        ),
        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
    )

    file_system = oci.wait_until(
        file_storage_client,
        file_storage_client.get_file_system(create_response.data.id),
        'lifecycle_state',
        'ACTIVE'
    ).data
    print('Created file system:\n{}'.format(file_system))
    print('=============================\n')
