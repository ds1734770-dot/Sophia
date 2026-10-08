import winreg

import pytest

from app.computer.autostart import Autostart, default_command

TEST_KEY = r"Software\SophiaTests\Run"


@pytest.fixture
def autostart():

    item = Autostart(key_path=TEST_KEY, name="SophiaTest", command='"x.exe" --minimized')

    yield item

    item.disable()

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\SophiaTests")

    except OSError:
        pass


def test_enable_and_disable(autostart):

    assert not autostart.is_enabled()

    autostart.set_enabled(True)
    assert autostart.is_enabled()

    autostart.set_enabled(False)
    assert not autostart.is_enabled()


def test_disable_when_not_enabled_is_harmless(autostart):

    autostart.disable()

    assert not autostart.is_enabled()


def test_default_command_points_at_main_and_starts_minimized():

    command = default_command()

    assert "main.py" in command
    assert command.endswith("--minimized")
