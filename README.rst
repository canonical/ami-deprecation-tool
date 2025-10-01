ami_deprecation_tool
--------------------

``ami_deprecation_tool`` can be used to apply a deprecation policy consistently across all regions of an account.

Usage
=====

The most simple usage of the tool is ``deprecate-amis -p policy.yaml --no-dry-run``. See below for a sample policy.

Use ``deprecate-amis --help`` for a full list of options

**Note: To avoid accidentally destructive behavior, 'dry-run' is the default behavior and --no-dry-run must be explicitly used**

Policy Definition
=================

.. code-block:: yaml

  ami-deprecation-tool:
    options:
      executable_users:
        - all  # public images only
      include_deprecated: false
      include_disabled: false
    images:
      some/image/path/image-A-$serial:
        action: delete
        keep: 1
      some/image/path/image-B-$serial:
        action: deprecate
        keep: 3

In the above example, ``some/image/path/image-A-$serial`` will find all images across all regions (owned by the current user) matching ``some/image/path/image-A-*`` where serial is replaced with a wildcard. These images will then be sorted by whatever matches in the place of $serial. The policy defined for this image is ``{action: delete, keep 1}`` meaning delete/deregister all except the latest image as defined by the sorted serials.

The second image (``some/image/path/image-B-$serial``) has a policy of ``{action: deprecate, keep 3}``. Rather than deregistering the AMIs, all but the latest three will be scheduled for deprecation 1 minute in the future. These images will not be visible in the browser and will only show in API results if the caller specifies they are searching for deprecated AMIs

**Note: $serial is assumed to be consistently sortable using normal alphanumeric sorting**

`executable_users` is a list of of accounts that can execute the images to be considered. It can include two special values, `self` and `all` where self is strictly private iamges and `all` which is all public AMIs. These values are passed directly to the AWS api and as such any of [their documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/describe_images.html) on the field applies.
