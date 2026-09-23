# Deploying HostPost

The VPS runs HostPost the way it runs fzdbot and fzd-api: its own nologin
account under `/opt`, `uv run --no-sync` under systemd, a read-only deploy key.

## The layout

```
/opt/hostpost/               home of `hostpost` (nologin)
├── .local/bin/uv            uv, installed for this account
├── .ssh/                    read-only deploy key for F-Zero-Discord/HostPost
├── .env                     600: DISCORD_TOKEN, DB_USER, DB_PASSWORD, FZD_API_KEY
└── app/                     checkout — hostpost.service
    └── .env                 everything else; gitignored, read by the bot itself
```

The unit passes `/opt/hostpost/.env` as its `EnvironmentFile`, and the bot reads
`app/.env` from its working directory. An environment variable takes precedence
over `app/.env`, so a setting in both uses the secrets file's value.

**One token, one bot.** Only one process may run HostPost's live application.
Do not `enable` or `start` the unit while another machine runs it.

## Installing it from scratch

```bash
sudo useradd --system --home-dir /opt/hostpost --create-home --shell /usr/sbin/nologin hostpost
sudo chmod 750 /opt/hostpost

# `sudo -u hostpost -i` fails on a nologin account; name the shell instead.
sudo -u hostpost -H bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -u hostpost -H bash -lc 'ssh-keygen -t ed25519 -N "" -C hostpost@fzd -f ~/.ssh/id_ed25519'
sudo cat /opt/hostpost/.ssh/id_ed25519.pub
#   -> add as a READ-ONLY deploy key on F-Zero-Discord/HostPost

sudo -u hostpost -H bash -lc '
  git clone -b dev git@github.com:F-Zero-Discord/HostPost.git /opt/hostpost/app
  cd /opt/hostpost/app && ~/.local/bin/uv sync --frozen --no-dev'
```

Write the two env files from `.env.example`, split as above. The prod API key
is minted on this box (see fzd-api's `deploy/README.md`, "API keys for bot
clients") and delivered from `/etc/fzd-api/issued/prod-hostpost.key`.

```bash
sudo install -m 644 deploy/systemd/hostpost.service /etc/systemd/system/
sudo install -m 755 deploy/update-hostpost /usr/local/sbin/
printf '%s ALL=(root) NOPASSWD: /usr/local/sbin/update-hostpost\n' "$USER" \
  | sudo tee /etc/sudoers.d/update-hostpost > /dev/null
sudo chmod 440 /etc/sudoers.d/update-hostpost && sudo visudo -c
sudo systemctl daemon-reload
sudo systemctl enable --now hostpost
```

## Updating it

```bash
ssh fzd sudo update-hostpost dev
```

It fetches, checks out the ref, runs `uv sync --frozen --no-dev`, restarts the
unit and prints the journal's last lines. `journalctl -u hostpost -f` follows it.
