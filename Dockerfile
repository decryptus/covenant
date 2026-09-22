FROM python:3.11-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf automake build-essential libtool libcurl4-openssl-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY requirements.txt setup.py setup.cfg setup.yml README.md ./
COPY covenant ./covenant
COPY bin ./bin
# setup.py imports yaml during metadata generation.
RUN python -m pip install --no-cache-dir 'setuptools<81' wheel PyYAML \
    && python -m pip wheel --no-cache-dir --no-build-isolation --wheel-dir /wheels .

FROM python:3.11-slim-bookworm
LABEL maintainer="docker@doowan.net"
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl libcurl4 libmagic1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels covenant \
    && rm -rf /wheels
COPY --chmod=755 docker-run.sh /run.sh
COPY etc/covenant/metrics.d /etc/covenant/metrics.d
COPY etc/covenant/modules /etc/covenant/modules
COPY etc/covenant/probes.d /etc/covenant/probes.d
EXPOSE 9118/tcp
CMD ["/run.sh"]
