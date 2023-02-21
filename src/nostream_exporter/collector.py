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

    # TODO: refactor database connection 
    def get_event_counts(self) -> dict:
        '''
        Query postgresql to get relay metrics.
        @returns a list of tuples with the event kind and count.
        '''
        metrics = {}
        conn = psycopg2.connect(
            host=self.host,
            database=self.database,
            user=self.user,
            password=self.password
        )

        # We do not want metrics for all possible event types because it compounds our cardinality.
        # See: https://www.robustperception.io/cardinality-is-key/
        # TODO: make this configurable
        event_kinds= "7,1,6,1984,4,3,9735"
        # 7: Reaction (nip-25)
        # 1: Short Text Note
        # 6: Reposts (nip-18)
        # 1984: Reporting (nip-56)
        # 4: Encrypted Direct Messages (nip-04)
        # 3: Contacts (nip-02)
        # 9735: Zap (nip-57)
        select_configured_event_kinds = f"select event_kind, count(id) as count from events where event_kind in ({event_kinds}) group by event_kind order by count(id) desc limit 5;"
        select_other_event_kinds = f"select count(id) from events where event_kind not in ({event_kinds}) ;"
        
#       all_time_top_talker_pubkeys = "select encode(event_pubkey, 'hex'), count(id) from events group by encode(event_pubkey, 'hex') order by count(id) desc limit 10;"
#       recent_top_talker_pubkeys = "select encode(event_pubkey, 'hex'), count(id) from events WHERE first_seen >= CURRENT_DATE - INTERVAL '3 days' group by encode(event_pubkey, 'hex') order by count(id) desc limit 10;"

        cur = conn.cursor()
        cur.execute(select_configured_event_kinds)
        event_counts = cur.fetchall()
        cur.execute(select_other_event_kinds)
        count_other_events = cur.fetchall()
        other_events_count = ('other', count_other_events[0][0])
        event_counts.append(other_events_count)
        return event_counts

    @REQUEST_TIME.time()
    def collect(self):
        event_counts = self.get_event_counts()
        try:
#           yield GaugeMetricFamily('total_events', 'Total count of events seen by the relay', value=relay_metrics['event_count'] )
            # Labels and values are mutually exclusive.
            g = GaugeMetricFamily( "events", "Count of events by kind", labels=[ "kind" ])
            for event in event_counts:
                event_kind = event[0]
                event_count = event[1]
                g.add_metric([ 
                    str(event_kind), 
                ],event_count)
            yield g

        except Exception as e:
            exit( f"Exception: \n{e}")

def main():
    '''Start the prometheus client child process and register the NostreamCollector to it.'''

    # Optional environment variable to set the bind options.
    if environ.get("METRICS_PORT"):
        METRICS_PORT = int(environ.get("METRICS_PORT"))
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