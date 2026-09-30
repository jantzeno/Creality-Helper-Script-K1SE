#!/bin/sh

set -e

remove_creality_web_interface_message() {
  top_line
  title 'Remove Creality Web Interface' "$yellow"
  inner_line
  hr
  printf ' │ %-62s │\n' "Replaces Creality Web Interface with Fluidd or Mainsail on"
  printf ' │ %-62s │\n' "port 80. Creality Print Wi-Fi printing becomes unavailable."
  hr
  bottom_line
}

restore_creality_web_interface_message() {
  top_line
  title 'Restore Creality Web Interface' "$yellow"
  inner_line
  hr
  printf ' │ %-62s │\n' "This restores Creality Web Interface on port 80."
  hr
  bottom_line
}

web_interface_config() {
  # ponytail: only edit the helper's listener layout; reject custom layouts
  # rather than maintaining a general Nginx parser.
  awk -v target="$2" '
    {
      line = $0
      sub(/[[:space:]]*#.*/, "", line)
      if (line ~ /^[[:space:]]*listen[[:space:]]+440[89][[:space:]]+default_server;[[:space:]]*$/) {
        port = line
        sub(/^[[:space:]]*listen[[:space:]]+/, "", port)
        sub(/[[:space:]].*$/, "", port)
        seen[port]++
        previous = port
        print
        if (port == target) print "        listen 80;"
        next
      }
      if (line ~ /^[[:space:]]*listen[[:space:]]+80;[[:space:]]*$/ && previous) {
        owners++
        previous = ""
        next
      }
      if (line ~ /^[[:space:]]*listen[[:space:]]+([^ ;]*:)?80([[:space:];]|$)/) invalid = 1
      if (line ~ /[^[:space:]]/) previous = ""
      print
    }
    END {
      if (seen[4408] != 1 || seen[4409] != 1 || owners > 1 || invalid) exit 1
    }
  ' "$1"
}

# A subshell keeps transaction variables and signal traps out of the menu.
web_interface_change() (
  target="$1"
  nginx="$NGINX_FOLDER/sbin/nginx"
  config="$NGINX_FOLDER/nginx/nginx.conf"
  if [ "$model" = "3V3" ]; then
    nginx=$(command -v nginx) || exit 1
    config=/etc/nginx/nginx.conf
  fi
  service_dir=$(dirname "$CREALITY_WEB_FILE")
  expected=
  case "$target" in
    mainsail) port=4409; expected="$MAINSAIL_FOLDER/index.html";;
    fluidd) port=4408; expected="$FLUIDD_FOLDER/index.html";;
    creality) port=0;;
    *) echo "Unknown web interface: $target" >&2; exit 1;;
  esac
  if [ ! -x "$nginx" ] || [ ! -x "$CURL" ] || [ ! -f "$config" ] || [ -L "$config" ]; then
    echo "Missing Nginx/curl, or unsupported configuration path: $config" >&2
    exit 1
  fi
  if [ "$target" = creality ]; then
    if [ ! -f "$INITD_FOLDER/S99start_app" ] || [ -d "$GUPPY_SCREEN_FOLDER" ]; then
      echo "Restore the stock startup service and remove Guppy Screen first." >&2
      exit 1
    fi
  elif [ ! -s "$expected" ]; then
    echo "Missing installed interface: $expected" >&2
    exit 1
  fi

  mkdir -p "$HS_BACKUP_FOLDER/web-interface" || exit 1
  backup=$(mktemp -d "$HS_BACKUP_FOLDER/web-interface/change.XXXXXX") || exit 1
  candidate=
  changed=0

  fetch_page() {
    rm -f "$backup/response" || return 1
    "$CURL" -q --noproxy '*' --silent --show-error --fail --max-time 2 \
      --output "$backup/response" --write-out '%{http_code}' \
      "http://127.0.0.1:$1/" 2>"$backup/http-error"
  }

  wait_page() {
    local attempt code
    attempt=0
    while [ "$attempt" -lt 5 ]; do
      if code=$(fetch_page "$1") && [ "$code" = 200 ] && [ -s "$backup/response" ]; then
        if [ -z "$2" ] || cmp -s "$backup/response" "$2"; then
          return 0
        fi
      fi
      attempt=$((attempt + 1))
      [ "$attempt" -eq 5 ] || sleep 1
    done
    echo "HTTP verification failed on port $1 (status $code)." >&2
    cat "$backup/http-error" >&2
    return 1
  }

  wait_free() {
    local attempt status
    attempt=0
    while [ "$attempt" -lt 5 ]; do
      if "$CURL" -q --noproxy '*' --silent --max-time 2 --output /dev/null \
        http://127.0.0.1:80/ 2>"$backup/http-error"; then
        status=0
      else
        status=$?
      fi
      # Only connection refusal proves the old listener has gone away.
      [ "$status" -eq 7 ] && return 0
      attempt=$((attempt + 1))
      [ "$attempt" -eq 5 ] || sleep 1
    done
    echo "Port 80 was not released; refusing to start the stock web server." >&2
    return 1
  }

  stop_stock() {
    local name attempt
    for name in Monitor web-server; do
      if pidof "$name" >/dev/null 2>&1; then
        killall -q "$name" || { echo "Could not stop $name." >&2; return 1; }
        attempt=0
        while pidof "$name" >/dev/null 2>&1; do
          [ "$attempt" -lt 5 ] || { echo "$name did not stop." >&2; return 1; }
          sleep 1
          attempt=$((attempt + 1))
        done
      fi
    done
  }

  reload_nginx() {
    "$nginx" -t -c "$config" >>"$backup/nginx.log" 2>&1 &&
      "$nginx" -c "$config" -s reload >>"$backup/nginx.log" 2>&1
  }

  restore_names() {
    local name state running file
    while read -r name state running; do
      file="$service_dir/$name"
      case "$state" in
        enabled) [ ! -e "$file.disabled" ] || mv "$file.disabled" "$file" || return 1;;
        disabled) [ ! -e "$file" ] || mv "$file" "$file.disabled" || return 1;;
      esac
    done <"$backup/services"
  }

  start_stock() {
    local name state running file attempt
    while read -r name state running; do
      file="$service_dir/$name"
      if [ "$1" = restore ]; then
        [ ! -e "$file.disabled" ] || mv "$file.disabled" "$file" || return 1
        [ -x "$file" ] || continue
      else
        [ "$running" = 1 ] || continue
      fi
      "$file" >/dev/null 2>&1 &
      attempt=0
      until pidof "$name" >/dev/null 2>&1; do
        [ "$attempt" -lt 5 ] || { echo "Could not start $name." >&2; return 1; }
        sleep 1
        attempt=$((attempt + 1))
      done
    done <"$backup/services"
  }

  rollback() {
    stop_stock || return 1
    cp -p "$backup/nginx.conf" "$config" || return 1
    restore_names || return 1
    reload_nginx || return 1
    if [ "$web_running" = 1 ]; then
      wait_free || return 1
    fi
    start_stock rollback || return 1
    if [ "$web_running" = 1 ]; then
      wait_page 80 "" || return 1
    elif [ "$before_http" = 1 ]; then
      wait_page 80 "$backup/before.html" || return 1
    fi
  }

  finish() {
    local status=$?
    trap - EXIT HUP INT TERM
    if [ "$status" -ne 0 ]; then
      # Recovery makes its own requests; keep the failed response for diagnosis.
      [ ! -f "$backup/response" ] || cp "$backup/response" "$backup/failed-response" || :
      [ ! -f "$backup/http-error" ] || cp "$backup/http-error" "$backup/failed-http-error" || :
      if [ "$changed" = 1 ]; then
        if rollback; then
          echo "Previous configuration and stock service state restored." >&2
        else
          echo "Automatic recovery failed. Backup and diagnostics: $backup" >&2
        fi
      fi
      [ ! -f "$backup/nginx.log" ] || cat "$backup/nginx.log" >&2
      echo "Backup and diagnostics: $backup" >&2
    else
      rm -f "$backup/response" "$backup/before.html" "$backup/http-error"
    fi
    [ -z "$candidate" ] || rm -f "$candidate"
    exit "$status"
  }
  trap finish EXIT
  trap 'exit 1' HUP INT TERM

  cp -p "$config" "$backup/nginx.conf" || exit 1
  web_running=0
  for name in web-server Monitor; do
    file="$service_dir/$name"
    state=missing
    if [ -e "$file" ] && [ -e "$file.disabled" ]; then
      echo "Both $file and $file.disabled exist; refusing to overwrite either." >&2
      exit 1
    fi
    if [ -e "$file" ]; then
      [ -x "$file" ] || exit 1
      state=enabled
    elif [ -e "$file.disabled" ]; then
      [ -x "$file.disabled" ] || exit 1
      state=disabled
    fi
    running=0
    if pidof "$name" >/dev/null 2>&1; then
      if [ "$state" != enabled ]; then
        echo "Unexpected running service without an enabled executable: $name" >&2
        exit 1
      fi
      running=1
    fi
    if [ "$name" = web-server ]; then
      [ "$state" != missing ] || { echo "Missing stock web-server executable." >&2; exit 1; }
      web_running="$running"
    fi
    printf '%s %s %s\n' "$name" "$state" "$running" >>"$backup/services" || exit 1
  done

  candidate=$(mktemp "$config.XXXXXX") || exit 1
  cp -p "$config" "$candidate" || exit 1
  if ! web_interface_config "$config" "$port" >"$candidate"; then
    echo "Unrecognized or ambiguous Nginx listener layout; nothing changed." >&2
    exit 1
  fi
  "$nginx" -t -c "$config" >"$backup/nginx.log" 2>&1 || exit 1
  "$nginx" -t -c "$candidate" >>"$backup/nginx.log" 2>&1 || exit 1
  if [ "$port" != 0 ]; then
    wait_page "$port" "$expected" || exit 1
  fi
  before_http=0
  if code=$(fetch_page 80) && [ "$code" = 200 ] && [ -s "$backup/response" ]; then
    cp "$backup/response" "$backup/before.html" || exit 1
    before_http=1
  fi

  echo "Backup saved: $backup"
  # Mark before the first mutation so partial moves and signals also roll back.
  changed=1
  if [ "$target" != creality ]; then
    for name in Monitor web-server; do
      file="$service_dir/$name"
      [ ! -e "$file" ] || mv "$file" "$file.disabled" || exit 1
    done
  fi
  stop_stock || exit 1
  mv "$candidate" "$config" || exit 1
  candidate=
  reload_nginx || exit 1
  if [ "$target" = creality ]; then
    wait_free || exit 1
    start_stock restore || exit 1
    pidof web-server >/dev/null 2>&1 || exit 1
  fi
  wait_page 80 "$expected" || exit 1
  exit 0
)

