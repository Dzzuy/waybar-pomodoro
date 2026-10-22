# waybar-pomodoro

Countdown in the top-right of Waybar + an animated terminal view.
Needs: bash, python3, flock (util-linux), a Nerd Font (Omarchy has these). Optional: notify-send, paplay.

## Install

```sh
mkdir -p ~/.config/waybar/scripts
cp pomodoro.sh pomodoro-tui.py ~/.config/waybar/scripts/
chmod +x ~/.config/waybar/scripts/pomodoro*
# paste config.jsonc into ~/.config/waybar/config.jsonc (add "custom/pomodoro" first in modules-right)
cat style.css >> ~/.config/waybar/style.css
omarchy-restart-waybar   # or: pkill waybar; waybar & disown
```

## Use

- Left click: start / pause
- Right click: reset phase (twice = back to session 1)
- Middle click: open the animated terminal
- In the terminal: `space` start/pause, `s` skip, `r` reset, `q` quit

## Terminal on your second monitor (Hyprland)

```ini
# ~/.config/hypr/bindings.conf
bind = SUPER ALT, P, exec, alacritty --class pomodoro -e ~/.config/waybar/scripts/pomodoro-tui.py
# ~/.config/hypr/hyprland.conf
windowrule = monitor 1, class:pomodoro
windowrule = fullscreen, class:pomodoro
```

Using Ghostty/Kitty? Replace `alacritty --class pomodoro -e` with `ghostty --class=pomodoro -e` / `kitty --class pomodoro`.

## Custom durations

Set before Waybar starts (e.g. in `~/.config/uwsm/env`):

```sh
export POMO_WORK=50 POMO_SHORT=10 POMO_LONG=20 POMO_LONG_EVERY=4 POMO_AUTOSTART=1
```
