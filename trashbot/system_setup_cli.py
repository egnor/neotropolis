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
def main(base, bot, desk):
    ok_logging_setup.install()
    sub = ok_subprocess_defaults.SubprocessDefaults()

    if (base + bot + desk) > 1:
        raise click.ClickException("Set only one of --base, --bot, or --desk")
    if not (base or bot or desk):
        node = platform.node().split(".")[0]
        base, bot = (node == "trashbase"), (node == "trashbot")
        if not (base or bot):
            raise click.ClickException("Set one of --base, --bot, or --desk")

    reboot_required = False

    #
    # apt packages
    #

    apt_needed = ["build-essential", "libusb-1.0-0-dev", "libhidapi-libusb0"]
    udev_restart_required = False

    logging.info("🎁 Checking apt packages...")
    apt_query = ["dpkg-query", "--show", "--showformat=${Package}\\n"]
    if apt_missing := set(apt_needed) - set(sub.stdout_lines(*apt_query)):
        sub.run("sudo", "apt", "install", "-y", *apt_missing)

    #
    # kernel command line arguments
    #

    if base or bot:
        boot_line_path = Path("/boot/firmware/cmdline.txt")
        logging.info("🥾 Checking boot args: %s", boot_line_path)
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

        if (new_boot := " ".join(boot_args)) != boot_line:
            tee_command = ["sudo", "tee", boot_line_path]
            sub.run(*tee_command, input=new_boot, encoding="utf8")
            print()  # boot line has no trailing newline
            reboot_required = True

    #
    # sundry system config files
    #

    config_files = {
        Path("/etc/udev/rules.d/10-streamdeck.rules"): (
            'SUBSYSTEMS=="usb", ATTRS{idVendor}=="0fd9", '
            'GROUP="users", TAG+="uaccess"\n'
        )
    }

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

        status_lines = sub.stdout_lines(
            "systemctl", "--user", "show", service_name
        )
        if "ActiveState=active" not in status_lines:
            sub.run("systemctl", "--user", "restart", service_name)

    #
    # All done
    #

    if reboot_required:
        logging.info("\n🚨 REBOOT REQUIRED to finish setup\n")
    else:
        logging.info("\n🏁 Done with system setup\n")
