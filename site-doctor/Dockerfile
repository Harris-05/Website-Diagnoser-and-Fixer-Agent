# Site Doctor -- image for non-interactive audit runs.
#
# Entry point is run_audit.py, NOT agent/graph.py. graph.py prompts with
# input() in its entry node, which would hang forever in a container.
#
# Deliberately not built on the official Playwright image: `playwright install
# --with-deps` fetches Chromium *and* apt-installs its system libraries itself,
# which keeps this on a slim base and avoids having to pin the pip playwright
# version to match a base-image tag.

FROM python:3.12-slim

# Lighthouse 12 needs Node >= 18.20. Debian bookworm ships 18.19, just under
# the line, so Node 20 comes from NodeSource.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g lighthouse \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Browsers land somewhere world-readable instead of /root/.cache, so the
# non-root user created below can actually reach them.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Dependencies before source, so editing code does not reinstall everything.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

# Lighthouse's chrome-launcher hunts for a system Chrome and will not find
# Playwright's copy. CHROME_PATH is its supported override. The symlink keeps
# the path stable across Chromium revisions, and the `test -n` guard turns a
# failed lookup into a failed build rather than a silent broken symlink.
RUN CHROME_BIN="$(find /ms-playwright -type f -name chrome | head -n1)" \
    && test -n "$CHROME_BIN" \
    && ln -s "$CHROME_BIN" /usr/local/bin/chrome
ENV CHROME_PATH=/usr/local/bin/chrome

COPY . .

# Chrome refuses to run as root unless --no-sandbox is passed, and
# audit/lighthouse.py hardcodes its --chrome-flags -- a line this image must
# not change. Running as an ordinary user avoids the problem entirely.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Artifacts (crawled HTML, screenshots, Lighthouse JSON, the PDF) are written
# to a path relative to WORKDIR. Mount a host directory here to collect them:
#   -v ${PWD}/out:/app/.site-doctor-cache
ENTRYPOINT ["python", "run_audit.py"]
CMD ["--help"]
