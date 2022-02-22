import boto3
from random import choices
import string
from botocore.exceptions import ClientError


class Ssm:

    client = None
    Name = None
    Type = None
    Value = None
    Version = None
    Selector = None
    SourceResult = None
    LastModifiedDate = None
    ARN = None
    DataType = None

    """
    Interacts with ssm 
    """
    def __init__(self, parameter='None'):
        self.client = boto3.client('ssm')
        self.get_parameter(parameter_key=parameter)

    def get_parameter(self, parameter_key):
        try:
            res = self.client.get_parameter(
                Name=parameter_key,
                WithDecryption=True
            )

            for key in res['Parameter']:
                setattr(self, key, res['Parameter'][key])

        except ClientError as e:
            raise SsmException(e)

    @staticmethod
    def add_parameter(parameter: dict, profile='default', region='us-west-2', random=False):

        if random:
            parameter['Value'] = ''.join(choices(string.ascii_uppercase + string.digits, k=22))

        session = boto3.Session(profile_name=profile)
        client = session.client('ssm', region)
        try:
            res = client.put_parameter(
                Name=parameter['Name'],
                Description=parameter['Description'],
                Value=parameter['Value'],
                Type=parameter['Type'],
                Tier='Standard',
            )
            return Ssm(parameter=parameter['Name'])
        except ClientError as e:
            raise SsmException(e)


class SsmException(Exception):
    pass
