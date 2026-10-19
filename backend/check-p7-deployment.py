"""Host-side read-only Docker wiring audit. Never print raw inspect or secrets."""
import argparse
import json
import secrets
import subprocess


def audit(backend, agent):
    def env(container):
        return dict(entry.split("=", 1) for entry in container["Config"].get("Env", []) if "=" in entry)

    be, ai = env(backend), env(agent)

    def same_token(name):
        left, right = be.get(name, ""), ai.get(name, "")
        return len(left) >= 32 and secrets.compare_digest(left.encode(), right.encode())

    cmd = agent["Config"].get("Cmd") or []
    checks = {
        "ai_service_token_matches": same_token("AI_SERVICE_TOKEN"),
        "backend_tool_token_matches": same_token("BACKEND_TOOL_TOKEN"),
        "ai_service_url": be.get("AI_SERVICE_URL", "").rstrip("/") == "http://agent:8767",
        "backend_base_url": ai.get("BACKEND_BASE_URL", "").rstrip("/") == "http://backend:8000",
        "p7_entrypoint": "conversation.app:create_app" in cmd and "--factory" in cmd,
        "explicit_p7_engine": ai.get("P3_ENGINE") in {"rules", "deepseek"},
        "shared_network": bool(set(backend["NetworkSettings"]["Networks"]) & set(agent["NetworkSettings"]["Networks"])),
        "ai_no_host_ports": not any(agent["NetworkSettings"].get("Ports", {}).values()),
        "ai_no_database_password": not any(ai.get(k) for k in ("DB_PASSWORD", "POSTGRES_PASSWORD")),
        "ai_cache_mounted": any(m.get("Destination", "").rstrip("/") == "/app/agent/.cache"
                                for m in agent.get("Mounts", [])),
        "ai_read_only": agent["HostConfig"].get("ReadonlyRootfs") is True,
    }
    if ai.get("P3_ENGINE") == "deepseek":
        checks["provider_key_present"] = bool(ai.get("DEEPSEEK_API_KEY"))
        checks["priced_model_selected"] = ai.get("LLM_MODEL") == "deepseek-flash"
    return {"checks": checks, "wiring_passed": all(checks.values()),
            "model_called": False, "configuration_changed": False,
            "token_values_disclosed": False, "live_acceptance_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", required=True)
    parser.add_argument("--agent", required=True)
    args = parser.parse_args()
    try:
        result = subprocess.run(["sudo", "-n", "docker", "inspect", "--", args.backend, args.agent],
                                capture_output=True, check=True, text=True, timeout=15)
        backend, agent = json.loads(result.stdout)
        report = audit(backend, agent)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        print(json.dumps({"wiring_passed": False, "error_code": "DOCKER_AUDIT_UNAVAILABLE"}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report["wiring_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
