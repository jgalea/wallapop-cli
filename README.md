<div align="center">

# wallapop

[![License](https://img.shields.io/badge/LICENSE-MIT-5C9E31?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/PYTHON-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Built by](https://img.shields.io/badge/BUILT%20BY-JGALEA-8A2BE2?style=for-the-badge&logo=github&logoColor=white)](https://github.com/jgalea)

**Search, message sellers and make offers on Wallapop in Spain and Portugal from the terminal.**

</div>

Wallapop's own search matches loosely, so a search for one product returns pages of others. `wallapop` keeps only listings whose title has every word you searched for, and adds a radius around any town, price limits, ships-only and JSON output.

```
uv tool install git+https://github.com/jgalea/wallapop-cli

wallapop search "hue signe"                          # title must contain every word
wallapop search hue --near Valencia --radius 30      # km around a town, nearest first
wallapop search "hue go" --max 60 --ships --sort cheap
wallapop search "philips hue" --loose --json
wallapop show 8z887xwkolz3                           # or a listing URL
```

Uses Wallapop's public search API with a Chrome TLS fingerprint (curl_cffi). Wallapop only applies `--radius` when sorting by distance, so `--radius` switches the sort to nearest-first. Place names are geocoded with OpenStreetMap Nominatim.

## Messages and offers

Log in to Wallapop in Chrome, then let the CLI reuse that session. macOS asks once for Keychain access to read Chrome's cookies.

```
wallapop login                                       # or --cookie <value> to paste it
wallapop inbox
wallapop chat 8z887xwkolz3                           # a conversation, or an item you've messaged about
wallapop send 8z887xwkolz3 "¿Sigue disponible?"      # starts the conversation if needed
wallapop offer 8z887xwkolz3 25 --dry-run             # checks Wallapop's offer limits
wallapop offer 8z887xwkolz3 25
```

`offer` uses Wallapop's own make-an-offer flow, not a chat message. Wallapop rejects offers more than a set percentage under the asking price (30% at the time of writing) and caps offers per day, so `offer` reads both first and refuses rather than sending something that will bounce.

The session lives in `~/.config/wallapop/session.json` (mode 600). Wallapop rotates the cookie on every use and it stays valid for 30 days after the last one. Messages go out over PubNub, the same way the web app sends them. The chat and offer endpoints were mapped by [Microck/wallapop-cli](https://github.com/Microck/wallapop-cli).

Not affiliated with Wallapop.
