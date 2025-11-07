# ORBIT Podman Setup Guide

Use this guide to run ORBIT with Podman as a drop-in alternative to the Docker workflows. The Podman assets mirror the Docker equivalents so you can migrate without changing your day-to-day commands.

## Prerequisites
- Podman 4.0+
- Podman Compose (`podman compose` subcommand) or `podman-compose`
- Git
- 4GB+ RAM and 10GB+ free disk space

Verify your install:
```bash
podman --version
podman compose --help  # or podman-compose --version
```

## Quick Start
```bash
cd orbit/podman
chmod +x podman-init.sh orbit-podman.sh
./podman-init.sh --build
```

The init script mirrors the Docker behaviour: it prepares config/env files, optionally downloads GGUF models, builds the image, starts the services, and runs a health check.

## Configuration

- The Podman compose file lives at `podman/compose.yml`. Edit it if you need to add services or change volumes.

1. Copy `env.example` to `.env` (the script does this automatically if missing).
2. Ensure MongoDB and Redis hosts resolve to the Compose service names:
   ```bash
   INTERNAL_SERVICES_MONGODB_HOST=mongodb
   INTERNAL_SERVICES_REDIS_HOST=redis
   ```
3. Update `config/` as needed or pass a specific file with `--config`.

## Running ORBIT

Use `orbit-podman.sh` for lifecycle management:
```bash
./orbit-podman.sh start --profile cloud
./orbit-podman.sh logs --follow
./orbit-podman.sh status
./orbit-podman.sh cli key list
```

Authentication helpers (login/logout/me/auth-status/register) wrap the same CLI commands inside the running container.

## Managing Services

- Stop services: `./orbit-podman.sh stop`
- Restart: `./orbit-podman.sh restart`
- View logs: `./orbit-podman.sh logs`
- Exec shell: `./orbit-podman.sh exec bash`
- Health check: `./orbit-podman.sh status`

## Cleanup

Use `podman-cleanup.sh` to reclaim space or reset the Podman environment:
```bash
./podman-cleanup.sh
```

It stops/removes containers, images, volumes, and networks, then reports current Podman state. For Podman machine users it suggests additional pruning options.

## Troubleshooting

- Ensure `CONFIG_PATH` points to the correct file when overriding configs.
- If ports fail to bind, confirm your Podman machine/rootless setup allows the mapping (e.g. `podman machine ssh` on macOS/Windows).
- Inspect logs: `podman compose logs orbit-server`
- Rebuild without cache: `./podman-init.sh --rebuild --profile all`

Happy orbiting with Podman! 🚀
