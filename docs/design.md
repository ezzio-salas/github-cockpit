# GitHub Cockpit — Design

Date: 2026-10-05

## Purpose

A small, frameless, always-on-top Linux widget that shows the open pull requests waiting on
you — the ones you opened and the ones asking for your review — without opening a browser
or a terminal.

It is the sibling of [Claude Cockpit](https://github.com/ezzio-salas/claude-cockpit) and
keeps its look and its habits: the same dark glass card, the same cyan, the same Orbitron
labels, the same refusal to show a number it did not read.

Success: the card floats above other windows, lists the pull requests that need attention
with the repository under each one, opens a pull request when you click it, and keeps
itself up to date.

## Scope

In scope:

- One floating card with a section per list: `MINE` and `REVIEW`.
- A click on a row opens that pull request in the browser.
- Automatic refresh, manual refresh, quit, a remembered position.

Out of scope: a settings window (the config file is the interface), issues, review state,
CI status, notifications, comment counts, more than one account, a queue long enough to
scroll.

## Data source

The widget runs the GitHub CLI, which is already signed in:

```sh
gh search prs --author=@me          --state=open --limit=5 --sort=updated --json=…
gh search prs --review-requested=@me --state=open --limit=5 --sort=updated --json=…
```

- `gh search prs` searches all of GitHub, so the card is not tied to one repository or to
  the current working directory.
- `--json=number,title,repository,url,isDraft,updatedAt` asks only for what the card draws.
- `GH_PAGER=cat` and `NO_COLOR=1` are set, because a pager or color codes would corrupt the
  JSON. stdin is `/dev/null`, so a CLI that decides to prompt fails fast instead of hanging.
- Authentication is whatever `gh` already has; the widget never touches a token.

Example answer:

```json
[{"isDraft":false,"number":44,
  "repository":{"name":"material-tailwind","nameWithOwner":"ezzio-salas/material-tailwind"},
  "title":"[Snyk] Security upgrade next from 10.2.3 to 15.5.10",
  "updatedAt":"2026-02-01T12:05:49Z",
  "url":"https://github.com/ezzio-salas/material-tailwind/pull/44"}]
```

## Structure

Python with PyGObject and GTK4, no build step. The split follows Claude Cockpit's:
`cockpit_core` is pure logic and fully unit-tested, `github_cockpit` is the GTK card.

```
github-cockpit/
  run.sh                        # run from the checkout
  install.sh                    # launcher, desktop entry and font into ~/.local
  resources/Orbitron.ttf, Orbitron-OFL.txt
  src/
    cockpit_core/               # pure logic, unit-tested
      pull_request.py
      pr_fetcher.py
      relative_time.py
      appearance.py
    github_cockpit/             # the card
      __main__.py
      app.py
      panel.py
      view.py
      pr_row.py
      theme.py
      fonts.py
  tests/
```

### cockpit_core

**`PullRequest`** — a frozen dataclass: `number`, `title`, `repo` (`owner/name`), `url`,
`is_draft`, `updated_at`. `reference` is the `#412` the card shows beside the title.

**`parse`** — `parse(text) -> list[PullRequest]`.

- A row missing a number, title, repository or url is skipped rather than guessed at, so a
  change in `gh`'s output costs at most a row, never the card.
- An unreadable `updatedAt` leaves the age blank; the rest of the row still draws.
- An empty array is an empty list, which is a normal state. A reply that is not a JSON
  array raises `ParseError`, because the card has to tell "nothing to show" apart from
  "could not read".

**`PullRequestFetcher`** — runs `gh` and returns its raw answer.

- The command is `gh` by default and can be changed in the config file, for example to a
  wrapper that selects another account.
- Resolved on each fetch, so a CLI installed while the widget runs is picked up. A value
  containing `/` is a path; a bare name is looked up in `~/.local/bin`, mise's shims,
  `/usr/local/bin` and `/usr/bin`, then on `PATH` — launchers do not always inherit a login
  shell's `PATH`.
- 20s timeout. Failures are typed: `CliNotFound`, `TimedOut`, `NotAuthenticated`,
  `CommandFailed`, so the card can say which one happened.

**`relative_time`** — `compact(seconds)` gives `30s`, `5m`, `3h`, `2d` for the stale marker;
`age(moment, now)` gives `JUST NOW`, `5M AGO`, `2D AGO` for a row. A moment in the future
reads as `JUST NOW`, because a clock a little out of step should not look like a bug.

**`HexColor` / `CockpitAppearance` / `AppearanceStore`** — the title and three colors, as in
Claude Cockpit. Linux has no `defaults`, so they live in
`~/.config/github-cockpit/config.json`, written through a temporary file so an interrupted
save cannot leave a half file. An unreadable file, or one unreadable value in it, falls back
to the default rather than stopping the widget: the card is the only interface, so it has to
come up.

### github_cockpit (UI)

**Window** — a `Gtk.ApplicationWindow`, undecorated, made a layer surface by
[gtk4-layer-shell](https://github.com/wmww/gtk4-layer-shell): layer `OVERLAY` so it sits
above full-screen windows, keyboard mode `NONE` so it never takes focus or interrupts
typing, anchored to the top and right edges with the saved margins. The namespace
`github-cockpit` is what a compositor rule addresses to blur behind it.

Without the library the window is an ordinary toplevel and the compositor has to be told to
float and pin it; the README has the rules. This is a fallback, not the intended setup.

**Appearance**

- 300pt wide — wider than Claude Cockpit's 260, because a pull request title needs the room
  a percentage does not. Height fits the rows.
- Dark glass (`rgba(5, 10, 18, 0.55)`), 16pt corner radius, a 1pt cyan edge and a soft outer
  glow drawn as a `box-shadow`, which only ever falls outside the card.
- The blur behind the glass is the compositor's to draw: on Hyprland, one `layerrule`.
- Header: the title in Orbitron, small and letter-spaced, with the status marker on the
  right. Then a section per list, each with an Orbitron title.
- One row per pull request, two lines: the title with `#412` on the right, and the
  repository with the age on the right in a dimmer tone. The title is what gives way when
  there is not enough room; the number and the age stay readable.
- A draft recedes to the secondary tone. Amber is kept for the stale marker, where the color
  is a warning.
- Orbitron is copied once into `~/.local/share/fonts/github-cockpit`, because fontconfig has
  no way to register a font for a single process. If that fails the card falls back to a
  monospaced font.

**Interaction**

- Drag anywhere to move. The position is saved as margins from the top and right edges.
- Click a row to open that pull request; the portal is tried first and `xdg-open` is the
  fallback, because a layer surface is not a toplevel a portal can always parent to.
- Right-click: Refresh, Open GitHub Pull Requests, Quit.

A drag and a click share the card, so the drag gesture runs in the capture phase and claims
the sequence once the pointer has travelled 3pt. Past that the row underneath never fires,
which is what keeps moving the card from opening a pull request.

### macOS

`macos/` is a Swift package with the same split, following Claude Cockpit's macOS build:
`CockpitCore` (pull request parsing, the `gh` runner, relative times, the appearance) is
pure Foundation and unit-tested; `GitHubCockpit` is the AppKit card.

- The window is a borderless, non-activating `NSPanel` at the floating level that joins every
  Space, so it sits above full-screen apps and never takes focus. The blur is an
  `NSVisualEffectView` behind the glass.
- Settings live in user defaults (`local.github-cockpit`) and are edited in a Personalize
  window, offered once on first launch and afterwards from the right-click menu.
- `gh` is looked up in `~/.local/bin`, `/opt/homebrew/bin` and `/usr/local/bin`, then by a
  login `zsh`, because apps launched from Finder do not inherit the shell's `PATH`.
- The card's view is the only mouse target. A press that travels 3pt moves the card; a click
  is routed by position to the row under it, which opens that pull request, or anywhere else
  refreshes.

## Refresh and state

- Fetch on launch, then every 60 seconds, on a worker thread. A fetch never overlaps
  another; a manual refresh during one is ignored.
- Ages and the stale marker are redrawn every 30 seconds without fetching.
- State: the last good reading and when it was taken, the last failure, whether a fetch is
  running.

## Failure handling

- With an earlier reading: keep showing it at 45% opacity with `STALE · 2m` in the header.
  The next good read clears it.
- With no reading yet, one line in place of the sections:

| Message | Meaning |
| --- | --- |
| `READING PULL REQUESTS` | The first read is in progress. |
| `GH CLI NOT FOUND` | The `gh` executable was not found. |
| `TIMED OUT` | `gh` did not answer within 20 seconds. |
| `NOT SIGNED IN` | `gh` is installed but not authenticated. |
| `COULD NOT READ PRS` | `gh` exited with an error. |
| `UNRECOGNIZED OUTPUT` | `gh` answered, but not with a list of pull requests. |

An empty section is hidden. `NO OPEN PULL REQUESTS` appears only when both are empty — that
is a successful read, not a failure, so it is not dimmed.

## Testing

Unit tests for `cockpit_core`:

- Parser: the real sample above; an empty array; drafts; trimmed titles; every shape of
  incomplete row; one bad row among good ones; a timestamp without a zone; unreadable
  timestamps; replies that are not JSON arrays.
- Time: every boundary of `compact`, a negative duration, each `age` form, a missing
  timestamp, a clock running ahead.
- Appearance: hex parsing and rejection, clamping, the round trip through the file, that
  saving the appearance keeps the position and the other way round, the on-disk shape, and
  every fallback for an unreadable file or value.
- Fetcher: against stand-in `gh` scripts, so no test reaches the network — the arguments
  passed, the disabled pager, a missing or non-executable CLI, being signed out told apart
  from other failures, a non-zero exit, a CLI that outlives the timeout, lookup by bare
  name, resolution on each fetch, and that stdin is never the widget's.

The card itself is checked by running it and comparing against `gh search prs`.