web_interface_result() {
  local target port address
  target="$1"
  if web_interface_change "$target"; then
    address=$(check_ipaddress)
    ok_msg "$target is verified on port 80."
    echo "Open http://$address/"
    case "$target" in
      mainsail) port=4409;;
      fluidd) port=4408;;
      creality) port=;;
    esac
    [ -z "$port" ] || echo "Also available at http://$address:$port/"
    echo "If the old interface still appears, try a private window, then clear"
    echo "cached files/site data for the printer's IP."
  else
    error_msg "Web interface change failed. See the diagnostics above."
  fi
  return 0
}

remove_creality_web_interface() {
  remove_creality_web_interface_message
  local yn interface_choice
  while true; do
    remove_msg "Creality Web Interface" yn
    case "$yn" in
      Y|y) break;;
      N|n) error_msg "Deletion canceled!"; return 0;;
      *) error_msg "Please select a correct choice!";;
    esac
  done
  if [ -d "$FLUIDD_FOLDER" ] && [ -d "$MAINSAIL_FOLDER" ]; then
    while true; do
      read -r -p "Default interface on port 80 (fluidd/mainsail): " interface_choice || return 0
      case "$interface_choice" in
        FLUIDD|fluidd) interface_choice=fluidd; break;;
        MAINSAIL|mainsail) interface_choice=mainsail; break;;
        *) error_msg "Please select a correct choice!";;
      esac
    done
  elif [ -d "$MAINSAIL_FOLDER" ]; then
    interface_choice=mainsail
  elif [ -d "$FLUIDD_FOLDER" ]; then
    interface_choice=fluidd
  else
    error_msg "Install Fluidd or Mainsail first."
    return 0
  fi
  web_interface_result "$interface_choice"
}

restore_creality_web_interface() {
  restore_creality_web_interface_message
  local yn
  while true; do
    restore_msg "Creality Web Interface" yn
    case "$yn" in
      Y|y) web_interface_result creality; return 0;;
      N|n) error_msg "Restoration canceled!"; return 0;;
      *) error_msg "Please select a correct choice!";;
    esac
  done
}
