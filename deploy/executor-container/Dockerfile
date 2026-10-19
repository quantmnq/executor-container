# Build only with scripts/build-executor-container.py's allowlisted context.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS builder
WORKDIR /build
COPY build-requirements.lock requirements.lock install-api.py ./
RUN python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r build-requirements.lock \
    && python -m venv /opt/venv \
    && python install-api.py
COPY follow_executor-*.whl /wheels/
RUN /opt/venv/bin/python -m pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock \
    && /opt/venv/bin/python -m pip install --no-cache-dir --no-deps /wheels/*.whl \
    && /opt/venv/bin/python -m pip check \
    && /opt/venv/bin/python -c 'from ibapi.client import EClient; from ibapi.order_cancel import OrderCancel; import follow_executor.cli'

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build/api-notices /usr/share/licenses/ibapi
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md /usr/share/licenses/follow-executor/
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp XDG_CONFIG_HOME=/data/config XDG_STATE_HOME=/data/state \
    FOLLOW_EXECUTOR_LAUNCHER=./follow-container
WORKDIR /tmp
USER 65532:65532
STOPSIGNAL SIGTERM
ENTRYPOINT ["follow-executor"]
CMD ["--help"]
