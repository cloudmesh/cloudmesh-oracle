import oci
from pprint import pprint
import os

from cloudmesh.storage.StorageNewABC import StorageABC
from cloudmesh.configuration.Config import Config

class Provider(StorageABC):

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

    def __init__(self, service=None, config="~/.cloudmesh/cloudmesh.yaml"):
        """
        TBD

        :param service: TBD
        :param config: TBD
        """
        super().__init__(service=service, config=config)
        configure = Config(config)["cloudmesh"]["storage"]["oracle"][
            "credentials"]
        credential = self._get_credentials(configure)
        virtual_network = oci.core.VirtualNetworkClient(credential)
        identity_client = oci.identity.IdentityClient(credential)
        self.object_storage = oci.object_storage.ObjectStorageClient(credential)
        self.compartment_id = credential["compartment_id"]

        self.namespace = self.object_storage.get_namespace().data
        self.bucket_name = "example-bucket"
        object_name = "example-object"
        self.storage_dict = {}

    def update_dict(self, elements, kind=None):
        # this is an internal function for building dict object
        d = []
        for element in elements:
            entry = element
            entry["cm"] = {
                "kind": "storage",
                "cloud": self.cloud,
                "name": entry['fileName']
            }
            d.append(entry)
        return d

    # function to massage file path and do some transformations
    # for different scenarios of file inputs
    @staticmethod
    def massage_path(file_name_path):
        massaged_path = file_name_path

        # convert possible windows style path to unix path
        massaged_path = massaged_path.replace('\\', '/')

        # remove leading slash symbol in path
        if len(massaged_path) > 0 and massaged_path[0] == '/':
            massaged_path = massaged_path[1:]

        # expand home directory in path
        massaged_path = massaged_path.replace('~', os.path.expanduser('~'))
        # pprint(massaged_path)

        # expand possible current directory reference in path
        if massaged_path[0:2] == '.\\' or massaged_path[0:2] == './':
            massaged_path = os.path.abspath(massaged_path)

        return massaged_path

    # Function to extract obj dict from metadata
    @staticmethod
    def extract_file_dict(filename, metadata):
        info = {
            "fileName": filename,
            "lastModificationDate":
                metadata['last-modified'],
            "contentLength":
                metadata['Content-Length']
        }
        return info

    def bucket_create(self, name=None):
        if name is None:
            name = self.bucket_name
            
        request = oci.object_storage.models.CreateBucketDetails(
            name=self.bucket_name,
            compartment_id=self.compartment_id)

        bucket = self.object_storage.create_bucket(self.namespace, request)
        print("Bucket Created:", name)

        self.storage_dict['action'] = 'bucket_create'
        self.storage_dict['bucket'] = name
        self.bucket_name = name
        self.storage_dict['message'] = 'Bucket created'
        self.storage_dict['objlist'] = [self.extract_file_dict(name, bucket.headers)]

        dictObj = self.update_dict(self.storage_dict['objlist'])
        return dictObj

    def bucket_exists(self, name=None):
        is_bucket_exists = False
        if name:
            try:
                result = self.object_storage.get_bucket(self.namespace, name)
                if result.data:
                    is_bucket_exists = True
            except:
                is_bucket_exists = False
        return is_bucket_exists

    def create_dir(self, directory=None):
        """
        creates a directory
        :param directory: the name of the directory
        :return: dict
        """
        print("Creating directories without creating a file is not supported "
              "in Oracle")

    def list(self, source=None, dir_only=False, recursive=False):
        """
        lists the information as dict

        :param source: the source which either can be a directory or file
        :param dir_only: Only the directory names
        :param recursive: in case of directory the recursive refers to all
                          subdirectories in the specified source
        :return: dict

        """
        if source is None:
            source = self.bucket_name

        self.storage_dict['action'] = 'list'
        self.storage_dict['source'] = source
        self.storage_dict['recursive'] = recursive

        objs = self.object_storage.list_objects(self.namespace,
                                                source).data.objects
        dir_files_list = []
        for obj in objs:
            metadata = self.object_storage.get_object(self.namespace, source,
                                                      obj.name)
            dir_files_list.append(self.extract_file_dict(obj.name,
                                                         metadata.headers))

        if len(dir_files_list) == 0:
            print("No files found in directory")
            self.storage_dict['message'] = ''
        else:
            self.storage_dict['message'] = dir_files_list

        self.storage_dict['objlist'] = dir_files_list
        dictObj = self.update_dict(self.storage_dict['objlist'])
        return dictObj

    # function to delete file or directory
    def delete(self, source=None, recursive=False):
        """
        deletes the source
        :param source: the source which either can be a directory or file
        :param recursive: in case of directory the recursive refers to all
                          subdirectories in the specified source
        :return: dict
        """
        self.storage_dict['action'] = 'delete'
        self.storage_dict['source'] = source
        self.storage_dict['recursive'] = recursive
        trimmed_source = self.massage_path(source)
        dict_obj = None

        try:
            file_data = self.object_storage.get_object(self.namespace,
                                                       self.bucket_name,
                                                       trimmed_source)
            self.object_storage.delete_object(self.namespace,
                                                         self.bucket_name,
                                                         trimmed_source)

            self.storage_dict['message'] = 'Source Deleted'
            self.storage_dict['objlist'] = [self.extract_file_dict(
                trimmed_source, file_data.headers)]
            dict_obj = self.update_dict(self.storage_dict['objlist'])
        except:
            print("File not found")
            
        return dict_obj

    # function to upload file
    def put(self, source=None, destination=None, recursive=False):
        """
        puts the source on the service
        :param source: the source file
        :param destination: the destination which either can be a directory or file
        :param recursive: in case of directory the recursive refers to all
                          subdirectories in the specified source
        :return: dict
        """
        # check if the source and destination roots exist
        self.storage_dict['action'] = 'put'
        self.storage_dict['source'] = source
        self.storage_dict['destination'] = destination
        self.storage_dict['recursive'] = recursive
        pprint(self.storage_dict)

        trimmed_source = self.massage_path(source)
        trimmed_destination = self.massage_path(destination)
        is_source_file = os.path.isfile(trimmed_source)

        files_uploaded = []

        bucket = self.bucket_name
        if not self.bucket_exists(bucket):
            self.bucket_create(bucket)

        if is_source_file is True:
            # Its a file and need to be uploaded to the destination
            # check if trimmed_destination is file or a directory

            self.object_storage.put_object(self.namespace,
                                           self.bucket_name,
                                           trimmed_destination,
                                           open(trimmed_source, 'r'))

            # make head call since file upload does not return
            # obj dict to extract meta data
            metadata = self.object_storage.get_object(self.namespace,
                                                      self.bucket_name,
                                                      trimmed_destination)
            files_uploaded.append(
                self.extract_file_dict(trimmed_source, metadata.headers))

            self.storage_dict['message'] = 'Source uploaded'
            self.storage_dict['objlist'] = files_uploaded
            dictObj = self.update_dict(self.storage_dict['objlist'])
            return dictObj
        return None

    # function to download file or directory
    def get(self, source=None, destination=None, recursive=False):
        """
        gets the source from the service
        :param source: the source which either can be a directory or file
        :param destination: the destination which either can be a directory or file
        :param recursive: in case of directory the recursive refers to all
                          subdirectories in the specified source
        :return: dict
        """
        self.storage_dict['action'] = 'get'
        self.storage_dict['source'] = source
        self.storage_dict['destination'] = destination
        self.storage_dict['recursive'] = recursive

        trimmed_source = self.massage_path(source)
        trimmed_destination = self.massage_path(destination)

        file_obj = self.object_storage.get_object(self.namespace,
                                                  self.bucket_name,
                                                  trimmed_source)

        files_downloaded = []
        is_target_dir = os.path.isdir(trimmed_destination)

        if file_obj.data:
            try:
                if is_target_dir:
                    f = open(trimmed_destination+trimmed_source, "w+")
                    f.write(file_obj.data)
                    f.close()
                else:
                    f = open(trimmed_destination, "w+")
                    f.write(file_obj.data)
                    f.close()

                files_downloaded.append(
                    self.extract_file_dict(trimmed_source, file_obj.headers))
                self.storage_dict['message'] = 'Source downloaded'
            except FileNotFoundError as e:
                self.storage_dict['message'] = 'Destination not found'

        self.storage_dict['objlist'] = files_downloaded
        dictObj = self.update_dict(self.storage_dict['objlist'])
        return dictObj

    # function to search a file or directory and list its attributes
    def search(self,
               directory=None,
               filename=None,
               recursive=False):
        """
         searches for the source in all the folders on the cloud.

        :param directory: the directory which either can be a directory or file
        :param filename: filename
        :param recursive: in case of directory the recursive refers to all
                          subdirectories in the specified source
        :return: dict
        """

        self.storage_dict['search'] = 'search'
        self.storage_dict['directory'] = directory
        self.storage_dict['filename'] = filename
        self.storage_dict['recursive'] = recursive

        # TODO
