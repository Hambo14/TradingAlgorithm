#===================================================
#
# Author: Zane Hampton
#
# Created: 26/04/2022
# Last Edit: 26/04/2022
#
# Version: 0.01.00
#
# Notes: Functions to pull all data needed for the 
#        trading algorithm
#
# Script Name: parentClass.py 
#
# Description:
#
# Data is sourced using the IEX Cloud API. In order 
# for the data to be successfully requested, you need
# to have a valid IEX Cloud Token saved into your 
# environment variables as IEX_TOKEN.
#
#---------------------------------------------------

import pandas as pd
import numpy as np
import os
import requests

class iexCloud:

    def __init__(self, sandbox: bool) -> None:

        if sandbox == True:
            self.base_url = 'https://sandbox.iexapis.com/stable/'
            self.token = os.environ.get('IEX_SANDBOX_TOKEN')
        else:
            self.base_url = 'https://cloud.iexapis.com/v1'
            self.token = os.environ.get('IEX_TOKEN')

        self.params = {'token':self.token}
        pass

    def historicalData(self, stockTickers, range = None, date = None):
       endpoint = f'{self.base_url}/stock/{stockTickers}/chart'
       if range:
           endpoint += f'/{range}'
       elif date:
           endpoint += f'/date/{date}'
        
       resp = requests.get(endpoint, params = self.params)
       try:
           historicalData = resp.json()
       except:
           return print(resp.raise_for_status())
       return historicalData

if __name__ == '__main__':
    base_url = 'https://cloud.iexapis.com/v1'
    sandbox_url = 'https://sandbox.iexapis.com/stable/'

    token = os.environ.get('IEX_TOKEN')
    sandbox_token = os.environ.get('IEX_SANDBOX_TOKEN')

    params = {'token':token}
    sandbox_params = {'token':sandbox_token}

    resp = requests.get(sandbox_url + 'stock/AAPL/chart', params = sandbox_params)
    resp.raise_for_status()

    df = pd.DataFrame(resp.json())
    print(df.head())
