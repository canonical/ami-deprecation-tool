from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import pytest

from ami_deprecation_tool import api, configmodels

ONE_MONTH_AGO = datetime.now() - timedelta(days=30)
SIX_MONTHS_AGO = datetime.now() - timedelta(days=180)


def mk_image(image_id, name, date):
    return {"ImageId": image_id, "Name": name, "CreationDate": date}


def mk_reg_img(region, image_id, date):
    return api.RegionImageContainer(region=region, image_id=image_id, creation_date=date, snapshots=[])


def make_region_images(
    image_count_expired: int, image_count_unexpired: int, missing: list[int] = []
) -> dict[str, list[dict]]:
    """
    Generate a dict shaped like boto3.describe_images with a list of images.
    :param image_count_expired: number of images to create with an old creation date
    :param image_count_unexpired: number of images to create with a new creation date
    :param image_count_expired: list of ami suffixes (like ["111","112","113"])
    :param missing: optional list of ids to skip (simulate images absent in this region)
    """

    images = []

    for id_ in range(1, image_count_expired + image_count_unexpired + 1):
        if id_ in missing:
            continue
        creation_date = SIX_MONTHS_AGO if id_ < image_count_expired else ONE_MONTH_AGO
        images.append(mk_image(f"ami-{110 + id_}", f"Image-2025{100 + id_:04d}", creation_date))

    return {"Images": images}


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
            mk_image("125", "image-1-125", ONE_MONTH_AGO),
            mk_image("124", "image-1-124", ONE_MONTH_AGO),
            mk_image("126", "image-1-126", ONE_MONTH_AGO),
            mk_image("123", "image-1-123", ONE_MONTH_AGO),
        ]
    }

    mock_options = MagicMock()
    result = api._get_images(mock_client, "image-1-$serial", mock_options)

    assert result == [
        mk_image("126", "image-1-126", ONE_MONTH_AGO),
        mk_image("125", "image-1-125", ONE_MONTH_AGO),
        mk_image("124", "image-1-124", ONE_MONTH_AGO),
        mk_image("123", "image-1-123", ONE_MONTH_AGO),
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
        "image-20250101": [
            mk_reg_img("region-1", "ami-111", ONE_MONTH_AGO),
            mk_reg_img("region-2", "ami-112", ONE_MONTH_AGO),
        ],
        "image-20250201": [mk_reg_img("region-2", "ami-113", ONE_MONTH_AGO)],
        "image-20250301": [
            mk_reg_img("region-1", "ami-211", ONE_MONTH_AGO),
            mk_reg_img("region-2", "ami-212", ONE_MONTH_AGO),
        ],
        "image-20250401": [
            mk_reg_img("region-1", "ami-311", ONE_MONTH_AGO),
            mk_reg_img("region-2", "ami-312", ONE_MONTH_AGO),
        ],
        "image-20250501": [
            mk_reg_img("region-1", "ami-411", ONE_MONTH_AGO),
            mk_reg_img("region-2", "ami-412", ONE_MONTH_AGO),
        ],
        "image-20250601": [mk_reg_img("region-2", "ami-413", ONE_MONTH_AGO)],
    }
    region_clients = {"region-1": mock_client, "region-2": mock_client}

    policy = configmodels.ConfigPolicyModel(**{"keep": 3, "action": "delete"})
    api._apply_deprecation_policy(region_images.copy(), region_clients, policy, True)
    mock_delete_images.assert_called_once_with(
        True,
        region_clients,
        {
            "image-20250101": [
                mk_reg_img("region-1", "ami-111", ONE_MONTH_AGO),
                mk_reg_img("region-2", "ami-112", ONE_MONTH_AGO),
            ],
            "image-20250201": [mk_reg_img("region-2", "ami-113", ONE_MONTH_AGO)],
        },
    )

    policy = configmodels.ConfigPolicyModel(**{"keep": 1, "action": "deprecate"})
    api._apply_deprecation_policy(region_images.copy(), region_clients, policy, True)
    mock_deprecate_images.assert_called_once_with(
        True,
        region_clients,
        {
            "image-20250101": [
                mk_reg_img("region-1", "ami-111", ONE_MONTH_AGO),
                mk_reg_img("region-2", "ami-112", ONE_MONTH_AGO),
            ],
            "image-20250201": [mk_reg_img("region-2", "ami-113", ONE_MONTH_AGO)],
            "image-20250301": [
                mk_reg_img("region-1", "ami-211", ONE_MONTH_AGO),
                mk_reg_img("region-2", "ami-212", ONE_MONTH_AGO),
            ],
            "image-20250401": [
                mk_reg_img("region-1", "ami-311", ONE_MONTH_AGO),
                mk_reg_img("region-2", "ami-312", ONE_MONTH_AGO),
            ],
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


def expect(delete, deprecate, keep, skip, policy):
    return {
        "image-20250101": api.Actions(
            images=api.ActionImages(
                delete=delete,
                deprecate=deprecate,
                keep=keep,
                skip=skip,
            ),
            policy=policy,
        )
    }


@dataclass(frozen=True)
class Scenario:
    # ---- inputs ----
    region1: dict
    region2: dict
    policy: dict
    # ---- expected outputs ----
    delete: list[str]
    deprecate: list[str]
    keep: list[str]
    skip: list[str]


SCENARIOS: dict[str, Scenario] = {
    # 1. test_action_output
    "action_output": Scenario(
        region1=make_region_images(image_count_expired=0, image_count_unexpired=4),
        region2=make_region_images(image_count_expired=0, image_count_unexpired=4, missing=[3]),
        policy={"action": "deprecate", "keep": 2, "keep_days": 0},
        delete=[],
        deprecate=["Image-20250101"],
        keep=["Image-20250104", "Image-20250102"],
        skip=["Image-20250103"],
    ),
    # 2. test_deprecate_images_past_expiration”)
    # Some images expired, only keep within keep budget
    "past_expiration": Scenario(
        region1=make_region_images(image_count_expired=5, image_count_unexpired=1),
        region2=make_region_images(image_count_expired=5, image_count_unexpired=1, missing=[4]),
        policy={"action": "deprecate", "keep": 3, "keep_days": 90},
        delete=[],
        deprecate=["Image-20250101", "Image-20250102"],
        keep=["Image-20250106", "Image-20250105", "Image-20250103"],
        skip=["Image-20250104"],
    ),
    # 3. test_keep_past_expiration
    # All images expired but keep-budget still applies
    "keep_past_expiration": Scenario(
        region1=make_region_images(image_count_expired=6, image_count_unexpired=0),
        region2=make_region_images(image_count_expired=6, image_count_unexpired=0, missing=[4]),
        policy={"action": "deprecate", "keep": 3, "keep_days": 90},
        delete=[],
        deprecate=["Image-20250101", "Image-20250102"],
        keep=["Image-20250106", "Image-20250105", "Image-20250103"],
        skip=["Image-20250104"],
    ),
    # 4. test_keep_unexpired
    # No image expired, so nothing removed
    "unexpired": Scenario(
        region1=make_region_images(image_count_expired=0, image_count_unexpired=6),
        region2=make_region_images(image_count_expired=0, image_count_unexpired=6, missing=[4]),
        policy={"action": "deprecate", "keep": 3, "keep_days": 90},
        delete=[],
        deprecate=[],
        keep=[
            "Image-20250106",
            "Image-20250105",
            "Image-20250103",
            "Image-20250102",
            "Image-20250101",
        ],
        skip=["Image-20250104"],
    ),
}


@pytest.mark.parametrize("name, scenario", SCENARIOS.items(), ids=list(SCENARIOS))
@patch("ami_deprecation_tool.api._get_snapshot_ids", return_value=[])
@patch("ami_deprecation_tool.api.boto3")
def test_deprecation_scenarios(mock_boto, _snap, name: str, scenario: Scenario):
    # common boto plumbing
    base, r1, r2 = MagicMock(), MagicMock(), MagicMock()
    base.describe_regions.return_value = {"Regions": [{"RegionName": "region1"}, {"RegionName": "region2"}]}
    r1.describe_images.return_value = scenario.region1
    r2.describe_images.return_value = scenario.region2
    mock_boto.client.side_effect = [base, r1, r2]

    cfg = configmodels.ConfigModel(images={"image-20250101": scenario.policy}, options={})
    actions = api.deprecate(cfg, True)

    assert actions == expect(
        scenario.delete,
        scenario.deprecate,
        scenario.keep,
        scenario.skip,
        scenario.policy,
    )
