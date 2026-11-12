#!/usr/bin/with-contenv bashio
set -e

option() {
    if bashio::config.has_value "$1"; then
        bashio::config "$1"
    else
        printf '%s' "${2:-}"
    fi
}

if bashio::config.true debug; then
    export DEBUG=true
fi

if bashio::config.true scan; then
    exec bluetti-mqtt --scan
fi

read -r -a addresses <<< "$(option bt_mac)"
if (( ${#addresses[@]} == 0 )); then
    bashio::exit.nok "Set bt_mac or enable scan before starting."
fi

host=$(option mqtt_host)
if [[ -z "$host" ]]; then
    if ! bashio::services.available mqtt; then
        bashio::exit.nok "Configure mqtt_host or provide an MQTT service."
    fi
    host=$(bashio::services mqtt host)
    port=$(option mqtt_port "$(bashio::services mqtt port)")
    username=$(option mqtt_username "$(bashio::services mqtt username)")
    password=$(option mqtt_password "$(bashio::services mqtt password)")
else
    port=$(option mqtt_port 1883)
    username=$(option mqtt_username)
    password=$(option mqtt_password)
fi

export BLUETTI_MQTT_PASSWORD="$password"
args=(--broker "$host" --port "$port" --interval "$(bashio::config poll_sec)"
    --ha-config "$(bashio::config ha_config)")
if [[ -n "$username" ]]; then
    args+=("--username=$username")
fi
exec bluetti-mqtt "${args[@]}" "${addresses[@]}"
