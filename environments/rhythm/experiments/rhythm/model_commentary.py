"""Two finite JSON records: action first, then a short live public explanation."""
import json

INSTRUCTION='''\nOUTPUT FORMAT OVERRIDE (also overrides older ONLY clauses in model_memory):
In this SAME response, emit exactly two JSON records separated by a newline.
FIRST: the unchanged requested action JSON. Finish it before writing anything else.
SECOND: {"comment":"one brief Chinese public explanation, at most 80 characters"}.
Explain visible evidence and the action choice briefly, including when choosing no taps.
No step-by-step derivation or private chain of thought. No new commands in the comment.
No Markdown or extra records. The complete first record is dispatched immediately;
the comment is displayed live separately and never changes any action or time.
'''


def prompt(base,language='zh'):
    if language not in ('zh','en'):raise ValueError('Unsupported commentary language')
    return base+(INSTRUCTION.replace('Chinese','English') if language=='en' else INSTRUCTION)


def action_prefix(text):
    start=len(text)-len(text.lstrip())
    value,end=json.JSONDecoder().raw_decode(text,start)
    if not isinstance(value,dict):raise ValueError('Action record must be an object')
    return text[start:end],end


def comment_prefix(text):
    action,end=action_prefix(text)
    rest=text[end:]
    if not rest or '\n' not in rest[:len(rest)-len(rest.lstrip())]:raise ValueError('Expected newline before comment')
    start=end+len(rest)-len(rest.lstrip())
    value,stop=json.JSONDecoder().raw_decode(text,start)
    if not isinstance(value,dict) or set(value) != {'comment'} or not isinstance(value['comment'],str) or len(value['comment'])>80:
        raise ValueError('Expected one comment string of at most80 characters')
    return action,value['comment'],stop


def complete(text):
    action,comment,end=comment_prefix(text)
    if text[end:].strip():raise ValueError('Unexpected content after comment record')
    return action,comment
