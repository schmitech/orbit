# MongoDB Installation Guide for Amazon Linux 2023

## Lessons Learned & Best Practices

This guide documents the proper way to install MongoDB on Amazon Linux 2023, based on troubleshooting a GPG key verification failure.

## The Problem

During MongoDB installation, you may encounter this error:
```
Error: GPG check FAILED
The GPG keys listed for the "MongoDB Repository" repository are already installed but they are not correct for this package.
Check that the correct key URLs are configured for this repository.
```

## Root Cause

This error occurs when:
1. Multiple MongoDB repository configurations exist with conflicting GPG keys
2. Repository is configured for one MongoDB version (e.g., 7.0) but trying to install another version (e.g., 8.0)
3. GPG keys don't match the MongoDB version being installed

## Proper Installation Steps

### Step 1: Clean Up Existing Repository Configurations

Remove any existing MongoDB repository files to avoid conflicts:
```bash
sudo rm -f /etc/yum.repos.d/mongodb-org*.repo
```

### Step 2: Import the Correct GPG Key

For MongoDB 8.0:
```bash
sudo rpm --import https://www.mongodb.org/static/pgp/server-8.0.asc
```

For other versions, use the appropriate GPG key:
- MongoDB 7.0: `https://www.mongodb.org/static/pgp/server-7.0.asc`
- MongoDB 6.0: `https://www.mongodb.org/static/pgp/server-6.0.asc`

### Step 3: Create the Repository Configuration

Create a single, correct repository file for MongoDB 8.0:
```bash
sudo tee /etc/yum.repos.d/mongodb-org-8.0.repo > /dev/null << 'EOF'
[mongodb-org-8.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/amazon/2023/mongodb-org/8.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-8.0.asc
EOF
```

### Step 4: Clean Cache and Update Metadata

```bash
sudo yum clean all
sudo yum makecache
```

### Step 5: Install MongoDB

```bash
sudo yum install -y mongodb-org
```

## Version-Specific Repository Configurations

### MongoDB 8.0 (Latest Stable)
```ini
[mongodb-org-8.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/amazon/2023/mongodb-org/8.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-8.0.asc
```

### MongoDB 7.0
```ini
[mongodb-org-7.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/amazon/2023/mongodb-org/7.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-7.0.asc
```

### MongoDB 6.0
```ini
[mongodb-org-6.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/amazon/2023/mongodb-org/6.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-6.0.asc
```

## Post-Installation Steps

### 1. Check Installation
```bash
mongod --version
mongosh --version
```

### 2. Start MongoDB Service
```bash
sudo systemctl start mongod
sudo systemctl enable mongod
```

### 3. Verify Service Status
```bash
sudo systemctl status mongod
```

### 4. Connect to MongoDB
```bash
mongosh
```

## Configuring External Access

By default, MongoDB only accepts connections from localhost (127.0.0.1). To allow external connections:

### Enable External Connections

1. **Edit the MongoDB configuration file**:
```bash
sudo nano /etc/mongod.conf
```

2. **Modify the network section**:
```yaml
# network interfaces
net:
  port: 27017
  bindIp: 0.0.0.0  # Accept connections from anywhere
```

3. **Restart MongoDB service**:
```bash
sudo systemctl restart mongod
```

4. **Verify the configuration**:
```bash
sudo netstat -tlnp | grep :27017
```
You should see: `tcp 0 0 0.0.0.0:27017 0.0.0.0:* LISTEN`

### Security Considerations for External Access

⚠️ **CRITICAL**: Opening MongoDB to external connections without proper security is dangerous!

#### 1. Enable Authentication (Essential)

```bash
# Connect to MongoDB
mongosh

# Create an admin user
use admin
db.createUser({
  user: "admin",
  pwd: "your-secure-password",
  roles: ["userAdminAnyDatabase", "dbAdminAnyDatabase", "readWriteAnyDatabase"]
})

# Exit mongosh
exit
```

#### 2. Enable Security in Configuration

Add to `/etc/mongod.conf`:
```yaml
security:
  authorization: enabled
```

Then restart MongoDB:
```bash
sudo systemctl restart mongod
```

#### 3. Test Authentication

```bash
# This should fail (no authentication)
mongosh --eval "db.adminCommand('listCollections')"

# This should work (with authentication)
mongosh -u admin -p your-secure-password --authenticationDatabase admin --eval "db.adminCommand('listCollections')"
```

