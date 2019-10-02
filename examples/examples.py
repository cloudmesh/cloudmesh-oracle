## Lists account users
import oci
config = oci.config.from_file()
identity = oci.identity.IdentityClient(config)
users = identity.list_users(config["tenancy"]).data
for user in users:
    print(user.id, user.description)

## List all VM instances in a compartment
compute = oci.core.ComputeClient(config)
compartment_id = config["compartment_id"]
instances = compute.list_instances(compartment_id).data
for instance in instances:
    print(instance.display_name, instance.lifecycle_state)
delete_instance = instances[0]

## List running VM instances in a compartment
compute = oci.core.ComputeClient(config)
compartment_id = config["compartment_id"]
instances = compute.list_instances(compartment_id, lifecycle_state="RUNNING").data
for instance in instances:
    print(instance.display_name, instance.lifecycle_state)

## Lists images in a compartment
images = compute.list_images(compartment_id)
for image in images.data:
    print(image.display_name)

## Terminate a vm instance
compute.terminate_instance(delete_instance)