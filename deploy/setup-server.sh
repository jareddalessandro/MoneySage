#!/bin/sh
# One-time setup of a fresh Ubuntu 24.04 server (e.g. AWS Lightsail) for Tallyvio:
# Docker, 2 GB of swap, automatic security updates, and a firewall that only lets in SSH and the web.
# Run as the default user (ubuntu), from a checkout of the repository:  sudo sh deploy/setup-server.sh
set -eu
if [ "$(id -u)" -ne 0 ]; then
	echo "Run with sudo." >&2
	exit 1
fi

echo "== Updates"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
DEBIAN_FRONTEND=noninteractive apt-get -y install ca-certificates curl git ufw unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== Docker (Docker's own apt repository)"
if ! command -v docker >/dev/null; then
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	. /etc/os-release
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
		> /etc/apt/sources.list.d/docker.list
	apt-get update
	apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "${SUDO_USER:-ubuntu}"

echo "== Swap (a safety net for memory spikes on small servers)"
if ! swapon --show | grep -q /swapfile; then
	fallocate -l 2G /swapfile
	chmod 600 /swapfile
	mkswap /swapfile
	swapon /swapfile
	echo '/swapfile none swap sw 0 0' >> /etc/fstab
	echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
	sysctl -p /etc/sysctl.d/99-swappiness.conf
fi

echo "== Firewall: SSH, HTTP and HTTPS only (also set the same in the Lightsail console's Networking tab)"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable

echo
echo "Done. Log out and back in (so docker works without sudo), then follow deploy/README.md from 'Configure'."
