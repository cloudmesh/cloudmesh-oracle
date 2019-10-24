# Documentation

[![image](https://img.shields.io/travis/TankerHQ/cloudmesh-oracle.svg?branch=master)](https://travis-ci.org/TankerHQ/cloudmesn-oracle)

[![image](https://img.shields.io/pypi/pyversions/cloudmesh-oracle.svg)](https://pypi.org/project/cloudmesh-oracle)

[![image](https://img.shields.io/pypi/v/cloudmesh-oracle.svg)](https://pypi.org/project/cloudmesh-oracle/)

[![image](https://img.shields.io/github/license/TankerHQ/python-cloudmesh-oracle.svg)](https://github.com/TankerHQ/python-cloudmesh-oracle/blob/master/LICENSE)

see cloudmesh.cloud

* https://github.com/cloudmesh/cloudmesh-cmd5

## Oracle Compute Cloud interface

We provide the Oracle Cloud Compute interfaces

## Getting an Account

TBD

## Oracle Cloud Python interface

### Cloudmesh Config

Add the following entry to you cloudmesh.yaml file:

```
oracle:
      cm:
        active: true
        heading: ORACLE
        host: cloud.oracle.com
        label: oracle
        kind: oracle
        version: TBD
        service: compute
      default:
        image: ami-0f65671a86f061fcd
        size: t2.micro
      credentials:
        user : TBD
        fingerprint : TBD
        key_file : ~/.oci/oci_api_key.pem
        pass_phrase : TBD
        tenancy : TBD
        compartment_id : TBD
        region : us-ashburn-1
```

        
TBD. describe how we use cloudmesh config

design an entry

In prg you use 

config = Config["cloudmesh.cloud.oracle"]

to get oracle configuration from cloudmesh.yaml

### List Flavors

point to example prg examples/flavors.py
use cloidmesh.yaml

### List Images 

point to example prg examples/images.py
use cloidmesh.yaml

### List VMs

point to example prg examples/vms.py
use cloidmesh.yaml

### Boot VMs

point to example prg examples/boot.py
use cloidmesh.yaml

Naturally you nee to deal with keys and secgroups also 

... 

## References

* https://oracle-cloud-infrastructure-python-sdk.readthedocs.io/en/latest/
* https://oracle-cloud-infrastructure-python-sdk.readthedocs.io/en/latest/api/core/client/oci.core.ComputeClient.html
* https://docs.cloud.oracle.com/iaas/Content/API/SDKDocs/pythonsdk.htm
* https://github.com/oracle/oci-python-sdk
* https://github.com/oracle/oci-python-sdk/blob/master/examples/launch_instance_example.py
* https://github.com/cloudmesh-community/fa19-516-162/blob/master/project/report.md

