import oci
from pprint import pprint
import os
from pathlib import Path

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

        # Get credentials
        configure = Config(config)["cloudmesh"]["storage"]["oracle"][
            "credentials"]
        credential = self._get_credentials(configure)
        self.object_storage = oci.object_storage.ObjectStorageClient(credential)
        self.compartment_id = credential["compartment_id"]
        self.namespace = self.object_storage.get_namespace().data

        # Get defaults
        self.bucket_name = Config(config)["cloudmesh"]["storage"]["oracle"][
            "default"]["bucket"]
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

    def ls_files(self, dir_path, recursive):
        files = []
        for item in os.listdir(dir_path):
            abspath = os.path.join(dir_path, item)
            try:
                if os.path.isdir(abspath):
                    if recursive:
                        files = files + self.ls_files(abspath, recursive)
                else:
                    files.append(abspath)
            except FileNotFoundError:
                print('Invalid Directory')
        return files

    # function to massage file path and do some transformations
    # for different scenarios of file inputs
    @staticmethod
    def get_os_path(file_name_path):
        os_path = Path(file_name_path)
        return os_path

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

    # Function to extract obj dict from metadata
    def get_and_extract_file_dict(self, filename):

        metadata = self.object_storage.head_object(
            self.namespace, self.bucket_name,
            filename)

        return self.extract_file_dict(filename, metadata.headers)

    def bucket_create(self, name=None):
        if name is None:
            name = self.bucket_name
            
        request = oci.object_storage.models.CreateBucketDetails(
            name=self.bucket_name,
            compartment_id=self.compartment_id)

        bucket = self.object_storage.create_bucket(self.namespace, request)
        print("Bucket Created:", name)

        # Update in db
        self.storage_dict['action'] = 'bucket_create'
        self.storage_dict['bucket'] = name
        self.bucket_name = name
        self.storage_dict['message'] = 'Bucket created'
        self.storage_dict['objlist'] = []
        self.storage_dict['objlist'].append({
            "fileName": name,
            "lastModificationDate":
                bucket.headers['Date'],
            "contentLength":
                bucket.headers['Content-Length']
        })
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

    def list(self, source=None, dir_only=False, recursive=True):
        """
        lists the information as dict

        :param source: the source which either can be a directory or file
        :param dir_only: Only the directory names
        :param recursive: in case of directory the recursive refers to all
                          subdirectories in the specified source
        :return: dict

        """

        self.storage_dict['action'] = 'list'
        self.storage_dict['recursive'] = recursive
        dir_files_list = []

        if source is None:
            # Get all items from bucket
            objs = self.object_storage.list_objects(
                self.namespace, self.bucket_name).data.objects
        else:
            # Get items from bucket that start with name 'source'
            source = str(self.get_os_path(source))

            objs = self.object_storage.list_objects(
                self.namespace, self.bucket_name, prefix=source)\
                .data.objects

        # Extract information of matched objects
        for obj in objs:
            dir_files_list.append(self.get_and_extract_file_dict(obj.name))

        self.storage_dict['source'] = source
        self.storage_dict['objlist'] = dir_files_list
        dictObj = self.update_dict(self.storage_dict['objlist'])
        return dictObj

    # function to delete file or directory
    def delete(self, source=None, recursive=True):
        """
        deletes the source
        :param source: the source which either can be a directory or file
        :param recursive: in case of directory the recursive refers to all
                          subdirectories in the specified source
        :return: dict
        """

        if source is None:
            print("Please enter the file/directory name to delete.")
            exit(0)
        self.storage_dict['action'] = 'delete'
        self.storage_dict['source'] = source
        self.storage_dict['recursive'] = recursive
        trimmed_source = str(self.get_os_path(source))
        is_source_dir = os.path.isdir(trimmed_source)
        dict_obj = []

        objs = self.object_storage.list_objects(
            self.namespace, self.bucket_name, prefix=trimmed_source)

        if recursive is False and is_source_dir:
            self.storage_dict['message'] = "The directory has child files. " \
                                           "Please select the recursive option."
        else:
            for obj in objs.data.objects:
                # Save deleted object details to be updated in the db
                dict_obj.append(self.get_and_extract_file_dict(obj.name))

                # Delete object
                self.object_storage.delete_object(self.namespace,
                                                  self.bucket_name,
                                                  obj.name)

            self.storage_dict['message'] = 'Source Deleted'
        self.storage_dict['objlist'] = dict_obj
        return self.update_dict(self.storage_dict['objlist'])

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

        self.storage_dict['action'] = 'put'
        self.storage_dict['source'] = source
        self.storage_dict['destination'] = destination
        self.storage_dict['recursive'] = recursive
        pprint(self.storage_dict)

        trimmed_source = self.get_os_path(source)
        trimmed_destination = self.get_os_path(destination)
        is_source_file = os.path.isfile(trimmed_source)
        is_source_dir = os.path.isdir(trimmed_source)
        files_uploaded = []

        if not self.bucket_exists(self.bucket_name):
            self.bucket_create(self.bucket_name)

        if is_source_file is True:
            # Its a file and need to be uploaded to the destination
            self.object_storage.put_object(self.namespace,
                                           self.bucket_name,
                                           str(trimmed_destination),
                                           open(trimmed_source, 'rb'))

            # make head call since file upload does not return
            # obj dict to extract meta data
            files_uploaded.append(
                self.get_and_extract_file_dict(str(trimmed_destination)))

            self.storage_dict['message'] = 'Source uploaded'
        elif is_source_dir is True:
            # Its a directory, get all files from the directory to upload
            for f in self.ls_files(trimmed_source, recursive):
                dest_file_name = str(trimmed_destination /
                        os.path.relpath(f, trimmed_source))
                # Object upload
                self.object_storage.put_object(
                    self.namespace, self.bucket_name,
                    dest_file_name,
                    open(f, 'rb'))

                # Extract header data from object
                files_uploaded.append(
                    self.get_and_extract_file_dict(dest_file_name))

            self.storage_dict['message'] = 'Source uploaded'
        else:
            self.storage_dict['message'] = 'Source not found'

        self.storage_dict['objlist'] = files_uploaded
        pprint(self.storage_dict)
        return self.update_dict(self.storage_dict['objlist'])

    # function to download file or directory
    def get(self, source=None, destination=None, recursive=True):
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

        trimmed_source = self.get_os_path(source)
        trimmed_destination = self.get_os_path(destination)

        file_objs = self.object_storage.list_objects(
            self.namespace, self.bucket_name, prefix=str(trimmed_source))

        files_downloaded = []
        is_target_dir = os.path.isdir(trimmed_destination)

        if len(file_objs.data.objects) > 1 and not is_target_dir:
            print("Please provide a directory to copy multiple files.")
        else:
            for file_obj in file_objs.data.objects:

                obj_data = self.object_storage.get_object(self.namespace,
                                                          self.bucket_name,
                                                          file_obj.name)

                try:
                    if is_target_dir:
                        with open(trimmed_destination / os.path.basename(
                                file_obj.name), 'wb') as f:
                            for chunk in obj_data.data.raw.stream(
                                    1024 * 1024, decode_content=False):
                                f.write(chunk)
                    else:
                        with open(trimmed_destination, 'wb') as f:
                            for chunk in obj_data.data.raw.stream(
                                    1024 * 1024, decode_content=False):
                                f.write(chunk)

                    files_downloaded.append(
                        self.extract_file_dict(str(trimmed_source),
                                               obj_data.headers))
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

        if directory is None:
            file_path = filename
        else:
            file_path = self.get_os_path(directory) / filename

        if recursive is False:
            objs = self.object_storage.list_objects(
                self.namespace, self.bucket_name, prefix=str(file_path))
        elif directory is None:
            objs = self.object_storage.list_objects(
                self.namespace, self.bucket_name)
        else:
            objs = self.object_storage.list_objects(
                self.namespace, self.bucket_name, prefix=str(directory))

        info_list = []

        for obj in objs.data.objects:
            if os.path.basename(obj.name) == filename:
                info_list.append(self.get_and_extract_file_dict(obj.name))

        self.storage_dict['objlist'] = info_list

        if len(info_list) == 0:
            self.storage_dict['message'] = 'File not found'
        else:
            self.storage_dict['message'] = 'File found'

        pprint(self.storage_dict)
        dictObj = self.update_dict(self.storage_dict['objlist'])
        return dictObj

