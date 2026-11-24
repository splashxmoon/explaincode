# gitwrapped

A year in review for your git history, with no dependencies.

It reads one year of commits and prints your streaks, busiest day, hour and month, your biggest commit, your most-touched files and a coding persona. It can also write a shareable SVG card. Everything runs locally; nothing is uploaded.

## Usage

```sh
python3 gitwrapped.py                       # this repo, you, this year
python3 gitwrapped.py path/to/repo --year 2025
python3 gitwrapped.py . --all-authors       # the whole team
python3 gitwrapped.py . --svg wrapped.svg   # a card to share
python3 gitwrapped.py . --json
```

`--author` matches a name or email; by default it is your `git config user.name`.

Needs Python 3.8 or later and `git` on your PATH.
