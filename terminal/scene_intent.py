"""Single-object parsing inside the explicitly invoked scene tool."""
import re

KINDS = {'衣柜':'wardrobe','双开门衣柜':'wardrobe','可开门衣柜':'wardrobe',
         '桌子':'table','桌':'table','椅子':'chair','椅':'chair','小球':'sphere','球':'sphere',
         '电脑':('asset','computer'),'显示器':('asset','monitor'),'键盘':('asset','keyboard'),
         '笔记本电脑':('asset','laptop')}


def direct_edit(text):
    text=text.strip().rstrip('。.!！')
    # Exact, single-object creation means a fresh scene; addition is explicit.
    match=re.fullmatch(r'(?:请|帮我|请帮我)?(?:生成|生产成|创建)(?:一个|一把|一张)?('+'|'.join(KINDS)+r')',text)
    if not match:
        # Corrections such as "现在打开的是完整场景，我只需要一个衣柜".
        match=re.search(r'(?:只要|只需要|只生成|仅生成|仅需要)(?:的)?(?:一个|一把|一张)?('+'|'.join(KINDS)+r')(?:[，,。!！]|$)',text)
        if match and re.search(r'不要只|不是只|不只|是否|怎么|如何|[?？]',text): return None
        if match:
            remainder=text[match.end():].strip('，,。!！ ')
            if remainder and not re.fullmatch(r'(?:不要|不需要)(?:其他|其它|其余|别的)(?:物品|东西|物体|家具)?',remainder): return None
    if not match: return None
    noun=match[1];kind=KINDS[noun]
    item={'name':kind if isinstance(kind,str) else kind[1], 'kind':kind if isinstance(kind,str) else kind[0]}
    if isinstance(kind,tuple): item['query']=kind[1]
    return {'base':'empty','add':[item], 'assumptions':['Explicit single-object request; previous saved scenes are retained on disk.']}
