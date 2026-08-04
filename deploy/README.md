# Deployment runbook

How Site Doctor gets from the `test` branch onto an EC2 instance, and what to
do when something breaks.

## Why there is no Docker here

Containerisation was attempted and set aside. The `Dockerfile` is still in
`site-doctor/` and works in principle, but the local build environment could
not complete it. Deploying straight onto the instance moves the dependency
installation to a clean Ubuntu box with adequate disk, which is where it was
always going to be easier. If containers come back later, `run_audit.py` and
the trimmed `requirements.txt` are equally useful either way.

## Architecture

```
push to `test`
      |
      v
GitHub Actions (.github/workflows/deploy.yml)
      |  ssh, using EC2_SSH_KEY + EC2_HOST secrets
      v
EC2 t3.micro, Ubuntu, us-east-1
      |
      +-- /opt/sitedoctor          git checkout + venv
      +-- /etc/sitedoctor/env      secrets, root-only 600
      +-- systemd timer            runs run_audit.py daily
      +-- /var/www/sitedoctor      status page + generated reports
      +-- Caddy :80                serves it; HTTPS once DNS points here
```

There is deliberately **no API service yet** — the application has no HTTP
surface. `remote-deploy.sh` already restarts `sitedoctor-api.service` if it
finds one, so when that API is built nothing here needs changing.

## Instance facts

| | |
|---|---|
| Region | `us-east-1` (N. Virginia) |
| Type | `t3.micro` — 908 MB RAM, 2 vCPU |
| Disk | 20 GiB |
| OS | Ubuntu 26.04 LTS |
| User | `ubuntu` |
| Swap | 2 GB file, added by `setup-ec2.sh` |

**The 908 MB matters.** An audit runs Playwright's Chromium to crawl and then
Lighthouse launching its own Chrome. Without the swap file the kernel OOM
killer ends one of them mid-run, and it presents as a random intermittent
failure rather than as memory exhaustion. `--max-pages` is capped at 2 in the
systemd unit for the same reason. If audits fail unpredictably, check
`free -h` and `journalctl -k | grep -i oom` before suspecting the code.

## Deploy key (do this first)

The repository is **private**, so the instance cannot clone over HTTPS — it
would stop to ask for a password and a non-interactive deploy would hang. It
authenticates with a GitHub deploy key instead.

On the instance, as `ubuntu`:

```bash
ssh-keygen -t ed25519 -C "sitedoctor-ec2" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Add that public key at **Repo → Settings → Deploy keys → Add deploy key**.
Leave **"Allow write access" unticked** — the instance only ever needs to read.
A read-only key that leaks cannot be used to push malicious code.

Verify before going further:

```bash
ssh -T git@github.com     # expect "successfully authenticated"
```

A deploy key is scoped to this one repository, unlike a personal access token,
which would carry your whole account's access onto a public-facing server.

## First-time provisioning

Once per instance, after the deploy key works:

```bash
ssh -i ~/.ssh/sitedoctor-key.pem ubuntu@<elastic-ip>
git clone --branch test git@github.com:Harris-05/Website-Diagnoser-and-Fixer-Agent.git /tmp/sd
sudo bash /tmp/sd/deploy/setup-ec2.sh
sudo nano /etc/sitedoctor/env      # real OPENAI_API_KEY and SITEDOCTOR_TARGET_URL
```

Then confirm the pipeline actually runs before trusting the timer:

```bash
sudo systemctl start sitedoctor-audit.service
journalctl -u sitedoctor-audit.service -f
```

`setup-ec2.sh` is idempotent — every step checks whether it has already run,
so re-running it is safe.

## GitHub Secrets required

Repository → Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `EC2_HOST` | the Elastic IP |
| `EC2_SSH_KEY` | full contents of the deploy private key, including the BEGIN/END lines |

`OPENAI_API_KEY` is **not** here. GitHub Secrets are for CI; the runtime key
lives in `/etc/sitedoctor/env` on the instance and never passes through
GitHub.

## Deploying

Push to `test`. That is all. To redeploy without a commit, use
**Actions → Deploy to EC2 → Run workflow**.

By hand, exactly as CI does it:

```bash
ssh ubuntu@<elastic-ip> 'sudo bash /opt/sitedoctor/deploy/remote-deploy.sh'
```

## Rolling back

Every deploy prints the commit it replaced. To go back:

```bash
sudo -u ubuntu git -C /opt/sitedoctor reset --hard <previous-sha>
sudo bash /opt/sitedoctor/deploy/remote-deploy.sh
```

## Enabling HTTPS

Only after DNS resolves. Check first — do not skip this:

```bash
dig +short sitedoctor.example.com     # must print the Elastic IP
```

If it prints nothing, wait. Pointing Caddy at a hostname that does not yet
resolve burns Let's Encrypt retries and gets the name rate-limited for an hour
at a time.

Once it resolves, replace `:80 {` at the top of `/etc/caddy/Caddyfile` with
the hostname and reload:

```bash
sudo nano /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo journalctl -u caddy -f          # watch the certificate being issued
```

Caddy handles issuance, renewal and the HTTP→HTTPS redirect itself. No
certbot, no cron job.

`remote-deploy.sh` will **not** overwrite a Caddyfile that has a hostname
configured, so a later deploy cannot silently revert HTTPS back to plain HTTP.
The trade-off is that genuine Caddyfile changes in the repo then need applying
by hand.

## Switching to `main` later

When Haris's work is complete and your changes are merged into `main`:

1. `.github/workflows/deploy.yml` — change `branches: [test]` to `[main]`
2. On the instance: `sudo -u ubuntu DEPLOY_BRANCH=main git -C /opt/sitedoctor checkout main`

One instance, one environment at a time. Free tier covers 750 hours a month,
which is one instance running continuously — a second one for staging is
roughly $10/month plus another public IPv4. Do not run test and production on
this box simultaneously: an audit in one will OOM-kill the other.

## Diagnosing

```bash
systemctl list-timers sitedoctor-audit.timer     # when does it next run
journalctl -u sitedoctor-audit.service -n 100    # last audit's output
journalctl -u caddy -n 50                        # web server / certificates
free -h                                          # memory and swap in use
journalctl -k | grep -i oom                      # was something OOM-killed
df -h /                                          # disk
ls -la /var/www/sitedoctor/reports/               # what has been published
```

## Known follow-ups

- **AWS Parameter Store for the runtime secret.** `/etc/sitedoctor/env` is
  fine and root-only, but Parameter Store is the better answer and is what the
  project's own notes call for. It needs an IAM role, an instance profile and
  the AWS CLI resident in memory — deferred on a 908 MB box, not rejected.
- **Port 22 exposure.** GitHub-hosted runners have changing IPs, so SSH has to
  accept a wide range. Password authentication is off by default on the Ubuntu
  AMI, so key-only access is the protection. A self-hosted runner on the
  instance would remove inbound SSH entirely.
- **No log shipping or alerting.** Everything is in `journalctl` on one box. If
  the instance dies, so do the logs. CloudWatch agent is the next step.
- **No HTTPS until the domain arrives**, and no automated certificate test.
