"""Deterministic fixture generator matching the thelook_ecommerce schema."""
import random, datetime as dt, csv, pathlib

random.seed(42)
OUT = pathlib.Path("fixtures"); OUT.mkdir(exist_ok=True)

STATES = ["Texas","California","New York","Florida","Illinois","Pennsylvania","Ohio","Georgia"]
CITIES = {"Texas":["Houston","Austin","Dallas"],"California":["Los Angeles","San Diego","San Jose"],
          "New York":["New York","Buffalo"],"Florida":["Miami","Tampa"],"Illinois":["Chicago"],
          "Pennsylvania":["Philadelphia"],"Ohio":["Columbus"],"Georgia":["Atlanta"]}
BRANDS = ["Calvin Klein","Levi's","Nike","Adidas","Carhartt","Wrangler","Hanes","Columbia"]
CATS = ["Jeans","Tops & Tees","Sweaters","Outerwear & Coats","Accessories","Shorts","Swim"]
DEPTS = ["Men","Women"]
TRAFFIC = ["Search","Organic","Facebook","Email","Display"]
OI_STATUS = ["Complete","Shipped","Processing","Cancelled","Returned"]
OI_W      = [0.42,      0.24,     0.14,        0.10,       0.10]
FIRST = ["James","Mary","John","Patricia","Robert","Jennifer","Michael","Linda","David","Elizabeth"]
LAST  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez"]

START = dt.datetime(2022,1,1); END = dt.datetime(2024,6,30)
def rand_dt(a=START,b=END):
    return a + dt.timedelta(seconds=random.randint(0,int((b-a).total_seconds())))

# ---- users -----------------------------------------------------------
users=[]
for i in range(1,2001):
    st=random.choice(STATES); g=random.choice(["M","F"])
    fn=random.choice(FIRST); ln=random.choice(LAST)
    users.append(dict(
        id=i, first_name=fn, last_name=ln,
        email=f"{fn.lower()}.{ln.lower()}{i}@example.com",
        age=random.randint(18,70), gender=g, state=st,
        street_address=f"{random.randint(100,9999)} Oak St",
        postal_code=f"{random.randint(10000,99999)}",
        city=random.choice(CITIES[st]), country="United States",
        latitude=round(random.uniform(25,48),4), longitude=round(random.uniform(-124,-71),4),
        traffic_source=random.choice(TRAFFIC), created_at=rand_dt(START, dt.datetime(2024,1,1)),
    ))

# ---- products --------------------------------------------------------
products=[]
for i in range(1,501):
    cost=round(random.uniform(4,90),2)
    products.append(dict(
        id=i, cost=cost, category=random.choice(CATS),
        name=f"Product {i}", brand=random.choice(BRANDS),
        retail_price=round(cost*random.uniform(1.6,3.0),2),
        department=random.choice(DEPTS), sku=f"SKU{i:05d}",
        distribution_center_id=random.randint(1,10),
    ))

# Texas users deliberately skew to cheaper products + fewer orders,
# so the assignment's "why is state X underspending" question has a real answer.
tx = {u["id"] for u in users if u["state"]=="Texas"}

orders=[]; items=[]; oid=0; iid=0
for u in users:
    n = random.randint(0,4) if u["id"] in tx else random.randint(0,7)
    for _ in range(n):
        oid+=1
        created=rand_dt(max(START,u["created_at"]),END)
        nitem=random.randint(1,4)
        ostat=random.choices(["Complete","Shipped","Processing","Cancelled","Returned"],
                             [0.45,0.22,0.13,0.10,0.10])[0]
        orders.append(dict(order_id=oid,user_id=u["id"],status=ostat,gender=u["gender"],
                           created_at=created,returned_at=None,shipped_at=None,
                           delivered_at=None,num_of_item=nitem))
        for _ in range(nitem):
            iid+=1
            pool = [p for p in products if p["retail_price"]<45] if u["id"] in tx else products
            p=random.choice(pool)
            items.append(dict(id=iid,order_id=oid,user_id=u["id"],product_id=p["id"],
                              inventory_item_id=iid,
                              status=random.choices(OI_STATUS,OI_W)[0],
                              created_at=created,shipped_at=None,delivered_at=None,
                              returned_at=None,sale_price=p["retail_price"]))

for name,rows in [("users",users),("products",products),("orders",orders),("order_items",items)]:
    with open(OUT/f"{name}.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"{name:<12} {len(rows):>7,} rows")
