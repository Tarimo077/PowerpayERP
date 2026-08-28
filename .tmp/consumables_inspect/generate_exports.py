import os,sys
from pathlib import Path
from datetime import date
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[2])); os.environ.setdefault("DJANGO_SETTINGS_MODULE","powerpayerp.settings")
import django
django.setup()
from django.contrib.auth.models import User
from django.db import connection
from django.test import RequestFactory
from erp.models import ItemRequest,ItemRequestLine,Organization,Profile
from erp.views import item_request_export
connection.creation.create_test_db(verbosity=0,autoclobber=True)
try:
    org=Organization.objects.create(name="PowerPay Africa",slug="powerpay-export-qa",business_email="info@powerpay.africa",address="Nairobi, Kenya")
    manager_user=User.objects.create_user("manager",first_name="Grace",last_name="Manager"); manager=Profile.objects.create(user=manager_user,organization=org,role="manager",position="Operations Manager")
    user=User.objects.create_user("requester",first_name="Alex",last_name="Employee"); Profile.objects.create(user=user,organization=org,role="employee",manager=manager,position="Operations Officer")
    req=ItemRequest.objects.create(organization=org,number="IR-2026-0001",requested_by=user,purpose="Office kitchen and cleaning supplies for normal operations.",needed_by=date(2026,9,10),delivery_location="Nairobi office",requested_approver=manager)
    rows=[("Sugar","2 kg",Decimal("305"),"https://www.quickmart.co.ke/mumias-sugar-2-kg-1","Brown sugar acceptable"),("Tissues","10 rolls",Decimal("299"),"https://www.quickmart.co.ke/velvex-extra-toilet-tissue-10-pack-67","Soft 2-ply"),("Mop bucket","1 pc",Decimal("335"),"https://www.quickmart.co.ke/kenpoly-mop-bucket-no.-4-67","")]
    for item,quantity,cost,link,notes in rows: ItemRequestLine.objects.create(request=req,item=item,quantity=quantity,estimated_cost=cost,source_link=link,notes=notes)
    factory=RequestFactory(); out=Path(".tmp/consumables_inspect/generated"); out.mkdir(parents=True,exist_ok=True)
    for fmt in ("xlsx","docx","pdf"):
        request=factory.get(f"/item-requests/{req.pk}/export/{fmt}/"); request.user=user; response=item_request_export(request,req.pk,fmt); (out/f"{req.number}.{fmt}").write_bytes(response.content)
finally: connection.creation.destroy_test_db(verbosity=0)
