#!/usr/bin/env bash
set -eu

run_app() (
    scenario=$1
    unset BLUETTI_MQTT_PASSWORD
    bashio::config() {
        case "$1" in
            bt_mac)
                if [[ "$scenario" != missing-mac ]]; then
                    printf '%s' '00:11:22:33:44:55 AA:BB:CC:DD:EE:FF'
                fi
                ;;
            mqtt_host) if [[ "$scenario" == external ]]; then printf '%s' 'external-broker'; fi ;;
            mqtt_username) if [[ "$scenario" == external ]]; then printf '%s' 'user name'; fi ;;
            mqtt_password) if [[ "$scenario" == external ]]; then printf '%s' 'password with spaces'; fi ;;
            poll_sec) printf '%s' 15 ;;
            ha_config) printf '%s' normal ;;
        esac
    }
    bashio::config.has_value() { [[ -n "$(bashio::config "$1")" ]]; }
    bashio::config.true() { [[ "$1" == scan && "$scenario" == scan ]]; }
    bashio::services.available() { [[ "$scenario" == supervisor ]]; }
    bashio::services() {
        [[ "$scenario" == supervisor && "$1" == mqtt ]] || exit 99
        case "$2" in
            host) printf '%s' 'internal-broker' ;;
            port) printf '%s' 1884 ;;
            username) printf '%s' 'service-user' ;;
            password) printf '%s' 'service-password' ;;
        esac
    }
    bashio::exit.nok() { printf '%s\n' "$1"; exit 1; }
    exec() {
        printf '<%s>' "$@"
        printf '\n%s\n' "${BLUETTI_MQTT_PASSWORD:-}"
        exit 0
    }
    source ./run.sh
)

scan=$(run_app scan)
[[ "$scan" == '<bluetti-mqtt><--scan>' ]]
addresses='<00:11:22:33:44:55><AA:BB:CC:DD:EE:FF>'
options='<--interval><15><--ha-config><normal>'
external=$(run_app external)
expected="<bluetti-mqtt><--broker><external-broker><--port><1883>$options<--username=user name>$addresses"
[[ "$external" == "$expected"$'\npassword with spaces' ]]
supervisor=$(run_app supervisor)
expected="<bluetti-mqtt><--broker><internal-broker><--port><1884>$options<--username=service-user>$addresses"
[[ "$supervisor" == "$expected"$'\nservice-password' ]]
if run_app missing-mac || run_app missing-broker; then
    exit 1
fi
printf '%s\n' 'App startup: scan, external MQTT, Supervisor MQTT and missing configuration checks passed.'
