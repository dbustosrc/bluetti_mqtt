#!/usr/bin/env bash
set -eu
image=$1
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT

docker run --rm --entrypoint /bin/sh "$image" -c 'bluetoothctl --version && python -m pip check'
printf '#!/command/with-contenv sh\nprintf "Bridge lifecycle test started\\n"\nexit "$APP_EXIT_CODE"\n' > "$test_dir/run.sh"
chmod 755 "$test_dir/run.sh"

for expected in 0 7; do
    actual=0
    docker run --rm -e APP_EXIT_CODE="$expected" \
        --mount "type=bind,src=$test_dir/run.sh,dst=/run.sh,readonly" \
        "$image" > "$test_dir/log" 2>&1 || actual=$?
    cat "$test_dir/log"
    [[ "$actual" -eq "$expected" ]]
    [[ $(grep -c 'Bridge lifecycle test started' "$test_dir/log") -eq 1 ]]
    ! grep -q 's6-rc.d is empty' "$test_dir/log"
done
printf '%s\n' 'Container: BlueZ tools, single service startup and exit status checks passed.'
