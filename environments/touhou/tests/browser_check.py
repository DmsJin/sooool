from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={"width":1280,"height":940})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    from datetime import datetime,timedelta,timezone
    fixed=datetime(2026,1,1,tzinfo=timezone.utc)
    page.clock.install(time=fixed)
    page.clock.pause_at(fixed+timedelta(seconds=1))
    response=page.goto('http://127.0.0.1:8791')
    assert response.status==200
    page.screenshot(path='/tmp/kaguya-v5-title.png',full_page=True)
    page.get_by_role('button',name='开始练习').click()
    page.clock.run_for(700)
    assert page.evaluate('danmaku.getPresentation().intro')>0
    assert page.evaluate('danmaku.getState().tick')==0
    assert page.evaluate('danmaku.getPresentation().portraitLoaded')
    page.screenshot(path='/tmp/kaguya-v5-cutin.png',full_page=True)
    page.clock.run_for(2300)
    initial=page.evaluate('danmaku.getState()')
    page.keyboard.down('ArrowLeft')
    page.keyboard.down('KeyZ')
    page.clock.run_for(800)
    page.keyboard.up('ArrowLeft')
    page.keyboard.up('KeyZ')
    state=page.evaluate('danmaku.getState()')
    assert state['player']['x']<initial['player']['x']
    assert state['shots'] or state['score']>0
    page.keyboard.down('KeyX')
    page.clock.run_for(30)
    page.keyboard.up('KeyX')
    assert page.evaluate('danmaku.getState().player.bombs')==2
    assert page.evaluate('danmaku.getState().bombOrbs.length')==8
    page.clock.run_for(300)
    page.screenshot(path='/tmp/kaguya-v5-dream-seal.png',full_page=True)
    page.keyboard.press('Escape')
    tick=page.evaluate('danmaku.getState().tick')
    page.clock.run_for(500)
    assert page.evaluate('danmaku.getState().tick')==tick
    page.keyboard.press('Escape')
    page.get_by_role('button',name='重新开始',exact=True).click()
    page.clock.run_for(8000)
    page.screenshot(path='/tmp/kaguya-v5-gameplay.png',full_page=True)
    page.keyboard.down('KeyZ')
    found_crash=False
    for _ in range(200):
        page.clock.run_for(200)
        state=page.evaluate('danmaku.getState()')
        if state['player']['dying']>0:
            found_crash=True
            page.screenshot(path='/tmp/kaguya-v5-crash.png',full_page=True)
            x=state['player']['x']
            page.keyboard.down('ArrowLeft')
            page.clock.run_for(100)
            page.keyboard.up('ArrowLeft')
            assert page.evaluate('danmaku.getState().player.x')==x
            page.clock.run_for(800)
            assert page.evaluate('danmaku.getState().player.dying')==0
            assert page.evaluate('danmaku.getState().player.inv')>0
            break
    assert found_crash
    page.clock.run_for(70000)
    final=page.evaluate('danmaku.getState()')
    assert final['status'] in ('lost','won','survived'),final
    assert page.locator('#overlay').is_visible()
    page.get_by_role('button',name='再来一局').click()
    assert page.evaluate('danmaku.getState().player.lives')==3
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path='/tmp/kaguya-v5-mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.locator('.menu-portrait').evaluate('(img)=>img.complete && img.naturalWidth>0')
    assert not errors,errors
    print('Browser gameplay passed: start, move, shoot, bomb, pause, restart, complete episode, mobile layout.', final['status'], final['tick'])
    browser.close()
