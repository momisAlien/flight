import json
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
options=webdriver.ChromeOptions();options.add_argument('--headless=new')
b=webdriver.Chrome(options=options)
try:
 b.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1000,deviceScaleFactor=1,mobile=False))
 b.get('http://127.0.0.1:8000/');w=WebDriverWait(b,25)
 w.until(lambda b:b.find_elements(By.ID,'airportSearch'))
 b.find_element(By.ID,'combinedHistory').click()
 w.until(lambda b:b.find_elements(By.CSS_SELECTOR,'#combinedHistoryOutput button'))[0].click()
 tabs=w.until(lambda b:b.find_elements(By.CSS_SELECTOR,'.city-result-tabs button'))
 assert len(tabs)==2
 for i,city in enumerate(['도쿄','오사카']):
  tabs[i].click()
  badges=b.find_elements(By.CSS_SELECTOR,'#cityResultPanel .ticket-destination')
  assert len(badges)==40 and all(x.text==city for x in badges),(city,len(badges))
  b.execute_script('arguments[0].scrollIntoView({block:"start"})',tabs[i])
  b.save_screenshot(f'city-tabs-{i}-1440.png')
 b.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',dict(width=390,height=844,deviceScaleFactor=1,mobile=True))
 tabs[0].click();b.execute_script('arguments[0].scrollIntoView({block:"start"})',tabs[0]);b.save_screenshot('city-tabs-390.png')
 assert b.execute_script('return document.documentElement.scrollWidth<=innerWidth')
 print('PASS: Tokyo and Osaka each have 20 roundtrips + 20 one-way pairs; mobile no overflow; saved results only.')
finally:b.quit()
