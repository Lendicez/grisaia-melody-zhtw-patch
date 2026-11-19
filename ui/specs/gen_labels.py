import numpy as np, cv2, json
from PIL import Image
inv=json.load(open('inventory.json')); inv=inv if isinstance(inv,list) else inv.get('frames')
zh={f"{i['file']}#{i['frame']:03d}":i['zh'].split('\n') for i in inv}
def rows_in(f,x0,x1,y0=95,y1=720):
    a=np.array(Image.open(f'src/{f}.png').convert('RGBA')).astype(int); lum=a[...,:3].mean(-1)
    d=((lum[y0:y1,x0:x1]<110)&(a[y0:y1,x0:x1,3]>128)).astype(np.uint8)
    n,lab,st,_=cv2.connectedComponentsWithStats(d,8)
    boxes=sorted((y+y0,y+h+y0,x+x0,x+w+x0) for x,y,w,h,ar in st[1:] if w<=40 and 2<=h<=30)
    rows=[]
    for b in boxes:
        if rows and b[0]<rows[-1][1]+1 and b[1]>rows[-1][0]-1:
            r=rows[-1]; rows[-1]=[min(r[0],b[0]),max(r[1],b[1]),min(r[2],b[2]),max(r[3],b[3]),r[4]+1]
        else: rows.append([b[0],b[1],b[2],b[3],1])
    out=[]
    for r in rows:
        if r[4]<4: continue
        cols=((lum[r[0]:r[1],r[2]:r[3]+1]<110)).any(0)
        # icon then gap
        if r[1]-r[0] < 20: continue   # 沒有圖示的列（Slow/Fast 等）略過
        first=int(np.argmax(cols)); i=first+22
        while i<len(cols) and not cols[i]: i+=1
        ya, yb = r[0], min(r[1], r[0]+23)
        c2=(lum[ya:yb, r[2]+i:x1]<110).any(0)
        end=0; gap=0
        for j,v in enumerate(c2):
            if v: end=j; gap=0
            else:
                gap+=1
                if gap>=25: break
        out.append((int(r[2]+i), int(ya), int(r[2]+i+end+1), int(yb)))
    return out
groups=[]
def add(name, lines, regions):
    assert len(lines)==len(regions), (name, len(lines), len(regions), regions)
    for z,r in zip(lines,regions): groups.append([{"name":name,"zh":z,"region":r,"maxw":(470 if r[0]<640 else 450)}])
sub=[55,69,900,90]
# sys_text
L=rows_in('sys_text#075',70,640); R=rows_in('sys_text#075',675,1220)
regs=[[x-1,y0-1,x1+4,y1+1] for x,y0,x1,y1 in L+R]
add('sys_text#075', zh['sys_text#075'], regs)
L=rows_in('sys_dialogconf#077',70,640); R=rows_in('sys_dialogconf#077',672,1220)
z=zh['sys_dialogconf#077']; groups.append([{"name":"sys_dialogconf#077","zh":z[0],"region":sub,"size":19}])
add('sys_dialogconf#077', z[1:], [[x-1,y0-1,x1+4,y1+1] for x,y0,x1,y1 in L+R])
z=zh['sys_progress#227']; groups.append([{"name":"sys_progress#227","zh":z[0],"region":sub,"size":19}])
groups.append([{'name':'sys_progress#227','zh':z[1],'region':[143,597,470,621],'font':'msjh.ttc','size':22}])
groups.append([{'name':'sys_jump#000','zh':'跳轉中','region':[225,10,445,48],'font':'msjh.ttc','size':32,'align':'center','opt':{'light':True,'thr':30,'dilate':2}}])
json.dump({"font":"msjhbd.ttc","h_adj":0,"size":22,"probe":"設定確認","groups":groups},open('spec-labels.json','w'),ensure_ascii=False,indent=1)
for g in groups: print(g[0]['name'],g[0]['region'],g[0]['zh'])
