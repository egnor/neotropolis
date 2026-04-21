#!/usr/bin/env python3
"""Machine setup for trashbot/trashbase Pi"""

import asyncclick as click
import logging
import ok_logging_setup
import ok_subprocess_defaults
import pathlib
import platform
import re
import textwrap


REPO_PATH = pathlib.Path(__file__).parent.parent


@click.command()
@click.option("--bot", is_flag=True)
@click.option("--base", is_flag=True)
def main(bot, base):
    ok_logging_setup.install()
    sub = ok_subprocess_defaults.SubprocessDefaults()
    reboot_required = False

    if bot and base:
        raise click.ClickException("Set only one of --bot or --base")
    if not (bot or base):
        node = platform.node().split(".")[0]
        bot, base = (node == "trashbot"), (node == "trashbase")
        if not (bot or base):
            raise click.ClickException("Set --bot or --base")

    #
    # apt packages
    #

    apt_needed = ["build-essential"]
    apt_needed.extend(["libusb-1.0-0-dev", "libhidapi-libusb0"] if base else [])

    logging.info("🎁 Checking apt packages...")
    apt_query = ["dpkg-query", "--show", "--showformat=${Package}\\n"]
    if apt_missing := set(apt_needed) - set(sub.stdout_lines(*apt_query)):
        sub.run("sudo", "apt", "install", "-y", *apt_missing)

    #
    # kernel command line arguments
    #

    boot_line_path = pathlib.Path("/boot/firmware/cmdline.txt")
    logging.info("🥾 Checking boot args: %s", boot_line_path)
    boot_line = boot_line_path.read_text().strip()
    arg_rx = re.compile(r'([\w.-]+(?:=("[^"]*")+|=[^"\s]*)?(?![^\s]))\s*|(.)')
    boot_args = [m[1] for m in re.finditer(arg_rx, boot_line)]
    if not all(boot_args):
        ok_logging_setup.exit(f"Can't parse boot args: {boot_args}")

    if bot:  # lock down video modes
        boot_args = [
            *(a for a in boot_args if not a.startswith("video=")),
            *["video=HDMI-A-1:1024x768MR@30e", "video=HDMI-A-2:1024x768MR@30e"],
        ]

    if (new_boot := " ".join(boot_args)) != boot_line:
        sub.run("sudo", "tee", boot_line_path, input=new_boot, encoding="utf8")
        print()  # boot line has no trailing newline
        reboot_required = True

    #
    # screen layout config via Kanshi
    # https://gitlab.freedesktop.org/emersion/kanshi
    # Kanshi is started by default on Pi OS (/etc/xdg/labwc/autostart)
    #

    kanshi_config = None
    if bot:
        # Place displays in a consistent position
        # Note, both displays are forced on with "...@30e" kernel modes above
        serials = [
            "JZI Beetronics bee0097-73092",
            "JZI BEETRONICS bee0097-63090",
        ]
        kanshi_config = textwrap.dedent(f"""
            profile {{
                output "{serials[0]}" position 0,0
                output "{serials[1]}" position 1024,0
            }}
        """).lstrip()

    if kanshi_config:
        kanshi_config_path = pathlib.Path.home() / ".config/kanshi/config"
        kanshi_config_path.parent.mkdir(parents=True, exist_ok=True)
        logging.info("🖥️ Setting screen layout: %s", kanshi_config_path)
        kanshi_config_path.write_text(kanshi_config)

    #
    # sundry system config files
    #

    config_files: dict[str, str] = {}
    if base:
        config_files["/etc/udev/rules.d/10-streamdeck.rules"] = (
            'SUBSYSTEMS=="usb", ATTRS{idVendor}=="0fd9", '
            'GROUP="users", TAG+="uaccess"\n'
        )

    updated: set[str] = set()
    for path_str, contents in config_files.items():
        path = pathlib.Path(path_str)
        logging.info("⚙️ Checking %s", path_str)
        if not (path.is_file() and path.read_text() == contents):
            sub.run("sudo", "tee", path, input=contents, encoding="utf8")
            updated.add(path_str)

    if any(p.startswith("/etc/udev") for p in updated):
        sub.run("sudo", "udevadm", "control", "--reload-rules")

    #
    # systemd services (runs last after everything else is set up)
    #
    # The bot service is a *user* unit so it inherits the desktop session's
    # Wayland/XDG environment (it drives Wayland-backed "eye" displays).
    # It starts/stops with the pi console autologin session; without a
    # compositor there's no display to drive anyway.
    #

    service_name = None
    if bot:
        service_name = "trashbot.service"

    if service_name:
        source_unit_path = REPO_PATH / service_name
        user_unit_path = (
            pathlib.Path.home() / ".config/systemd/user" / service_name
        )

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
