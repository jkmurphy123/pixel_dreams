# Running pixel_dreams as a user service

Two example units, matching the style of the other user services on this host
(`daedalus.service`): ordering-only dependencies, `RequiresMountsFor=/mnt/ssd`, journal
logging, `Restart=on-failure`.

**Nothing here is installed or enabled.** These are files to copy when you want it; the
commands below are yours to run.

| Unit | What it runs | When to use it |
| --- | --- | --- |
| `pixel_dreams.service` | the app **with the display** plus the embedded panel on `0.0.0.0:8090` | a kiosk that boots straight into the wall |
| `pixel_dreams-panel.service` | `--panel-only` — the panel, no pygame, no display | tuning from a laptop while something else drives the wall, or with the wall off |

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

`--panel-bind 0.0.0.0` requires `panel_token` in `secrets.json`; without it the controller
refuses to start rather than exposing an unauthenticated control surface. To read the token and
open the panel once:

```bash
python3 -c "import json;print(json.load(open('secrets.json'))['panel_token'])"
# then, from another machine:  http://jetsons:8090/?token=<that token>
```

That first visit sets an httpOnly cookie which lasts 60 days. Scripts should send
`X-Panel-Token: <token>` instead — that form is never remembered as a cookie.

To keep the panel off the network entirely, change `--panel-bind 0.0.0.0` to `127.0.0.1`.

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

- `--auto 30` in the unit is the rotation interval; remove it for manual LEFT/RIGHT control.
- The profiles themselves, the backups (`.backups/`) and the recorded active profile
  (`runtime/active_profile.json`) are all plain files in the project directory, so a service
  restart never loses tuning work.
- If the unit fails immediately, check `journalctl --user-unit ...` for the actual reason: a
  busy port 8090, a missing `secrets.json` token on a LAN bind, and a missing `/mnt/ssd` mount
  are the three that this setup refuses over.
