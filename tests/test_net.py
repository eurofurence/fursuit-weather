"""The optional IP-family pin.

Nothing here goes near the network: ``resolves`` is stubbed, because a test
that depended on what DNS answers today would fail on any machine behind a
resolver that behaves differently -- which is the whole class of problem this
feature exists to diagnose.
"""

from __future__ import annotations

import socket

import pytest
from urllib3.util import connection as urllib3_connection

from app import net
from app.config import Settings, load_settings


@pytest.fixture(autouse=True)
def restore_family():
    """Leave the process the way we found it: the pin is a global."""
    yield
    net.apply_ip_family("auto")


@pytest.mark.parametrize(
    "given, expected",
    [
        ("auto", "auto"),
        ("ipv4", "ipv4"),
        ("IPv6", "ipv6"),
        ("  IPV4  ", "ipv4"),
        ("v6", "ipv6"),
        ("6", "ipv6"),
        ("inet", "ipv4"),
        (None, "auto"),
        ("", "auto"),
        ("carrier pigeon", "auto"),
    ],
)
def test_normalise(given, expected):
    assert net.normalise(given) == expected


def test_auto_leaves_urllib3_alone():
    net.apply_ip_family("auto")
    assert urllib3_connection.allowed_gai_family is net._original_allowed_gai_family
    assert net.applied() == "auto"


@pytest.mark.parametrize(
    "family, af",
    [("ipv4", socket.AF_INET), ("ipv6", socket.AF_INET6)],
)
def test_pin_sets_the_address_family(family, af):
    net.apply_ip_family(family)
    assert net.applied() == family
    # This is the value urllib3 hands getaddrinfo, so it is the whole mechanism.
    assert urllib3_connection.allowed_gai_family() == af


def test_pin_is_reversible():
    net.apply_ip_family("ipv6")
    net.apply_ip_family("auto")
    assert urllib3_connection.allowed_gai_family is net._original_allowed_gai_family


def test_bad_value_does_not_pin_anything():
    net.apply_ip_family("ipv6")
    net.apply_ip_family("nonsense")
    assert net.applied() == "auto"
    assert urllib3_connection.allowed_gai_family is net._original_allowed_gai_family


def test_preflight_is_silent_under_auto(monkeypatch):
    called = []
    monkeypatch.setattr(net, "resolves", lambda host, family: called.append(host) or True)
    net.apply_ip_family("auto")
    assert net.preflight() == {}
    assert not called, "auto should cost no lookups at all"


def test_preflight_reports_each_host(monkeypatch):
    monkeypatch.setattr(net, "resolves", lambda host, family: host != "maps.dwd.de")
    net.apply_ip_family("ipv6")
    assert net.preflight(["opendata.dwd.de", "maps.dwd.de"]) == {
        "opendata.dwd.de": True,
        "maps.dwd.de": False,
    }


def test_preflight_warns_when_a_host_has_no_address(monkeypatch, caplog):
    """The case that prompted all of this: IPv6 pinned, DWD publishing only A."""
    monkeypatch.setattr(net, "resolves", lambda host, family: False)
    net.apply_ip_family("ipv6")
    with caplog.at_level("ERROR", logger="app.net"):
        net.preflight(["opendata.dwd.de"])
    assert "AAAA" in caplog.text
    assert "DNS64/NAT64" in caplog.text


def test_resolves_never_raises(monkeypatch):
    def boom(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    assert net.resolves("nowhere.invalid", "ipv6") is False


# --------------------------------------------------------------------- config


def test_network_defaults_are_the_old_behaviour():
    settings = Settings()
    assert settings.network.ip_family == "auto"
    assert settings.network.bind_host == "0.0.0.0"


def test_network_can_be_set_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("EFW_IP_FAMILY", "ipv6")
    monkeypatch.setenv("EFW_BIND_HOST", "::")
    settings = load_settings(tmp_path / "does-not-exist.json")
    assert settings.network.ip_family == "ipv6"
    assert settings.network.bind_host == "::"


def test_network_can_be_set_from_the_config_file(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"network": {"ip_family": "ipv4"}}', encoding="utf-8")
    settings = load_settings(config)
    assert settings.network.ip_family == "ipv4"
    # Untouched keys keep their default rather than being dropped by the merge.
    assert settings.network.bind_host == "0.0.0.0"
