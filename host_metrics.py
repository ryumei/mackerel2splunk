# -*- coding: utf-8 -*-
# Get Mackerel host metrics and 
# Post to metrics index via Spluk HTTP Event Collector.
#
import os
import json
import ssl
import logging
import logging.config
from six.moves.urllib.parse import urlencode
from six.moves.urllib.request import Request
from six.moves.urllib.request import urlopen
from six.moves.urllib.error import URLError
from six.moves.urllib.error import HTTPError
from six.moves.urllib.parse import urlparse
ssl._create_default_https_context = ssl._create_unverified_context

def request(url, data=None, headers=None, params=None):
    u'''Simple HTTP Client'''
    if params is not None:
        query = urlencode(params)
        url = '%s?%s' % (url, query)
    req = Request(url, headers=headers)
    if data is not None:
        req.add_data(data)
    try:
        logging.debug("%s %s", req.get_method(), url)
        res = urlopen(req)
        return json.loads(res.read())
    except HTTPError as err:
        logging.error("%s. Client error GET %s with status %d.",
                      err.reason, url, err.code)
    except URLError as err:
        logging.exception(err)
    except (ValueError, TypeError) as err:
        logging.error(err)
    return None

'''
metrics_names = [
    'loadavg5',

    'cpu.user.percentage',
    'cpu.iowait.percentage',
    'cpu.system.percentage',
    'cpu.idle.percentage',
    'cpu.nice.percentage',
    'cpu.irq.percentage',
    'cpu.softirq.percentage',
    'cpu.steal.percentage',
    'cpu.guest.percentage',

    'memory.used',
    'memory.available',
    'memory.total',
    'memory.swap_used',
    'memory.swap_cached',
    'memory.swap_total',

    'interface.eth0.rxBytes.delta',
    'interface.eth0.txBytes.delta',

    'filesystem.sda.size',
    'filesystem.sda.used',
    'filesystem.sdb.size',
    'filesystem.sdb.used',
]
'''

MACKEREL_BASE_URL = 'https://mackerel.io'
class MackerelReader(object):
    def __init__(self, apikey, base_url=MACKEREL_BASE_URL):
        self.apikey = apikey
        self.base_url = base_url

    def _request_headers(self):
        return { 'X-Api-Key': self.apikey }

    def host_information(self, hostId):
        u'''GET host detailed information'''
        url = self.base_url + '/api/v0/hosts/{}'.format(hostId)
        data = request(url, headers=self._request_headers())
        return data['host']

    def metric_names(self, hostId):
        u'''GET host metrics of a host'''
        url = self.base_url + '/api/v0/hosts/{}/metric-names'.format(hostId)
        data = request(url, headers=self._request_headers())

        name_map = {}
        for name in data['names']:
            items = name.split('.')
            if items[0] != 'custom':
                parent = items[0]
            else: # custom メトリック場合は、ふたつ目まで
                parent = ".".join(items[0:2])

            if parent not in name_map:
                name_map[parent] = []
            name_map[parent].append(name)

        for metric_group, metric_names in name_map.items():
            if metric_group.startswith('custom.'): # skip custom metrics
                continue
            yield metric_names

    def host_metrics(self, hostIds):
        u'''GET Mackerel host metrics and return as generator'''
        url = self.base_url + '/api/v0/tsdb/latest'
        for hostId in hostIds:
            for metric_names in self.metric_names(hostId):
                params = [ ('hostId', hostId) ] # as list of tuples
                for metric_name in metric_names:
                    params.append(('name', metric_name))
                data = request(url, headers=self._request_headers(), params=params)
                hostInfo = self.host_information(hostId)
                yield {
                    'hostname': hostInfo['name'],
                    'host_id': hostId,
                    'metrics': data['tsdbLatest'][hostId],
                }

SPLUNK_HEC_URL = 'https://localhost:8088/services/collector'
def post2hec(data, token, url=SPLUNK_HEC_URL):
    u'''POST metrics to Splunk HEC endpoint'''
    hec_headers = {"Authorization": "Splunk {}".format(token)}

    hostId = data['host_id']
    hostname = data['hostname']
    metrics = []
    for metric_name, v in data['metrics'].items():
        metrics.append({
            "time": v['time'],
            "event": "metric",
            "source": "mackerel.io",
            "host": hostname,
            "fields": {
                "metric_name": metric_name,
                "_value": v['value'],
            },
        })
    post_data = "".join([json.dumps(m) for m in metrics])
    res = request(url, headers=hec_headers, data=post_data)
    logging.debug(json.dumps(res))

def main(mackerel_apikey, host_ids, splunk_url, hec_token, dryrun=False):
    mackerel = MackerelReader(mackerel_apikey)
    for data in mackerel.host_metrics(host_ids):
        logging.debug(data)
        if not dryrun:
            post2hec(data, url=splunk_url, token=hec_token)

DEFAULT_CONF = 'mackerel2splunk.conf'
if __name__ == '__main__':
    from argparse import ArgumentParser
    from six.moves.configparser import ConfigParser
    parser = ArgumentParser()
    parser.add_argument('-c', '--conf', dest='conf', default=DEFAULT_CONF)
    parser.add_argument('--dryrun', dest='dryrun',
                        action='store_true', default=False)

    args = parser.parse_args()
    conf_name = args.conf

    logging.config.fileConfig(conf_name)
    config = ConfigParser()
    config.read([conf_name])

    mackerel_apikey = config.get('mackerel', 'apikey')
    mackerel_base_url = config.get('mackerel', 'base_url')
    host_ids = [h.strip() for h in config.get('mackerel', 'host_ids').split(',')]
    hec_token = config.get('splunk', 'token')
    splunk_url = config.get('splunk', 'hec_url')

    main(mackerel_apikey, host_ids, splunk_url, hec_token, dryrun=args.dryrun)

