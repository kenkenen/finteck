import sys
import os
import boto3
from datetime import datetime

awsDir = os.environ.get('HOME') + "/.aws"
profile = sys.argv[1]
setupFile = "." + profile + ".initsetup"
mfaToken = sys.argv[2]

while True:
    try:

print(awsDir)