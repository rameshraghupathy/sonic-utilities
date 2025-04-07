import os
import sys
import paramiko
from sonic_py_common import device_info
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from copy_ssh_key import copy_ssh_key, remove_ssh_key_from_dpu
from swsscommon.swsscommon import SonicV2Connector

PASSWORD_FILE = "/usr/share/sonic/device/x86_64-8102_28fh_dpu_o-r0/dpupassword"

def write_credentials(username, password, append=True):
    """Write username and password to the password file.

    - If `append` is False (default), it **replaces** the existing file.
    - If `append` is True, it **adds** the new credentials to the file.
    """

    mode = "a" if append else "w"  # 'a' for append, 'w' for replace
    try:
        with open(PASSWORD_FILE, mode) as f:
            f.write(f"{username}\n{password}\n")

        # Set strict permissions (owner read/write only) only when replacing
        if not append:
            os.chmod(PASSWORD_FILE, 0o600)

        action = "Appended" if append else "Saved"
        # print(f"{action} credentials to {PASSWORD_FILE}")

    except Exception as e:
        print(f"Failed to write credentials: {e}", err=True)

def get_module_ip(module):
    """Get modulIe ip from module name"""
    db = SonicV2Connector(host='127.0.0.1')
    db.connect(db.STATE_DB, False) 
    key =  "CHASSIS_MIDPLANE_TABLE|" + module
    # return db.hget(db.STATE_DB, key, "ip_address")
    ip = db.get(db.STATE_DB, key, "ip_address")
    key =  "CHASSIS_MODULE_TABLE|" + module
    state = db.get(db.STATE_DB, key, "oper_status")
    if state == "Offline":
        print(f"{ip} is {state}")
        ip = None
    return ip 

def disable_dpu_passwordless_ssh(dpu):
    """Disable passwordless SSH for a specific DPU by removing its SSH key"""
    # Assuming `get_dpu_ip()` retrieves the IP address of the DPU
    ip = get_module_ip(dpu)
    # Remove the SSH key from the DPU
    if get_passwordless_ssh_state(ip) == 'Enabled':
        remove_ssh_key_from_dpu(ip)

def remove_password_file():
    """Remove the password file used for SSH authentication"""
    
    try:
        os.remove(PASSWORD_FILE)
        print("Password file removed successfully.")
    except Exception as e:
        click.echo(f"Error while removing password file: {str(e)}")

def enable_dpu_passwordless_ssh(module):
    """Enable passwordless SSH on a given DPU."""
    ip = get_module_ip(module)
    if ip:
        copy_ssh_key(ip)

def read_password_from_file():
    """Read the password from the password file."""
    if not os.path.exists(PASSWORD_FILE):
        # print(f'File not found {PASSWORD_FILE}')
        return None

    with open(PASSWORD_FILE, "r") as f:
        passwords = f.readlines()

    # Try each password and return the first successful one (or handle accordingly)
    for password in passwords:
        password = password.strip()
        if password:  # Ensure non-empty passwords are used
            return password

    raise Exception("No valid password found in the file.")

def get_passwordless_ssh_state(ip):
    """Get if passwordless SSH is enabled on the given DPU."""
    # Assuming the DPU's IP address can be obtained with the dpu variable, if not, replace with the IP
    username = "admin"  # Adjust as necessary if username differs
    password = read_password_from_file()  # Function to read the password from your password file

    # Try SSH connection
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # SSH to the DPU
        client.connect(ip, username=username, password=password, timeout=10)

        # Check if authorized_keys file exists
        stdin, stdout, stderr = client.exec_command('test -f ~/.ssh/authorized_keys && echo "exists" || echo "not found"')
        result = stdout.read().decode().strip()

        client.close()

        if result == "exists":
            return "Enabled"  # Passwordless SSH is enabled
        else:
            return "Disabled"  # Passwordless SSH is not enabled
    except Exception as e:
        # print(f"Error checking passwordless SSH state for DPU {ip}: {e}")
        return "Disabled"  # Handle error case if SSH connection fails

def get_chassis_local_interfaces():
    lst = []
    platform = device_info.get_platform()
    chassisdb_conf=os.path.join('/usr/share/sonic/device/', platform, "chassisdb.conf")
    if os.path.exists(chassisdb_conf):
        lines=[]
        with open(chassisdb_conf, 'r') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            if "chassis_internal_intfs" in line:
                data = line.split("=")
                lst = data[1].split(",")
                return lst
    return lst


def is_smartswitch():
    return hasattr(device_info, 'is_smartswitch') and device_info.is_smartswitch()


def is_dpu():
    return hasattr(device_info, 'is_dpu') and device_info.is_dpu()


# Utility to get the number of DPUs
def get_num_dpus():
    if hasattr(device_info, 'get_num_dpus'):
        return device_info.get_num_dpus()
    return 0


# utility to get dpu module name list
def get_all_dpus():
    try:
        # Convert the entries in the list to uppercase
        return [dpu.upper() for dpu in device_info.get_dpu_list()]
    except Exception:
        return []


# utility to get dpu module name list and all
def get_all_dpu_options():
    dpu_list = get_all_dpus()

    # Add 'all' to the list
    dpu_list += ['all']

    return dpu_list
