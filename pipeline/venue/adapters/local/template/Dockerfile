FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 TZ=UTC \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Base + build + data tools. One layer, apt lists removed.
# Native libs are the build deps for Python wheels / the XBRL and
# venue test suites; sqlite3 is both a job tool and a library dep.
# The Chromium OS libraries are image-carried so Playwright legs
# run after any rebuild — installed by hand in the container,
# they vanish at the next recreate and every leg fails on
# missing dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git openssh-client openssh-server \
    curl wget ca-certificates gnupg sudo \
    ripgrep fd-find jq tree file less nano vim-tiny tmux \
    procps psmisc iproute2 iputils-ping dnsutils netcat-openbsd \
    unzip zip rsync sqlite3 locales tzdata time systemd \
    build-essential pkg-config python3 python3-dev python3-pip python3-venv \
    libffi-dev libssl-dev libsqlite3-dev zlib1g-dev libbz2-dev \
    libreadline-dev liblzma-dev \
    libnss3 libnspr4 libglib2.0-0 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2t64 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "$(command -v fdfind)" /usr/local/bin/fd \
    && mkdir -p /var/run/sshd \
    && sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config \
    && sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config

# Node 22 LTS from NodeSource (Ubuntu 24.04's apt nodejs is 18, too old
# for the frontend toolchains) + Corepack for pnpm/yarn shims.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && corepack enable

# uv, system-wide (jobs resolve it from PATH or the per-user fallbacks;
# in this container /usr/local/bin is the canonical location).
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

RUN useradd -m -s /bin/bash agent \
    && echo "agent ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
    && AGENT_HOME="$(getent passwd agent | cut -d: -f6)" \
    && mkdir -p "$AGENT_HOME/.ssh" && chmod 700 "$AGENT_HOME/.ssh" \
    && chown -R agent:agent "$AGENT_HOME/.ssh" \
    && git config --system init.defaultBranch main \
    && git config --system --add safe.directory '*'

WORKDIR /workspace
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 22
CMD ["/entrypoint.sh"]
