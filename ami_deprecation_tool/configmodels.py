from typing import Literal

from pydantic import BaseModel, Field


class ConfigPolicyModel(BaseModel):
    """
    Deprecation policy Configuration
    """

    action: Literal["delete", "deprecate"] = Field(
        description="The action to be performed on AMIs that are out of policy"
    )
    keep: int = Field(description="The number of AMIs to exempt from the policy")
    keep_days: int = Field(description="How many days to exempt AMIs from the policy", default=0)


class ConfigOptionsModel(BaseModel):
    """
    Tool configuration model
    """

    executable_users: list[str] = Field(
        default=[],
        description=(
            "List of accounts with run permissions. Special values 'self' and"
            " 'all' are permitted. An empty list will allow all"
            " configurations."
        ),
    )
    include_deprecated: bool = Field(default=False, description=("Include deprecated images in policy application"))
    include_disabled: bool = Field(default=False, description=("Include disabled images in policy application"))


class ConfigModel(BaseModel):
    """
    The base model for configuration
    """

    options: ConfigOptionsModel
    images: dict[str, ConfigPolicyModel]
