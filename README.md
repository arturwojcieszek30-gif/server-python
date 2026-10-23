# 🐹 Mini Chomik

A tiny self-hosted file sharing app built with Flask and SQLite.
Register, drag and drop your files, and share download links on your local network.

## Features

- Drag and drop upload with per-file progress bars (multiple files at once)
- User accounts with hashed passwords
- Public file list with download counters
- One-click "Copy link" and delete with confirmation
- Light and dark theme, responsive layout
- Up to 50 GB per upload (configurable)

## Quick start

```bash
git clone https://github.com/arturwojcieszek30-gif/mini-chomik.git
cd mini-chomik
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`, or `http://<your-LAN-IP>:5000` from another device on the same network.

## Configuration

| Variable      | Default   | Description                   |
|---------------|-----------|-------------------------------|
| `CHOMIK_HOST` | `0.0.0.0` | Interface to listen on        |
| `CHOMIK_PORT` | `5000`    | Port to listen on             |

The upload size limit is `MAX_CONTENT_LENGTH` in `app.py`.

## Data

Everything is stored next to `app.py`: the database (`chomik.db`), uploaded files (`uploads/`)
and the session key (`secret.key`). All of these are git-ignored.

## Security notes

This is a hobby project meant for a trusted network. Anyone can download any file if they have
the link, and there is no HTTPS. If you expose it to the internet, put it behind a reverse proxy
with TLS and add rate limiting.
