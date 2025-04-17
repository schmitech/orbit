# 🚀 Chroma Vector Database

This guide helps you easily configure Chroma Vector Database as a systemd service, ensuring it automatically starts with your server.

---

## ✅ Step 1: Install Dependencies

Install the Python virtual environment package:

```bash
sudo apt install python3-venv
```

---

## 🛠️ Step 2: Set Up Virtual Environment

Create and activate your Python environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required packages:

```bash
pip install -r requirements.txt
```
---

## 📝 Step 3: Create Systemd Service

Create a new service file:

```bash
sudo vim /etc/systemd/system/chroma.service
```

Paste and edit the following configuration:

```ini
[Unit]
Description=Chroma Vector Database Server
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/open-inference-platform/backend/chroma
ExecStart=/bin/bash -c 'source venv/bin/activate && chroma run --host 0.0.0.0 --port 8000 --path ./chroma_db'
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Replace:
- `your_username` with your actual system username
- `/path/to/open-inference-platform/backend/chroma` with your actual Chroma directory path

---

## ⚙️ Step 4: Enable & Start Service

Run these commands to activate your service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable chroma
sudo systemctl start chroma
sudo systemctl status chroma
```

---

## 🔧 Managing the Service

Use these commands to manage Chroma:

- **Start Service:**
  ```bash
  sudo systemctl start chroma
  ```

- **Stop Service:**
  ```bash
  sudo systemctl stop chroma
  ```

- **Restart Service:**
  ```bash
  sudo systemctl restart chroma
  ```

- **View Logs:**
  ```bash
  sudo journalctl -u chroma -f
  ```

---

## 🗑️ Removing the Service

Fully remove the Chroma service:

```bash
sudo systemctl stop chroma
sudo systemctl disable chroma
sudo rm /etc/systemd/system/chroma.service
sudo systemctl reset-failed
systemctl status chroma | cat
```

---

## 🚨 Troubleshooting

If the service doesn't start:

1. Check logs:
   ```bash
   sudo journalctl -u chroma -f
   ```

2. Verify paths and virtual environment.
3. Ensure user permissions are correct.

