from datetime import datetime,timedelta,timezone
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1280,'height':940})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8791')
    page.get_by_role('button',name='开始练习').click(timeout=30000)
    page.wait_for_function('!bgm.paused && bgm.currentTime>.5')
    page.wait_for_function('bgm.rms()>.001',timeout=10000)
    state=page.evaluate('danmaku.getPresentation()')
    assert state['assets']['ready'] and state['assets']['atlases']==13
    assert abs(state['bgm']['loopStart']-37.85868480725624)<1e-9
    assert abs(state['bgm']['loopEnd']-179.97786848072562)<1e-9
    assert abs(state['bgm']['duration']-179.97786848072562)<.001
    page.keyboard.press('Escape');position=page.evaluate('bgm.currentTime')
    page.wait_for_timeout(250)
    assert page.evaluate('bgm.paused') and abs(page.evaluate('bgm.currentTime')-position)<.01
    page.keyboard.press('Escape')
    page.wait_for_function('!bgm.paused')
    page.evaluate('bgm.currentTime=bgm.points.loopEndSeconds-.12')
    page.wait_for_function('bgm.currentTime>37.858 && bgm.currentTime<39',timeout=5000)
    assert page.evaluate('bgm.source.loopStart')==state['bgm']['loopStart']
    assert page.evaluate('bgm.source.loopEnd')==state['bgm']['loopEnd']
    page.get_by_role('button',name='声音：开',exact=True).click();assert page.evaluate('bgm.muted')
    page.get_by_role('button',name='声音：关',exact=True).click();assert not page.evaluate('bgm.muted')
    page.locator('#bgm-volume').evaluate("e=>{e.value='25';e.dispatchEvent(new Event('input',{bubbles:true}));}")
    assert page.evaluate('bgm.volume')==.25
    page.locator('#bgm-volume').blur()
    page.get_by_role('button',name='重新开始',exact=True).click()
    page.wait_for_function('!bgm.paused && bgm.currentTime<1')
    page.wait_for_function('danmaku.getState().tick>100',timeout=15000)
    page.keyboard.down('KeyZ');page.wait_for_timeout(300);page.keyboard.up('KeyZ')
    assert page.evaluate('danmaku.getState().shots.length')>0
    page.screenshot(path='/tmp/th08-v5-final.png',full_page=True)
    page.keyboard.press('KeyX');page.wait_for_timeout(400)
    assert page.evaluate('danmaku.getState().bombOrbs.length')==8
    page.screenshot(path='/tmp/th08-v5-final-bomb.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path='/tmp/th08-v5-mobile.png',full_page=True)
    assert not errors,errors
    print('Original atlases, sprites, HUD, non-silent decoded OGG, exact loop wrap, pause/resume, mute, volume, restart and mobile layout passed.',state['bgm'])
    browser.close()
