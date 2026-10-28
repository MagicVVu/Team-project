"""Rotate only the TLS leaf when <30 days remain; retain the internal CA."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


root = Path("/etc/magicvvu/ip-direct")
tls = root / "tls"
initial = "--initial" in sys.argv
if not initial and subprocess.run(["openssl", "x509", "-checkend", "2592000", "-noout", "-in", str(tls / "server.crt")], stdout=subprocess.DEVNULL).returncode == 0:
    sys.exit(0)
run("openssl", "x509", "-checkend", "10368000", "-noout", "-in", str(root / "ca/ca.crt"))
with tempfile.TemporaryDirectory(dir=root) as temp:
    temp = Path(temp)
    ip = (root / "public-ip").read_text().strip()
    (temp / "extensions").write_text(f"subjectAltName=IP:{ip}\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n")
    run("openssl", "req", "-new", "-newkey", "rsa:3072", "-nodes", "-subj", f"/CN={ip}", "-keyout", str(temp / "server.key"), "-out", str(temp / "server.csr"))
    run("openssl", "x509", "-req", "-sha256", "-days", "90", "-in", str(temp / "server.csr"),
        "-CA", str(root / "ca/ca.crt"), "-CAkey", str(root / "ca/ca.key"), "-CAcreateserial",
        "-extfile", str(temp / "extensions"), "-out", str(temp / "server.crt"))
    run("openssl", "verify", "-CAfile", str(root / "ca/ca.crt"), "-verify_ip", ip, str(temp / "server.crt"))
    for name in ("server.key", "server.crt"):
        staged = tls / (name + ".new")
        shutil.copyfile(temp / name, staged)
        os.chown(staged, 10001, 10001)
        staged.chmod(0o400 if name.endswith("key") else 0o444)
        staged.replace(tls / name)
if not initial:
    run("systemctl", "reload", "magicvvu-direct.service")
