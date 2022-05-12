#===================================================
#
# Author: Zane Hampton
#
# Created: 05/05/2022
# Last Edit: 05/05/2022
#
# Version: 0.01.00
#
# Notes: Class that will buy, sell, rebalance and hold 
#        transaction history
#
# Script Name: portfolio.py 
#
# Description:
#
#---------------------------------------------------

import algorithmModule as am

if __name__ == "__main__":
    portfolio = am.portfolio(sandbox=True)
    print(portfolio.spxList())