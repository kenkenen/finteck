import math


def ophunt(funds, current_price, puts):
    put_data = [
        [
            "Ticker",
            "GME",
            "Current Price:",
            "$ " + str(current_price)
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
            last_price = put['lastPrice']
            bid = put['bid']
            ask = put['ask']
            average = round((put['bid'] + put['ask']) / 2, 2)
            volume = put['volume']
            qty = math.ceil(funds/(strike * 100))
            if strike - current_price < 0:
                total = round(average * 100 * qty, 2)
            else:
                total = round(((strike - current_price) - average) * 100 * qty,2)
            target_buy_back = round((average - (total / 100 / qty)), 2)
            if bid > 0:
                diff_from_bid = round((target_buy_back - bid) / bid, 4)
                if diff_from_bid > 0.03:
                    put_data.append(
                        [
                            symbol,
                            '$ ' + str(strike),
                            '$ ' + str(last_price),
                            '$ ' + str(bid),
                            '$ ' + str(ask),
                            '$ ' + str(average),
                            volume,
                            qty,
                            '$ ' + str(total),
                            '$ ' + str(target_buy_back),
                            diff_from_bid
                        ]
                    )
    return put_data
