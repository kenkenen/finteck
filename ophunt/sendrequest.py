import requests


def sendrequest(requestdata):
    try:
        if requestdata['method'] == 'GET':
            res = requests.get(
                requestdata['resource'],
                headers=requestdata['headers'],
                params=requestdata['params']
            ).json()
            return res
        elif requestdata['method'] == 'POST' and 'json' in requestdata:
            res = requests.post(
                requestdata['resource'],
                headers=requestdata['headers'],
                json=requestdata['json']
            ).json()
            return res
        elif requestdata['method'] == 'POST':
            res = requests.post(
                requestdata['resource'],
                params=requestdata['params']
            ).json()
            return res
    except Exception as e:
        print('Api request failed to send: %s', e)
        return False