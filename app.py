from flask import Flask, render_template, request
import psycopg2
import os
import json
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name="dlcfbkt8c",
    api_key="826689228987982",
    api_secret="G4Y5b2DSAwDYq7Wpe5pwOaZ9xUo"
)



app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


# =========================
# INIT DB
# =========================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            ref_number TEXT UNIQUE,

            mobile TEXT,
            name TEXT,
            address TEXT,
            address1 TEXT,
            city TEXT,
            pincode TEXT,
            state TEXT,
            remarks TEXT,

            email TEXT,
            gstin TEXT,

            product TEXT,
            qty INTEGER,
            problem TEXT,
            serial TEXT,
            bill TEXT,
            date DATE,
            warranty TEXT,

            search_mobile TEXT,
            customer_type TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


init_db()


# =========================
# FORM PAGE
# =========================
@app.route('/')
def form():
    with open('products.json') as f:
        products = json.load(f)

    with open('states.json') as s:
        states = json.load(s)

    with open('branches.json') as b:
        branches = json.load(b)

    with open('online.json') as o:
        online_list = json.load(o)

    with open('problemstemp.json') as p:
        problems_list = json.load(p)

    return render_template('form.html', products=products, states=states,branches=branches,online_list=online_list,problems_list=problems_list)


@app.route('/learn_more')
def learn_more():
    return render_template('learn_more.html')



