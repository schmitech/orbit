# Setting up Chroma as a Systemd Service

This guide explains how to set up Chroma Vector Database as a systemd service that automatically starts when your server boots.

# Install python3-venv if not already installed
```bash
sudo apt install python3-venv
```

# Create a new virtual environment
```bash
python3 -m venv venv
```

# Activate the virtual environment
```bash
source myenv/bin/activate
```

# Now you can safely install packages
```bash
pip install -r requirements.txt
```

## 1. Create the Service File

Create a new systemd service file using:

```bash
sudo vim /etc/systemd/system/chroma.service
```

Add the following content:

```bash
[Unit]
Description=Chroma Vector Database Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/bin/bash -c 'source myenv/bin/activate && chroma run --host 0.0.0.0 --port 8000 --path ./chroma_db'
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Make sure to replace:
- `User=ubuntu` with your system username if different
- `WorkingDirectory=/home/ubuntu` with the path where your virtual environment is located
- Adjust the path in `myenv/bin/activate` if your virtual environment has a different name

## 2. Enable and Start the Service

After creating the service file, run these commands:

```bash
# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable chroma

# Start the service
sudo systemctl start chroma

# Check the status
sudo systemctl status chroma
```

## 3. Managing the Service

You can manage the service using these commands:

```bash
# Stop the service
sudo systemctl stop chroma

# Restart the service
sudo systemctl restart chroma

# View logs
sudo journalctl -u chroma -f
```

## 4. Removing the Service

If you want to completely remove the Chroma service from systemd:

```bash
# Stop the service
sudo systemctl stop chroma

# Disable the service from starting on boot
sudo systemctl disable chroma

# Remove the service file
sudo rm /etc/systemd/system/chroma.service

# Reload systemd to recognize the changes
sudo systemctl daemon-reload

# Reset any failed status
sudo systemctl reset-failed
```

After these commands, the service will be completely removed from systemd and won't start on system boot anymore.

## Troubleshooting

If the service fails to start:
1. Check the logs using `sudo journalctl -u chroma -f`
2. Verify that the paths in the service file are correct
3. Ensure the virtual environment is properly set up and Chroma is installed within it
4. Check that the user specified in the service file has the necessary permissions