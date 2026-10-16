#!/usr/bin/env bash
set -euo pipefail
umask 077
release=/srv/magicvvu/releases/app-v08-20261016
network=magicvvu-app-v08-test
db=magicvvu-app-v08-test-db
backend=magicvvu-app-v08-test-backend
agent=magicvvu-app-v08-test-agent
envfile="$release/.test.env"
python3 - "$envfile" <<'PY'
import pathlib, secrets, sys
password = secrets.token_urlsafe(32)
pathlib.Path(sys.argv[1]).write_text(
    f'POSTGRES_PASSWORD={password}\nDB_PASSWORD={password}\n'
    'POSTGRES_DB=magicvvu_shopping_test\nDB_NAME=magicvvu_shopping_test\nDB_USER=postgres\nDB_HOST=db\n'
    'SHOPPING_TEST_ISOLATED=yes\nISOLATED_APP_TEST=yes\nAUTH_ALLOW_UNVERIFIED_SIGNUP=true\n'
    'AI_SERVICE_URL=http://agent:8767\nBACKEND_BASE_URL=http://backend:8000\nP1_ENGINE=rules\n'
    f'AI_SERVICE_TOKEN={secrets.token_urlsafe(48)}\nBACKEND_TOOL_TOKEN={secrets.token_urlsafe(48)}\n'
)
PY
sudo -n docker network create --internal "$network" > /dev/null
sudo -n docker network create "${network}-access" > /dev/null
sudo -n docker run --rm -d --name "$db" --network "$network" --network-alias db \
    --memory 192m --cpus 0.5 --tmpfs /var/lib/postgresql/data:rw,size=192m \
    --env-file "$envfile" public.ecr.aws/docker/library/postgres:17 > /dev/null
for attempt in $(seq 1 45); do
    if sudo -n docker exec "$db" pg_isready -U postgres -d magicvvu_shopping_test > /dev/null 2>&1; then break; fi
    sleep 1
done
sudo -n docker run --rm --network "$network" --memory 256m --cpus 0.75 --env-file "$envfile" \
    --mount "type=bind,src=$release/backend/tests,dst=/tests,readonly" -e PYTHONPATH=/app \
    magicvvu/backend:app-v0.8 sh -c 'alembic upgrade head && python /tests/check_shopping_postgres.py'
sudo -n docker run --rm -d --name "$backend" --network "${network}-access" \
    -p 127.0.0.1:18081:8000 --memory 256m --cpus 0.75 --env-file "$envfile" \
    magicvvu/backend:app-v0.8 > /dev/null
sudo -n docker network connect --alias backend "$network" "$backend"
sudo -n docker run --rm -d --name "$agent" --network "$network" --network-alias agent \
    --memory 192m --cpus 0.5 --env-file "$envfile" --tmpfs /app/agent/.cache:rw,size=16m,mode=1777 \
    magicvvu/agent:p1-v0.6 > /dev/null
for attempt in $(seq 1 30); do
    if curl -fsS --max-time 2 http://127.0.0.1:18081/api/v1/ready > /dev/null 2>&1; then break; fi
    sleep 1
done
curl -fsS --max-time 5 http://127.0.0.1:18081/api/v1/health
printf '\nISOLATED APP TEST SERVICE READY ON LOOPBACK 18081\n'
