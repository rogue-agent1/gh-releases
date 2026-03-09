# gh-releases

Track GitHub releases across multiple repos. Get notified when projects you care about ship new versions.

**Pure Python, zero dependencies.**

## Usage

```bash
# Track a repo
python3 releases.py add openclaw/openclaw
python3 releases.py add anthropics/anthropic-sdk-python

# Check for new releases
python3 releases.py check

# Show recent releases for any repo
python3 releases.py releases vercel/next.js -n 3

# List tracked repos
python3 releases.py list

# JSON output for scripting
python3 releases.py check --format json
```

## Output

```
🆕 2 new release(s):

  📦 openclaw/openclaw → v2026.3.8 (2026-03-09)
     CLI/backup: add openclaw backup create and verify
     https://github.com/openclaw/openclaw/releases/tag/v2026.3.8

  📦 rust-lang/rust → 1.94.0 (2026-03-06)
     https://github.com/rust-lang/rust/releases/tag/1.94.0
```

## Features

- Track unlimited repos
- Detect all new releases since last check (not just latest)
- Tag fallback for repos without formal releases
- Rate limiting (0.5s between API calls)
- JSON output mode
- Works with `GITHUB_TOKEN` for higher rate limits

## License

MIT
