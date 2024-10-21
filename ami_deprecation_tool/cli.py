import logging
import sys

import click
import yaml
from botocore.exceptions import ClientError
from pydantic import ValidationError

from . import api
from .configmodels import ConfigModel


@click.command()
@click.option(
    "-p",
    "--policy",
    "policy_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="path to yaml config file.",
)
@click.option(
    "-v",
    "log_level",
    count=True,
    help="Set log verbosity. The default log level is WARNING. '-v' will set to INFO and '-vv' will set to DEBUG",
)
@click.option(
    "--dry-run/--no-dry-run",
    "dry_run",
    default=True,
    help="Prevent deprecation, only log intended actions (default=True)",
)
def deprecate(policy_path, log_level, dry_run):
    _setup_logging(log_level)
    config = _load_policy(policy_path)
    try:
        api.deprecate(config, dry_run)
    except ClientError as e:
        sys.exit(e)


def _load_policy(policy_path: str) -> ConfigModel:
    with open(policy_path) as fh:
        config = yaml.safe_load(fh)
    try:
        return ConfigModel(**config)
    except ValidationError as e:
        sys.exit(e.json())


def _setup_logging(log_level: int) -> None:
    root_logger = logging.getLogger()
    log_formatter = logging.Formatter("%(asctime)s:%(name)s:%(levelname)s:%(message)s")

    # Set log level by verbosity (stop at 10/DEBUG to avoid accidentally using NOTSET)
    root_logger.setLevel(max(30 - (10 * log_level), 10))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)

    root_logger.addHandler(console_handler)
