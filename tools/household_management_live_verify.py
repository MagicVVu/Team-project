"""Server-only TLS acceptance with uniquely scoped temporary users and households."""
import http.client
import json
import secrets
import socket
import ssl
import subprocess
from uuid import uuid4

marker="household-acceptance-"+uuid4().hex
context=ssl.create_default_context(cafile="/etc/magicvvu/ip-direct/ca/ca.crt")
checks={}
actors={key:{"id":str(uuid4()),"token":secrets.token_urlsafe(32)} for key in ("owner","admin","member","outsider")}


class Connection(http.client.HTTPSConnection):
    def connect(self):
        raw=socket.create_connection(("127.0.0.1",8000),timeout=self.timeout)
        self.sock=self._context.wrap_socket(raw,server_hostname=self.host)


def request(method,path,actor="owner",body=None):
    conn=Connection("8.134.172.165",8000,context=context,timeout=15)
    headers={"Content-Type":"application/json"}
    if actor:
        headers["Authorization"]="Bearer "+actors[actor]["token"]
    try:
        conn.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
        response=conn.getresponse()
        raw=response.read()
        return response.status,json.loads(raw) if raw else None
    finally:
        conn.close()


def check(name,condition):
    checks[name]=bool(condition)
    if not condition:
        raise AssertionError(name)


def database_script(source):
    r=subprocess.run(["docker","exec","-i","magicvvu-starter-backend-1","python","-B","-c",source],
        input=json.dumps({"marker":marker,"actors":actors}),text=True,capture_output=True,timeout=30)
    if r.returncode:
        raise RuntimeError("Synthetic database setup/cleanup failed")


seed='''
import json,sys
from uuid import UUID
from datetime import timedelta
from app.database import SessionLocal
from app.models import User,AuthSession
from app.security import digest_token,now_utc
data=json.load(sys.stdin)
with SessionLocal.begin() as db:
 for actor,v in data['actors'].items():
  db.add(User(id=UUID(v['id']),email=data['marker']+'-'+actor+'@example.invalid',display_name=data['marker']+'-'+actor,password_hash='disabled-test-fixture'))
 db.flush()
 for v in data['actors'].values():
  db.add(AuthSession(user_id=UUID(v['id']),token_hash=digest_token(v['token']),expires_at=now_utc()+timedelta(hours=1)))
'''
cleanup='''
import json,sys
from uuid import UUID
from sqlalchemy import delete,select,func
from app.database import SessionLocal
from app.models import User,AuthSession,Household,HouseholdMember
data=json.load(sys.stdin)
ids=[UUID(v['id']) for v in data['actors'].values()]
with SessionLocal.begin() as db:
 for user in db.scalars(select(User).where(User.id.in_(ids))):
  assert user.email.startswith(data['marker']+'-') and user.email.endswith('@example.invalid')
 homes=db.scalars(select(Household).where(Household.created_by_user_id.in_(ids))).all()
 for home in homes:
  assert home.name==data['marker'] or home.name==data['marker']+'-other'
  assert not db.scalar(select(func.count()).select_from(HouseholdMember).where(HouseholdMember.household_id==home.id,HouseholdMember.user_id.not_in(ids)))
  db.execute(delete(Household).where(Household.id==home.id))
 db.execute(delete(AuthSession).where(AuthSession.user_id.in_(ids)))
 db.execute(delete(User).where(User.id.in_(ids)))
with SessionLocal() as db:
 assert db.scalar(select(func.count()).select_from(User).where(User.id.in_(ids)))==0
'''

passed=False
error=None
try:
    database_script(seed)
    check("tls_health",request("GET","/health",None)[0]==200)
    check("anonymous_401",request("POST","/api/v1/households/"+str(uuid4())+"/leave",None)[0]==401)
    status,home=request("POST","/api/v1/households",body={"name":marker})
    check("create_household",status==201)
    root="/api/v1/households/"+home["id"]
    status,other=request("POST","/api/v1/households","outsider",{"name":marker+"-other"})
    check("create_other_household",status==201)
    for actor in ("admin","member"):
        status,invite=request("POST",root+"/invitations")
        check(actor+"_invite",status==201)
        check(actor+"_join",request("POST","/api/v1/households/join",actor,{"invite_code":invite["invite_code"]})[0]==200)
    check("owner_cannot_leave",request("POST",root+"/leave")[0]==409)
    check("outsider_cannot_manage",request("DELETE",root+"/members/"+actors["member"]["id"],"outsider")[0]==404)
    check("promote_admin",request("PATCH",root+"/members/"+actors["admin"]["id"],body={"role":"admin"})[0]==200)
    check("admin_cannot_transfer",request("POST",root+"/transfer-ownership","admin",{"new_owner_user_id":actors["member"]["id"]})[0]==403)
    status,item=request("POST",root+"/shopping-list/items","member",{"name":"Acceptance fixture","quantity":"1","unit":"box"})
    check("shared_shopping_write",status==201)
    status,_=request("POST",root+"/shopping-list/items/"+item["id"]+"/purchase","member",{})
    check("purchase_stocked",status==200)
    _,old_invite=request("POST",root+"/invitations","admin")
    check("admin_remove_member",request("DELETE",root+"/members/"+actors["member"]["id"],"admin")[0]==204)
    check("removed_cannot_read",request("GET",root+"/inventory-items","member")[0]==404)
    check("old_invite_revoked",request("POST","/api/v1/households/join","member",{"invite_code":old_invite["invite_code"]})[0]==400)
    status,inventory=request("GET",root+"/inventory-items")
    check("shared_stock_retained",status==200 and inventory["total"]==1)
    _,invite=request("POST",root+"/invitations")
    check("rejoin_with_new_invite",request("POST","/api/v1/households/join","member",{"invite_code":invite["invite_code"]})[0]==200)
    check("demote_admin",request("PATCH",root+"/members/"+actors["admin"]["id"],body={"role":"member"})[0]==200)
    check("demoted_cannot_invite",request("POST",root+"/invitations","admin")[0]==403)
    check("transfer_ownership",request("POST",root+"/transfer-ownership",body={"new_owner_user_id":actors["member"]["id"]})[0]==200)
    check("old_owner_cannot_dissolve",request("DELETE",root,body={"confirmation_name":marker})[0]==403)
    check("old_owner_leave",request("POST",root+"/leave")[0]==204)
    check("left_cannot_read",request("GET",root+"/shopping-list")[0]==404)
    check("new_owner_remove_member",request("DELETE",root+"/members/"+actors["admin"]["id"],"member")[0]==204)
    check("wrong_name_rejected",request("DELETE",root,"member",{"confirmation_name":"wrong"})[0]==409)
    check("dissolve_household",request("DELETE",root,"member",{"confirmation_name":marker})[0]==204)
    check("dissolved_cannot_read",request("GET",root+"/inventory-items","member")[0]==404)
    check("other_household_unaffected",request("GET","/api/v1/households/"+other["id"]+"/members","outsider")[0]==200)
    check("cleanup_other_household",request("DELETE","/api/v1/households/"+other["id"],"outsider",{"confirmation_name":marker+"-other"})[0]==204)
    passed=True
except Exception as exc:
    error=type(exc).__name__
finally:
    try:
        database_script(cleanup)
        checks["synthetic_users_and_data_removed"]=True
    except Exception:
        checks["synthetic_users_and_data_removed"]=False
    result={"passed":passed and all(checks.values()),"checks":checks,"error_type":error,"certificate_verified":True,"transport":"published TLS listener via server loopback"}
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(0 if result["passed"] else 1)
