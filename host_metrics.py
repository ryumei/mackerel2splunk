# -*- coding: utf-8 -*-
# Get Mackerel host metrics and 
# Post to metrics index via Spluk HTTP Event Collector.
#
import os
import logging
import urllib
import urllib2
import urlparse
import json
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

def request(url, data=None, headers=None, params=None):
    if params is not None:
        query = urllib.urlencode(params)
        url = '%s?%s' % (url, query)
    req = urllib2.Request(url, headers=headers)
    if data is not None:
        req.add_data(data)
    try:
        logging.debug("%s %s", req.get_method(), url)
        res = urllib2.urlopen(req)
        return json.loads(res.read())
    except urllib2.HTTPError as err:
        logging.error("%s. Client error GET %s with status %d.",
                      err.reason, url, err.code)
    except urllib2.URLError as err:
        logging.exception(err)
    except (ValueError, TypeError) as err:
        logging.error(err)
    return None

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

MACKEREL_BASE_URL = 'https://mackerel.io'
def latest_metrics(apikey, hostIds=None, base_url=MACKEREL_BASE_URL):
    u'''GET Mackerel host metrics'''
    headers= { 'X-Api-Key': apikey }

    params = []
    for hostId in hostIds:
        params.append(('hostId', hostId))
    for metrics_name in metrics_names:
        params.append(('name', metrics_name))
    url = base_url + '/api/v0/tsdb/latest'

    data = request(url, headers=headers, params=params)
    return data

SPLUNK_HEC_URL = 'https://localhost:8088/services/collector'
def post2hec(data, token, url=SPLUNK_HEC_URL):
    u'''POST metrics to Splunk HEC endpoint'''
    hec_headers = {"Authorization": "Splunk {}".format(token)}

    for hostId, values in data['tsdbLatest'].items():
        metrics = []
        for metric_name, v in values.items():
            metrics.append({
                "time": v['time'],
                "event": "metric",
                "source": "mackerel.io",
                "host": hostId,
                "fields": {
                    "metric_name": metric_name,
                    "_value": v['value'],
                },
            })
        post_data = "".join([json.dumps(m) for m in metrics])
        res = request(url, headers=hec_headers, data=post_data)
        logging.debug(json.dumps(res))

def main(mackerel_apikey, host_ids, splunk_url, hec_token):
    data = latest_metrics(mackerel_apikey, hostIds=host_ids)
    post2hec(data, url=splunk_url, token=hec_token)

if __name__ == '__main__':
    from argparse import ArgumentParser
    from ConfigParser import ConfigParser
    parser = ArgumentParser()
    parser.add_argument('-c', '--conf', dest='conf',
                        default='host_metrics.conf')
    args = parser.parse_args()
    conf_name = args.conf

    config = ConfigParser()
    config.read([conf_name])

    mackerel_apikey = config.get('mackerel', 'apikey')
    mackerel_base_url = config.get('mackerel', 'base_url')
    host_ids = [h.strip() for h in config.get('mackerel', 'host_ids').split(',')]
    hec_token = config.get('splunk', 'token')
    splunk_url = config.get('splunk', 'hec_url')

    main(mackerel_apikey, host_ids, splunk_url, hec_token)

