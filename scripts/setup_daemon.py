
import os
import sys
from pathlib import Path

def create_systemd_service():
    """Generates a systemd service file for Genesis Guardian"""
    
    current_user = os.getlogin()
    home_dir = str(Path.home())
    working_dir = f"{home_dir}/Genesis"
    exec_path = sys.executable
    script_path = f"{working_dir}/genesis_daemon.py"
    
    service_content = f"""[Unit]
Description=Genesis Guardian Daemon
After=network.target

[Service]
Type=simple
User={current_user}
WorkingDirectory={working_dir}
ExecStart={exec_path} {script_path}
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    
    service_path = Path(f"{home_dir}/.config/systemd/user/genesis-guardian.service")
    service_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(service_path, "w") as f:
        f.write(service_content)
        
    print(f"✅ Systemd service file created at: {service_path}")
    print("\nTo enable and start:")
    print("  systemctl --user daemon-reload")
    print("  systemctl --user enable --now genesis-guardian.service")
    print("  systemctl --user status genesis-guardian.service")
    print("\nTo view logs:")
    print(f"  tail -f {home_dir}/.nanogenesis/guardian.log")

if __name__ == "__main__":
    create_systemd_service()
