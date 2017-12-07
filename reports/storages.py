import os.path
import shutil
from tempfile import NamedTemporaryFile
from ConfigParser import ConfigParser

import boto3
from botocore.exceptions import ClientError

from abc import ABCMeta, abstractmethod
from pkg_resources import iter_entry_points, DistributionNotFound

from reports.vault import Vault
from logging import getLogger

try:
    import swiftclient.service
    from swiftclient.utils import generate_temp_url
    SWIFT = True
except ImportError:
    SWIFT = False


PKG_NAMESPACE = 'billing.storages'
REGISTRY = {}
LOGGER = getLogger("BILLING")


class Config(object):

    def __init__(self, config):
        self.config = config
        self.type = self.config.get('storage').get('type')
        self.bucket = self.config.get(self.type).get('bucket')
        self.expires = self.config.get(self.type).get('expires')
        self.password_prefix = self.config.get(self.type).get('password_prefix')


class BaseStorate(object):
    __metaclass__ = ABCMeta

    def __init__(self, config):
        """"""

    @abstractmethod
    def list_objects(self, key):
        """Get list of available objects mached key
           Used to send emails with links to existing objects
        """

    @abstractmethod
    def upload_file(self, file):
        """
        Upload file to remote storage
        """

    @abstractmethod
    def generate_presigned_url(self, file):
        """
        Generage public url to file
        """


class MemoryStorage(BaseStorate):
    storage = {}

    def __init__(self, config):
        self.config = Config(config)
        self.vault = Vault(config)
        user_pass = self.vault.get(self.config.password_prefix)
        LOGGER.debug("Inited memory storage with user: {} password: {}".format(
            user_pass.get("user"),
            user_pass.get('password')
            ))

    def generate_presigned_url(self, key):
        return "file://{}".format(self.storage[key])

    def upload_file(self, file, timestamp):
        key = '/'.join((timestamp, os.path.basename(file)))
        with NamedTemporaryFile(mode='w+') as tmp_file:
            with open(file, 'r') as in_file:
                shutil.copyfileobj(in_file, tmp_file)
            self.storage[key] = tmp_file.name
        return self.generate_presigned_url(key)

    def list_objects(self, prefix):
        for k, v in self.storage.items():
            if k.startswith(prefix):
                yield k


class S3Storage(BaseStorate):

    def __init__(self, config):
        self.config = Config(config)
        self.client = boto3.client
        self.vault = Vault(config)
        user_pass = self.vault.get(self.config.password_prefix)
        self.storage = boto3.client(
            's3',
            aws_access_key_id=user_pass.get(
                'AWS_ACCESS_KEY_ID',
                str(user_pass.get('user', 'AWS_ACCESS_KEY_ID'))
                ),
            aws_secret_access_key=user_pass.get(
                'AWS_SECRET_ACCESS_KEY',
                str(user_pass.get('password', 'AWS_SECRET_ACCESS_KEY'))
                ),
            region_name=user_pass.get(
                'AWS_DEFAULT_REGION',
                str(user_pass.get('region', 'eu-west-2'))
                )
            )

    def generate_presigned_url(self, key):
        return self.client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.config.bucket, 'Key': key},
                    ExpiresIn=self.config.expires,
                    )

    def upload_file(self, file, timestamp):
        # timestamp aka full path prefix
        # accepts only full system path to the file
        assert timestamp
        key = '/'.join((timestamp, os.path.basename(file)))
        try:
            self.storage.upload_file(
                file,
                self.config.bucket,
                key
                )
        except ClientError as e:
            LOGGER.fatal(
                "Falied to upload file {}. Error {}".format(file, e)
                )
            return ""
        try:
            return self.generate_presigned_url(key)
        except Exception as e:
            LOGGER.fatal(
                'Falied to sign url for file {}. Error: {}'.format(key, e)
                )
            return ""

    def list_objects(self, prefix):
        return self.client.list_objects(
                Bucket=self.config.bucket,
                Prefix=prefix
                )['Contents']


if SWIFT:
    class SwiftConfig(Config):
        def __init__(self, config):
            super(self, SwiftConfig).__init__(config)
            self.swift_url_prefix = self.config.get(self.type).get('url_prefix')

    class SwiftStorage(BaseStorate):

        def __init__(self, config):
            """
            Swift client wrapper

            :param config: System path to configuration file.
            """
            self.config = SwiftConfig(config)
            self.vault = Vault(self.config)
            user_pass = self.vault.get(self.config.password_prefix)
            self.swift = swiftclient.service.SwiftService(options={
                    "auth_version": user_pass.get('auth_version', '3'),
                    "os_username": user_pass.get('os_username'),
                    "os_user_domain_name": user_pass.get('os_user_domain_name', 'default'),
                    "os_password": user_pass.get('os_password'),
                    "os_project_name": user_pass.get('os_project_name'),
                    "os_project_domain_name": user_pass.get('os_project_domain_name', 'default'),
                    "os_auth_url": user_pass.get('os_auth_url'),
                })
            self.temporary_url_key = user_pass.get('temp_url_key')

        def generate_presigned_url(self, key):
            """
            Generates temporary public URL from given full key
            to swift object

            :param key: Full path to the object.
            :return: Full URL to the object for unauthenticated used to
                     being able to download object.
            """
            return generate_temp_url(
                    key,
                    self.config.expires,
                    self.temporary_url_key,
                    'GET'
                    )

        def upload_file(self, file, timestamp):
            with open(file, 'r') as upload_stream:
                try:
                    with self.swift as swift:
                        key = '/'.join((timestamp, os.path.basename(file)))
                        upload_obj = swiftclient.service.SwiftUploadObject(
                            upload_stream,
                            object_name=key
                            )
                        result = swift.upload(
                                    container=self.config.bucket,
                                    objects=[upload_obj]
                                    )
                        if result['success']:
                            return '/'.join((
                                self.config.swift_url_prefix,
                                self.generate_presigned_url(key)
                                ))
                        LOGGER.fatal(
                            "Falied to upload object {} with error {}".format(
                                key,
                                result['error']
                            ))
                        return ""

                except swiftclient.service.SwiftError as error:
                    LOGGER.fatal(
                        "Falied to upload file to swift with error {}".format(
                            error
                            )
                        )
                    return ""

        def list_objects(self, prefix):
            with self.swift as swift:
                try:
                    result = swift.list(
                            container=self.container,
                            prefix=prefix
                            )
                    if result['success']:
                        return result['listing']
                    LOGGER.fatal(
                            "Request  status {} with error {}".format(
                                result['success'], result['error']
                                )
                            )
                    return []
                except swiftclient.service.SwiftError as e:
                    LOGGER.fatal(
                            "Error {} on getting listint of "
                            "objects of {} with prefix {}".format(
                                e, self.container, prefix)
                            )
                    return []


for storage in iter_entry_points(PKG_NAMESPACE):
    try:
        REGISTRY[storage.name] = storage.load()
    except DistributionNotFound:
        continue
