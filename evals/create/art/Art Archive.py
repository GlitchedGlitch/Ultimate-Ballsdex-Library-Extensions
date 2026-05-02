
# Note: On the up= line at the beginning you can put specific balls to update or create forums.
# There's also a new=True on the same line,
# False will update specific balls inputted or all the forums if left empty,
# True will only create missing forums useful for new balls updates
# Remember to put the Forum Channel ID on line 13

.eval
import asyncio,os
from io import BytesIO
from discord import File

ch=await bot.fetch_channel(ForumChannelIDHere)
up={"Ball 1", "Ball 2"}; new=True; s=1.2; B="./admin_panel/media/"
C={}; E={".png",".jpg",".jpeg",".gif",".webp"}

count=0 

def R(p):
 p=p[1:] if p and p[0]=="/" else p
 a=os.path.join(B,p or "")
 if a not in C:
  with open(a,"rb") as f:C[a]=f.read()
 return C[a]

def G(c,i):
 o=[]
 for k,pfx in (("wild_card","spawn"),("collection_card","card")):
  p=getattr(c,k,None)
  if not p: continue
  ex=os.path.splitext(p)[1].lower()
  if ex not in E: ex=".png"
  o.append((p,f"{pfx}_{i}{ex}"))
 return o

def MK(pairs):
 return [File(BytesIO(R(p)),filename=fn) for p,fn in pairs]

tc={t.name:t for t in ch.threads}
async for t in ch.archived_threads(limit=None): tc.setdefault(t.name,t)

for i,c in enumerate(await Ball.all(),1):
 n=c.country; t=tc.get(n)
 if new and t: continue
 if (not new) and t and n not in up: continue

 e=bot.get_emoji(int(c.emoji_id)) if c.emoji_id else None
 em=str(e) if e else ""

 cm=f"**Current**\n{em} **{n}**\nImage Credits: {c.credits}"
 am=f"{em} **{n}**\nImage Credits: {c.credits}"

 pairs=G(c,i)

 try:
  if t:
   if getattr(t,"archived",False): await t.edit(archived=False,locked=False)
   try:
    m=await t.fetch_message(t.id)
    await m.edit(content=cm,attachments=MK(pairs))
   except:
    await t.send(content=cm,files=MK(pairs))
   await t.send(content=am,files=MK(pairs))
  else:
   cr=await ch.create_thread(name=n,content=cm,files=MK(pairs))
   await cr.thread.send(content=am,files=MK(pairs))
   tc[n]=cr.thread

  count+=1 

 except Exception as ex:
  print("Fail",n,ex)

 await asyncio.sleep(s)

return f"Created/Updated {count} forums"
