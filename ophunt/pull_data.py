import requests
import math
import sys
import boto3
from datetime import datetime
import time
import pprint
from tabulate import tabulate
from ssm import Ssm
import json

pp = pprint.PrettyPrinter(width=41, compact=True)
funds = int(sys.argv[1])
shares = int(sys.argv[2])
costBasis = int(sys.argv[3])
date = datetime.strptime(sys.argv[4], "%y%m%d")
expiration = str(time.mktime(date.timetuple()) - 18000).split(".")[0]
url = "https://yfapi.net/v7/finance/options/GME?date=" + expiration

try:
    yfApiKey = boto3.client('ssm').get_parameter(
        Name='yfApiKey',
        WithDecryption=True
    )
    tsApiKey = json.loads(boto3.client('ssm').get_parameter(
        Name='tsApiKey',
        WithDecryption=True
    )['Parameter']['Value'])
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
options = response.json()['optionChain']['result'][0]['options']
def ophunt(funds, current_price, options):

    if options:
        print("Options found. Parsing...")

    options_data = [
        [
            "Ticker",
            "GME",
            "Current Price:",
            "$ " + str(current_price)
        ],
        [
            "Symbol",
            "Strike",
            "Last",
            "Bid",
            "Ask",
            "Average",
            "Volume",
            "Qty",
            "Ext Value",
            "Target Buy Back",
            "Trigger",
            "Differential",
            "Expiry Profit"
        ],
        [
            "Puts  ++++++++++++"
        ]
    ]

    for put in options[0]['puts']:
        if 'volume' in put:
            symbol = put['contractSymbol']
            strike = put['strike']
            last_price = put['lastPrice']
            bid = put['bid']
            ask = put['ask']
            average = round((put['bid'] + put['ask']) / 2, 2)
            volume = put['volume']
            qty = math.ceil(funds/(strike * 100))
            if strike - current_price < 0:
                int_value = 0
            else:
                int_value = strike - current_price
            ext_value = round(average - int_value, 2)
            target_buy_back = round((average - (ext_value * .50)), 2)
            profit = round((ext_value) * qty * 100, 2)
            trigger = round(target_buy_back + ((ask - bid) / 2), 2)
            if bid > 0:
                diff_from_bid = round((target_buy_back - bid) / bid, 4)
                if ext_value > 0:
                    options_data.append(
                        [
                            symbol,
                            '$ ' + str(strike),
                            '$ ' + str(last_price),
                            '$ ' + str(bid),
                            '$ ' + str(ask),
                            '$ ' + str(average),
                            volume,
                            qty,
                            '$ ' + str(ext_value),
                            '$ ' + str(target_buy_back),
                            '$ ' + str(trigger),
                            diff_from_bid,
                            '$ ' + str(profit)
                        ]
                    )

    options_data.append(
        [
            "Calls ++++++++++++"
        ]
    )

    for call in options[0]['calls']:
        if 'volume' in call:
            symbol = call['contractSymbol']
            strike = call['strike']
            last_price = call['lastPrice']
            bid = call['bid']
            ask = call['ask']
            average = round((call['bid'] + call['ask']) / 2, 2)
            volume = call['volume']
            qty = math.ceil(shares / 100)
            if current_price - strike < 0:
                int_value = 0
            else:
                int_value = current_price - strike
            ext_value = round(average - int_value, 2)
            target_buy_back = round((average - (ext_value * .50)), 2)
            profit = round((ext_value) * qty * 100, 2)
            trigger = round(target_buy_back + ((ask - bid) / 2), 2)
            if bid > 0:
                diff_from_bid = round((target_buy_back - bid) / bid, 4)
                if ext_value > 0 and strike > costBasis:
                    options_data.append(
                        [
                            symbol,
                            '$ ' + str(strike),
                            '$ ' + str(last_price),
                            '$ ' + str(bid),
                            '$ ' + str(ask),
                            '$ ' + str(average),
                            volume,
                            qty,
                            '$ ' + str(ext_value),
                            '$ ' + str(target_buy_back),
                            '$ ' + str(trigger),
                            diff_from_bid,
                            '$ ' + str(profit)
                        ]
                    )
    print("Results: ")
    print(tabulate(options_data))


ophunt(funds, currentPrice, options)