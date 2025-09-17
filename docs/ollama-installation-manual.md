# Ollama Installation Manual

## Overview
This manual provides step-by-step instructions for installing and configuring Ollama on Ubuntu Linux, including troubleshooting common permission issues.

## Prerequisites
- Ubuntu Linux (tested on Ubuntu with kernel 6.8.0)
- Root or sudo access
- Internet connection

## Installation Steps

### 1. Download and Install Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Create System User and Directory Structure
The installation script may not properly set up the system user and directories. Run these commands to ensure proper configuration:

```bash
# Create ollama system user (if not already exists)
sudo useradd -r -s /bin/false -m -d /usr/share/ollama ollama

# Create required directories
sudo mkdir -p /usr/share/ollama/.ollama

# Set proper ownership
sudo chown -R ollama:ollama /usr/share/ollama
```

### 3. Create Systemd Service File
Create the service file at `/etc/systemd/system/ollama.service`:

```bash
sudo tee /etc/systemd/system/ollama.service > /dev/null <<EOF
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="OLLAMA_HOST=0.0.0.0:11434"

[Install]
WantedBy=default.target
EOF
```

### 4. Enable and Start the Service
```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable ollama

# Start the service
sudo systemctl start ollama

# Check service status
sudo systemctl status ollama
```

## Verification

### Check Service Status
```bash
sudo systemctl status ollama
```

Expected output should show:
- `Active: active (running)`
- `Listening on [::]:11434`
- No permission denied errors

### Test Ollama API
```bash
# Test if Ollama is responding
curl http://localhost:11434/api/tags

# Or test with a simple model pull
ollama pull gema3:12b
```

### Connection Testing

#### 1. Network Binding Verification
```bash
# Check if Ollama is listening on all interfaces
ss -tlnp | grep 11434
```
**Expected output**: `LISTEN 0 4096 *:11434 *:*` (the `*` indicates listening on all interfaces)

#### 2. API Response Testing
```bash
# Test API response with detailed output
curl -s -w "HTTP Status: %{http_code}\nResponse Time: %{time_total}s\n" http://localhost:11434/api/tags

# Test HTTP headers
curl -s -I http://localhost:11434/api/tags
```

#### 3. Different Interface Testing
```bash
# Test localhost interface
curl -s http://127.0.0.1:11434/api/tags

# Test with external IP (replace with your server's IP)
curl -s http://YOUR_SERVER_IP:11434/api/tags
```

#### 4. Model Interaction Test
```bash
# Test a simple chat request (replace model name with available model)
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-oss:20b",
    "prompt": "Hello, how are you?",
    "stream": false
  }'
```

#### 5. Real-time Monitoring
```bash
# Monitor incoming connections
sudo ss -tlnp | grep 11434

# Watch service logs in real-time
journalctl -u ollama.service -f
```

#### 6. Port Availability Check
```bash
# Check what's using port 11434
sudo lsof -i :11434

# Alternative method
sudo fuser 11434/tcp
```

## Troubleshooting

### Common Issues

#### 1. Permission Denied Error
**Error**: `Error: could not create directory mkdir /usr/share/ollama: permission denied`

**Solution**:
```bash
# Create directory with proper ownership
sudo mkdir -p /usr/share/ollama/.ollama
sudo chown -R ollama:ollama /usr/share/ollama
sudo systemctl restart ollama
```

#### 2. Service Fails to Start
**Check logs**:
```bash
journalctl -u ollama.service --no-pager -n 50
```

**Common fixes**:
- Ensure ollama user exists: `id ollama`
- Check binary location: `ls -la /usr/local/bin/ollama`
- Verify service file syntax: `sudo systemctl cat ollama.service`

#### 3. Port Already in Use
**Check what's using port 11434**:
```bash
sudo netstat -tlnp | grep 11434
```

**Kill existing process**:
```bash
sudo pkill -f ollama
sudo systemctl start ollama
```

## Service Management Commands

```bash
# Start service
sudo systemctl start ollama

# Stop service
sudo systemctl stop ollama

# Restart service
sudo systemctl restart ollama

# Check status
sudo systemctl status ollama

# View logs
journalctl -u ollama.service -f

# Disable auto-start
sudo systemctl disable ollama

# Enable auto-start
sudo systemctl enable ollama
```

## Configuration

### Environment Variables
The service can be configured using environment variables in the systemd service file:

- `OLLAMA_HOST`: Set the host and port (default: `0.0.0.0:11434`)
- `OLLAMA_MODELS`: Set custom models directory
- `OLLAMA_ORIGINS`: Set allowed origins for CORS

### Example with Custom Configuration
```bash
sudo tee /etc/systemd/system/ollama.service > /dev/null <<EOF
[Unit]
Description=Ollama Service
After=network-online.target

[Service]
ExecStart=/usr/local/bin/ollama serve
User=ollama
Group=ollama
Restart=always
RestartSec=3
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_MODELS=/usr/share/ollama/models"
Environment="OLLAMA_ORIGINS=*"

[Install]
WantedBy=default.target
EOF
```

## Security Considerations

1. **Firewall**: Consider restricting access to port 11434 if not needed externally
2. **User Permissions**: The ollama user should only have access to necessary directories
3. **Model Storage**: Be aware that models are stored in `/usr/share/ollama/.ollama/models/`

## Uninstallation

To completely remove Ollama:

```bash
# Stop and disable service
sudo systemctl stop ollama
sudo systemctl disable ollama

# Remove service file
sudo rm /etc/systemd/system/ollama.service
sudo systemctl daemon-reload

# Remove binary
sudo rm /usr/local/bin/ollama

# Remove user and data (optional)
sudo userdel ollama
sudo rm -rf /usr/share/ollama
```

## Notes

- Ollama version tested: 0.11.10
- Default port: 11434
- Models are downloaded on first use
- GPU support is automatically detected if available
- Service runs as `ollama` user for security

## Support

For additional help:
- Official documentation: https://ollama.com/docs
- GitHub repository: https://github.com/ollama/ollama
- Check service logs: `journalctl -u ollama.service -f`
