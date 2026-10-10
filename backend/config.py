"""Semantta backend configuration."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass


DEFAULT_FUSEKI_DATASET_URL = "http://localhost:3030/obmms"
DEFAULT_FUSEKI_TIMEOUT = 120.0


@dataclass(frozen=True)
class FusekiConfig:
    """Configuration required to communicate with the Fuseki dataset."""

    dataset_url: str
    timeout: float


def load_fuseki_config() -> FusekiConfig:
    """Load Fuseki configuration from the environment."""
    dataset_url = os.getenv(
        "FUSEKI_DATASET_URL",
        DEFAULT_FUSEKI_DATASET_URL,
    ).rstrip("/")

    timeout_raw = os.getenv(
        "FUSEKI_TIMEOUT",
        str(DEFAULT_FUSEKI_TIMEOUT),
    )

    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = DEFAULT_FUSEKI_TIMEOUT

    if timeout <= 0:
        timeout = DEFAULT_FUSEKI_TIMEOUT

    return FusekiConfig(
        dataset_url=dataset_url,
        timeout=timeout,
    )


FUSEKI_CONFIG = load_fuseki_config()


def is_loopback_host(host: str) -> bool:
    """Return whether a host identifies a loopback address."""
    host = host.strip().lower()

    if host == "localhost":
        return True

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False

    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            address = address.ipv4_mapped

    return address.is_loopback