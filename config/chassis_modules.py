#!/usr/sbin/env python

import click
import time
import re
import subprocess
import utilities_common.cli as clicommon
from utilities_common.chassis import is_smartswitch, get_all_dpus, get_all_dpu_options, enable_dpu_passwordless_ssh, write_credentials, disable_dpu_passwordless_ssh, remove_password_file

TIMEOUT_SECS = 10


#
# 'chassis_modules' group ('config chassis_modules ...')
#
@click.group(cls=clicommon.AliasedGroup)
def chassis():
    """Configure chassis commands group"""
    pass

@chassis.group()
def modules():
    """Configure chassis modules"""
    pass


def get_config_module_state(db, chassis_module_name):
    config_db = db.cfgdb
    fvs = config_db.get_entry('CHASSIS_MODULE', chassis_module_name)
    if not fvs:
        if is_smartswitch():
            return 'down'
        else:
            return 'up'
    else:
        return fvs['admin_status']


#
# Name: check_config_module_state_with_timeout
# return: True: timeout, False: not timeout
#
def check_config_module_state_with_timeout(ctx, db, chassis_module_name, state):
    counter = 0
    while get_config_module_state(db, chassis_module_name) != state:
        time.sleep(1)
        counter += 1
        if counter >= TIMEOUT_SECS:
            ctx.fail("get_config_module_state {} timeout".format(chassis_module_name))
            return True
    return False


def get_asic_list_from_db(chassisdb, chassis_module_name):
    asic_list = []
    asics_keys_list = chassisdb.keys("CHASSIS_STATE_DB", "CHASSIS_FABRIC_ASIC_TABLE*")
    for asic_key in asics_keys_list:
        name = chassisdb.get("CHASSIS_STATE_DB", asic_key, "name")
        if name == chassis_module_name:
            asic_id = int(re.search(r"(\d+)$", asic_key).group())
            asic_list.append(asic_id)
    return asic_list


#
# Syntax: fabric_module_set_admin_status <chassis_module_name> <'up'/'down'>
#
def fabric_module_set_admin_status(db, chassis_module_name, state):
    chassisdb = db.db
    chassisdb.connect("CHASSIS_STATE_DB")
    asic_list = get_asic_list_from_db(chassisdb, chassis_module_name)

    if len(asic_list) == 0:
        return

    if state == "down":
        for asic in asic_list:
            click.echo("Stop swss@{} and peer services".format(asic))
            clicommon.run_command(['sudo', 'systemctl', 'stop', 'swss@{}.service'.format(asic)])

        is_active = subprocess.call(["systemctl", "is-active", "--quiet", "swss@{}.service".format(asic)])

        if is_active == 0:  # zero active,  non-zero, inactive
            click.echo("Stop swss@{} and peer services failed".format(asic))
            return

        click.echo("Delete related CAHSSIS_FABRIC_ASIC_TABLE entries")

        for asic in asic_list:
            chassisdb.delete("CHASSIS_STATE_DB", "CHASSIS_FABRIC_ASIC_TABLE|asic" + str(asic))

        # Start the services in case of the users just execute issue command "systemctl stop swss@/syncd@"
        # without bring down the hardware
        for asic in asic_list:
            # To address systemd service restart limit by resetting the count
            clicommon.run_command(['sudo', 'systemctl', 'reset-failed', 'swss@{}.service'.format(asic)])
            click.echo("Start swss@{} and peer services".format(asic))
            clicommon.run_command(['sudo', 'systemctl', 'start', 'swss@{}.service'.format(asic)])
    elif state == "up":
        for asic in asic_list:
            click.echo("Start swss@{} and peer services".format(asic))
            clicommon.run_command(['sudo', 'systemctl', 'start', 'swss@{}.service'.format(asic)])

#
# 'shutdown' subcommand ('config chassis_modules shutdown ...')
#
@modules.command('shutdown')
@clicommon.pass_db
@click.argument('chassis_module_name',
                metavar='<module_name>',
                required=True,
                type=click.Choice(get_all_dpus(), case_sensitive=False) if is_smartswitch() else str
                )
