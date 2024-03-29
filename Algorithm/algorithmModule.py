#====================================================================
#
# Author: Zane Hampton
#
# Created: 26/04/2022
# Last Edit: 21/08/2022
#
# Version: 0.01.00
#
# Notes: All classes and functions used to run algorithm
#
# Script Name: algorithmModule.py
#
# Description:
#
# Historical price data is sourced using the IEX Cloud API. In order
# for the data to be successfully requested, you need to have a
# valid IEX Cloud Token saved into your environment variables as
# IEX_TOKEN and IEX_SANDBOX_TOKEN. The fundamental ratios used in 
# the algorithm is sourced using yfinance. Data is stored into SQLite3
# database.
#
#-------------------------------------------------------------------

import pandas as pd
import os
import requests
import yfinance as yf
from scipy import stats
from bs4 import BeautifulSoup as bs
import multiprocessing as mp
from datetime import datetime
import json
import sqlite3

def convertToString(stockTickers):
    if type(stockTickers) == str:
            stockTickers = stockTickers.split()

    tickerString = ','.join(stockTickers)

    return tickerString, stockTickers

# Yield successive n-sized chunks from lst
def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

class requestError(Exception):
    pass

# Following class will be used to determine each stock on the SPX ranking
class requestData:

    '''requestData class is used to retrieve financial data and to rank the stocks'''

    def __init__(self, sandbox: bool) -> None:

        if sandbox == True:
            self.base_url = 'https://sandbox.iexapis.com/stable/'
            try:
                with open("secrets.json") as f:
                    self.token = json.load(f)['IEX_SANDBOX_TOKEN']
            except:
                self.token = os.environ.get('IEX_SANDBOX_TOKEN')
        else:
            self.base_url = 'https://cloud.iexapis.com/v1'
            try:
                with open("secrets.json") as f:
                    self.token = json.load(f)['IEX_TOKEN']
            except:
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

        #tickerList = convertToString(stockTickers)[1]
        tickerList = ' '.join(stockTickers)
        tickers = yf.Tickers(tickerList)
        tickersDict = tickers.tickers

        columns = ['Ticker','PB', 'ROE']
        fundamentalsDf = pd.DataFrame(index=stockTickers)
        for ticker in tickersDict.keys():
            tickerInfo = tickersDict[f'{ticker}'].info

            try:
                PB = tickerInfo['priceToBook']
            except KeyError:
                PB = None

            try:
                ROE = tickerInfo['returnOnEquity']
            except KeyError:
                ROE = None

            fundamentalsDf = fundamentalsDf.append(
                pd.Series(
                    [
                        f'{ticker}',
                        PB,
                        ROE
                    ],
                    index = columns
                ),
                ignore_index=True
            )
        fundamentalsDf.dropna(inplace = True)
        return fundamentalsDf
    
    def fundParallelProcessing(self, stockTickers: list or str):

        stockChunks = chunks(stockTickers, round(len(stockTickers)/mp.cpu_count()))
        pool = mp.Pool(mp.cpu_count())
        stockFund = pool.map(self.fundamentals, [stockTickers for stockTickers in stockChunks])
        pool.close()
        stockFundDf = pd.concat(stockFund)

        return stockFundDf

    # Finds the average monthly return for each stock
    def averageMonthlyReturn(self, stockTickers: list):

        if len(stockTickers) > 100:

            stockChunks = list(chunks(stockTickers, 100))
            monthlyReturnDict = {}

            for chunk in stockChunks:
                monthlyData = self.historicalData(chunk, range = '3m')

                for ticker in chunk:
                    tickerDf = pd.json_normalize(monthlyData[f'{ticker}'], record_path=['chart'])
                    monthlyReturnDict[f'{ticker}'] = (tickerDf['changePercent'].mean())*21
        else:

            monthlyData = self.historicalData(stockTickers, range = '3m')
            monthlyReturnDict = {}

            for ticker in stockTickers:
                tickerDf = pd.json_normalize(monthlyData[f'{ticker}'], record_path=['chart'])
                monthlyReturnDict[f'{ticker}'] = (tickerDf['changePercent'].mean())*21

        return monthlyReturnDict

    # Compiles the price to book, return on equity and monthly rate of return into
    # one dataframe
    def completeData(self, stockTickers: list):
        fundamentalsDf = self.fundParallelProcessing(stockTickers)
        monthlyRoR = self.averageMonthlyReturn(list(fundamentalsDf['Ticker']))

        fundamentalsDf.insert(3,'RoR',monthlyRoR.values(),True)
        fundamentalsDf.reset_index(drop=True,inplace=True)
        return fundamentalsDf

    def stocksRanked(self, stockTickers: list):
        finData = self.completeData(stockTickers)

        for row in finData.index:
            for column in range(1,4):
                finData.iloc[row,column] = stats.percentileofscore(
                                                            finData.iloc[:,column],
                                                            finData.iloc[row,column],
                                                            )
        finData["sum"] = finData.sum(axis=1, numeric_only=True)
        rankStocks = finData.iloc[:,[0,4]]
        rankStocks.sort_values(by=['sum'],ascending=False,inplace=True)
        rankStocks.reset_index(drop=True,inplace=True)
        rankStocks.columns = ['Ticker','sum']
        return rankStocks

