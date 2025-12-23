# AWS Production Deployment Guide

This guide covers deploying the Orbit Chat App to AWS EC2 behind an Application Load Balancer (ALB) with WAF protection.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Security Model](#security-model)
- [Prerequisites](#prerequisites)
- [EC2 Instance Selection](#ec2-instance-selection)
- [Docker Deployment](#docker-deployment)
- [AWS Infrastructure Setup](#aws-infrastructure-setup)
- [Environment Configuration](#environment-configuration)
- [Health Checks](#health-checks)
- [Monitoring & Logging](#monitoring--logging)
- [Security Checklist](#security-checklist)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Internet  │────▶│   AWS WAF   │────▶│     ALB     │────▶│     EC2     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                                                                   ▼
                                                            ┌─────────────┐
                                                            │   Docker    │
                                                            │  Container  │
                                                            │             │
                                                            │ orbitchat   │
                                                            │   :3000     │
                                                            └─────────────┘
                                                                   │
                                                                   ▼
                                                            ┌─────────────┐
                                                            │  Backend    │
                                                            │  API Server │
                                                            │ (External)  │
                                                            └─────────────┘
```

### Request Flow

1. User requests arrive at AWS WAF for filtering
2. WAF forwards allowed requests to the ALB
3. ALB routes to healthy EC2 instances
4. Docker container serves the React app and proxies API requests
5. API keys are injected server-side; never exposed to the browser

---

## Security Model

The middleware proxy pattern ensures sensitive credentials never reach the browser:

| Data | Exposed to Browser? | Location |
|------|---------------------|----------|
| Adapter names | Yes (intentional) | `/api/adapters` response |
| API keys | **No** | Server memory only, injected at proxy |
| Backend API URLs | **No** | Server-side proxy configuration |

### How It Works

1. Browser requests `/api/adapters` → receives only adapter names
2. Browser sends chat request to `/api/v1/chat` with header `X-Adapter-Name: "Simple Chat"`
3. Server looks up the adapter's `apiKey` and `apiUrl` from environment
4. Server proxies request to backend with `X-API-Key` header injected
5. Response streams back through the proxy to the browser

---

## Prerequisites

- AWS Account with appropriate IAM permissions
- Docker installed locally (for building images)
- AWS CLI configured
- ECR repository created (or use Docker Hub)

---

## EC2 Instance Selection

### Recommended Instance Types

| Instance | vCPU | RAM | Monthly Cost* | Use Case |
|----------|------|-----|---------------|----------|
| t3.micro | 2 | 1 GB | ~$8 | Development/Testing |
| **t3.small** | 2 | 2 GB | ~$15 | Light production (< 100 users) |
| **t3.medium** | 2 | 4 GB | ~$30 | Medium load (100-1000 users) |
| t3.large | 2 | 8 GB | ~$60 | High load (1000+ users) |

*Prices are approximate for us-east-1, On-Demand pricing.

### Why t3 Family?

- **Burstable performance**: Ideal for web servers with variable load
- **Cost-effective**: Pay baseline + burst credits
- **Sufficient resources**: The app is lightweight (serves static files + proxies)

### Resource Requirements

- **Memory**: ~150 MB for the container
- **CPU**: Minimal (mostly I/O bound)
- **Disk**: 8 GB EBS is sufficient
- **Network**: Standard networking is fine

---

## Docker Deployment

### Building the Image

```bash
# Navigate to the chat-app directory
cd clients/chat-app

# Build the Docker image
docker build -t orbitchat:latest .

# Test locally
docker run -p 3000:3000 \
  -e 'VITE_ADAPTERS=[{"name":"Simple Chat","apiKey":"your-key","apiUrl":"https://your-backend.com"}]' \
  -e VITE_ENABLE_API_MIDDLEWARE=true \
  orbitchat:latest
```

### Using Docker Compose (Local Testing)

```bash
# Copy and configure environment
cp .env.production.example .env.production

# Edit .env.production with your adapter configuration
# Then run:
docker-compose up --build
```

### Pushing to Amazon ECR

```bash
# Authenticate Docker to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Tag the image
docker tag orbitchat:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/orbitchat:latest

# Push to ECR
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/orbitchat:latest
```

---

## AWS Infrastructure Setup

### 1. VPC Configuration

Use an existing VPC or create one with:
- Public subnets (for ALB)
- Private subnets (for EC2, recommended)
- NAT Gateway (if EC2 in private subnet)

### 2. Security Groups

#### ALB Security Group
```
Inbound:
- HTTPS (443) from 0.0.0.0/0
- HTTP (80) from 0.0.0.0/0 (redirect to HTTPS)

Outbound:
- All traffic to EC2 security group
```

#### EC2 Security Group
```
Inbound:
- TCP 3000 from ALB security group only
- SSH (22) from your IP (for maintenance)

Outbound:
- HTTPS (443) to 0.0.0.0/0 (for backend API calls)
```

### 3. Application Load Balancer

#### Target Group Configuration

| Setting | Value |
|---------|-------|
| Target type | Instance |
| Protocol | HTTP |
| Port | 3000 |
| Health check path | `/api/adapters` |
| Health check interval | 30 seconds |
| Healthy threshold | 2 |
| Unhealthy threshold | 3 |
| Timeout | 5 seconds |

#### Listener Rules

| Listener | Action |
|----------|--------|
| HTTP:80 | Redirect to HTTPS:443 |
| HTTPS:443 | Forward to target group |

### 4. WAF Configuration

Recommended WAF rules:

| Rule | Purpose |
|------|---------|
| AWS Managed - Common Rule Set | Block common attacks (SQLi, XSS) |
| AWS Managed - Known Bad Inputs | Block malicious payloads |
| Rate-based rule | Limit requests per IP (e.g., 2000/5min) |
| Geo-blocking (optional) | Restrict to specific countries |

### 5. EC2 Instance Setup

#### User Data Script (Amazon Linux 2023)

```bash
#!/bin/bash
# Install Docker
dnf update -y
dnf install -y docker
systemctl start docker
systemctl enable docker
usermod -aG docker ec2-user

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Pull and run the container
docker pull <account-id>.dkr.ecr.us-east-1.amazonaws.com/orbitchat:latest

docker run -d \
  --name orbitchat \
  --restart unless-stopped \
  -p 3000:3000 \
  -e 'VITE_ADAPTERS=<your-adapters-json>' \
  -e VITE_ENABLE_API_MIDDLEWARE=true \
  -e VITE_ENABLE_UPLOAD=true \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/orbitchat:latest
```

---

## Environment Configuration

### Required Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_ADAPTERS` | JSON array of adapters | `[{"name":"Chat","apiKey":"key","apiUrl":"https://api.com"}]` |
| `VITE_ENABLE_API_MIDDLEWARE` | Enable middleware mode | `true` |

### Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 3000 | Server port |
| `VITE_ENABLE_UPLOAD` | false | Enable file uploads |
| `VITE_ENABLE_AUDIO_OUTPUT` | false | Enable TTS |
| `VITE_ENABLE_CONVERSATION_THREADS` | false | Enable threading |
| `VITE_MAX_FILES_PER_CONVERSATION` | 5 | Max files per conversation |
| `VITE_MAX_FILE_SIZE_MB` | 50 | Max file size |
| `VITE_MAX_CONVERSATIONS` | 10 | Max conversations |
| `VITE_MAX_MESSAGE_LENGTH` | 1000 | Max message chars |

### Storing Secrets Securely

**Option 1: AWS Secrets Manager**

```bash
# Create secret
aws secretsmanager create-secret \
  --name orbitchat/adapters \
  --secret-string '[{"name":"Chat","apiKey":"your-secret-key","apiUrl":"https://api.example.com"}]'

# In EC2 user data, retrieve and use:
ADAPTERS=$(aws secretsmanager get-secret-value --secret-id orbitchat/adapters --query SecretString --output text)
docker run -e "VITE_ADAPTERS=$ADAPTERS" ...
```

**Option 2: AWS Systems Manager Parameter Store**

```bash
# Create parameter
aws ssm put-parameter \
  --name /orbitchat/adapters \
  --type SecureString \
  --value '[{"name":"Chat","apiKey":"your-secret-key","apiUrl":"https://api.example.com"}]'

# Retrieve in EC2:
ADAPTERS=$(aws ssm get-parameter --name /orbitchat/adapters --with-decryption --query Parameter.Value --output text)
```

---

## Health Checks

### Container Health Check

The Dockerfile includes a built-in health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/api/adapters', (r) => process.exit(r.statusCode === 200 ? 0 : 1))"
```

### ALB Health Check

Configure the target group health check:

- **Path**: `/api/adapters`
- **Expected response**: HTTP 200
- **Response body**: `{"adapters":[{"name":"..."}]}`

### Manual Health Check

```bash
# From EC2 instance
curl http://localhost:3000/api/adapters

# Expected response (only names, no keys/URLs)
{"adapters":[{"name":"Simple Chat"},{"name":"Chat With Files"}]}
```

---

## Monitoring & Logging

### CloudWatch Container Logs

Add logging driver to Docker run command:

```bash
docker run -d \
  --log-driver=awslogs \
  --log-opt awslogs-region=us-east-1 \
  --log-opt awslogs-group=/ecs/orbitchat \
  --log-opt awslogs-stream-prefix=orbitchat \
  ...
```

### Key Metrics to Monitor

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| CPU Utilization | EC2 | > 80% sustained |
| Memory Utilization | EC2 | > 85% |
| Healthy Host Count | ALB | < 1 |
| Target Response Time | ALB | > 5 seconds |
| 5XX Error Rate | ALB | > 1% |
| Request Count | ALB | Baseline + 200% |

### CloudWatch Alarms (Example)

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name orbitchat-high-cpu \
  --metric-name CPUUtilization \
  --namespace AWS/EC2 \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:<account>:alerts
```

---

## Security Checklist

### Application Security

- [x] API keys never sent to browser
- [x] Backend URLs never exposed to browser
- [x] Container runs as non-root user
- [x] Only adapter names in `/api/adapters` response
- [ ] Store `VITE_ADAPTERS` in Secrets Manager (configure this)
- [ ] Enable HTTPS on ALB with valid certificate
- [ ] Configure WAF rules

### Infrastructure Security

- [ ] EC2 in private subnet with NAT Gateway
- [ ] Security groups restrict traffic (ALB → EC2 only)
- [ ] IMDSv2 required on EC2
- [ ] EBS volumes encrypted
- [ ] CloudTrail enabled
- [ ] VPC Flow Logs enabled

### Operational Security

- [ ] Automated patching via SSM
- [ ] Regular container image updates
- [ ] Secrets rotation schedule
- [ ] Incident response runbook

---

## Troubleshooting

### Container Won't Start

```bash
# Check container logs
docker logs orbitchat

# Common issues:
# - Missing VITE_ADAPTERS environment variable
# - Invalid JSON in VITE_ADAPTERS
# - Port 3000 already in use
```

### Health Check Failing

```bash
# Test health endpoint manually
curl -v http://localhost:3000/api/adapters

# Check if adapters are configured
# Response should be: {"adapters":[{"name":"..."}]}
# If empty or error, check VITE_ADAPTERS env var
```

### API Proxy Errors

```bash
# Check container logs for proxy errors
docker logs orbitchat 2>&1 | grep -i proxy

# Common issues:
# - Backend API URL unreachable from container
# - Invalid API key
# - Network security group blocking outbound HTTPS
```

### ALB 502/503 Errors

1. Verify target group health checks are passing
2. Check security group allows ALB → EC2 on port 3000
3. Verify container is running: `docker ps`
4. Check container health: `docker inspect orbitchat | grep -A 10 Health`

---

## Quick Reference

### Build & Deploy Commands

```bash
# Build image
docker build -t orbitchat:latest .

# Run locally
docker-compose up --build

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker tag orbitchat:latest <account>.dkr.ecr.us-east-1.amazonaws.com/orbitchat:latest
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/orbitchat:latest

# Deploy to EC2 (SSH in, then)
docker pull <account>.dkr.ecr.us-east-1.amazonaws.com/orbitchat:latest
docker stop orbitchat && docker rm orbitchat
docker run -d --name orbitchat --restart unless-stopped -p 3000:3000 \
  -e "VITE_ADAPTERS=$ADAPTERS" \
  -e VITE_ENABLE_API_MIDDLEWARE=true \
  <account>.dkr.ecr.us-east-1.amazonaws.com/orbitchat:latest
```

### Important Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serve React app |
| `/api/adapters` | GET | List adapter names (health check) |
| `/api/*` | POST | Proxy API requests to backend |

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/schmitech/orbit/issues
- Documentation: Check the main README.md
