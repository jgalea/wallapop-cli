<div align="center">

# wallapop

[![License](https://img.shields.io/badge/LICENSE-MIT-5C9E31?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/PYTHON-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Built by](https://img.shields.io/badge/BUILT%20BY-JGALEA-8A2BE2?style=for-the-badge&logo=github&logoColor=white)](https://github.com/jgalea)

**Search Wallapop listings in Spain and Portugal from the terminal.**

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

Not affiliated with Wallapop.
