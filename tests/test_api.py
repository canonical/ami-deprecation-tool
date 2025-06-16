from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import pytest

from ami_deprecation_tool import api, configmodels


@patch("ami_deprecation_tool.api._get_all_regions")
@patch("ami_deprecation_tool.api.boto3")
def test_deprecate_region_iteration(mock_boto, mock_get_all_regions):
    regions = ["region-1", "region-2", "region-3"]
    mock_get_all_regions.return_value = regions

    config = configmodels.ConfigModel(**{"images": {}, "options": {}})

    api.deprecate(config, True)

    mock_boto.client.assert_has_calls(
        [
            call("ec2"),
            *[call("ec2", region_name=r) for r in regions],
        ]
    )


@patch("ami_deprecation_tool.api.boto3")
def test_get_images(mock_boto):
    mock_client = mock_boto.client.return_value
    mock_client.describe_images.return_value = {
        "Images": [
            {"Name": "image-1-125", "ImageId": "125"},
            {"Name": "image-1-124", "ImageId": "124"},
            {"Name": "image-1-126", "ImageId": "126"},
            {"Name": "image-1-123", "ImageId": "123"},
        ]
    }

    mock_options = MagicMock()
    result = api._get_images(mock_client, "image-1-$serial", mock_options)

    assert result == [
        {"Name": "image-1-126", "ImageId": "126"},
        {"Name": "image-1-125", "ImageId": "125"},
        {"Name": "image-1-124", "ImageId": "124"},
        {"Name": "image-1-123", "ImageId": "123"},
    ]


@pytest.mark.parametrize(
    "options_dict",
    [
        {},
        {"include_disabled": False, "include_deprecated": False, "executable_users": ["all"]},
        {"include_disabled": True, "include_deprecated": True, "executable_users": ["all"]},
    ],
)
@patch("ami_deprecation_tool.api.boto3")
def test_get_images_options(mock_boto, options_dict):
    mock_client = mock_boto.client.return_value
    options = configmodels.ConfigOptionsModel(**options_dict)
    image_name = "image-name"
    future_deprecation_time = (datetime.now() + timedelta(minutes=5)).isoformat()

    mock_images = {
        "Images": [
            {"Name": "image-name-1"},
            {"Name": "image-name-2", "DeprecationTime": None},
            {"Name": "image-name-3", "DeprecationTime": ""},
            {"Name": "image-name-4", "DeprecationTime": future_deprecation_time},
            {"Name": "image-name-4", "DeprecationTime": "2025-01-01T00:00:00Z"},
        ]
    }
    mock_client.describe_images.return_value = mock_images

    images = api._get_images(mock_client, image_name, options)

    mock_client.describe_images.assert_called_once_with(
        Owners=["self"],
        IncludeDisabled=options.include_disabled,
        Filters=[{"Name": "name", "Values": [image_name]}],
        ExecutableUsers=options.executable_users,
    )

    if options.include_deprecated:
        assert len(images) == 5
    else:
        assert len(images) == 4


@patch("ami_deprecation_tool.api._delete_images")
@patch("ami_deprecation_tool.api._deprecate_images")
@patch("ami_deprecation_tool.api.boto3")
def test_apply_policy(mock_boto, mock_deprecate_images, mock_delete_images):
    mock_client = mock_boto.client.return_value
    region_images = {
        "image-20250101": [("region-1", "ami-111"), ("region-2", "ami-112")],
        "image-20250201": [("region-2", "ami-113")],
        "image-20250301": [("region-1", "ami-211"), ("region-2", "ami-212")],
        "image-20250401": [("region-1", "ami-311"), ("region-2", "ami-312")],
        "image-20250501": [("region-1", "ami-411"), ("region-2", "ami-412")],
        "image-20250601": [("region-2", "ami-413")],
    }
    region_clients = {"region-1": mock_client, "region-2": mock_client}

    policy = configmodels.ConfigPolicyModel(**{"keep": 3, "action": "delete"})
    api._apply_deprecation_policy(region_images.copy(), region_clients, policy, True)
    mock_delete_images.assert_called_once_with(
        True,
        region_clients,
        {
            "image-20250101": [("region-1", "ami-111"), ("region-2", "ami-112")],
            "image-20250201": [("region-2", "ami-113")],
        },
    )

    policy = configmodels.ConfigPolicyModel(**{"keep": 1, "action": "deprecate"})
    api._apply_deprecation_policy(region_images.copy(), region_clients, policy, True)
    mock_deprecate_images.assert_called_once_with(
        True,
        region_clients,
        {
            "image-20250101": [("region-1", "ami-111"), ("region-2", "ami-112")],
            "image-20250201": [("region-2", "ami-113")],
            "image-20250301": [("region-1", "ami-211"), ("region-2", "ami-212")],
            "image-20250401": [("region-1", "ami-311"), ("region-2", "ami-312")],
        },
    )


@patch("ami_deprecation_tool.api._perform_operation")
@patch("ami_deprecation_tool.api.boto3")
def test_snapshot_deleted_if_not_used(mock_boto, mock_perform_operation):
    mock_client = mock_boto.client.return_value
    mock_client.describe_images.return_value = {"Images": []}
    api._delete_snapshot(mock_client, "snapshot_id", True)
    mock_perform_operation.assert_called_once()


@patch("ami_deprecation_tool.api._perform_operation")
@patch("ami_deprecation_tool.api.boto3")
def test_snapshot_skipped_if_in_use(mock_boto, mock_perform_operation):
    mock_client = mock_boto.client.return_value
    mock_client.describe_images.return_value = {"Images": [{"ImageId": "ami-123"}]}
    api._delete_snapshot(mock_client, "snapshot_id", True)
    mock_perform_operation.assert_not_called()


@patch("ami_deprecation_tool.api._get_snapshot_ids")
@patch("ami_deprecation_tool.api.boto3")
def test_action_output(mock_boto, mock_get_snapshot_ids):
    region1_images = {
        "Images": [
            {"ImageId": "ami-111", "Name": "Image-20250101"},
            {"ImageId": "ami-112", "Name": "Image-20250102"},
            {"ImageId": "ami-113", "Name": "Image-20250103"},
            {"ImageId": "ami-114", "Name": "Image-20250104"},
        ]
    }
    region2_images = {
        "Images": [
            {"ImageId": "ami-111", "Name": "Image-20250101"},
            {"ImageId": "ami-112", "Name": "Image-20250102"},
            # ami-113 is not in region2
            {"ImageId": "ami-114", "Name": "Image-20250104"},
        ]
    }

    base_client = MagicMock()
    region1_client = MagicMock()
    region2_client = MagicMock()

    base_client.describe_regions.return_value = {"Regions": [{"RegionName": "region1"}, {"RegionName": "region2"}]}
    region1_client.describe_images.return_value = region1_images
    region2_client.describe_images.return_value = region2_images

    mock_boto.client.side_effect = [base_client, region1_client, region2_client]

    config = configmodels.ConfigModel(
        **{
            "images": {
                "image-20250101": {"action": "deprecate", "keep": 2},
            },
            "options": {},
        }
    )

    actions = api.deprecate(config, True)
    assert actions == {
        "image-20250101": api.Actions(
            images=api.ActionImages(
                delete=[],
                deprecate=["Image-20250101"],
                keep=["Image-20250104", "Image-20250102"],
                skip=["Image-20250103"],
            ),
            policy={"action": "deprecate", "keep": 2},
        )
    }
