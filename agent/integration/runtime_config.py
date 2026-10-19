"""Operator-side AI configuration. Secrets are entered only in the user's terminal.

No provider requests, backend changes, service restarts, or credential generation.
The deployment's existing service/tool tokens remain authoritative.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import tempfile
import warnings


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = {"DEEPSEEK_API_KEY": "", "LLM_MODEL": "deepseek-flash", "P3_ENGINE": "deepseek"}
REQUIRED = ("DEEPSEEK_API_KEY", "AI_SERVICE_TOKEN", "BACKEND_TOOL_TOKEN", "BACKEND_BASE_URL")
PROFILES = {"p6": "v1.app:create_app", "p7": "conversation.app:create_app"}
HEADER = "# Private AI runtime configuration; never commit or upload this file.\n"


class ConfigError(Exception):
    pass


def config_path(root=ROOT):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ConfigError("AI workspace must be an existing real directory.")
    path = root / ".env.runtime"
    if path.is_symlink():
        raise ConfigError("Refusing a symlinked runtime configuration.")
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ConfigError("Runtime configuration must be a regular file.")
        if hasattr(os, "getuid") and info.st_uid != os.getuid():
            raise ConfigError("Runtime configuration belongs to another account.")
    return path


def read_config(root=ROOT):
    path = config_path(root)
    if not path.exists():
        return {}
    values = {}
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or key in values:
            raise ConfigError(f"Invalid or duplicate configuration name on line {index}.")
        try:
            tokens = shlex.split(value, comments=True, posix=True)
        except ValueError:
            raise ConfigError(f"Invalid quoting on line {index}.") from None
        if len(tokens) > 1:
            raise ConfigError(f"Configuration values must be quoted on line {index}.")
        # No shell evaluation or variable interpolation, including $() / backticks.
        values[key] = tokens[0] if tokens else ""
    return values


def write_config(values, root=ROOT):
    path = config_path(root)
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or not isinstance(value, str):
            raise ConfigError("Invalid runtime configuration entry.")
        if any(ord(char) < 32 or ord(char) > 126 for char in value):
            raise ConfigError("Runtime configuration values must use printable ASCII.")
    # POSIX single quotes are supported by Docker env_file as literal values.
    # Real keys are never inserted into command arguments or Python source.
    content = HEADER + "".join(key + "=" + shlex.quote(value) + "\n" for key, value in values.items())
    descriptor, temporary = tempfile.mkstemp(prefix=".env.runtime.tmp-", dir=path.parent)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Check again before the atomic replacement; never follow a symlink.
        config_path(root)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def initialize(root=ROOT):
    values = read_config(root)
    for key, default in DEFAULTS.items():
        if not values.get(key):
            values[key] = default
    # Configuring the provider means explicitly opting into the model engine.
    values["P3_ENGINE"] = "deepseek"
    write_config(values, root)


def set_key(root=ROOT, prompt=None):
    if prompt is None:
        if not sys.stdin.isatty():
            raise ConfigError("Enter the key in your own interactive SSH terminal.")

        def prompt(message):
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                try:
                    return getpass.getpass(message)
                except getpass.GetPassWarning:
                    raise ConfigError("Secure hidden input unavailable; key was not requested.") from None
    key = prompt("DeepSeek API key (hidden input): ")
    if not 16 <= len(key) <= 4096 or any(char.isspace() or not 33 <= ord(char) <= 126 for char in key):
        raise ConfigError("Invalid key format; existing configuration was not changed.")
    confirmed = prompt("Enter the same key again: ")
    if key != confirmed:
        raise ConfigError("The two entries differ; existing configuration was not changed.")
    values = read_config(root)
    for name, default in DEFAULTS.items():
        if not values.get(name):
            values[name] = default
    values["DEEPSEEK_API_KEY"] = key
    values["P3_ENGINE"] = "deepseek"
    write_config(values, root)
    print("DeepSeek key saved privately. Its value has not been displayed.")


def environment(root=ROOT, inherited=None):
    env = dict(os.environ if inherited is None else inherited)
    for key, value in read_config(root).items():
        if value or key not in env:
            env[key] = value
    # This loader runs the host-side venv. Container deployments retain their
    # existing BACKEND_BASE_URL and service/tool credentials via Compose.
    if not env.get("BACKEND_BASE_URL"):
        env["BACKEND_BASE_URL"] = "http://127.0.0.1:8000"
    return env


def launch_arguments(root=ROOT, profile="p6"):
    # Keep the historical default; P7 must be selected explicitly by operators.
    if profile not in PROFILES:
        raise ConfigError("Unknown AI profile; choose p6 or p7.")
    python = Path(root) / ".venv-p2/bin/python"
    if not python.is_file():
        python = Path(sys.executable)
    return [str(python), "-B", "-m", "uvicorn", PROFILES[profile], "--factory",
            "--host", "127.0.0.1", "--port", "8767"]


def status(root=ROOT, inherited=None, profile="p6"):
    argv = launch_arguments(root, profile)
    env = environment(root, inherited)
    present = {key: bool(env.get(key)) for key in REQUIRED}
    engine_ok = env.get("P3_ENGINE") == "deepseek"
    model_ok = env.get("LLM_MODEL") == "deepseek-flash"
    return {"config_exists": config_path(root).is_file(), "configured": present,
            "profile": profile, "entrypoint": PROFILES[profile],
            "argv": argv, "deepseek_selected": engine_ok,
            "model_matches_existing_pricing": model_ok,
            "provider_key_present": present["DEEPSEEK_API_KEY"],
            "missing_configuration": [key for key, ready in present.items() if not ready],
            "service_ready": all(present.values()) and engine_ok and model_ok,
            "readiness_scope": "local_configuration_only",
            "backend_connectivity_verified": False, "services_started": False,
            "provider_key_validated_online": False}


def run_service(root=ROOT, inherited=None, execute=None, profile="p6"):
    argv = launch_arguments(root, profile)
    env = environment(root, inherited)
    missing = [key for key in REQUIRED if not env.get(key)]
    if missing:
        raise ConfigError("Service not started. Deployment must supply: " + ", ".join(missing))
    if env.get("P3_ENGINE") != "deepseek" or env.get("LLM_MODEL") != "deepseek-flash":
        raise ConfigError("Expected the configured deepseek engine and verified model.")
    os.chdir(root)
    # exec inherits the terminal; no daemon, background process or public port.
    (execute or os.execve)(argv[0], argv, env)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private host-side AI configuration")
    parser.add_argument("command", choices=["init", "set-key", "status", "check", "run"])
    parser.add_argument("--profile", choices=PROFILES, default="p6",
                        help="Explicit runtime profile; legacy default is p6")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            initialize()
        elif args.command == "set-key":
            set_key()
        elif args.command == "run":
            run_service(profile=args.profile)
            return 0
        result = status(profile=args.profile)
        print(json.dumps(result))
        if args.command == "check" and not result["service_ready"]:
            return 1
        return 0
    except (ConfigError, OSError, UnicodeError):
        # ConfigError messages contain names only, never parsed values or keys.
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, ConfigError) else "Runtime configuration is not accessible.", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("Cancelled. Use status to check whether configuration was saved.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