@app.route("/get-customer")
def get_customer():
    mobile = request.args.get("mobile")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT name, address, address1, city, pincode, state, email, gstin
        FROM customers
        WHERE mobile = %s
        ORDER BY id DESC
        LIMIT 1
    """, (mobile,))

    row = cur.fetchone()

    cur.close()
    conn.close()

    if row:
        return {
            "found": True,
            "name": row[0],
            "address": row[1],
            "address1": row[2],
            "city": row[3],
            "pincode": row[4],
            "state": row[5],
            "email": row[6],
            "gstin": row[7]
            
        }
    else:
        return {"found": False}
# =========================
# SUBMIT (MULTI PRODUCT SAFE + NO DUPLICATE REF)
# =========================
@app.route('/submit', methods=['POST'])
def submit():

    conn = get_conn()
    cur = conn.cursor()

    def safe(lst, i, default=""):
        return lst[i] if i < len(lst) else default

    def clean_date(value):
        return value if value else None

    # ---------------- CUSTOMER INFO ----------------
    search_mobile = request.form.get('search_mobile')
    customer_type = request.form.get('customer_type')

    mobile = request.form['mobile']
    name = request.form['name'].upper()
    address = request.form['address'].upper()

    email = request.form.get('email')
    gstin = request.form.get('gstin')

    address1 = request.form.get('address1')
    city = request.form.get('city')
    pincode = request.form.get('pincode')
    state = request.form.get('state')
    remarks = request.form.get('remarks')
    tc_accepted = "YES" if request.form.get("tc_accepted") else "NO"
      
    service_mode = request.form.get("service_mode")
    
    def to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    courier_image_url = None
    if service_mode != "COURIER":
        courier_name = None
        no_boxes = None
        no_items = None
        docket_no = None
        docket_date = None
        weight = None
        courier_remarks = None
        courier_image_url = None
        to_branch = None
        branch_address = None
    else:
        courier_name = request.form.get("courier_name") or None
        no_boxes = to_int(request.form.get("no_boxes"))
        no_items = to_int(request.form.get("no_items"))
        docket_no = request.form.get("docket_no") or None
        docket_date = request.form.get("docket_date") or None
        weight = request.form.get("weight") or None
        courier_remarks = request.form.get("courier_remarks") or None
        courier_image_file = request.files.get("courier_image")
        to_branch = request.form.get("to_branch")
        branch_address = request.form.get("branch_address")
    
    warning_msg = ""

    if service_mode == "COURIER":

        missing_fields = []

        if not courier_name:
            missing_fields.append("@ Courier Name")

        if not docket_no:
            missing_fields.append("@ Docket Number")

        if not docket_date:
            missing_fields.append("@ Docket Date")

        if not no_boxes:
            missing_fields.append("@ No. of Boxes")

        if missing_fields:
            missing_str = ", ".join(missing_fields)
            warning_msg = f"COURIER DETAILS REQUIRED: {missing_str}. YOUR COMPLAINT IS SAVED, BUT PLEASE UPDATE COURIER DETAILS."

    if service_mode == "COURIER" and courier_image_file and courier_image_file.filename != '':

        courier_image_file.seek(0, 2)
        size = courier_image_file.tell()
        courier_image_file.seek(0)

        if size > 2 * 1024 * 1024:
            return "Courier image too large"

        result = cloudinary.uploader.upload(
            courier_image_file,
            folder="courier_images",   # 👈 keeps images separate
            resource_type="image"
        )

        courier_image_url = result['secure_url']
            
    # ---------------- MULTI PRODUCT DATA ----------------
    products = request.form.getlist('product[]')
    qtys = request.form.getlist('qty[]')
    problems = request.form.getlist('problem[]')
    serials = request.form.getlist('serial[]')
    bills = request.form.getlist('bill[]')
    dates = request.form.getlist('date[]')
    files = request.files.getlist('invoice[]')
    warranties = request.form.getlist('warranty[]')
    purchase_types = request.form.getlist('purchase_type[]')
    shop_names = request.form.getlist('shop_name[]')
    online_platforms = request.form.getlist('online_platform[]')

    if not products:
        return "❌ No product added"

    # ======================================================
    # 🔥 STEP 1: GET UNIQUE REF NUMBER FROM POSTGRES SEQUENCE
    # ======================================================
    cur.execute("SELECT nextval('ref_seq')")
    ref_id = cur.fetchone()[0]

    # 🔥 CUSTOMER TYPE LETTER
    if customer_type == "DIRECT CUSTOMER":
        cust_letter = "C"
    elif customer_type == "PARTNERS":
        cust_letter = "P"
    else:
        cust_letter = "X"  # fallback safety

    # 🔥 SERVICE MODE LETTER
    if service_mode == "SERVICE CENTRE":
        service_letter = "S"
    elif service_mode == "COURIER":
        service_letter = "C"
    else:
        service_letter = "X"  # fallback safety

    
    ref_number = f"ZEB-{cust_letter}{service_letter}-{ref_id:08d}"




    files = request.files.getlist('invoice[]')
    
    file = files[0] if files else None

    invoice_url = ""

    if file and file.filename != '':
        file.seek(0, 2)
        size = file.tell()
        file.seek(0)

        if size > 1 * 1024 * 1024:
            return "File too large"

        result = cloudinary.uploader.upload(
            file,
            resource_type="raw",        # ✅ IMPORTANT for PDF
            type="upload",              # ✅ makes it public
            access_mode="public",       # ✅ avoid 401
            use_filename=True,
            unique_filename=False
        )
        
        invoice_url = result['secure_url']



    
    # ======================================================
    # STEP 2: INSERT FIRST PRODUCT (WITH REF)
    # ======================================================
    cur.execute("""
        INSERT INTO customers
        (ref_number, mobile, name, address, address1, city, pincode, state, remarks,
         email, gstin, service_mode, courier_name, no_boxes, no_items, docket_no, weight, courier_remarks,
         product, qty, problem, serial, bill, date, warranty,
         search_mobile, customer_type,docket_date,invoice_url,courier_image_url,to_branch,branch_address,purchase_type,shop_name,online_platform,tc_accepted)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        ref_number,
        mobile,
        name,
        address,
        address1,
        city,
        pincode,
        state,
        remarks,
        email,
        gstin,
        service_mode,
        courier_name,
        no_boxes,
        no_items,
        docket_no,
        weight,
        courier_remarks,
        products[0],
        qtys[0] if qtys else 1,
        safe(problems, 0),
        safe(serials, 0),
        safe(bills, 0),
        clean_date(safe(dates, 0)),
        safe(warranties, 0),
        

        search_mobile,
        customer_type,
        docket_date,
        invoice_url,
        courier_image_url,
        to_branch,
        branch_address,
        safe(purchase_types, 0),
        safe(shop_names, 0),
        safe(online_platforms, 0),
        tc_accepted
        
    ))

    # ======================================================
    # STEP 3: INSERT REMAINING PRODUCTS (SAME REF)
    # ======================================================
    for i in range(1, len(products)):
        invoice_url = ""

        file = files[i] if i < len(files) else None

        if file and file.filename:
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)

            if size > 1 * 1024 * 1024:
                return "File too large"

            result = cloudinary.uploader.upload(
                file,
                resource_type="raw",
                type="upload",
                access_mode="public",
                use_filename=True,
                unique_filename=False
            )

            invoice_url = result['secure_url']



        
        cur.execute("""
            INSERT INTO customers
            (ref_number, mobile, name, address, address1, city, pincode, state, remarks,
             email, gstin, service_mode, courier_name, no_boxes, no_items, docket_no, weight, courier_remarks,
             product, qty, problem, serial, bill, date, warranty,
             search_mobile, customer_type,docket_date,invoice_url,courier_image_url,to_branch,branch_address,purchase_type,shop_name,online_platform,tc_accepted)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            ref_number,
            mobile,
            name,
            address,
            address1,
            city,
            pincode,
            state,
            remarks,

            email,
            gstin,
            service_mode,
            courier_name,
            no_boxes,
            no_items,
            docket_no,
            weight,
            courier_remarks,
            products[i],
            qtys[i] if i < len(qtys) else 1,
            safe(problems, i),
            safe(serials, i),
            safe(bills, i),
            clean_date(safe(dates, i)),
            safe(warranties, i),


            search_mobile,
            customer_type,
            docket_date,
            invoice_url,
            courier_image_url,
            to_branch,
            branch_address,
            safe(purchase_types, i),
            safe(shop_names, i),
            safe(online_platforms, i),
            tc_accepted
            
        ))

    conn.commit()
    cur.close()
    conn.close()

    return f"""
<html>
<head>
    <title>Complaint Registered</title>
    <style>
        body {{
            font-family: Arial;
            background: #f4f6f8;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
        }}

        .box {{
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0px 0px 15px rgba(0,0,0,0.15);
            max-width: 600px;
            text-align: center;
        }}

        .title {{
            font-size: 26px;
            font-weight: bold;
            color: #2e7d32;
            margin-bottom: 15px;
        }}

        .text {{
            font-size: 16px;
            color: #333;
            line-height: 1.6;
            margin-bottom: 20px;
        }}

        .ref {{
            font-size: 22px;
            font-weight: bold;
            color: #000;
            margin-top: 10px;
        }}

        .note {{
            font-size: 14px;
            color: #777;
            margin-top: 15px;
        }}
    </style>
</head>

<body>

<div class="box">

    <div class="title">Complaint Registered Successfully</div>

    <div class="text">
        Your service request has been received and is now being processed.
    </div>

    <div class="ref">
        Reference Number: {ref_number}
    </div>

    <div class="text">
        Please keep this number for future communication and tracking.
    </div>
    
    {f"<div style='color:red;font-weight:bold;'>{warning_msg}</div>" if warning_msg else ''}
    
</div>

<script>
    // ✅ Create text content
    let content = `Complaint Registered Successfully

Reference Number: {ref_number}

Your service request has been received and is being processed.
`;

    // ✅ Create file
    let blob = new Blob([content], {{ type: "text/plain" }});

    let link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "Complaint_{ref_number}.txt";

    // ✅ Auto download
    link.click();

    // ✅ Then redirect back
    sessionStorage.setItem("clearProducts", "true");

    setTimeout(function() {{
        window.location.href = "/";
    }}, 10000);
</script>

</body>
</html>
"""

@app.route("/search-products")
def search_products():
    q = request.args.get("q", "").upper()

    with open("products.json") as f:
        products = json.load(f)

    items = []

    for p in products:
        if q in p.upper():
            items.append({"id": p, "text": p})
        if len(items) >= 20:
            break

    return {"items": items}
# =========================
# ADMIN PANEL
# =========================
@app.route('/admin')
def admin():

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, ref_number, mobile, name, address, address1, city, pincode, state,
               remarks, email, gstin, product, qty, problem, serial, bill, date,
               warranty, search_mobile, customer_type, service_mode, courier_name, docket_no, docket_date, no_boxes, no_items, weight, courier_remarks, to_branch, branch_address, purchase_type, shop_name, online_platform, tc_accepted, invoice_url, courier_image_url
        FROM customers
        ORDER BY id DESC
    """)

    data = cur.fetchall()

    cur.close()
    conn.close()

    html = """
    <html>
    <head>
        <title>Admin Panel</title>
        <style>
            body { font-family: Arial; background: #f5f5f5; padding:20px; }
            table { border-collapse: collapse; width: 100%; background: white; font-size: 13px; }
            th, td { border: 1px solid #ddd; padding: 6px; }
            th { background: #28a745; color: white; }
            tr:nth-child(even) { background: #f2f2f2; }
        </style>
    </head>
    <body>
    <h2>Product Complaint Report</h2>
    <table>
        <tr>
            <th>ID</th>
            <th>Ref No</th>
            <th>Mobile</th>
            <th>Name</th>
            <th>Address</th>
            <th>Addr1</th>
            <th>City</th>
            <th>Pincode</th>
            <th>State</th>
            <th>Remarks</th>
            <th>Email</th>
            <th>GSTIN</th>
            <th>Product</th>
            <th>Qty</th>
            <th>Problem</th>
            <th>Serial</th>
            <th>Bill</th>
            <th>Date</th>
            <th>Warranty</th>
            <th>Search Mobile</th>
            <th>Customer Type</th>
            <th>Service Type</th>
            <th>Courier Name</th>
            <th>Courier Docket No</th>
            <th>Courier Docket Date</th>
            <th>No of Boxes</th>
            <th>No of Items</th>
            <th>Weight</th>
            <th>Courier Remarks</th>
            <th>To Branch</th>
            <th>To Branch Address</th>
            <th>Purchase Type</th>
            <th>Offline Shop</th>
            <th>Online Mode</th>
            <th>TC Check</th>
            <th>Bill</th>
            <th>Packing</th>
        </tr>
    """

    for row in data:
        html += "<tr>"

        for i, col in enumerate(row):
            if i == len(row) - 2:  # invoice
                if col:
                    html += f"<td><a href='{col}' target='_blank'>📄View</a></td>"
                else:
                    html += "<td></td>"

            elif i == len(row) - 1:  # courier image
                if col:
                    html += f"<td><a href='{col}' target='_blank'>📦View</a></td>"
                else:
                    html += "<td></td>"

            else:
                html += f"<td>{col if col else ''}</td>"

        
        html += "</tr>"

    html += "</table></body></html>"
    return html


# =========================
# RUN APP
# =========================
if __name__ == '__main__':
    app.run(debug=True)
