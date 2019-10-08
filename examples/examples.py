import oci
from cloudmesh.configuration.Config import Config

# Initialize
name = "oracle"
config_file = "~/.cloudmesh/cloudmesh.yaml"
config = Config(config_file)["cloudmesh"]["cloud"][name]
compute = oci.core.ComputeClient(config)

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
def get_image(image_id):
    image = compute.get_image(image_id).data
    print(image)


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