class portfolio:

    '''Following class will be used to execute buy and sell orders, rebalance the portfolio
    and keep a log of all buy and sell orders. The class will first be defined through a
    class method that will datascrape all the tickers in the S&P 500, rank them using
    requestData.stocksRanked(), and then pick the highest ranking stocks'''

    def __init__(self, sandbox: bool, portfolioValue) -> None:

        self.dataRequester = requestData(sandbox)

        # SET UP THE SQLITE DATABASE TO STORE DATA
        conn = sqlite3.connect('portfolio.db')
        c = conn.cursor()

        try:
            c.execute("""CREATE TABLE portfolioValue(Date INT,Value REAL)""")
            c.execute("""CREATE TABLE portfolio(Ticker TEXT, numShares REAL, holdAmount REAL)""")
            c.execute("""CREATE TABLE orderHistory(Date INT, Ticker TEXT, sharesBought REAL, sharePrice REAL)""")
        except:
            None
        c.execute(f"INSERT INTO portfolioValue VALUES ({int(datetime.today().strftime('%Y%m%d'))},{portfolioValue})")

        conn.commit()
        conn.close()

        None

    def portfolioValue(self):
        
        # RETRIEVE THE LATEST VALUE OF THE PORTFOLIO
        conn = sqlite3.connect('portfolio.db')
        c = conn.cursor()
        c.execute("""SELECT Value 
                     FROM portfolioValue 
                     WHERE Date = (
                        SELECT MAX(Date)
                        FROM portfolioValue
                     )""")
        conn.commit()
        self._portfolioValue = c.fetchone()[0]
        conn.close()
        return self._portfolioValue

    @staticmethod
    def spxList():
        url = 'https://www.slickcharts.com/sp500'
        request = requests.get(url,headers={'User-Agent': 'Mozilla/5.0'})
        soup = bs(request.text, "lxml")
        stats = soup.find('table',class_='table table-hover table-borderless table-sm')
        spx = pd.read_html(str(stats))[0]
        spx['% Chg'] = spx['% Chg'].str.strip('()-%')
        spx['% Chg'] = pd.to_numeric(spx['% Chg'])
        spx['Chg'] = pd.to_numeric(spx['Chg'])
        return spx

    def createPortfolio(self):
        stockList = self.spxList()['Symbol']
        stocksToBuy = self.dataRequester.stocksRanked(stockList[0:25])
        stocksToBuy = stocksToBuy.loc[0:9,'Ticker']
        portfolioValue = self.portfolioValue()

        portfolioRow = []
        orderHistoryRow = []
        sharePrices = self.spxList()[['Symbol','Price']]
        sharePrices.set_index('Symbol', inplace=True)
        for stock in stocksToBuy:
            price = sharePrices.loc[stock, 'Price']
            shareNumber = (portfolioValue/len(stocksToBuy))/price
            holdingAmount = price*shareNumber
            portfolioRow.append(tuple([stock,shareNumber,holdingAmount]))
            orderHistoryRow.append(tuple(
                [int(datetime.today().strftime('%Y%m%d')),
                stock,
                shareNumber,
                price]))
            
        conn = sqlite3.connect('portfolio.db')
        c = conn.cursor()
        c.executemany("INSERT INTO portfolio VALUES (?,?,?);",portfolioRow)
        c.executemany("INSERT INTO orderHistory VALUES (?,?,?,?);",orderHistoryRow)
        conn.commit()
        conn.close()

        None

    def portfolio(self):

        conn = sqlite3.connect('portfolio.db')
        portfolioDf = pd.read_sql_query("SELECT * FROM portfolio",conn)
        conn.close()
        self._portfolio = portfolioDf

        return portfolioDf
    
    def orderHistory(self):

        conn = sqlite3.connect('portfolio.db')
        orderHistoryDf = pd.read_sql_query("SELECT * FROM orderHistory", conn)
        conn.close()
        self._orderHistory = orderHistoryDf

        return orderHistoryDf

    def updatePortfolio(self):
        self.portfolio()
        stockList = self._portfolio.loc[:,"Ticker"].values
        newHistoricalData = self.dataRequester.historicalData(stockList)
        newStockPrices = []
        for stock in stockList:
            newStockPrice = pd.json_normalize(newHistoricalData[stock],record_path=['chart']).tail(1)["close"].values[0]
            newStockPrices.append(newStockPrice)

        portfolioRow = []
        stockRow = []
        for i, stockPrice in enumerate(newStockPrices):
            holdingAmount = stockPrice*self._portfolio.loc[i,"numShares"]
            portfolioRow.append(tuple([holdingAmount]))
            stockRow.append(tuple([stockList[i]]))
        
        conn = sqlite3.connect('portfolio.db')
        c = conn.cursor()
        for hold, stock in zip(portfolioRow,stockRow):
            c.execute("UPDATE portfolio SET holdAmount = (?) WHERE Ticker = (?)",(hold[0],stock[0],))

        d = conn.cursor()
        d.execute("SELECT holdAmount FROM portfolio")
        portfolioValue = sum([i[0] for i in d.fetchall()])
        c.execute("INSERT INTO portfolioValue VALUES (?,?)",(int(datetime.today().strftime('%Y%m%d')),portfolioValue))
        
        conn.commit()
        conn.close()

        None

    def rebalancePortfolio(self):
        self.portfolioValue()
        self.portfolio()
        stockList = self.spxList()['Symbol']
        stocksToBuy = self.dataRequester.stocksRanked(stockList[0:25])
        stocksToBuy = stocksToBuy.loc[0:9,'Ticker']

        sharePrices = self.spxList()[['Symbol','Price']]
        sharePrices.set_index('Symbol', inplace=True)
        conn = sqlite3.connect('portfolio.db')
        c = conn.cursor()
        c.execute("DELETE FROM portfolio;")
        for stock in stocksToBuy:
            price = sharePrices.loc[stock, 'Price']
            shareNumber = (self._portfolioValue/len(stocksToBuy))/price
            holdingAmount = price*shareNumber
        
            if (stock in self._portfolio["Ticker"].values):
                sharesOwned = self._portfolio.loc[self._portfolio["Ticker"] == stock].values[0][1]
                amountToBuy = shareNumber - sharesOwned
            else:
                amountToBuy = shareNumber

            c.execute("INSERT INTO portfolio VALUES (?,?,?);",(stock,shareNumber,holdingAmount))
            c.execute("INSERT INTO orderHistory VALUES (?,?,?,?)",(int(datetime.today().strftime('%Y%m%d')),stock,amountToBuy,price))
        conn.commit()
        conn.close()

        None

if __name__ == '__main__':
    None
