## Instructions

You need a Linux server with CUDA GPU to run these scripts. Install uv before running.

```bash
git clone https://github.com/NVIDIA/personaplex.git
```

Put these scripts under `personaplex` directory cloned above, then:

```bash
clean-caches.sh
setup-native.sh
start-moshi-server.sh --start
```