from unittest.mock import call, patch

from ami_deprecation_tool import api, configmodels


@patch("ami_deprecation_tool.api._get_all_regions")
@patch("ami_deprecation_tool.api.boto3")
def test_deprecate_region_iteration(mock_boto, mock_get_all_regions):
    regions = ["region-1", "region-2", "region-3"]
    mock_get_all_regions.return_value = regions

    config = configmodels.ConfigModel(**{"images": {}})

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

    result = api._get_images(mock_client, "image-1-$serial")

    assert result == [
        {"Name": "image-1-126", "ImageId": "126"},
        {"Name": "image-1-125", "ImageId": "125"},
        {"Name": "image-1-124", "ImageId": "124"},
        {"Name": "image-1-123", "ImageId": "123"},
    ]


@patch("ami_deprecation_tool.api._delete_images")
@patch("ami_deprecation_tool.api._deprecate_images")
@patch("ami_deprecation_tool.api.boto3")
def test_apply_policy(mock_boto, mock_deprecate_images, mock_delete_images):
    mock_client = mock_boto.client.return_value
    region_images = {
        "image-1": [("region-1", "ami-111"), ("region-2", "ami-112")],
        "image-1a": [("region-2", "ami-113")],
        "image-2": [("region-1", "ami-211"), ("region-2", "ami-212")],
        "image-3": [("region-1", "ami-311"), ("region-2", "ami-312")],
        "image-4": [("region-1", "ami-411"), ("region-2", "ami-412")],
        "image-4a": [("region-2", "ami-413")],
    }
    region_clients = {"region-1": mock_client, "region-2": mock_client}

    policy = configmodels.ConfigPolicyModel(**{"keep": 3, "action": "delete"})
    api._apply_deprecation_policy(region_images.copy(), region_clients, policy, True)
    mock_delete_images.assert_called_once_with(
        True,
        region_clients,
        {
            "image-4": [("region-1", "ami-411"), ("region-2", "ami-412")],
            "image-4a": [("region-2", "ami-413")],
        },
    )

    policy = configmodels.ConfigPolicyModel(**{"keep": 1, "action": "deprecate"})
    api._apply_deprecation_policy(region_images.copy(), region_clients, policy, True)
    mock_deprecate_images.assert_called_once_with(
        True,
        region_clients,
        {
            "image-1a": [("region-2", "ami-113")],
            "image-2": [("region-1", "ami-211"), ("region-2", "ami-212")],
            "image-3": [("region-1", "ami-311"), ("region-2", "ami-312")],
            "image-4": [("region-1", "ami-411"), ("region-2", "ami-412")],
            "image-4a": [("region-2", "ami-413")],
        },
    )
