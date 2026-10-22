#!/usr/bin/env bash
# Waybar Pomodoro — pomodoro.sh {status|toggle|reset|skip|tui}
# Env overrides: POMO_WORK POMO_SHORT POMO_LONG (minutes), POMO_LONG_EVERY, POMO_AUTOSTART (1/0), POMO_SIGNAL
WORK=${POMO_WORK:-25}
SHORT=${POMO_SHORT:-5}
LONG=${POMO_LONG:-15}
EVERY=${POMO_LONG_EVERY:-4}
AUTOSTART=${POMO_AUTOSTART:-1}
SIGNAL=${POMO_SIGNAL:-8}

DIR="${XDG_CACHE_HOME:-$HOME/.cache}/waybar-pomodoro"
F="$DIR/state"
mkdir -p "$DIR"
exec 9>"$DIR/lock"
flock 9

dur() { case $1 in short) echo $((SHORT * 60)) ;; long) echo $((LONG * 60)) ;; *) echo $((WORK * 60)) ;; esac; }
load() {
  MODE=work STATUS=idle END=0 REMAIN=$(dur work) COUNT=0
  [[ -f $F ]] && . "$F"
}
save() { printf 'MODE=%s\nSTATUS=%s\nEND=%s\nREMAIN=%s\nCOUNT=%s\n' "$MODE" "$STATUS" "$END" "$REMAIN" "$COUNT" >"$F.tmp" && mv "$F.tmp" "$F"; }
refresh() { pkill -RTMIN+"$SIGNAL" waybar 2>/dev/null; }
left() { if [[ $STATUS == running ]]; then echo $((END - $(date +%s))); else echo "$REMAIN"; fi; }

advance() {
  if [[ $MODE == work ]]; then
    COUNT=$((COUNT + 1))
    if ((COUNT % EVERY == 0)); then MODE=long; else MODE=short; fi
  else
    MODE=work
  fi
  REMAIN=$(dur "$MODE")
  if [[ $AUTOSTART == 1 ]]; then STATUS=running END=$(($(date +%s) + REMAIN)); else STATUS=idle END=0; fi
}

alert() {
  local title body
  case $MODE in
    work)  title="Focus" body="Session $((COUNT % EVERY + 1)) of $EVERY. Let's go." ;;
    short) title="Short break" body="Stand up, stretch, drink water." ;;
    long)  title="Long break" body="$COUNT sessions done. You earned it." ;;
  esac
  command -v notify-send >/dev/null && notify-send -a Pomodoro -i alarm-symbolic "$title" "$body" 9>&-
  if command -v paplay >/dev/null; then
    for s in /usr/share/sounds/freedesktop/stereo/complete.oga /usr/share/sounds/freedesktop/stereo/bell.oga; do
      [[ -f $s ]] && { paplay "$s" 9>&- & break; }
    done
  fi
}

load
case ${1:-status} in
  toggle)
    if [[ $STATUS == running ]]; then REMAIN=$(left) STATUS=paused
    else END=$(($(date +%s) + REMAIN)) STATUS=running; fi
    save; refresh ;;
  reset)
    # first reset = restart current phase; reset again while idle = back to session 1
    if [[ $STATUS == idle && $REMAIN == "$(dur "$MODE")" ]]; then MODE=work COUNT=0; fi
    STATUS=idle END=0 REMAIN=$(dur "$MODE")
    save; refresh ;;
  skip)
    advance; save; alert; refresh ;;
  tui)
    exec 9>&-
    exec "$(dirname "$(readlink -f "$0")")/pomodoro-tui.py" ;;
  status)
    L=$(left)
    if [[ $STATUS == running ]] && ((L <= 0)); then advance; save; alert; L=$(left); fi
    ((L < 0)) && L=0
    TOTAL=$(dur "$MODE")
    PCT=$(((TOTAL - L) * 100 / TOTAL))
    case $MODE in
      work)  ICON=$'\uf017' LABEL="Focus" ;;
      short) ICON=$'\uf0f4' LABEL="Short break" ;;
      long)  ICON=$'\uf0f4' LABEL="Long break" ;;
    esac
    [[ $STATUS == paused ]] && ICON=$'\uf04c'
    [[ $STATUS == idle ]] && ICON=$'\uf04b'
    CLS="\"$MODE\",\"$STATUS\""
    [[ $STATUS == running ]] && ((L <= 60)) && CLS+=',"ending"'
    DONE=$((COUNT % EVERY))
    [[ $MODE == long && $DONE == 0 && $COUNT -gt 0 ]] && DONE=$EVERY
    DOTS=""
    for ((i = 0; i < EVERY; i++)); do if ((i < DONE)); then DOTS+="●"; else DOTS+="○"; fi; done
    TIP="$LABEL · $STATUS\\n$DOTS  $COUNT done today\\n\\nLeft: start/pause · Right: reset · Middle: terminal"
    printf '{"text":"%s %02d:%02d","alt":"%s","tooltip":"%s","class":[%s],"percentage":%d}\n' \
      "$ICON" $((L / 60)) $((L % 60)) "$MODE" "$TIP" "$CLS" "$PCT" ;;
  *)
    echo "usage: $0 {status|toggle|reset|skip|tui}" >&2; exit 1 ;;
esac
