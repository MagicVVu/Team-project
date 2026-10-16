#!/usr/bin/env bash
# One-time v0.6 -> v0.7 upgrade after the isolated tests pass.
set -euo pipefail
umask 077
release=/srv/magicvvu/releases/shopping-v07-20261016
cd /srv/magicvvu/magicvvu-starter
compose() { sudo -n docker compose --env-file deploy/.env -f deploy/compose.yaml "$@"; }
compose config --quiet
sudo -n docker image inspect magicvvu/backend:shopping-v0.7 > /dev/null
python3 - <<'PY'
from pathlib import Path
text = Path('deploy/compose.yaml').read_text()
assert text.count('image: magicvvu/backend:agent-gateway-v0.6') == 1, 'Unexpected baseline image; STOP'
PY
backup=$(mktemp -d "/srv/magicvvu/backups/v07_$(date -u +%Y%m%d_%H%M%S)_XXXXXX")
cp -a backend "$backup/backend"
cp -a deploy/compose.yaml "$backup/compose.yaml"
cp -a deploy/.env "$backup/env.backup"
sudo -n docker inspect --format '{{.Image}}' magicvvu-starter-backend-1 > "$backup/backend-image-id.txt"
compose exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' \
    > "$backup/postgres_before_v07.dump"
test -s "$backup/postgres_before_v07.dump"
compose exec -T db pg_restore -l < "$backup/postgres_before_v07.dump" > "$backup/archive-contents.txt"
test -s "$backup/archive-contents.txt"
printf 'VERIFIED BACKUP: %s\n' "$backup"
changed=no
rollback_on_error() {
    code=$?
    trap - ERR
    if [ "$changed" = yes ]; then
        printf 'Upgrade verification failed; restoring v0.6 source and Compose config.\n' >&2
        cp -a "$backup/compose.yaml" deploy/compose.yaml
        mv backend "$backup/failed-v07-backend"
        cp -a "$backup/backend" backend
        compose up -d --no-deps --no-build backend
    fi
    exit "$code"
}
trap rollback_on_error ERR
changed=yes
cp -a "$release/backend/." backend/
python3 - <<'PY'
from pathlib import Path
p = Path('deploy/compose.yaml')
text = p.read_text()
p.write_text(text.replace('image: magicvvu/backend:agent-gateway-v0.6', 'image: magicvvu/backend:shopping-v0.7'))
PY
compose config --quiet
compose up -d --no-deps --no-build backend
healthy=no
for attempt in $(seq 1 60); do
    if [ "$(sudo -n docker inspect --format '{{.State.Health.Status}}' magicvvu-starter-backend-1)" = healthy ]; then
        healthy=yes
        break
    fi
    sleep 1
done
test "$healthy" = yes
curl -fsS --max-time 10 http://127.0.0.1:8000/api/v1/health | \
    python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="ok" and d["version"]=="0.7.0"; print(d)'
curl -fsS --max-time 10 http://127.0.0.1:8000/api/v1/ready | \
    python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["database"]=="ok"; print(d)'
curl -fsS --max-time 10 http://127.0.0.1:8000/openapi.json | python3 -c '
import json,sys
d=json.load(sys.stdin)
p="/api/v1/households/{household_id}/shopping-list"
assert "get" in d["paths"][p]
assert set(d["paths"][p+"/items"])=={"get","post"}
assert set(d["paths"][p+"/items/{item_id}"])=={"patch","delete"}
assert "post" in d["paths"][p+"/items/{item_id}/purchase"]
print("SHOPPING OPENAPI VERIFIED")
'
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 \
    http://127.0.0.1:8000/api/v1/households/00000000-0000-0000-0000-000000000001/shopping-list/items)
test "$code" = 401
compose exec -T backend python -m app.ai_agent_smoke
compose ps
printf 'V0.7 DEPLOYED; BACKUP: %s\n' "$backup"
