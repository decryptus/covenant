# covenant project

## Quickstart

Using covenant in Docker

`docker-compose up -d`

See [docker-compose.yml](docker-compose.yml)

## Installation

pip install covenant

## Running

### Running daemon

`covenant -c <conffile> -p <pidfile> --logfile <logfile>`

### Running foreground

`covenant -f -c <conffile> -p <pidfile> --logfile <logfile>`

### Examples:

curl http://localhost:9118/metrics/apache1

curl http://localhost:9118/metrics/nginx1

curl http://localhost:9118/metrics/rabbitmq1

curl http://localhost:9118/metrics/redis1

curl http://localhost:9118/probe/secure-layer1?target=https://example.com

curl http://localhost:9118/probe/sshd-pidfile-exists?target=/var/run/sshd.pid
