"""Local DOM acceptance for batched visible-card reads. No external requests."""
import json
import threading
from urllib.parse import quote
from flightcore.browser_prices import BrowserCollector


def main():
    collector=BrowserCollector('naver',threading.Event())
    try:
        collector.open()
        card='<div class="combination_ConcurrentItemContainer__test" {attrs}>{text}</div>'
        body=''.join(card.format(attrs=attrs,text=text) for attrs,text in [
            ('','Visible<br>same'),('','Visible<br>same'),
            ('style="display:none"','Hidden display'),
            ('style="visibility:hidden"','Hidden visibility'),
            ('style="opacity:0"','Hidden opacity')])
        body+='<div style="display:none">'+card.format(attrs='',text='Hidden parent')+'</div>'
        body+=card.format(attrs='style="position:absolute;top:5000px"',text='Below fold')
        collector.driver.get('data:text/html;charset=utf-8,'+quote(body))
        actual=[row['text'] for row in collector.visible_cards()]
        expected=[el.text for el in collector.driver.find_elements('css selector','[class*="combination_ConcurrentItemContainer__"]') if el.is_displayed()]
        assert actual==expected==['Visible\nsame','Visible\nsame','Below fold'],(actual,expected)
        print(json.dumps({'local_dom_pass':True,'visible':len(actual),'duplicates_retained':True,'below_fold_retained':True}))
    finally:
        collector.close()


if __name__=='__main__':main()