#### 4. Firewall Configuration (Recommended)

For production environments, restrict access to specific IP ranges:

```bash
# Install firewalld if not already installed
sudo yum install -y firewalld
sudo systemctl start firewalld
sudo systemctl enable firewalld

# Allow MongoDB only from specific network
sudo firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='192.168.1.0/24' port protocol='tcp' port='27017' accept"

# Or allow from specific IP
sudo firewall-cmd --permanent --add-rich-rule="rule family='ipv4' source address='192.168.1.100' port protocol='tcp' port='27017' accept"

# Apply changes
sudo firewall-cmd --reload

# Check rules
sudo firewall-cmd --list-all
```

#### 5. Additional Security Measures

- **Use SSL/TLS encryption** for production environments
- **Regularly monitor connection logs**: `/var/log/mongodb/mongod.log`
- **Use strong passwords** and consider key-based authentication
- **Keep MongoDB updated** to the latest version
- **Consider using MongoDB Atlas** for managed database hosting

### Testing External Connections

From another machine:
```bash
# Without authentication (if security is disabled)
mongosh "mongodb://your-server-ip:27017"

# With authentication
mongosh "mongodb://admin:your-secure-password@your-server-ip:27017/admin"
```

## Troubleshooting Common Issues

### Issue 1: Repository Listed More Than Once
**Error**: `Repository mongodb-org-8.0 is listed more than once in the configuration`

**Solution**: Remove duplicate repository files:
```bash
ls /etc/yum.repos.d/mongodb-org*
sudo rm -f /etc/yum.repos.d/mongodb-org*.repo
# Then recreate the single correct repository file
```

### Issue 2: No Match for Package
**Error**: `No match for argument: mongodb-org`

**Solution**: 
1. Ensure repository is properly configured and enabled
2. Clean cache: `sudo yum clean all && sudo yum makecache`
3. Check if repository is accessible: `sudo yum repolist`

### Issue 3: Docker Repository Errors
If you see Docker repository errors (like 404 for docker-ce-stable), they can be safely ignored if you're only installing MongoDB. To clean them up:
```bash
sudo yum-config-manager --disable docker-ce-stable
```

## Best Practices

1. **Always use version-specific repositories**: Match the repository version with the MongoDB version you want to install
2. **Import GPG keys first**: Always import the correct GPG key before installation
3. **Clean up conflicting repositories**: Remove old/conflicting repository configurations
4. **Use specific versions**: Pin to specific MongoDB versions in production environments
5. **Test the installation**: Always verify the installation works before deploying

## Verification Commands

After installation, run these commands to verify everything works:
```bash
# Check installed packages
rpm -qa | grep mongodb-org

# Check service status
sudo systemctl status mongod

# Test connection
mongosh --eval "db.runCommand({hello: 1})"

# Check MongoDB version
mongod --version

# Verify network binding (after configuring external access)
sudo netstat -tlnp | grep :27017

# Check current configuration
sudo cat /etc/mongod.conf | grep -A 5 "net:"

# Test authentication (if enabled)
mongosh -u admin -p --authenticationDatabase admin --eval "db.adminCommand('listDatabases')"
```

## Production Considerations

- **Pin MongoDB version** in production to avoid unexpected upgrades
- **NEVER expose MongoDB to the internet without authentication** - Always enable security when using `bindIp: 0.0.0.0`
- **Configure appropriate security settings** in `/etc/mongod.conf`:
  - Enable `authorization: enabled` for authentication
  - Consider SSL/TLS encryption with `net.tls` settings
- **Set up proper backup procedures**
- **Monitor MongoDB logs**: `/var/log/mongodb/mongod.log`
- **Configure firewall rules** to restrict access to trusted networks only
- **Use strong passwords** and rotate them regularly
- **Regular security audits** and keep MongoDB updated
- **Consider MongoDB Atlas** for production workloads (managed service)

## Useful File Locations

- Configuration: `/etc/mongod.conf`
- Data directory: `/var/lib/mongo`
- Log file: `/var/log/mongodb/mongod.log`
- Service file: `/usr/lib/systemd/system/mongod.service`

---

**Created**: June 25, 2025  
**Last Updated**: June 25, 2025  
**MongoDB Version**: 8.0.10  
**OS**: Amazon Linux 2023 