from sys import exit
from os import environ, _exit
from platform import node
from json import loads
import psycopg2

# https://github.com/prometheus/client_python
from prometheus_client import start_http_server, Summary
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from time import sleep

REQUEST_TIME = Summary('request_processing_seconds', 'Time spent processing request')

class NostreamCollector(object):
    def __init__(self) -> None:
        '''Read environment variables.'''
        self.host=environ.get("DB_HOST") or exit( "Error: DB_HOST environment variable is required." )
        self.database=environ.get("DB_NAME") or exit( "Error: DB_NAME environment variable is required." )
        self.user=environ.get("DB_USER") or exit( "Error: DB_USER environment variable is required." )
        self.password=environ.get("DB_PASSWORD") or exit( "Error: DB_PASSWORD environment variable is required." )

    def get_relay_metrics(self) -> dict:
        '''Query postgresql to get relay metrics.'''
        metrics = {}
        conn = psycopg2.connect(
            host=self.host,
            database=self.database,
            user=self.user,
            password=self.password
        )
        select_event_count = "select count(id) from events;"
        select_top_event_kinds = "select event_kind, count(id) as count from events group by event_kind order by count(id) desc limit 5;"
        all_time_top_talker_pubkeys = "select encode(event_pubkey, 'hex'), count(id) from events group by encode(event_pubkey, 'hex') order by count(id) desc limit 10;"
        recent_top_talker_pubkeys = "select encode(event_pubkey, 'hex'), count(id) from events WHERE first_seen >= CURRENT_DATE - INTERVAL '3 days' group by encode(event_pubkey, 'hex') order by count(id) desc limit 10;"

        cur = conn.cursor()
        cur.execute(select_event_count)
        results = cur.fetchall()
        metrics['event_count'] = results[0][0]
        return metrics

    @REQUEST_TIME.time()
    def collect(self):
        relay_metrics = self.get_relay_metrics()
        try:
            yield GaugeMetricFamily('total_events', 'Total count of events seen by the relay', value=relay_metrics['event_count'] )

        except Exception as e:
            exit( f"Exception: \n{e}")

def main():
    '''Start the prometheus client child process and register the NostreamCollector to it.'''

    # Optional environment variable to set the bind options.
    if environ.get("METRICS_PORT"):
        METRICS_PORT = environ.get("METRICS_PORT")
    else:
        METRICS_PORT = 9101
    if environ.get("METRICS_BIND"):
        METRICS_BIND = environ.get("METRICS_BIND")
    else:
        METRICS_BIND = "127.0.0.1"

    # Prometheus client listener (default: 127.0.0.1:9102)
    start_http_server(METRICS_PORT, METRICS_BIND)
    REGISTRY.register(NostreamCollector())

    # This is a hack to prevent the child process from exiting.
    while True:
        sleep(10)

if __name__ == '__main__':
    try:
        main()
    # Catch cntrl+c
    except KeyboardInterrupt:
        try:
            exit(0)
        except SystemExit:
            _exit(0)