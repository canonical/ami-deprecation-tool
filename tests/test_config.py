# from unittest.mock import MagicMock, call, patch

import pytest

from ami_deprecation_tool import configmodels


@pytest.mark.parametrize(
    "config,expected_exec_users,expected_deprecated,expected_disabled",
    [
        ({}, [], False, False),
        ({"include_deprecated": True, "include_disabled": False}, [], True, False),
        ({"include_deprecated": False, "include_disabled": True}, [], False, True),
        ({"executable_users": ["all"]}, ["all"], False, False),
        ({"executable_users": ["123", "456", "789"]}, ["123", "456", "789"], False, False),
        ({"executable_users": ["self"], "include_deprecated": True, "include_disabled": True}, ["self"], True, True),
    ],
)
def test_config_options(
    config,
    expected_exec_users,
    expected_deprecated,
    expected_disabled,
):
    options = configmodels.ConfigOptionsModel(**config)
    assert options.executable_users == expected_exec_users
    assert options.include_disabled == expected_disabled
    assert options.include_deprecated == expected_deprecated
