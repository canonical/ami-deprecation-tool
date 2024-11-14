import datetime as dt
import logging
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

import boto3
from botocore.exceptions import ClientError
from mypy_boto3_ec2.client import EC2Client
from mypy_boto3_ec2.type_defs import ImageTypeDef

from .configmodels import ConfigModel, ConfigPolicyModel

logger = logging.getLogger(__name__)


@dataclass
class RegionImageContainer:
    region: str
    image_id: str
    snapshots: list[str]


class Action(StrEnum):
    DELETE = "delete"
    DEPRECATE = "deprecate"


def deprecate(config: ConfigModel, dry_run: bool) -> None:
    """
    Identify images to be deprecated and apply specified policy

    :param config: the deprecation policy config
    :type config: ConfigModel
    :param dry_run: disables actioning the images if True
    :type dry_run: bool
    """
    client = boto3.client("ec2")
    regions = _get_all_regions(client)
    region_clients = {}

    if dry_run:
        logger.info("DRY_RUN is enabled, all actions will be skipped")

    for region in regions:
        region_clients[region] = boto3.client("ec2", region_name=region)

    for image_name, policy in config.images.items():
        # key image_name, and value is a list of tuples containing (region, ami)
        region_images = defaultdict(list)
        for region, region_client in region_clients.items():
            images = _get_images(region_client, image_name)
            for image in images:
                region_images[image["Name"]].append(
                    RegionImageContainer(region, image["ImageId"], _get_snapshot_ids(image))
                )

        sorted_image_regions = dict(sorted(region_images.items()))

        _apply_deprecation_policy(sorted_image_regions, region_clients, policy, dry_run)


def _apply_deprecation_policy(
    region_images: dict[str, list[RegionImageContainer]],
    region_clients: dict[str, EC2Client],
    policy: ConfigPolicyModel,
    dry_run: bool,
) -> None:
    """
    Identify images to be deprecated based on policy and upload completeness (i.e. an
    image is present in all regions)

    :param region_images: a dictionary keyed on image names mapped to a list of tuples pairing the
    region name with the ami id in that region
    :type region_images: dict[str, list[RegionImageContainer]]
    :param region_clients: a dicitonary mapping region names to an EC2Client for that region
    :type region_clients: dict[str, EC2Client]
    :param policy: The deprecation policy for the given image set
    :type policy: ConfigPolicyModel
    :param dry_run: disables actioning the images if True
    :type dry_run: bool
    """
    completed_serials: int = 0

    for image in list(region_images.keys()):
        if completed_serials == policy.keep:
            break
        # check if image exists in all regions (i.e. is a completed upload)
        is_complete = len(region_images[image]) == len(region_clients.keys())
        if is_complete:
            completed_serials += 1
        region_images.pop(image)

    match policy.action:
        case Action.DEPRECATE:
            _deprecate_images(dry_run, region_clients, region_images)
        case Action.DELETE:
            _delete_images(dry_run, region_clients, region_images)


def _get_all_regions(client: EC2Client) -> list[str]:
    """
    Get all regions known to the active AWS profile

    :param client: an active EC2Client
    :type: EC2Client
    :return: a list of region names
    :rtype: list[str]
    """
    resp = client.describe_regions()
    return [r["RegionName"] for r in resp["Regions"]]


def _get_images(client: EC2Client, name: str) -> list[ImageTypeDef]:
    """
    Get images in a single region matching the provided name pattern.

    :param client: an active EC2Client for a region
    :type client: EC2Client
    :param name: An image name pattern to be searched
    :type name: str
    :return: the images in reverse order sorted by Name
    :rtype: list[ImageTypeDef]
    """
    # assumes images are consistently sortable
    images = client.describe_images(Owners=["self"], Filters=[{"Name": "name", "Values": [name]}])["Images"]
    return sorted(images, key=lambda x: x["Name"], reverse=True)


def _get_snapshot_ids(image: ImageTypeDef) -> list[str]:
    """
    Get list of snapshot ids from provided image
    :param image: an ec2 image
    :type image: ImageTypeDef
    :return: a list of snapshot ids associated with the given image
    :rtype: list[str]
    """
    return [device["Ebs"]["SnapshotId"] for device in image["BlockDeviceMappings"] if "Ebs" in device]


def _deprecate_images(
    dry_run: bool, region_clients: dict[str, EC2Client], images: dict[str, list[RegionImageContainer]]
) -> None:
    """
    Mark provided images for deprecation 1 minute in the future. 1 minute is the minimum allowed deprecation time.

    :param dry_run: disables actioning the images if True
    :type dry_run: bool
    :param region_clients: a dicitonary mapping region names to an EC2Client for that region
    :type region_clients: dict[str, EC2Client]
    :param images: a dictionary keyed on image names mapped to a list of tuples pairing the
    region name with the ami id in that region
    :type images: dict[str, list[RegionImageContainer]]
    """
    for image_name, image_containers in images.items():
        # Set DeprecationTime 1 minute in the future
        logger.info(f"Found image for deprecation ({image_name})")
        for image in image_containers:
            logger.info(f"Deprecating image ({image_name}) in region ({image.region})")
            client = region_clients[image.region]
            _perform_operation(
                client.enable_image_deprecation,
                {
                    "ImageId": image.image_id,
                    "DeprecateAt": str(dt.datetime.now() + dt.timedelta(minutes=1)),
                    "DryRun": dry_run,
                },
            )


def _delete_images(
    dry_run: bool, region_clients: dict[str, EC2Client], images: dict[str, list[RegionImageContainer]]
) -> None:
    """
    Delete/Deregister provided images

    :param dry_run: disables actioning the images if True
    :type dry_run: bool
    :param region_clients: a dicitonary mapping region names to an EC2Client for that region
    :type region_clients: dict[str, EC2Client]
    :param images: a dictionary keyed on image names mapped to a list of tuples pairing the
    region name with the ami id in that region
    :type images: dict[str, list[RegionImageContainer]]
    """
    for image_name, image_containers in images.items():
        logger.info(f"Found image for deletion ({image_name})")
        for image in image_containers:
            logger.info(f"Deleting image ({image_name}) in region ({image.region})")
            client = region_clients[image.region]
            _perform_operation(client.deregister_image, {"ImageId": image.image_id, "DryRun": dry_run})
            for snapshot_id in image.snapshots:
                logger.info(f"Deleting associated snapshot: {snapshot_id}")
                _perform_operation(client.delete_snapshot, {"SnapshotId": snapshot_id, "DryRun": dry_run})


def _perform_operation(operation: Callable, args: dict[str, str | bool]):
    """
    A thin wrapper around a callable to handle common exceptions (specifically dry-run)

    :param operation: a function to be called with the given arguments
    :type operation: Callable
    :param args: the arguments to pass to operation
    :type args: dict[str, str | bool]
    """
    logger.debug(f"Performing operation {operation} with the following arguments: {args}")
    try:
        operation(**args)
    except ClientError as e:
        match e.response["Error"]["Code"]:
            case "DryRunOperation":
                pass
            case _:
                raise e
