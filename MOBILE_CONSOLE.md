# Iron Legion Mobile Console (Phone Access)

This gives you a phone-friendly webpage with only:
- `Ticker`
- `Thesis`

It runs the full pipeline and shows links to outputs.

## 1) Start on your Mac

From repo root:

```bash
cd /Users/mdsb/Documents/GitHub/mk2-engine
./scripts/run_mobile_console.sh
```

One-command remote helper (checks Tailscale + prints phone URL + starts console):

```bash
cd /Users/mdsb/Documents/GitHub/mk2-engine
./scripts/start_mobile_remote.sh
```

Default URL on the Mac:

```text
http://0.0.0.0:8765
```

## 2) Open from your phone (same Wi-Fi)

Find Mac local IP:

```bash
ipconfig getifaddr en0
```

If that prints `192.168.1.25`, open on phone:

```text
http://192.168.1.25:8765
```

## 3) Run a pipeline from phone

1. Enter ticker (example `NVDA`)
2. Enter thesis text
3. Tap **Run Full Pipeline**
4. Wait for completion; open links shown on result page

## 4) Outputs shown on result page

- `*_IRONMAN_HUD.html`
- `*_NEWS_SOURCES.html` (J.A.R.V.I.S)
- `*_STORMBREAKER.html`
- `iron_legion_command_*.html`
- `receipts_*.html`
- `*_TIMESTONE.html`
- `*_Full_Investment_Memo.pdf`
- `pipeline_integrity_*.json`

## 5) Access from anywhere (recommended)

Use Tailscale:

1. Install Tailscale on Mac and phone
2. Log in on both
3. Start console on Mac
4. Open from phone using Mac Tailscale IP, e.g.
   `http://100.x.y.z:8765`

## Notes

- Mac must stay on and connected.
- The pipeline may degrade if DNS/provider network fails.
- Legacy dashboard/clickpack are not primary surfaces by default.
