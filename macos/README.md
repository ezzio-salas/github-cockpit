# GitHub Cockpit for macOS

A small frameless macOS widget that floats above your windows and shows the open pull
requests waiting on you: the ones you opened, and the ones asking for your review.

It is the macOS build of [GitHub Cockpit](../README.md); the Linux build is the rest of this
repository. Both keep the look and habits of
[Claude Cockpit](https://github.com/ezzio-salas/claude-cockpit).

## Requirements

- macOS 14 or later
- Swift 5.9 or later (Xcode, or the Command Line Tools: `xcode-select --install`)
- The [GitHub CLI](https://cli.github.com), signed in. Check with:

  ```sh
  gh auth status
  gh search prs --author=@me --state=open
  ```

  With Homebrew: `brew install gh && gh auth login`.

## Setup

```sh
git clone https://github.com/ezzio-salas/github-cockpit.git
cd github-cockpit/macos
./build.sh
open GitHubCockpit.app
```

`build.sh` compiles a release build and assembles `GitHubCockpit.app` in the project folder.
The app is self-contained, so you can move it to `/Applications` afterwards.

To start it when you log in, add `GitHubCockpit.app` under
**System Settings → General → Login Items & Extensions → Open at Login**.

## Using it

The app has no Dock icon and no menu bar item; the floating card is the whole interface.

| Action | Result |
| --- | --- |
| Click a row | Opens that pull request in your browser. |
| Rest the pointer on a row | Shows its latest comment beside the card. See [New comments](#new-comments). |
| Click elsewhere on the card | Refreshes now. `SYNC` shows in the header while it reads. |
| Drag the card | Moves it. The position is remembered between launches. |
| Right-click the card | Menu with **Refresh**, **Open GitHub Pull Requests**, **Customize…** and **Quit GitHub Cockpit**. |
| Right-click a row | The card's menu, topped with **Open Pull Request** and **Copy Link**. Copying shows `LINK COPIED` in the header for two seconds. |

The card stays above other windows on every Space, including full-screen apps, and never
takes keyboard focus. Pull requests are re-read every 60 seconds.

| Section | Shows |
| --- | --- |
| `MINE` | Open pull requests you opened, across all of GitHub. |
| `REVIEW` | Open pull requests waiting on your review. |

Each section lists the five most recently updated, and is hidden when it is empty. A draft
pull request is dimmed.

### New comments

When someone comments on one of the pull requests on the card, a speech bubble springs out
beside the card with the comment's author, its first few lines and the pull request it is on,
its tail pointing at that row. It stays until you dismiss it:

| Action | Result |
| --- | --- |
| Click the `×` | Dismisses the bubble. |
| Click the bubble | Opens the comment in your browser and dismisses the bubble. |

Conversation comments, review summaries and inline review comments all count; your own never
do. At launch the bubble shows the newest comment once, so you see where things stand; after
that only a comment newer than any already shown brings it up, and it replaces the one on
screen. Moving the card dismisses it.

Rest the pointer on a row to see that pull request's latest comment in the same bubble,
whoever wrote it. It stays while the pointer is on the row or on the bubble, so you can move
across to click it, and goes away shortly after the pointer leaves both. A new-comment bubble
that was up comes back once the pointer moves away. A pull request without comments shows
nothing.

### When a read fails

The widget only ever shows pull requests it actually read from GitHub.

- If it has an earlier reading, it keeps showing it dimmed, with `STALE · 2m` (time since
  the last good read) in the header. The next successful read clears it.
- If it has no reading yet, it shows one of these instead of the sections:

| Message | Meaning |
| --- | --- |
| `READING PULL REQUESTS` | The first read is in progress. |
| `GH CLI NOT FOUND` | The `gh` executable was not found. See [Troubleshooting](#troubleshooting). |
| `TIMED OUT` | `gh` did not answer within 20 seconds. |
| `NOT SIGNED IN` | `gh` is installed but not signed in. Run `gh auth login`. |
| `COULD NOT READ PRS` | `gh` exited with an error, for example with no network. |
| `UNRECOGNIZED OUTPUT` | `gh` answered, but not with a list of pull requests. |

`NO OPEN PULL REQUESTS` is not a failure — it means both sections are empty.

## Personalizing

The first time the app opens, a **Personalize GitHub Cockpit** window offers four settings.
Close it to keep the defaults; open it again any time with right-click → **Customize…**.

| Setting | Default | Notes |
| --- | --- | --- |
| Title | `GITHUB` | Shown in capitals, up to 14 characters. Leave it blank for the default. |
| Text color | cyan (`#4FE8FF`) | The section titles, the status note and the pull request numbers. |
| Border color | cyan (`#4FE8FF`) | The thin outline of the card. |
| Glow color | cyan (`#4FE8FF`) | The soft halo around the card. |

Changes show on the card as you make them and are saved immediately. The same settings can
be written from the command line; relaunch the app afterwards:

```sh
defaults write local.github-cockpit title "WORK"
defaults write local.github-cockpit accentColor "#B6FF5C"
defaults write local.github-cockpit borderColor "#FF4FD8"
defaults write local.github-cockpit glowColor "#FF9A3D"
```

## Using another GitHub account

`gh` is signed in to one account at a time. To read a different one, point the widget at a
wrapper that selects it, and relaunch:

```sh
defaults write local.github-cockpit cliCommand gh-work
```

The value is either a command name, found the same way `gh` is, or a path to an executable
such as `~/.local/bin/gh-work`. It has to be an executable file; a shell alias will not
work. A small wrapper does the job:

```sh
#!/bin/zsh
# ~/.local/bin/gh-work — the GitHub CLI with a separate config directory
export GH_CONFIG_DIR="$HOME/.config/gh-work"
exec /opt/homebrew/bin/gh "$@"
```

Make it executable with `chmod +x ~/.local/bin/gh-work`, then `gh-work auth login` once. To
go back to the default: `defaults delete local.github-cockpit cliCommand`.

## How it works

Every refresh runs the GitHub CLI twice, without a terminal:

```sh
gh search prs --author=@me           --state=open --limit=5 --sort=updated --json=…
gh search prs --review-requested=@me --state=open --limit=5 --sort=updated --json=…
```

Once the pull requests are on the card, one more call reads their latest comments for the
[comment bubble](#new-comments):

```sh
gh api graphql -f query=… -f ids[]=… -f ids[]=…
```

If that call fails, the card is unaffected; the failure is only logged.

The app makes no network requests of its own and never touches your token; signing in is
entirely `gh`'s business.

## Troubleshooting

**`GH CLI NOT FOUND`** — Apps started from Finder do not inherit your shell's `PATH`. The
widget looks for `gh` in `~/.local/bin`, `/opt/homebrew/bin` and `/usr/local/bin`, then asks
a login `zsh` (`command -v`). Make sure it is in one of those places or on the `PATH` of your
login shell.

**macOS asks for permission at launch** — If the app lives on an external drive, macOS asks
whether GitHub Cockpit may access files on a removable volume. The first read waits behind
that prompt and can show `TIMED OUT`; answer it, then click the card to refresh. The app is
signed ad hoc, so macOS asks again after each rebuild.

**Seeing why a read failed** — Failures are logged. In `zsh`, call `log` by its full path,
because `log` is also a shell builtin:

```sh
/usr/bin/log show --last 10m --predicate 'subsystem == "local.github-cockpit"'
```

## Development

```sh
swift test                # unit tests for everything in CockpitCore
swift run GitHubCockpit   # run without building the .app bundle
./build.sh                # build GitHubCockpit.app
```

Run with `swift run`, the widget uses the system monospaced font, because Orbitron is only
bundled into the `.app`.

| Path | Contents |
| --- | --- |
| `Sources/CockpitCore` | Pull request parsing, the `gh` runner, relative times and the appearance. No UI, fully unit-tested. |
| `Sources/GitHubCockpit` | The AppKit panel, views and the Personalize window. |
| `Tests/CockpitCoreTests` | Unit tests. |
| `../resources` | The Orbitron font and its license, shared with the Linux build. |

## Credits

Labels are set in [Orbitron](https://fonts.google.com/specimen/Orbitron), used under the
SIL Open Font License (`../resources/Orbitron-OFL.txt`).
