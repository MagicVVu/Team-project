"""Run as root on the TLS host; credentials stay in RAM on the server.

Creates one uniquely marked synthetic user through the real HTTPS API, then
removes only that user and its sessions in finally. No household/inventory writes.
Uses the existing private CA with full certificate and IP verification.
"""
import json
import http.client
import secrets
import string
import socket
import ssl
import subprocess
from uuid import uuid4

origin = "https://8.134.172.165:8000"
context = ssl.create_default_context(cafile="/etc/magicvvu/ip-direct/ca/ca.crt")
phone = "+1999" + str(secrets.randbelow(10**8)).zfill(8)
marker = "auth-acceptance-" + uuid4().hex
password = "T7" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
checks = {}
completed = False
attempted = False
tls_established = False
error_type = None


class LocalTLSConnection(http.client.HTTPSConnection):
    def connect(self):
        # The cloud public IP cannot hairpin back to this host. Reach the same
        # published TLS listener over loopback, verifying the real IP identity.
        transport = socket.create_connection(("127.0.0.1", 8000), timeout=self.timeout)
        self.sock = self._context.wrap_socket(transport, server_hostname=self.host)


def request(method, path, payload=None, token=None):
    global tls_established
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    connection = LocalTLSConnection("8.134.172.165", 8000, timeout=12, context=context)
    try:
        connection.request(method, path, body=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        tls_established = True
        response = connection.getresponse()
        return response.status, json.load(response)
    finally:
        connection.close()


def check(name, condition):
    checks[name] = bool(condition)
    if not condition:
        raise AssertionError(name)


try:
    check("tls_health_200", request("GET", "/health")[0] == 200)
    check("anonymous_profile_401", request("GET", "/api/v1/users/me")[0] == 401)
    for path in ("/docs", "/openapi.json", "/api/v1/ready", "/internal/v1/inventory/search"):
        check("public_blocks_" + path, request("GET", path)[0] == 404)
    credentials = {"phone": phone, "password": password}
    payload = {**credentials, "display_name": marker}
    check("invalid_signup_422", request("POST", "/api/v1/auth/register", {**payload, "password": "short"})[0] == 422)
    attempted = True
    status, user = request("POST", "/api/v1/auth/register", payload)
    check("register_201", status == 201)
    check("phone_unverified", user["phone_verified"] is False)
    check("no_password_in_response", not ({"password", "password_hash"} & user.keys()))
    check("duplicate_signup_409", request("POST", "/api/v1/auth/register", payload)[0] == 409)
    check("wrong_password_401", request("POST", "/api/v1/auth/login", {**credentials, "password": "wrong"})[0] == 401)
    status, login = request("POST", "/api/v1/auth/login", credentials)
    check("login_200", status == 200)
    check("token_contract", login["token_type"] == "bearer" and login["expires_in"] == 43200)
    token = login["access_token"]
    status, me = request("GET", "/api/v1/users/me", token=token)
    check("profile_identity_matches", status == 200 and me["id"] == user["id"] and me["display_name"] == marker)
    status, households = request("GET", "/api/v1/households", token=token)
    check("new_user_households_empty", status == 200 and households == [])
    check("logout_200", request("POST", "/api/v1/auth/logout", token=token)[0] == 200)
    check("revoked_token_401", request("GET", "/api/v1/users/me", token=token)[0] == 401)
    completed = True
except Exception as error:
    error_type = type(error).__name__
finally:
    if attempted:
        # Exact random phone + marker, checked together; never touch existing users.
        cleanup = '''import json, sys
from sqlalchemy import select, delete, func
from app.database import SessionLocal
from app.models import User, AuthSession, HouseholdMember, Household
identity=json.load(sys.stdin)
with SessionLocal.begin() as db:
 user=db.scalar(select(User).where(User.phone==identity['phone'], User.display_name==identity['marker']))
 if user is not None:
  assert db.scalar(select(func.count()).select_from(HouseholdMember).where(HouseholdMember.user_id==user.id)) == 0
  assert db.scalar(select(func.count()).select_from(Household).where(Household.created_by_user_id==user.id)) == 0
  db.execute(delete(AuthSession).where(AuthSession.user_id==user.id))
  db.execute(delete(User).where(User.id==user.id, User.phone==identity['phone'], User.display_name==identity['marker']))
with SessionLocal() as db:
 assert db.scalar(select(User.id).where(User.phone==identity['phone'], User.display_name==identity['marker'])) is None
print(json.dumps({'temporary_user_and_sessions_removed':True}))
'''
        result = subprocess.run(["docker", "exec", "-i", "magicvvu-starter-backend-1", "python", "-c", cleanup], input=json.dumps({"phone": phone, "marker": marker}), text=True, capture_output=True, timeout=25)
        checks["temporary_user_and_sessions_removed"] = result.returncode == 0 and json.loads(result.stdout).get("temporary_user_and_sessions_removed") is True
    print(json.dumps({"origin": origin, "transport": "server loopback to published TLS listener", "certificate_verified": tls_established, "error_type": error_type, "checks": checks, "passed": completed and all(checks.values())}, sort_keys=True))
    if not completed or not all(checks.values()):
        raise SystemExit(1)
