"""Read-only browser check of time controls and existing saved results."""
import json
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
options=webdriver.ChromeOptions()
options.add_argument('--headless=new')
browser=webdriver.Chrome(options=options)
report={}
try:
    browser.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',dict(width=1440,height=1000,deviceScaleFactor=1,mobile=False))
    browser.get('http://127.0.0.1:8000/')
    wait=WebDriverWait(browser,20)
    wait.until(lambda b:b.find_elements(By.ID,'searchOutStart'))
    browser.find_element(By.CSS_SELECTOR,'.search-time-settings summary').click()
    browser.save_screenshot('time-settings-1440.png')
    browser.find_element(By.ID,'combinedHistory').click()
    wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'#combinedHistoryOutput button'))[0].click()
    badge=wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'.ticket-destination'))[0]
    browser.execute_script('arguments[0].scrollIntoView({block:"center"})',badge)
    report['destination']=badge.text
    report['badge_border']=browser.execute_script('return getComputedStyle(arguments[0]).borderStyle',badge)
    report['notice']=browser.find_element(By.ID,'combinedOutput').text[:1000]
    browser.save_screenshot('destination-badge-1440.png')
    browser.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',dict(width=390,height=844,deviceScaleFactor=1,mobile=True))
    browser.execute_script('arguments[0].scrollIntoView({block:"center"})',badge)
    browser.save_screenshot('destination-badge-390.png')
    report['mobile_no_overflow']=browser.execute_script('return document.documentElement.scrollWidth<=innerWidth')
    browser.execute_script('document.querySelector(".search-time-settings").scrollIntoView({block:"center"})')
    browser.save_screenshot('time-settings-390.png')
    report['controls']=len(browser.find_elements(By.CSS_SELECTOR,'.search-time-settings input[type=time]'))
    assert report['mobile_no_overflow'] and report['controls']==4 and report['badge_border']=='solid',report
    Path('time-settings-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=True))
finally:
    browser.quit()
