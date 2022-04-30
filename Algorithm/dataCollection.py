#===================================================
#
# Author: Zane Hampton
#
# Created: 26/04/2022
# Last Edit: 01/05/2022
#
# Version: 0.01.00
#
# Notes: Functions to pull all data needed for the trading algorithm
#
# Script Name: dataCollection.py 
#
# Description:
#
# Historical price data is sourced using the IEX Cloud API. In order 
# for the data to be successfully requested, you need to have a
# valid IEX Cloud Token saved into your environment variables as 
# IEX_TOKEN. The fundamental ratios used in the algorithm is sourced
# using yfinance.
#
#---------------------------------------------------

import pandas as pd
import os
import requests
import yfinance as yf

def convertToString(stockTickers):
    if type(stockTickers) == str:
            stockTickers = stockTickers.split()

    tickerString = ','.join(stockTickers)
    
    return tickerString, stockTickers

class requestError(Exception):
    pass

class requestData:

    def __init__(self, sandbox: bool) -> None:

        if sandbox == True:
            self.base_url = 'https://sandbox.iexapis.com/stable/'
            self.token = os.environ.get('IEX_SANDBOX_TOKEN')
        else:
            self.base_url = 'https://cloud.iexapis.com/v1'
            self.token = os.environ.get('IEX_TOKEN')

        self.params = {'token':self.token}
        pass

    # Downloads monthly historical adjusted closing prices from the last quarter
    def historicalData(self, stockTickers, range = None, date = None):
        
        tickerString, tickerList = convertToString(stockTickers = stockTickers)

        if len(tickerList) == 1:
            endpoint = f'{self.base_url}/stock/{tickerString}/chart'
            if range:
                endpoint += f'/{range}'
            elif date:
                endpoint += f'/date/{date}'
        elif len(tickerList) > 1:
            endpoint = f'{self.base_url}/stock/market/batch?symbols={tickerString}&types=chart'
            if range:
                endpoint += f'&range={range}'
        elif len(tickerList) == 0:
            raise ValueError("Add one or more stocks to the list")

        endpoint += '&chartCloseOnly=true'
        resp = requests.get(endpoint, params = self.params)
        try:
            historicalData = resp.json()
        except:
            raise requestError(f'The request failed. Check if URL is valid. API status: {resp.raise_for_status()}')

        return historicalData

    # Downloads the price to book and return on equity ratio. Returns a dataframe
    def fundamentals(self, stockTickers: list or str):
        
        tickerList = convertToString(stockTickers)[1]
        tickers = [yf.Ticker(ticker) for ticker in tickerList]

        columns = ['Ticker','PB', 'ROE']
        fundamentalsDf = pd.DataFrame(index=stockTickers)
        for ticker in tickers:
            tickerInfo = ticker.info

            fundamentalsDf = fundamentalsDf.append(
                pd.Series(
                    [
                        ticker.ticker,
                        tickerInfo['priceToBook'],
                        tickerInfo['returnOnEquity']
                    ],
                    index = columns
                ),
                ignore_index=True
            )
        fundamentalsDf.dropna(inplace = True)
        return fundamentalsDf

    # Finds the average monthly return for each stock
    def averageMonthlyReturn(self, stockTickers: list):
        monthlyData = self.historicalData(stockTickers, range = '3m')

        monthlyReturnDict = {}
        for ticker in stockTickers:
            tickerDf = pd.json_normalize(monthlyData[f'{ticker}'], record_path=['chart'])
            monthlyReturnDict[f'{ticker}'] = (tickerDf['changePercent'].mean())*21
        return monthlyReturnDict
    
    # Compiles the price to book, return on equity and monthly rate of return into
    # one dataframe
    def completeData(self, stockTickers: list):
        fundamentalsDf = self.fundamentals(stockTickers)
        monthlyRoR = self.averageMonthlyReturn(stockTickers)
        
        fundamentalsDf.insert(3,'RoR',monthlyRoR.values(),True)
        return fundamentalsDf

if __name__ == '__main__':
    getData = requestData(sandbox = True)
    stockList = ['TWTR', 'GOOG', 'WFC']
    
    testDataFrame = getData.completeData(stockList)
    print(testDataFrame)
    None
