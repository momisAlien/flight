from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from pathlib import Path
import json
browser=webdriver.Chrome()
try:
 browser.set_window_size(1440,1100)
 browser.get('http://127.0.0.1:8000/')
 WebDriverWait(browser,20).until(lambda d:d.find_elements('id','airportSearch') and '8,798' in d.find_element('id','airportSearch').find_element('xpath','..').text)
 browser.find_element('id','airportSearch').send_keys('파리')
 WebDriverWait(browser,5).until(lambda d:'CDG' in d.find_element('id','airportMatches').text)
 buttons=browser.find_element('id','airportMatches').find_elements('tag name','button')
 next(b for b in buttons if 'CDG' in b.text).click()
 browser.save_screenshot('simple-search-desktop.png')
 print('desktop',browser.execute_script('return {width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,selected:document.getElementById("destinationCodes").value}'))
 browser.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
 browser.save_screenshot('simple-search-mobile.png')
 print('mobile',browser.execute_script('return {width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth}'))
 print('browser_errors',browser.get_log('browser'))
finally: browser.quit()
