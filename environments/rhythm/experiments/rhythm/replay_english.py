"""English presentation strings. Never translate model-authored commentary."""
STRINGS={
'GPT 实时决策':'GPT Live Decisions','GPT 决策回放':'GPT Decision Replay',
'gpt-6.1-sol  /  ultrafast  /  原速 1×  /  响应节选':'gpt-6.1-sol / ultrafast / 1x speed / selected responses',
'看到的画面':'Frame captured','解说收到时刻':'Comment received','这条响应返回':'Response received',
'生成中…':'Streaming…','完整 API 响应耗时':'Full API latency',
'正在等待第一条动作响应…':'Waiting for the first action response…',
'GPT 当场解说':'GPT Live Commentary','GPT 回看解说':'Retrospective Commentary',
'同次响应':'Same response','事后生成':'Retrospective',
'动作已交付，正在接收同次响应的解说…':'Action delivered. Receiving commentary from the same response…',
'模型读取原始截图，根据音符位置和公开时钟输出按键时间。':'Reading the frame. The model chooses keys and literal tap times.',
'动作先交付，解说紧随其后；文字为模型当场原文。':'Actions arrive first. Commentary is the model\'s original live text.',
'解说依据截图与日志生成；原始记录只有动作输出。':'Retrospective captions based on screenshots and action logs.',
'当时的原始输出':'Original action JSON','{"a":[]}  // 尚无响应':'{"a":[]}  // awaiting response',
'按键':'Key','模型计划的歌曲内时刻':'Planned song time','动作交付时的余量':'Lead at delivery',
'响应返回时的余量':'Lead at response','等待实际按键事件':'Waiting for key events',
'实采截图拼接 · 原速 1× · 同次 API 响应的动作与简短解说':'Captured compositor frames / 1x speed / actions and live commentary from the same API response',
'实采截图拼接 · 中文标签勘误 · 回看解说非原始推理记录':'Sampled screenshots / corrected labels / retrospective commentary'
}

def translate(text):
    if text in STRINGS:return STRINGS[text]
    text=text.replace('最新实际按键','Latest executed key').replace('相对模型计划','vs model plan')
    if text.startswith('另有 '):
        count=text.split()[1];return f'{count} more actions; see original JSON above'
    return text

class EnglishDraw:
    def __init__(self,draw):self.draw=draw
    def __getattr__(self,name):return getattr(self.draw,name)
    def text(self,xy,text,**kwargs):return self.draw.text(xy,translate(text),**kwargs)
