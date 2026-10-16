#!/usr/bin/env bash
# Isolated PostgreSQL verification. Does not attach production networks/volumes.
set -euo pipefail
umask 077
release=/srv/magicvvu/releases/shopping-v07-20261016
test_db=magicvvu-shopping-v07-test-db
test_env=$(mktemp /tmp/magicvvu-shopping-test.XXXXXX)
python3 - "$test_env" <<'PY'
import pathlib, secrets, sys
password = secrets.token_urlsafe(32)
pathlib.Path(sys.argv[1]).write_text(
    'POSTGRES_PASSWORD=' + password + '\nDB_PASSWORD=' + password + '\n'
    'POSTGRES_DB=magicvvu_shopping_test\nDB_NAME=magicvvu_shopping_test\n'
    'DB_USER=postgres\nDB_HOST=127.0.0.1\nSHOPPING_TEST_ISOLATED=yes\n'
)
PY
sudo -n docker run --rm -d --name "$test_db" --network none \
    --memory 192m --cpus 0.5 --tmpfs /var/lib/postgresql/data:rw,size=192m \
    --env-file "$test_env" public.ecr.aws/docker/library/postgres:17 > /dev/null
cleanup() {
    sudo -n docker stop "$test_db" > /dev/null
    rm -f "$test_env"
}
trap cleanup EXIT
ready=no
for attempt in $(seq 1 45); do
    if sudo -n docker exec "$test_db" pg_isready -h 127.0.0.1 -U postgres -d magicvvu_shopping_test > /dev/null 2>&1; then
        ready=yes
        break
    fi
    sleep 1
done
test "$ready" = yes
sudo -n docker run --rm --network "container:$test_db" \
    --memory 256m --cpus 0.75 --read-only --tmpfs /tmp:rw,size=32m,mode=1777 \
    --env-file "$test_env" -e PYTHONPATH=/app \
    --mount "type=bind,src=$release/backend/tests,dst=/tests,readonly" \
    magicvvu/backend:shopping-v0.7 \
    sh -c 'alembic upgrade head && python /tests/check_shopping_postgres.py'
printf 'ISOLATED POSTGRESQL SHOPPING TESTS PASSED\n'
