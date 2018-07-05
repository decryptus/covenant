# covenant project

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
