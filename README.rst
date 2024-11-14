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

  images:
    some/image/path/image-A-$serial:
      action: delete
      keep: 1
    some/image/path/image-B-$serial:
      action: deprecate
      keep: 3

In the above example, ``some/image/path/image-A-$serial`` will find all images across all regions (owned by the current user) matching ``some/image/path/image-A-*`` where serial is replaced with a wildcard. These images will then be sorted by whatever matches in the place of $serial. The policy defined for this image is ``{action: delete, keep 1}`` meaning delete/deregister all except the latest image as defined by the sorted serials.

The second image (``some/image/path/image-A-$serial``) has a policy of ``{action: deprecate, keep 3}``. Rather than deregistering the AMIs, all but the latest three will be scheduled for deprecation 1 minute in the future. These images will not be visible in the browser and will only show in API results if the caller specifies they are searching for deprecated AMIs

**Note: $serial is assumed to be consistently sortable using normal alphanumeric sorting**
