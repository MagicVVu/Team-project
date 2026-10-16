#!/usr/bin/env bash
# Upgrade only the backend. Additive migration remains compatible with v0.7.
set -euo pipefail
umask 077
release=/srv/magicvvu/releases/app-v08-20261016
cd /srv/magicvvu/magicvvu-starter
compose() { sudo -n docker compose --env-file deploy/.env -f deploy/compose.yaml "$@"; }
compose config --quiet
python3 - <<'PY'
from pathlib import Path
assert Path('deploy/compose.yaml').read_text().count('image: magicvvu/backend:shopping-v0.7') == 1, 'Unexpected baseline; STOP'
PY
backup=$(mktemp -d "/srv/magicvvu/backups/v08_$(date -u +%Y%m%d_%H%M%S)_XXXXXX")
cp -a backend "$backup/backend"
cp -a deploy/compose.yaml "$backup/compose.yaml"
cp -a deploy/.env "$backup/env.backup"
compose exec -T db sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -h 127.0.0.1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' > "$backup/postgres_before_v08.dump"
test -s "$backup/postgres_before_v08.dump"
compose exec -T db pg_restore -l < "$backup/postgres_before_v08.dump" > "$backup/archive-contents.txt"
printf 'VERIFIED BACKUP: %s\n' "$backup"
cat > "$backup/image-override.yaml" <<'YAML'
services:
  backend:
    image: magicvvu/backend:app-v0.8
YAML
sudo -n docker compose --env-file deploy/.env -f deploy/compose.yaml -f "$backup/image-override.yaml" \
    run --rm --no-deps backend alembic upgrade head
changed=no
rollback() {
    code=$?
    trap - ERR
    if [ "$changed" = yes ]; then
        cp -a "$backup/compose.yaml" deploy/compose.yaml
        mv backend "$backup/failed-v08-backend"
        cp -a "$backup/backend" backend
        # Retain the additive migration so source still describes the live DB.
        cp -a "$release/backend/alembic/versions/20261016_0006_app_inventory.py" backend/alembic/versions/
        compose up -d --no-deps --no-build backend
    fi
    printf 'Upgrade stopped; backup retained at %s. Do not downgrade the database.\n' "$backup" >&2
    exit "$code"
}
trap rollback ERR
changed=yes
cp -a "$release/backend/." backend/
python3 - <<'PY'
from pathlib import Path
p=Path('deploy/compose.yaml')
p.write_text(p.read_text().replace('image: magicvvu/backend:shopping-v0.7','image: magicvvu/backend:app-v0.8'))
PY
compose config --quiet
compose up -d --no-deps --no-build backend
healthy=no
for attempt in $(seq 1 60); do
    if [ "$(sudo -n docker inspect --format '{{.State.Health.Status}}' magicvvu-starter-backend-1)" = healthy ]; then healthy=yes; break; fi
    sleep 1
done
test "$healthy" = yes
curl -fsS --max-time 10 http://127.0.0.1:8000/api/v1/health | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["version"]=="0.8.0" and d["isolated_test"] is False; print(d)'
curl -fsS --max-time 10 http://127.0.0.1:8000/api/v1/ready | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["database"]=="ok"; print(d)'
curl -fsS --max-time 10 http://127.0.0.1:8000/openapi.json | python3 -c '
import sys,json
d=json.load(sys.stdin)
p="/api/v1/households/{household_id}/inventory-items"
assert set(d["paths"][p])=={"get","post"}
assert set(d["paths"][p+"/{item_id}"])=={"patch","delete"}
assert "post" in d["paths"][p+"/{item_id}/adjustments"]
assert "actual_quantity" in d["components"]["schemas"]["PurchaseRequest"]["properties"]
print("APP INVENTORY AND ACTUAL PURCHASE CONTRACT VERIFIED")
'
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8000/api/v1/households/00000000-0000-0000-0000-000000000001/inventory-items)
test "$code" = 401
compose exec -T backend python -m app.ai_agent_smoke
compose exec -T backend alembic current
compose ps
printf 'V0.8 DEPLOYED; BACKUP: %s\n' "$backup"
