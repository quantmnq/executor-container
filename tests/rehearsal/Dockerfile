FROM ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    qemu-system-arm qemu-utils qemu-efi-aarch64 cloud-image-utils openssh-client ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ARG REHEARSAL_UID=1001
RUN getent passwd "$REHEARSAL_UID" >/dev/null || useradd --uid "$REHEARSAL_UID" --no-create-home --home-dir /tmp rehearsal
WORKDIR /vm
# Runs software emulation; no host devices, privileges, Docker socket or cgroups.
ENTRYPOINT ["qemu-system-aarch64"]
