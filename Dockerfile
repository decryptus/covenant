FROM alpine:latest

LABEL maintainer="docker@doowan.net"

RUN apk -Uuv add autoconf \
                 automake \
                 bash \
                 cargo \
                 curl \
                 curl-dev \
                 gcc \
                 libffi-dev \
                 libmagic \
                 libtool \
                 linux-headers \
                 libressl-dev \
                 make \
                 musl-dev \
                 python3 \
                 python3-dev \
                 py3-curl \
                 py3-openssl \
                 py3-pip && \
    find /var/cache/apk/ -type f -delete

RUN pip3 install covenant

ADD docker-run.sh /run.sh
ADD etc/covenant/metrics.d /etc/covenant/metrics.d
ADD etc/covenant/modules /etc/covenant/modules
ADD etc/covenant/probes.d /etc/covenant/probes.d

EXPOSE 9118/tcp

CMD ["/run.sh"]
