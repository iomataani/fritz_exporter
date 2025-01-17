from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import attrs
import yaml
from attrs import converters, define, field, validators

from fritzexporter.fritzdevice import FRITZ_MAX_PASSWORD_LENGTH

from .exceptions import (
    ConfigError,
    ConfigFileUnreadableError,
    EmptyConfigError,
    FritzPasswordTooLongError,
    NoDevicesFoundError,
)

logger = logging.getLogger("fritzexporter.config")


def _read_config_file(config_file_path: str) -> dict:
    try:
        with Path(config_file_path).open() as config_file:
            config = yaml.safe_load(config_file)
    except OSError as e:
        logger.exception("Config file specified but could not be read.")
        raise ConfigFileUnreadableError from e
    logger.info("Read configuration from %s.", config_file_path)

    return config


def _read_config_from_env() -> dict:
    if not all(required in os.environ for required in ["FRITZ_USERNAME", "FRITZ_PASSWORD"]):
        logger.critical("Required env variables missing (FRITZ_USERNAME, FRITZ_PASSWORD)!")
        msg = "Required env variables missing (FRITZ_USERNAME, FRITZ_PASSWORD)!"
        raise ConfigError(msg)

    exporter_port = os.getenv("FRITZ_PORT")
    log_level = os.getenv("FRITZ_LOG_LEVEL")

    hostname = os.getenv("FRITZ_HOSTNAME")
    name: str = os.getenv("FRITZ_NAME", "Fritz!Box")
    username = os.getenv("FRITZ_USERNAME")
    password = os.getenv("FRITZ_PASSWORD")
    host_info: str = os.getenv("FRITZ_HOST_INFO", "False")

    config: dict[Any, Any] = {}
    if exporter_port:
        config["exporter_port"] = exporter_port
    if log_level:
        config["log_level"] = log_level

    config["devices"] = []
    device = {
        "username": username,
        "password": password,
        "host_info": host_info,
        "name": name,
    }
    if hostname:
        device["hostname"] = hostname
    config["devices"].append(device)

    logger.info("No configuration file specified: configuration read from environment")

    return config


def get_config(config_file_path: str | None) -> ExporterConfig:
    config = _read_config_file(config_file_path) if config_file_path else _read_config_from_env()
    return ExporterConfig.from_config(config)


@define
class ExporterConfig:
    exporter_port: int = field(
        default=9787,
        validator=[
            validators.instance_of(int),
            validators.ge(1024),
            validators.le(65535),
        ],
        converter=int,
    )
    log_level: str = field(
        default="INFO", validator=validators.in_(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    )
    devices: list[DeviceConfig] = field(factory=list)

    @devices.validator
    def check_devices(self, _: attrs.Attribute, value: list[DeviceConfig]) -> None:
        if value in [None, []]:
            logger.exception("No devices found in config.")
            msg = "No devices found in config."
            raise NoDevicesFoundError(msg)
        devicenames = [dev.name for dev in value]
        if len(devicenames) != len(set(devicenames)):
            logger.warning("Device names are not unique")

    @classmethod
    def from_config(cls, config: dict) -> ExporterConfig:
        if config is None:
            logger.exception("No config found (check Env vars or config file).")
            msg = "No config found (check Env vars or config file)."
            raise EmptyConfigError(msg)

        exporter_port = config.get("exporter_port", 9787)
        log_level = config.get("log_level", "INFO")
        devices: list[DeviceConfig] = [
            DeviceConfig.from_config(dev) for dev in config.get("devices", [])
        ]

        return cls(exporter_port=exporter_port, log_level=log_level, devices=devices)


@define
class DeviceConfig:
    hostname: str = field(validator=validators.min_len(1), converter=lambda x: str.lower(x))
    username: str = field(validator=validators.min_len(1))
    password: str = field(validator=validators.min_len(1))
    name: str = ""
    host_info: bool = field(default=False, converter=converters.to_bool)

    @password.validator
    def check_password(self, _: attrs.Attribute, value: str) -> None:
        if len(value) > FRITZ_MAX_PASSWORD_LENGTH:
            logger.exception(
                "Password is longer than 32 characters! "
                "Login may not succeed, please see documentation!"
            )
            raise FritzPasswordTooLongError

    @classmethod
    def from_config(cls, device: dict) -> DeviceConfig:
        hostname = device.get("hostname", "fritz.box")
        username = device.get("username", "")
        password = device.get("password", "")
        name = device.get("name", "")
        host_info = device.get("host_info", False)

        return cls(
            hostname=hostname,
            username=username,
            password=password,
            name=name,
            host_info=host_info,
        )
