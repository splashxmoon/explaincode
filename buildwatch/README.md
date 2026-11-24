# buildwatch

See what changed between two builds, with no dependencies.

Point it at two versions of an app, a firmware image, or an extracted package. It tells you which files were added, removed or changed, and it flags new network endpoints and secret-looking values, so you can spot a new telemetry host or a leaked key without reading a binary by hand.

Use it to review a release before you ship it, check a vendor update, or compare two versions of a tool you depend on.

## Usage

```sh
python3 buildwatch.py old-build/ new-build/
python3 buildwatch.py app-v1.bin app-v2.bin
python3 buildwatch.py old/ new/ --json
python3 buildwatch.py old/ new/ --fail-on-flags   # exit 1 if anything is flagged, for CI
```

Needs Python 3.8 or later. It uses only the standard library.

## What it checks

- **Files:** added, removed, changed (SHA-256), and unchanged.
- **Strings:** printable runs of 6+ characters, diffed between versions, so it works on binaries and text alike.
- **Flags** (new in the newer build only):
  - `url`: `http(s)://` endpoints
  - `ip`: IPv4 addresses
  - `email`: email addresses
  - `secret`: AWS-style access key IDs, private key headers, and `api_key=`, `token=`, `password=` assignments

Secret values are redacted in all output (only the first four characters are shown), and lines that contain them are left out of the sample.

## Limits

- This is a string-level diff, not a disassembler. It can't tell you what the code does with a string.
- A flag means "look at this," not "this is a vulnerability." Expect some false positives, such as example URLs in docs.
- Strings are ASCII only, so UTF-16 strings in Windows binaries are missed.

## Tests

```sh
python3 -m unittest -v test_buildwatch
```
