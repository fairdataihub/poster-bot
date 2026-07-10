# Exposing posterbot publicly via a relay VPS (Route B)

Give the conference a stable HTTPS URL **without opening any port at home**. A
tiny public VPS runs Caddy (TLS); this box (`hpcf`) holds an *outbound*
reverse-SSH tunnel to it. All data — DB, embeddings, LLM — stays on hpcf; the
VPS only relays HTTPS to the tunnel. Nothing at home is internet-reachable.

```
 attendee ──HTTPS──►  VPS (public IP, DuckDNS name)
                        └ Caddy :443  ──►  127.0.0.1:8722  (reverse-tunnel endpoint)
                                                  ▲
                        ssh -R (outbound from hpcf, auto-reconnecting)
                                                  │
 hpcf (home, behind NAT) ──────────────────────── ┘
   posterbot-api 127.0.0.1:8722  ·  ollama  ·  pgvector   (never internet-exposed)
```

**Why this shape:** the tunnel is initiated *from* hpcf (outbound 22 → allowed by
any home router), so no port-forward and no home-IP exposure. The `-R` binds the
VPS's **loopback** only, so the raw app port is never public — the public reaches
it solely through Caddy, which adds TLS. Kill switch = stop Caddy or the tunnel.

Cost: smallest tier at any provider (Hetzner CX22 ~€4, DigitalOcean/Vultr/Linode
~$5). 1 vCPU / 512MB–1GB is plenty — it only shuffles bytes.

---

## Prerequisites

- A VPS (Ubuntu 24.04), SSH access as a sudo user.
- A free DuckDNS hostname (https://www.duckdns.org) → point it at the VPS's public IP.
- `EVENT_CODE` set in `/storage/posterbot/.env` on hpcf **before** going live (gates `/api/chat`).

---

## Part A — VPS (public relay)

### 1. Point DNS at the VPS
On DuckDNS, set your subdomain's IP to the VPS public IP. Verify:
`dig +short posterbot.duckdns.org` → the VPS IP.

### 2. Base hardening
```bash
sudo apt update && sudo apt install -y ufw fail2ban unattended-upgrades
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo systemctl enable --now fail2ban
```
Confirm SSH is key-only in `/etc/ssh/sshd_config`: `PasswordAuthentication no`,
then `sudo systemctl reload ssh`.

### 3. A locked-down tunnel account
Its ONLY power is holding the reverse tunnel — no shell, forwarding only.
```bash
sudo adduser --disabled-password --gecos "" tunnel
sudo mkdir -p /home/tunnel/.ssh && sudo chmod 700 /home/tunnel/.ssh
# (the hpcf public key goes in here in Part B, step 2)
```

### 4. Caddy (TLS + reverse proxy)
```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy
```
Put `Caddyfile.example` at `/etc/caddy/Caddyfile` (edit the hostname), then:
`sudo systemctl reload caddy`. Caddy fetches the cert on first request — it will
502 until the hpcf tunnel is up (Part C), which is expected.

---

## Part B — hpcf (home box, tunnel origin)

### 1. A dedicated tunnel key
```bash
ssh-keygen -t ed25519 -N '' -f ~/.ssh/posterbot_tunnel -C posterbot-tunnel
```

### 2. Authorize it on the VPS — forwarding only
Append this to the VPS's `/home/tunnel/.ssh/authorized_keys` (one line;
`restrict` disables everything, then only port-forwarding is re-enabled):
```
restrict,port-forwarding <contents of ~/.ssh/posterbot_tunnel.pub>
```
```bash
# from hpcf, print the line to paste:
echo "restrict,port-forwarding $(cat ~/.ssh/posterbot_tunnel.pub)"
# on the VPS, after pasting:
sudo chown -R tunnel:tunnel /home/tunnel/.ssh && sudo chmod 600 /home/tunnel/.ssh/authorized_keys
```

### 3. Set the tunnel target + turn on the app's event-code gate
```bash
echo 'TUNNEL_TARGET=tunnel@posterbot.duckdns.org' > /storage/posterbot/.env.tunnel
chmod 600 /storage/posterbot/.env.tunnel
# gate chat behind a code you hand out at the CoFest session:
sed -i '/^EVENT_CODE=/d' /storage/posterbot/.env
echo 'EVENT_CODE=<pick-something>' >> /storage/posterbot/.env
```

### 4. Install the tunnel service
```bash
cp /storage/posterbot/deploy/posterbot-tunnel.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

---

## Part C — go live

```bash
# 1. bring the bot back up on hpcf (if shut down)
/storage/posterbot/up_db.sh
systemctl --user start posterbot-ollama posterbot-api
# 2. open the tunnel
systemctl --user enable --now posterbot-tunnel
systemctl --user status posterbot-tunnel --no-pager        # should be active
# 3. verify end-to-end
curl -s https://posterbot.duckdns.org/healthz              # {"db":31363,...}
```
Then open `https://posterbot.duckdns.org` from a phone on **cellular** (not home
wifi) — that proves the public path works. Print the QR for the session.

---

## Operating

- **Kill switch (instant):** `systemctl --user stop posterbot-tunnel` (drops the
  public URL; app keeps running privately). Or stop Caddy on the VPS.
- **Rotate the event code:** edit `EVENT_CODE` in `.env`, `systemctl --user restart posterbot-api`.
- **Bigger model for the demo:** `LLM_MODEL=` in `.env`, restart the API.
- **The app already** rate-limits per session, serves full text only for
  open-licensed posters, treats poster text as untrusted, and builds DOI links
  server-side — so the public surface is just Caddy + the event-gated chat.

## Teardown after the conference
```bash
systemctl --user disable --now posterbot-tunnel
```
Then delete the VPS. Home was never exposed, so there's nothing to close.
