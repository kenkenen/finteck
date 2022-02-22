import requests
import json
import math
import sys
import boto3
from datetime import datetime
import time
import os
import pprint
from tabulate import tabulate

pp = pprint.PrettyPrinter(width=41, compact=True)
funds = int(sys.argv[1])
date = datetime.strptime(sys.argv[2], "%y%m%d")
expiration = str(time.mktime(date.timetuple()) - 18000).split(".")[0]
url = "https://yfapi.net/v7/finance/options/GME?date=" + expiration

try:
    yfApiKey = boto3.client('ssm').get_parameter(
        Name='yfApiKey',
        WithDecryption=True
    )
except Exception as e:
    if 'ExpiredTokenException' in str(e):
        print("AWS Session is expired. Renew session and try again.")
        sys.exit(0)
        # mfaToken = input("AWS Session expired, please enter MFA token: ")
        # os.system(".~/devops/kenkenen/aws/awsps.sh ken " + mfaToken)
        # yfApiKey = boto3.client('ssm').get_parameter(
        #     Name='yfApiKey',
        #     WithDecryption=True
        # )
    else:
        sys.exit(0)

headers = {
    'x-api-key': yfApiKey['Parameter']['Value']
}

response = requests.request("GET", url, headers=headers)

quote = response.json()['optionChain']['result'][0]['quote']
currentPrice = quote['regularMarketPrice']
puts = response.json()['optionChain']['result'][0]['options'][0]['puts']
putData = [
    [
        "Ticker",
        "GME",
        "Current Price:",
        "$ " + str(currentPrice)
    ],
    [
        "Symbol",
        "Strike",
        "Last Price",
        "Current Bid",
        "Current Ask",
        "Bid/Ask Average",
        "Volume",
        "Quantity",
        "Total Ext Value",
        "Target Buy Back",
        "Differential from Bid"
    ]
]
for put in puts:
    if 'volume' in put:
        symbol = put['contractSymbol']
        strike = put['strike']
        lastPrice = put['lastPrice']
        bid = put['bid']
        ask = put['ask']
        average = round((put['bid'] + put['ask']) / 2, 2)
        volume = put['volume']
        qty = math.ceil(funds/(strike * 100))
        if strike - currentPrice < 0:
            total = round(average * 100 * qty, 2)
        else:
            total = round((average - (strike - currentPrice)) * 100 * qty,2)
        targetBuyBack = round((average - .50), 2)
        if bid > 0:
            diffFromBid = round((targetBuyBack - bid) / bid, 4)
            if diffFromBid > 0.03:
                putData.append(
                    [
                        symbol,
                        '$ ' + str(strike),
                        '$ ' + str(lastPrice),
                        '$ ' + str(bid),
                        '$ ' + str(ask),
                        '$ ' + str(average),
                        volume,
                        qty,
                        '$ ' + str(total),
                        '$ ' + str(targetBuyBack),
                        diffFromBid
                    ]
                )
print(tabulate(putData))

