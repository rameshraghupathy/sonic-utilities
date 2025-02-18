import paramiko
import os

PASSWORD_FILE = "/usr/share/sonic/device/x86_64-8102_28fh_dpu_o-r0/dpupassword"
SSH_KEY_FILE = os.path.expanduser("~/.ssh/id_rsa.pub")

def read_credentials():
    """Read the username-password pairs from the credentials file."""
    credentials = []
    try:
        with open(PASSWORD_FILE, "r") as f:
            lines = [line.strip() for line in f.readlines()]
            for i in range(0, len(lines), 2):  # Read in (username, password) pairs
                if i + 1 < len(lines):
                    credentials.append((lines[i], lines[i + 1]))
    except Exception as e:
        print(f"Error reading {PASSWORD_FILE}: {e}")
    return credentials


def copy_ssh_key(server_ip):
    """Attempt to copy SSH key using multiple username-password pairs."""
    credentials = read_credentials()

    if not os.path.exists(SSH_KEY_FILE):
        print("SSH key not found. Generating a new key...")
        os.system("ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ''")

    # Read the public key
    with open(SSH_KEY_FILE, "r") as f:
        public_key = f.read().strip()

    # print(f"Copying SSH key to {server_ip}...")

    for username, password in credentials:
        try:
            # print(f"Trying with username:{username}   password: {password}")

            # Establish SSH connection
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(server_ip, username=username, password=password, timeout=10)

            # Append key to authorized_keys
            cmd = (
                f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && '
                f'echo "{public_key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
            )
            stdin, stdout, stderr = client.exec_command(cmd)
            stdout.channel.recv_exit_status()  # Wait for command to complete

            print(f"SSH key successfully copied to {server_ip} using {username}.")
            client.close()
            return True  # Stop trying if successful

        except Exception as e:
            # print(f"Failed with {username}: {e}")
            pass

    print(f"All authentication attempts failed for {server_ip}.")
    return False  # If none of the credentials worked, return failure

def remove_ssh_key_from_dpu(ip):
    """Remove the SSH key from the DPU's authorized_keys file"""
    try:
        # Retrieve the username and password for SSH login
        credentials = read_credentials()
        # Create an SSH client object
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        for username, password in credentials:
            # Connect to the DPU using the provided credentials
            ssh.connect(ip, username=username, password=password)

            # Command to remove the SSH key from the authorized_keys file
            remove_command = "sed -i '/ssh-rsa/d' ~/.ssh/authorized_keys"
            stdin, stdout, stderr = ssh.exec_command(remove_command)

            error = stderr.read().decode().strip()
            ssh.close()

            if error:
                print(f"Error removing SSH key from DPU {ip}: {error}")
            else:
                break

    except Exception as e:
        print(f"Error while removing SSH key from DPU {ip}: {str(e)}")


# Only execute when run as a script
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <server_ip>")
        sys.exit(1)

    server_ip = sys.argv[1]
    success = copy_ssh_key(server_ip)
    sys.exit(0 if success else 1)
