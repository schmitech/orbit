#!/usr/bin/env python3
"""
ORBIT Windows setup helper — called by setup.bat for TOML-based operations.

Commands:
  list    <toml_file>                  Print available profiles
  resolve <toml_file> [profile ...]    Print resolved requirements (default + profiles)
"""

import sys

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("Error: TOML parser not available. Install it: pip install tomli", file=sys.stderr)
        sys.exit(1)


def get_default_deps(config):
    if "default" in config:
        return list(config["default"].get("dependencies", []))
    return list(config.get("profiles", {}).get("default", {}).get("dependencies", []))


def resolve_profile(config, name, resolved=None):
    if resolved is None:
        resolved = set()
    if name in resolved:
        return []
    resolved.add(name)
    profiles = config.get("profiles", {})
    if name not in profiles:
        print(f"Error: Unknown profile '{name}'", file=sys.stderr)
        print(f"Available profiles: {', '.join(profiles)}", file=sys.stderr)
        sys.exit(1)
    profile = profiles[name]
    deps = list(profile.get("dependencies", []))
    extends = profile.get("extends", [])
    if isinstance(extends, str):
        extends = [extends]
    for ext in extends:
        deps = resolve_profile(config, ext, resolved.copy()) + deps
    return deps


def dedupe(deps):
    seen = set()
    out = []
    for d in deps:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def main():
    if len(sys.argv) < 3:
        print("Usage: setup_helper.py <list|resolve> <toml_file> [profiles...]", file=sys.stderr)
        sys.exit(1)

    command, toml_file = sys.argv[1], sys.argv[2]

    try:
        with open(toml_file, "rb") as f:
            config = tomllib.load(f)
    except FileNotFoundError:
        print(f"Error: {toml_file} not found", file=sys.stderr)
        sys.exit(1)

    if command == "list":
        profiles = config.get("profiles", {})
        print(f"  {'Profile':<24} Description")
        print(f"  {'-'*24} {'-'*48}")
        default = profiles.get("default", {})
        print(f"  {'default':<24} {default.get('description', 'Core dependencies (always installed)')}")
        for name, profile in profiles.items():
            if name == "default":
                continue
            desc = profile.get("description", "")
            extends = profile.get("extends", [])
            ext_str = f" (extends: {', '.join(extends)})" if extends else ""
            print(f"  {name:<24} {desc}{ext_str}")

    elif command == "resolve":
        profiles_to_add = sys.argv[3:]
        all_deps = get_default_deps(config)
        for p in profiles_to_add:
            if p:
                all_deps.extend(resolve_profile(config, p))
        for dep in dedupe(all_deps):
            print(dep)

    else:
        print(f"Error: Unknown command '{command}'", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
