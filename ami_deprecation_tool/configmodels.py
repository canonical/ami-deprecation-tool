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


class ConfigModel(BaseModel):
    """
    The base model for configuration
    """

    images: dict[str, ConfigPolicyModel]