def shutdown_chassis_module(db, chassis_module_name):
    """Chassis-module shutdown of module"""
    config_db = db.cfgdb
    ctx = click.get_current_context()

    if not chassis_module_name.startswith("SUPERVISOR") and \
       not chassis_module_name.startswith("LINE-CARD") and \
       not chassis_module_name.startswith("FABRIC-CARD") and \
       not chassis_module_name.startswith("DPU"):
        ctx.fail("'module_name' has to begin with 'SUPERVISOR', 'LINE-CARD', 'FABRIC-CARD', 'DPU'")

    # Disable dpu passwordless ssh if enabled 
    disable_dpu_passwordless_ssh(chassis_module_name)

    # To avoid duplicate operation
    if get_config_module_state(db, chassis_module_name) == 'down':
        click.echo("Module {} is already in down state".format(chassis_module_name))
        return

    click.echo("Shutting down chassis module {}".format(chassis_module_name))
    fvs = {'admin_status': 'down'}
    config_db.set_entry('CHASSIS_MODULE', chassis_module_name, fvs)
    if chassis_module_name.startswith("FABRIC-CARD"):
        if not check_config_module_state_with_timeout(ctx, db, chassis_module_name, 'down'):
            fabric_module_set_admin_status(db, chassis_module_name, 'down')


#
# 'enable_passwordless_ssh' subcommand ('config chassis_modules enable_passwordless_ssh ...')
#
@modules.command('enable_passwordless_ssh')
@clicommon.pass_db
@click.argument('chassis_module_name',
                metavar='<module_name>',
                required=True,
                type=click.Choice(get_all_dpu_options(), case_sensitive=False) if is_smartswitch() else str
                )
@click.option('--username', prompt=False, help='The username for authentication')
@click.option('--password', prompt=False, hide_input=True, help='The password for authentication')
def enable_passwordless_ssh(db, chassis_module_name, username, password):
    """Enable passwordless SSH for DPUs"""
    if not is_smartswitch():
        return

    click.echo(f"Enabling dpu_passwordless_ssh for {chassis_module_name}")

    # Save username/password if provided
    if username and password:
        write_credentials(username, password)

    dpu_list = get_all_dpus()

    if chassis_module_name == 'all':
        for dpu in dpu_list:
            enable_dpu_passwordless_ssh(dpu)
    else:
        enable_dpu_passwordless_ssh(chassis_module_name)

@modules.command('disable_passwordless_ssh')
@clicommon.pass_db
@click.argument('chassis_module_name', metavar='<module_name>', required=True)
def disable_passwordless_ssh(db, chassis_module_name):
    """Disable passwordless SSH for DPUs"""
    if not is_smartswitch():
        return

    click.echo(f"Disabling passwordless SSH for {chassis_module_name}")

    dpu_list = get_all_dpus()

    if chassis_module_name == 'all':
        # If 'all' is specified, remove passwordless SSH from all DPUs and delete the password file
        click.echo("Disabling passwordless SSH for all DPUs and removing the password file...")
        for dpu in dpu_list:
            disable_dpu_passwordless_ssh(dpu)
        # Now remove the password file after disabling SSH for all DPUs
        remove_password_file()
    else:
        # Otherwise, disable passwordless SSH for the specific DPU
        disable_dpu_passwordless_ssh(chassis_module_name)
        click.echo(f"Passwordless SSH disabled for {chassis_module_name}")

#
# 'startup' subcommand ('config chassis_modules startup ...')
#
@modules.command('startup')
@clicommon.pass_db
@click.argument('chassis_module_name',
                metavar='<module_name>',
                required=True,
                type=click.Choice(get_all_dpus(), case_sensitive=False) if is_smartswitch() else str
                )
def startup_chassis_module(db, chassis_module_name):
    """Chassis-module startup of module"""
    config_db = db.cfgdb
    ctx = click.get_current_context()

    # To avoid duplicate operation
    if get_config_module_state(db, chassis_module_name) == 'up':
        click.echo("Module {} is already set to up state".format(chassis_module_name))
        return

    click.echo("Starting up chassis module {}".format(chassis_module_name))
    if is_smartswitch():
        fvs = {'admin_status': 'up'}
        config_db.set_entry('CHASSIS_MODULE', chassis_module_name, fvs)
    else:
        config_db.set_entry('CHASSIS_MODULE', chassis_module_name, None)

    if chassis_module_name.startswith("FABRIC-CARD"):
        if not check_config_module_state_with_timeout(ctx, db, chassis_module_name, 'up'):
            fabric_module_set_admin_status(db, chassis_module_name, 'up')
