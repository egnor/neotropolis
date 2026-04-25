#!/usr/bin/env python3
"""Machine setup for trashbot/trashbase/test computers"""

import asyncclick as click
import logging
import ok_logging_setup
import ok_subprocess_defaults
import platform
import re
import textwrap
from pathlib import Path


REPO_PATH = Path(__file__).parent.parent


@click.command()
@click.option("--base", is_flag=True)
@click.option("--bot", is_flag=True)
@click.option("--desk", is_flag=True)
def main(base: bool, bot: bool, desk: bool) -> None:
    ok_logging_setup.install()
    sub = ok_subprocess_defaults.SubprocessDefaults()

    if (base + bot + desk) > 1:
        raise click.ClickException("Set only one of --base, --bot, or --desk")
    if not (base or bot or desk):
        node = platform.node().split(".")[0]
        base, bot = (node == "trashbase"), (node == "trashbot")
        if not (base or bot):
            raise click.ClickException("Set one of --base, --bot, or --desk")

    config_files: dict[Path, str] = {}
    reboot_required = False

    #
    # apt packages
    #

    logging.info("🎁 Checking apt packages...")
    apt_needed = ["build-essential", "libusb-1.0-0-dev", "libhidapi-libusb0"]
    apt_query = ["dpkg-query", "--show", "--showformat=${Package}\\n"]
    if apt_missing := set(apt_needed) - set(sub.stdout_lines(*apt_query)):
        sub.run("sudo", "apt", "install", "-y", *apt_missing)

    #
    # kernel command line arguments
    #

    if base or bot:
        boot_line_path = Path("/boot/firmware/cmdline.txt")
        boot_line = boot_line_path.read_text().strip()
        arg_rx = re.compile(r'([\w.-]+(=("[^"]*")+|=[^"\s]*)?(?![^\s]))\s*|(.)')
        boot_args = [m[1] for m in re.finditer(arg_rx, boot_line)]
        if not all(boot_args):
            ok_logging_setup.exit(f"Can't parse boot args: {boot_args}")

        if bot:  # lock down video modes
            boot_args = [
                *(a for a in boot_args if not a.startswith("video=")),
                *[f"video=HDMI-A-{n}:1024x768MR@30e" for n in (1, 2)],
            ]

        config_files[boot_line_path] = " ".join(boot_args)

    #
    # /boot/firmware/config.txt managed block
    #

    config_add = ""
    if bot:
        config_add += textwrap.dedent("""
            # SPI0 for WS281x addressable LED strip (/dev/spidev0.0, GPIO 10)
            dtparam=spi=on
            # UART0 on GPIO 14/15 for ELRS RX (requires disabling Bluetooth)
            dtoverlay=disable-bt
            dtoverlay=uart0-pi5
        """).lstrip()

    if bot or base:
        config_add += textwrap.dedent("""
            # Lift USB port current limit (for powered peripherals)
            usb_max_current_enable=1
        """).lstrip()

    if config_add:
        tag = "trashbot" if bot else "trashbase"
        before = f"# BEGIN managed by system_setup_cli.py ({tag})\n[all]\n"
        after = "# END managed by system_setup_cli.py\n"
        managed_block = before + config_add + after

        # Strip any previous managed block before re-appending.
        old_block_rx = re.compile(
            r"# BEGIN managed by system_setup_cli\.py[^\n]*\n"
            r".*?"
            r"# END managed by system_setup_cli\.py[^\n]*\s*",
            re.DOTALL,
        )

        config_txt_path = Path("/boot/firmware/config.txt")
        original = config_txt_path.read_text()
        new_text = old_block_rx.sub("", original) + managed_block
        config_files[config_txt_path] = new_text

    #
    # other config files
    #

    # udev rule for StreamDeck
    config_files[Path("/etc/udev/rules.d/10-streamdeck.rules")] = (
        'SUBSYSTEMS=="usb", ATTRS{idVendor}=="0fd9",'
        ' GROUP="users", TAG+="uaccess"\n'
    )

    # udev rule for ODrive
    config_files[Path("/etc/udev/rules.d/91-odrive.rules")] = (
        'SUBSYSTEM=="usb", ATTR{idVendor}=="1209", ATTR{idProduct}=="0d3[0-9]",'
        ' MODE="0666", ENV{ID_MM_DEVICE_IGNORE}="1"\n'
        'SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="df11",'
        ' MODE="0666"\n'
    )

    if bot:
        # Kanshi is started by default on Pi OS (/etc/xdg/labwc/autostart)
        # Note, both displays are forced on with "...@30e" kernel modes above
        kanshi_config_path = Path.home() / ".config/kanshi/config"
        config_files[kanshi_config_path] = textwrap.dedent("""
            profile {
                output "JZI Beetronics bee0097-73092" position 0,0
                output "JZI BEETRONICS bee0097-63090" position 1024,0
            }
        """).lstrip()

    #
    # update system config files
    #

    udev_restart_required = False
    for path, contents in config_files.items():
        logging.info("⚙️ Checking %s", path)
        if not (path.is_file() and path.read_text() == contents):
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents)
                logging.info("✏️ Updated %s", path)
            except PermissionError:
                if not path.parent.is_dir():
                    sub.run("sudo", "mkdir", "-p", path.parent)
                sub.run("sudo", "tee", path, input=contents, encoding="utf8")

            reboot_required |= Path("/boot") in path.parents
            udev_restart_required |= Path("/etc/udev") in path.parents

    if udev_restart_required:
        sub.run("sudo", "udevadm", "control", "--reload-rules")

    #
    # systemd services (runs last after everything else is set up)
    #
    # The bot service is a *user* unit so it inherits the desktop session's
    # Wayland/XDG environment (it drives Wayland-backed "eye" displays).
    # It starts/stops with the pi console autologin session; without a
    # compositor there's no display to drive anyway.
    #

    if base:
        service_name = "trashbase.service"
    elif bot:
        service_name = "trashbot.service"
    else:
        service_name = None

    if service_name:
        source_unit_path = REPO_PATH / service_name
        user_unit_path = Path.home() / ".config/systemd/user" / service_name

        logging.info("⚙️ Checking user systemd unit: %s", service_name)
        if user_unit_path.resolve() != source_unit_path:
            sub.run("systemctl", "--user", "enable", source_unit_path)

        # always run this just in case things changed
        sub.run("systemctl", "--user", "daemon-reload")

        status_command = ["systemctl", "--user", "show", service_name]
        status_lines = sub.stdout_lines(*status_command)
        if "ActiveState=active" not in status_lines:
            sub.run("systemctl", "--user", "restart", service_name)

    #
    # All done
    #

    if reboot_required:
        logging.info("\n🚨 REBOOT REQUIRED to finish setup\n")
    else:
        logging.info("\n🏁 Done with system setup\n")
