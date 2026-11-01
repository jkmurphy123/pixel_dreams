# Running pixel_dreams as a user service

Three example units, matching the style of the other user services on this host
(`daedalus.service`): ordering-only dependencies, journal logging, and a restart policy.
The two Jetson units add `RequiresMountsFor=/mnt/ssd`; the Pi unit does not (the project lives
under the home directory there).

**Nothing here is installed or enabled.** These are files to copy when you want it; the
commands below are yours to run.

| Unit | What it runs | When to use it |
| --- | --- | --- |
| `pixel_dreams.service` | the app **with the display** plus the embedded panel on `0.0.0.0:8090` | a kiosk that boots straight into the wall |
| `pixel_dreams-panel.service` | `--panel-only` — the panel, no pygame, no display | tuning from a laptop while something else drives the wall, or with the wall off |
| `pixel_dreams-pi.service` | the Pi kiosk: `--config configs/modes_config_narrow_horz.json --input rotary` | a Raspberry Pi 1280x400 wall with a rotary encoder |

Only one may bind port 8090 at a time. They are separate files because they solve separate
problems — the app needs a graphical session, the panel-only one deliberately does not.

## Install (a user service)

```bash
mkdir -p ~/.config/systemd/user
cp deploy/pixel_dreams.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pixel_dreams.service
systemctl --user status pixel_dreams.service        # is it up?
```

Linger is already enabled for this user, so the service also starts at boot rather than only
at login:

```bash
loginctl show-user "$USER" --property=Linger       # Linger=yes
loginctl enable-linger "$USER"                     # if it ever needs re-enabling
```

## The panel over the LAN

As shipped, `deploy/pixel_dreams.service` binds the panel to `0.0.0.0` **and** passes
`--panel-open`, so `http://jetsons:8090` opens directly — no token, no cookie to keep. That is a
deliberate choice for a trusted LAN, made once in the unit's command line so it survives every
restart: a gated panel re-arms its gate on any start that leaves the flag out, which is what made
the token request come back the day after it worked.

Say it out loud: with `--panel-open` every device that can reach port 8090 can read **and write**
profiles, i.e. retune the wall. The startup log prints `UNGATED (--panel-open)` and the panel's
status card repeats it.

To put the token gate back, delete `--panel-open` from ExecStart (or run the app yourself without
it) and keep a token in `secrets.json`:

```bash
python3 -c "import json;print(json.load(open('secrets.json'))['panel_token'])"
# then, from another machine:  http://jetsons:8090/?token=<that token>
```

That first visit sets an httpOnly cookie which lasts 60 days. Scripts should send
`X-Panel-Token: <token>` instead — that form is never remembered as a cookie. Note the cookie only
lives as long as the browser keeps it: private windows, "clear cookies on exit" and a different
spelling of the host (`jetsons` vs the IP) each look like a fresh unauthenticated request.

To keep the panel off the network entirely, change `--panel-bind 0.0.0.0` to `127.0.0.1`.

### Starting it by hand

`scripts/run_kiosk.sh` is the same command the unit runs, `--panel-open` included, for starting the
kiosk from a terminal instead of a service:

```bash
./scripts/run_kiosk.sh                 # display :0, LAN panel ungated on :8090
./scripts/run_kiosk.sh --auto 60       # extra flags are appended (last one wins)
```

### Raspberry Pi 1280x400 kiosk

`deploy/pixel_dreams-pi.service` is the Pi variant. It is a **user** unit (a Pi kiosk normally runs
in the `pi` user's graphical session) and it pins two things that must not drift:

- `--config configs/modes_config_narrow_horz.json` — the narrow-horizontal 1280x400 profile
  (20 modes, including Trench Run at slot 17, Cyberspace Matrix at slot 18 and Space Station V at
  slot 19). It outranks `runtime/active_profile.json` and the registry, so another wall's recorded
  switch cannot move this wall, and the panel will not offer a profile switch. The portrait wall keeps
  `configs/modes_config_vert.json`; the two files never overlap.
- `--input rotary` — the encoder. Defaults are A=GPIO17, B=GPIO27, button=GPIO23 and eight
  optional LEDs on 5,6,13,19,26,21,20,16; override with `--rotary-pins`,
  `--rotary-button-pin`, `--rotary-led-pins` in `ExecStart` (BCM numbers, not header pins).

Install it like the other user units, but first edit the display block near the top of the file:

- **X11** (Bullseye/LXDE): keep the shipped `DISPLAY=:0` + `XAUTHORITY=%h/.Xauthority`.
- **Wayland** (Bookworm/labwc): comment those out and uncomment
  `SDL_VIDEODRIVER=wayland` / `XDG_RUNTIME_DIR=/run/user/%U`. If SDL cannot find the socket, run
  `systemctl --user import-environment WAYLAND_DISPLAY` once in the graphical session.

```bash
mkdir -p ~/.config/systemd/user
cp deploy/pixel_dreams-pi.service ~/.config/systemd/user/
# edit ~/.config/systemd/user/pixel_dreams-pi.service for your path, display and flags
systemctl --user daemon-reload
systemctl --user enable --now pixel_dreams-pi.service
journalctl --user-unit pixel_dreams-pi.service -f
```

The unit uses `Restart=always`: a short encoder press exits the app (the documented tap action) and
the kiosk comes back, rather than leaving the wall dark. `systemctl --user stop` is how you stop it
for real. The panel is off; add `--panel-port 8090` (and for the LAN
`--panel-bind 0.0.0.0 --panel-open`) to `ExecStart` if you want it. Do not add
`NoNewPrivileges=true` while `--rotary-hold reboot` is in effect: that blocks the `sudo -n reboot`
the hold runs.

See the README's "Raspberry Pi kiosk with a rotary encoder" for the gpiozero/lgpio install and the
pin table.

## Operating it

```bash
systemctl --user restart pixel_dreams.service       # after a config or code change
systemctl --user stop pixel_dreams.service
journalctl --user-unit pixel_dreams.service -f      # live log (startup says WHICH profile
                                                    # it loaded and why)
journalctl --user-unit pixel_dreams.service -n 100
```

`systemctl --user restart` is rarely needed for tuning: the panel's **Save & Apply** reloads
the config into the running process, the **enable switch** changes the rotation immediately, and
the profile card **switches profiles live**. A restart is for code changes and for picking up a
`--config` or flag change.

## Notes

- The unit starts in **manual** mode on `--start 0`, the profile's first enabled mode: nothing
  advances until you press LEFT/RIGHT on the kiosk keyboard or use the panel's transport buttons /
  mode list. Add `--auto 30` to ExecStart for timed rotation.
- The profiles themselves, the backups (`.backups/`) and the recorded active profile
  (`runtime/active_profile.json`) are all plain files in the project directory, so a service
  restart never loses tuning work.
- If the unit fails immediately, check `journalctl --user-unit ...` for the actual reason: a
  busy port 8090, a missing `secrets.json` token on a LAN bind, and a missing `/mnt/ssd` mount
  are the three that this setup refuses over.
