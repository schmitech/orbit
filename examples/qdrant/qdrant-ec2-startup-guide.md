# Qdrant EC2 Auto-Startup Guide

This guide explains how to configure Qdrant vector database to automatically start when your EC2 instance boots up using systemd services.

## Overview

The setup uses a systemd service that runs your `start_qdrant.sh` script after Docker is ready, ensuring Qdrant starts automatically on every system boot.

## Prerequisites

- EC2 instance running Amazon Linux 2023 or similar
- Docker installed and running
- `start_qdrant.sh` script in your home directory (`/home/ec2-user/`)
- Sudo privileges

## Files Required

### 1. start_qdrant.sh
Your existing script that starts Qdrant in Docker:

```bash
#!/bin/bash
# Script to start Qdrant vector database in the background using Docker

CONTAINER_NAME="qdrant"

# Stop and remove the container if it already exists
if [ "$(sudo docker ps -aq -f name=^/${CONTAINER_NAME}$)" ]; then
    echo "Stopping and removing existing container: ${CONTAINER_NAME}"
    sudo docker stop ${CONTAINER_NAME}
    sudo docker rm ${CONTAINER_NAME}
fi

echo "Starting a new ${CONTAINER_NAME} container..."

# Ensure storage directory exists
mkdir -p "$(pwd)/qdrant"

# Run Qdrant in detached mode with a fixed container name
sudo docker run -d \
  --name ${CONTAINER_NAME} \
  -p 6333:6333 \
  -v "$(pwd)/qdrant:/qdrant/storage" \
  qdrant/qdrant

echo "Qdrant container started successfully."
```

### 2. qdrant-startup.service
Systemd service file that will be created:

```ini
[Unit]
Description=Start Qdrant on boot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/home/ec2-user/start_qdrant.sh
User=ec2-user
WorkingDirectory=/home/ec2-user
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

## Step-by-Step Setup

### Step 1: Create the Service File

Create the systemd service file in your home directory:

```bash
cat > qdrant-startup.service << 'EOF'
[Unit]
Description=Start Qdrant on boot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/home/ec2-user/start_qdrant.sh
User=ec2-user
WorkingDirectory=/home/ec2-user
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
```

### Step 2: Move Service File to System Directory

```bash
sudo mv qdrant-startup.service /etc/systemd/system/
```

### Step 3: Reload Systemd

```bash
sudo systemctl daemon-reload
```

### Step 4: Enable the Service

```bash
sudo systemctl enable qdrant-startup.service
```

### Step 5: Test the Service

```bash
sudo systemctl start qdrant-startup.service
sudo systemctl status qdrant-startup.service
```

### Step 6: Verify Qdrant is Running

```bash
sudo docker ps | grep qdrant
```

## Service Configuration Explained

### Unit Section
- **Description**: Human-readable description of the service
- **After**: Ensures this service starts after Docker is ready
- **Requires**: Makes Docker a hard dependency

### Service Section
- **Type**: `oneshot` - runs once and exits successfully
- **ExecStart**: Path to your startup script
- **User**: Runs as ec2-user (your user)
- **WorkingDirectory**: Sets the working directory for the script
- **RemainAfterExit**: Keeps service marked as active after completion

### Install Section
- **WantedBy**: Makes the service start when the system reaches multi-user target (normal boot)

## Management Commands

### Check Service Status
```bash
sudo systemctl status qdrant-startup.service
```

### Start Service Manually
```bash
sudo systemctl start qdrant-startup.service
```

### Stop Service
```bash
sudo systemctl stop qdrant-startup.service
```

### Disable Auto-Startup
```bash
sudo systemctl disable qdrant-startup.service
```

### View Service Logs
```bash
sudo journalctl -u qdrant-startup.service
```

### View Recent Logs
```bash
sudo journalctl -u qdrant-startup.service -f
```

## Troubleshooting

### Service Fails to Start
1. Check if Docker is running: `sudo systemctl status docker`
2. Verify script permissions: `ls -la start_qdrant.sh`
3. Check service logs: `sudo journalctl -u qdrant-startup.service`

### Qdrant Container Not Running
1. Check Docker containers: `sudo docker ps -a`
2. Check Docker logs: `sudo docker logs qdrant`
3. Verify port availability: `sudo netstat -tlnp | grep 6333`

### Permission Issues
1. Ensure script is executable: `chmod +x start_qdrant.sh`
2. Verify user ownership: `ls -la start_qdrant.sh`
3. Check sudoers configuration if needed

## Alternative Methods (Not Recommended)

### Crontab Method
```bash
# Add to crontab
(crontab -l 2>/dev/null; echo "@reboot /home/ec2-user/start_qdrant.sh") | crontab -
```

**Disadvantages:**
- No dependency management
- Less reliable than systemd
- Harder to troubleshoot

### User Data Script
For new EC2 instances, you can add to User Data:
```bash
#!/bin/bash
cd /home/ec2-user
./start_qdrant.sh
```

**Disadvantages:**
- Only works on instance creation
- No automatic restart on reboot

## Benefits of Systemd Approach

1. **Reliability**: Proper dependency management
2. **Logging**: Integrated with system logging
3. **Management**: Standard systemctl commands
4. **Persistence**: Survives system updates and reboots
5. **Monitoring**: Easy status checking and debugging

## Security Considerations

- The service runs as your user (ec2-user)
- Uses sudo for Docker commands
- Consider restricting Docker access if needed
- Monitor container resource usage

## Performance Notes

- Service starts after Docker is ready (prevents race conditions)
- One-shot service type minimizes resource usage
- Container persists between service restarts
- Storage is mounted and persisted in `./qdrant` directory

## Verification Checklist

- [ ] Service file created in `/etc/systemd/system/`
- [ ] Service enabled with `systemctl enable`
- [ ] Service starts successfully with `systemctl start`
- [ ] Qdrant container running and accessible on port 6333
- [ ] Service status shows as "active (exited)"
- [ ] Container persists after service restart

## Next Steps

After setup, you can:
1. Test by rebooting your instance
2. Monitor startup logs
3. Configure Qdrant client connections
4. Set up monitoring and alerting
5. Configure backup strategies for your vector data

---

**Note**: This guide assumes Amazon Linux 2023. For other distributions, the systemd commands remain the same, but file paths may vary.
