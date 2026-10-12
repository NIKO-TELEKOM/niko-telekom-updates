# NIKO TELEKOM ENTERPRISE - offline desktop POS, SQLite
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3, os, sys, csv, shutil, datetime, pathlib, json, hashlib, threading, urllib.request, urllib.error
from decimal import Decimal, InvalidOperation

APP='NIKO TELEKOM V30 ONLINE UPDATER'
VERSION='30.0.0'
UPDATE_CONFIG=BASE/'update_settings.json'
BASE=pathlib.Path(os.environ.get('LOCALAPPDATA',str(pathlib.Path.home()))) / 'NikoTelekomEnterprise'
BASE.mkdir(parents=True,exist_ok=True)
DB=BASE/'niko_pos.sqlite3'
conn=sqlite3.connect(DB)
conn.execute('PRAGMA foreign_keys=ON')
conn.execute('PRAGMA journal_mode=WAL')
conn.execute('PRAGMA synchronous=FULL')
conn.execute('PRAGMA busy_timeout=5000')
conn.executescript('''
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT UNIQUE, category TEXT NOT NULL DEFAULT 'Digər', cost INTEGER NOT NULL DEFAULT 0, price INTEGER NOT NULL DEFAULT 0, qty INTEGER NOT NULL DEFAULT 0 CHECK(qty>=0), imei TEXT, warranty INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, product_id INTEGER, product_name TEXT NOT NULL, delta INTEGER NOT NULL, reason TEXT NOT NULL, FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, customer TEXT NOT NULL, subtotal INTEGER NOT NULL, discount INTEGER NOT NULL, total INTEGER NOT NULL, cash INTEGER NOT NULL, kapital INTEGER NOT NULL, other INTEGER NOT NULL, debt INTEGER NOT NULL, returned INTEGER NOT NULL DEFAULT 0 CHECK(returned IN (0,1)));
CREATE TABLE IF NOT EXISTS sale_items(id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL, product_id INTEGER, name TEXT NOT NULL, qty INTEGER NOT NULL, price INTEGER NOT NULL, cost INTEGER NOT NULL, FOREIGN KEY(sale_id) REFERENCES sales(id));
CREATE TABLE IF NOT EXISTS debts(id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL, customer TEXT NOT NULL, amount INTEGER NOT NULL, remaining INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS debt_payments(id INTEGER PRIMARY KEY, debt_id INTEGER NOT NULL, ts TEXT NOT NULL, amount INTEGER NOT NULL, method TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sale_returns(id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL UNIQUE, ts TEXT NOT NULL, amount INTEGER NOT NULL, method TEXT NOT NULL, FOREIGN KEY(sale_id) REFERENCES sales(id));
CREATE TABLE IF NOT EXISTS partial_returns(id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL, ts TEXT NOT NULL, amount INTEGER NOT NULL, method TEXT NOT NULL, FOREIGN KEY(sale_id) REFERENCES sales(id));
CREATE TABLE IF NOT EXISTS partial_return_items(id INTEGER PRIMARY KEY, return_id INTEGER NOT NULL, sale_item_id INTEGER NOT NULL, qty INTEGER NOT NULL CHECK(qty>0), amount INTEGER NOT NULL, FOREIGN KEY(return_id) REFERENCES partial_returns(id), FOREIGN KEY(sale_item_id) REFERENCES sale_items(id));
CREATE TABLE IF NOT EXISTS repairs(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, customer TEXT, phone TEXT, model TEXT NOT NULL, problem TEXT, status TEXT NOT NULL, price INTEGER NOT NULL DEFAULT 0, imei TEXT NOT NULL DEFAULT '', paid INTEGER NOT NULL DEFAULT 0 CHECK(paid>=0));
CREATE TABLE IF NOT EXISTS repair_payments(id INTEGER PRIMARY KEY, repair_id INTEGER NOT NULL, ts TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), method TEXT NOT NULL, FOREIGN KEY(repair_id) REFERENCES repairs(id));
CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, name TEXT NOT NULL, amount INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS supplier_bills(id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL, ts TEXT NOT NULL, invoice_no TEXT NOT NULL DEFAULT '', amount INTEGER NOT NULL, paid INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '', FOREIGN KEY(supplier_id) REFERENCES suppliers(id));
CREATE TABLE IF NOT EXISTS supplier_payments(id INTEGER PRIMARY KEY, bill_id INTEGER NOT NULL, ts TEXT NOT NULL, amount INTEGER NOT NULL, method TEXT NOT NULL, FOREIGN KEY(bill_id) REFERENCES supplier_bills(id));
CREATE INDEX IF NOT EXISTS idx_sales_ts ON sales(ts);
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_debts_remaining ON debts(remaining);
''')
# Safe migration for databases created by V23 or earlier.
_sales_cols={r[1] for r in conn.execute('PRAGMA table_info(sales)').fetchall()}
if 'returned' not in _sales_cols:
    conn.execute('ALTER TABLE sales ADD COLUMN returned INTEGER NOT NULL DEFAULT 0 CHECK(returned IN (0,1))')
_repair_cols={r[1] for r in conn.execute('PRAGMA table_info(repairs)').fetchall()}
if 'imei' not in _repair_cols:
    conn.execute("ALTER TABLE repairs ADD COLUMN imei TEXT NOT NULL DEFAULT ''")
if 'paid' not in _repair_cols:
    conn.execute("ALTER TABLE repairs ADD COLUMN paid INTEGER NOT NULL DEFAULT 0")
conn.execute("CREATE TABLE IF NOT EXISTS repair_payments(id INTEGER PRIMARY KEY, repair_id INTEGER NOT NULL, ts TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), method TEXT NOT NULL, FOREIGN KEY(repair_id) REFERENCES repairs(id))")
conn.execute('PRAGMA user_version=29')
conn.commit()
_db_check=conn.execute('PRAGMA quick_check').fetchone()[0]
if _db_check!='ok':
    conn.close()
    raise RuntimeError('NIKO TELEKOM məlumat bazasının yoxlaması uğursuz oldu: '+str(_db_check))
def audit(action, details):
    with conn:
        conn.execute('INSERT INTO audit_log(ts,action,details) VALUES(?,?,?)',(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),action,str(details)))
def auto_backup():
    try:
        folder=BASE/'backups'; folder.mkdir(parents=True,exist_ok=True)
        target=folder/('auto_'+datetime.datetime.now().strftime('%Y-%m-%d')+'.sqlite3')
        if not target.exists():
            with sqlite3.connect(target) as dest: conn.backup(dest)
        backups=sorted(folder.glob('auto_*.sqlite3'),key=lambda x:x.stat().st_mtime,reverse=True)
        for old in backups[30:]: old.unlink(missing_ok=True)
    except (sqlite3.Error,OSError):
        pass
def now():return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def cents(x):
    try:
        v=Decimal(str(x).strip().replace(',','.'))
        if v<0: raise ValueError
        return int((v*100).quantize(Decimal('1')))
    except (InvalidOperation,ValueError):raise ValueError('Düzgün, mənfi olmayan məbləğ yazın.')
def az(n):return f'{n/100:,.2f} ₼'
def qtyval(x):
    try:
        n=int(x)
        if n<0:raise ValueError
        return n
    except:raise ValueError('Miqdar 0 və ya müsbət tam ədəd olmalıdır.')
def table(parent,columns,width=110):
    frame=ttk.Frame(parent);frame.pack(fill='both',expand=True,pady=7)
    t=ttk.Treeview(frame,columns=columns,show='headings',selectmode='browse')
    for col in columns:t.heading(col,text=col);t.column(col,width=width,anchor='w')
    sc=ttk.Scrollbar(frame,orient='vertical',command=t.yview);t.configure(yscrollcommand=sc.set)
    t.pack(side='left',fill='both',expand=True);sc.pack(side='right',fill='y');return t
def fill(t,rows):
    t.delete(*t.get_children())
    for key,values in rows:t.insert('','end',iid=str(key),values=values)
def entry(parent,label,width=23):
    f=ttk.Frame(parent);f.pack(side='left',padx=5,pady=5)
    ttk.Label(f,text=label).pack(anchor='w');v=tk.StringVar();ttk.Entry(f,textvariable=v,width=width).pack();return v
def button(parent,label,cmd):ttk.Button(parent,text=label,command=cmd).pack(side='left',padx=5,pady=5)
class POS(tk.Tk):
 def __init__(self):
    super().__init__();self.title(APP+' | Windows POS');self.geometry('1190x780');self.minsize(960,600)
    self.style=ttk.Style(self)
    if 'clam' in self.style.theme_names():self.style.theme_use('clam')
    self.style.configure('TNotebook.Tab',padding=(14,9));self.style.configure('Treeview',rowheight=29,background='#ffffff',fieldbackground='#ffffff',foreground='#17233b')
    self.style.configure('Treeview.Heading',font=('Segoe UI',10,'bold'),background='#e8eef8',foreground='#17233b',padding=(7,8))
    self.style.configure('TButton',font=('Segoe UI',10,'bold'),padding=(10,7))
    self.style.configure('TLabel',font=('Segoe UI',10))
    self.style.configure('TLabelframe.Label',font=('Segoe UI',10,'bold'),foreground='#2457a7')
    self.style.configure('Title.TLabel',font=('Segoe UI',17,'bold'))
    self.cart={};self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=12,pady=12)
    self.build_products();self.build_receive();self.build_sales();self.build_debts();self.build_suppliers();self.build_repairs();self.build_expenses();self.build_reports();self.build_history();self.build_returns();self.build_audit();self.build_backup();self.build_updates()
    self.refresh();self.protocol('WM_DELETE_WINDOW',self.close)
 def tab(self,title):
    f=ttk.Frame(self.tabs,padding=12);self.tabs.add(f,text=title);return f
 def alert(self,e):messagebox.showerror('Xəta',str(e))
 def run(self,fn):
    try:fn()
    except (ValueError,sqlite3.Error,OSError) as e:self.alert(e)
 def build_products(self):
    f=self.tab('📦 Anbar');bar=ttk.Frame(f);bar.pack(fill='x');self.psearch=entry(bar,'Məhsul axtarışı',35);self.psearch.trace_add('write',lambda *_:self.refresh_products());button(bar,'Yenilə',self.refresh)
    form=ttk.LabelFrame(f,text='Məhsul əlavə et / seçilmiş məhsulu dəyiş');form.pack(fill='x',pady=8);row=ttk.Frame(form);row.pack(fill='x')
    self.pname=entry(row,'Məhsul adı *',27);self.pcode=entry(row,'Kod / barkod',16);self.pcat=entry(row,'Kateqoriya',20);self.pcost=entry(row,'Alış ₼',11);self.pprice=entry(row,'Satış ₼',11);self.pqty=entry(row,'İlkin say',9)
    self.pcat.set('Digər');self.pcost.set('0');self.pprice.set('0');self.pqty.set('0');buttons=ttk.Frame(form);buttons.pack(anchor='w')
    button(buttons,'Yeni məhsul əlavə et',lambda:self.run(self.add_product));button(buttons,'Seçilmişi redaktə et',lambda:self.run(self.edit_product));button(buttons,'Seçilmişi formaya gətir',self.load_product);button(buttons,'Say düzəlişi',lambda:self.run(self.adjust_stock))
    self.ptable=table(f,('ID','Məhsul','Kod','Kateqoriya','Alış','Satış','Qalıq'),130)
 def selected_id(self,t):
    s=t.selection()
    if not s:raise ValueError('Əvvəl siyahıdan sətir seçin.')
    return int(s[0])
 def add_product(self):
    name=self.pname.get().strip()
    if not name:raise ValueError('Məhsul adı boş ola bilməz.')
    n=qtyval(self.pqty.get());cost=cents(self.pcost.get());price=cents(self.pprice.get());code=self.pcode.get().strip() or None
    with conn:
     cur=conn.execute('INSERT INTO products(name,code,category,cost,price,qty) VALUES(?,?,?,?,?,?)',(name,code,self.pcat.get().strip() or 'Digər',cost,price,n))
     if n:conn.execute('INSERT INTO movements(ts,product_id,product_name,delta,reason) VALUES(?,?,?,?,?)',(now(),cur.lastrowid,name,n,'İlkin qalıq'))
    audit('Məhsul əlavə edildi',name+'; say='+str(n))
    self.refresh();messagebox.showinfo('Hazır','Məhsul anbara əlavə edildi.')
 def load_product(self):
    try:
     p=conn.execute('SELECT name,code,category,cost,price,qty FROM products WHERE id=?',(self.selected_id(self.ptable),)).fetchone()
     for v,x in zip((self.pname,self.pcode,self.pcat,self.pcost,self.pprice,self.pqty),(p[0],p[1] or '',p[2],str(p[3]/100),str(p[4]/100),str(p[5]))):v.set(x)
    except ValueError as e:self.alert(e)
 def edit_product(self):
    pid=self.selected_id(self.ptable);name=self.pname.get().strip()
    if not name:raise ValueError('Adı yazın.')
    new_cost=cents(self.pcost.get());new_price=cents(self.pprice.get());new_code=self.pcode.get().strip() or None;new_cat=self.pcat.get().strip() or 'Digər'
    with conn:conn.execute('UPDATE products SET name=?,code=?,category=?,cost=?,price=? WHERE id=?',(name,new_code,new_cat,new_cost,new_price,pid))
    audit('Məhsul redaktə edildi',f'ID={pid}; ad={name}; alış={az(new_cost)}; satış={az(new_price)}')
    self.refresh();messagebox.showinfo('Hazır','Məhsul yeniləndi. Sayı dəyişmək üçün Say düzəlişi düyməsindən istifadə edin.')
 def adjust_stock(self):
    pid=self.selected_id(self.ptable);p=conn.execute('SELECT name,qty FROM products WHERE id=?',(pid,)).fetchone()
    new=simpledialog.askinteger('Anbar sayımı',f'{p[0]}\nHazırkı say: {p[1]}\nYeni faktiki say:',minvalue=0,parent=self)
    if new is None:return
    reason=simpledialog.askstring('Səbəb','Say düzəlişinin səbəbi:',parent=self)
    if not reason or not reason.strip():raise ValueError('Say düzəlişinin səbəbi mütləq yazılmalıdır.')
    with conn:
     conn.execute('UPDATE products SET qty=? WHERE id=?',(new,pid));conn.execute('INSERT INTO movements(ts,product_id,product_name,delta,reason) VALUES(?,?,?,?,?)',(now(),pid,p[0],new-p[1],reason.strip()))
    self.refresh()
 def refresh_products(self):
    q='%'+self.psearch.get().strip()+'%';rows=conn.execute('SELECT id,name,coalesce(code,\'\'),category,cost,price,qty FROM products WHERE name LIKE ? OR code LIKE ? OR category LIKE ? ORDER BY name',(q,q,q)).fetchall()
    fill(self.ptable,[(r[0],(r[0],r[1],r[2],r[3],az(r[4]),az(r[5]),r[6])) for r in rows])
 def build_receive(self):
    f=self.tab('⬇ Məhsul qəbulu');r=ttk.Frame(f);r.pack(fill='x');self.rsearch=entry(r,'Məhsul adı / kod ilə axtar',35);self.rsearch.trace_add('write',lambda *_:self.refresh_receive())
    self.rtable=table(f,('ID','Məhsul','Kod','Qalıq','Alış'),140)
    bottom=ttk.LabelFrame(f,text='Seçilmiş məhsulu anbara qəbul et');bottom.pack(fill='x');r=ttk.Frame(bottom);r.pack(fill='x');self.rqty=entry(r,'Gələn say',13);self.rcost=entry(r,'Yeni alış qiyməti ₼',16);self.rqty.set('1');self.rcost.set('0');button(r,'Anbara qəbul et',lambda:self.run(self.receive))
    ttk.Label(f,text='Yeni məhsul ilk dəfə gəlirsə, əvvəl Anbar bölməsində yaradın.',foreground='#566').pack(anchor='w',pady=6)
 def refresh_receive(self):
    q='%'+self.rsearch.get().strip()+'%';rows=conn.execute('SELECT id,name,coalesce(code,\'\'),qty,cost FROM products WHERE name LIKE ? OR code LIKE ? ORDER BY name',(q,q)).fetchall();fill(self.rtable,[(r[0],(r[0],r[1],r[2],r[3],az(r[4]))) for r in rows])
 def receive(self):
    pid=self.selected_id(self.rtable);n=qtyval(self.rqty.get())
    if not n:raise ValueError('Qəbul miqdarı 0 ola bilməz.')
    cost=cents(self.rcost.get());product=conn.execute('SELECT name,qty,cost FROM products WHERE id=?',(pid,)).fetchone()
    if not product: raise ValueError('Məhsul tapılmadı.')
    name,old_qty,old_cost=product
    weighted_cost=(old_qty*old_cost+n*cost)//(old_qty+n) if old_qty+n else cost
    with conn:
     conn.execute('UPDATE products SET qty=qty+?,cost=? WHERE id=?',(n,weighted_cost,pid));conn.execute('INSERT INTO movements(ts,product_id,product_name,delta,reason) VALUES(?,?,?,?,?)',(now(),pid,name,n,'Məhsul qəbulu'))
    audit('Anbara qəbul',name+'; +'+str(n)+'; alış='+az(cost))
    self.refresh();messagebox.showinfo('Hazır',f'{name}: {n} ədəd anbara əlavə edildi.')
 def build_sales(self):
    f=self.tab('🛒 Satış');r=ttk.Frame(f);r.pack(fill='x');self.ssearch=entry(r,'Məhsul adı / kod',35);self.ssearch.trace_add('write',lambda *_:self.refresh_sale_products());self.sqty=entry(r,'Say',9);self.sqty.set('1');button(r,'Səbətə əlavə et',lambda:self.run(self.cart_add))
    self.stable=table(f,('ID','Məhsul','Qiymət','Qalıq'),145)
    ttk.Label(f,text='SATIŞ SƏBƏTİ',style='Title.TLabel').pack(anchor='w');self.ctable=table(f,('ID','Məhsul','Say','Qiymət','Cəmi'),135)
    r=ttk.Frame(f);r.pack(fill='x');button(r,'Səbətdən sil',lambda:self.run(self.cart_remove));button(r,'Səbəti təmizlə',self.cart_clear)
    r=ttk.LabelFrame(f,text='Ödəniş (bütün məbləğlər ₼)');r.pack(fill='x');a=ttk.Frame(r);a.pack(fill='x')
    self.customer=entry(a,'Müştəri adı',20);self.discount=entry(a,'Endirim',11);self.cash=entry(a,'Nağd',11);self.kapital=entry(a,'Kapital Bank kartı',15);self.other=entry(a,'Digər kart',11);self.debt=entry(a,'Borc',11)
    for v in (self.discount,self.cash,self.kapital,self.other,self.debt):v.set('0')
    self.sumlabel=ttk.Label(r,text='Səbət: 0.00 ₼',style='Title.TLabel');self.sumlabel.pack(anchor='w',padx=8,pady=5)
    button(r,'Satışı təsdiqlə',lambda:self.run(self.complete_sale));ttk.Label(r,text='Kapital Bank yalnız ödəniş üsulunun qeydidir; bank inteqrasiyası deyil.',foreground='#666').pack(anchor='w',padx=8)
 def refresh_sale_products(self):
    q='%'+self.ssearch.get().strip()+'%';rows=conn.execute('SELECT id,name,price,qty FROM products WHERE (name LIKE ? OR code LIKE ?) AND qty>0 ORDER BY name',(q,q)).fetchall();fill(self.stable,[(r[0],(r[0],r[1],az(r[2]),r[3])) for r in rows])
 def cart_add(self):
    pid=self.selected_id(self.stable);n=qtyval(self.sqty.get())
    if n<1:raise ValueError('Say ən azı 1 olmalıdır.')
    p=conn.execute('SELECT name,price,qty FROM products WHERE id=?',(pid,)).fetchone()
    if self.cart.get(pid,0)+n>p[2]:raise ValueError(f'Anbarda kifayət qədər məhsul yoxdur. Qalıq: {p[2]}')
    self.cart[pid]=self.cart.get(pid,0)+n;self.refresh_cart()
 def refresh_cart(self):
    rows=[];subtotal=0
    for pid,n in self.cart.items():
     p=conn.execute('SELECT name,price FROM products WHERE id=?',(pid,)).fetchone()
     if p:subtotal+=p[1]*n;rows.append((pid,(pid,p[0],n,az(p[1]),az(p[1]*n))))
    fill(self.ctable,rows);self.sumlabel.config(text='Səbət: '+az(subtotal))
 def cart_remove(self):self.cart.pop(self.selected_id(self.ctable),None);self.refresh_cart()
 def cart_clear(self):self.cart={};self.refresh_cart()
 def complete_sale(self):
    if not self.cart:raise ValueError('Səbət boşdur.')
    subtotal=0;items=[]
    for pid,n in self.cart.items():
     p=conn.execute('SELECT name,price,cost,qty FROM products WHERE id=?',(pid,)).fetchone()
     if not p or p[3]<n:raise ValueError('Anbar qalığı kifayət etmir. Yenidən yoxlayın.')
     subtotal+=p[1]*n;items.append((pid,p[0],n,p[1],p[2]))
    disc=cents(self.discount.get());total=subtotal-disc
    if total<0:raise ValueError('Endirim səbətdən çox ola bilməz.')
    cash,kap,other,debt=map(lambda x:cents(x.get()),(self.cash,self.kapital,self.other,self.debt))
    if cash+kap+other+debt!=total:raise ValueError(f'Ödənişlərin cəmi {az(total)} olmalıdır. Hazırda {az(cash+kap+other+debt)}')
    customer=self.customer.get().strip() or 'Pərakəndə müştəri'
    if debt and customer=='Pərakəndə müştəri':raise ValueError('Borc satışında müştəri adı mütləqdir.')
    with conn:
     cur=conn.execute('INSERT INTO sales(ts,customer,subtotal,discount,total,cash,kapital,other,debt) VALUES(?,?,?,?,?,?,?,?,?)',(now(),customer,subtotal,disc,total,cash,kap,other,debt));sid=cur.lastrowid
     for pid,name,n,price,cost in items:
      upd=conn.execute('UPDATE products SET qty=qty-? WHERE id=? AND qty>=?',(n,pid,n))
      if upd.rowcount!=1:raise ValueError('Anbar qalığı satış zamanı dəyişdi.')
      conn.execute('INSERT INTO sale_items(sale_id,product_id,name,qty,price,cost) VALUES(?,?,?,?,?,?)',(sid,pid,name,n,price,cost))
      conn.execute('INSERT INTO movements(ts,product_id,product_name,delta,reason) VALUES(?,?,?,?,?)',(now(),pid,name,-n,'Satış #'+str(sid)))
     if debt:conn.execute('INSERT INTO debts(sale_id,customer,amount,remaining) VALUES(?,?,?,?)',(sid,customer,debt,debt))
    audit('Satış tamamlandı','Satış #'+str(sid)+'; '+customer+'; yekun='+az(total)+'; borc='+az(debt))
    self.cart_clear();self.refresh();messagebox.showinfo('Satış tamamlandı',f'Satış #{sid}\nYekun: {az(total)}\nAnbar yeniləndi.')
 def build_debts(self):
    f=self.tab('💳 Borclar');self.dtable=table(f,('ID','Satış №','Müştəri','İlkin borc','Qalıq'),145)
    r=ttk.Frame(f);r.pack(fill='x');self.damount=entry(r,'Ödənilən məbləğ ₼',18);self.dmethod=tk.StringVar(value='Nağd');ttk.Combobox(r,textvariable=self.dmethod,values=('Nağd','Kapital Bank kartı','Digər kart'),state='readonly',width=22).pack(side='left',padx=5,pady=5);button(r,'Seçilmiş borca ödəniş et',lambda:self.run(self.pay_debt))
 def pay_debt(self):
    did=self.selected_id(self.dtable);n=cents(self.damount.get());remaining=conn.execute('SELECT remaining FROM debts WHERE id=?',(did,)).fetchone()[0]
    if n<=0 or n>remaining:raise ValueError('Ödəniş 0-dan böyük və qalıq borcdan çox olmamalıdır.')
    with conn:
     conn.execute('UPDATE debts SET remaining=remaining-? WHERE id=?',(n,did));conn.execute('INSERT INTO debt_payments(debt_id,ts,amount,method) VALUES(?,?,?,?)',(did,now(),n,self.dmethod.get()))
    audit('Borc ödənişi','Borc #'+str(did)+'; məbləğ='+az(n)+'; üsul='+self.dmethod.get())
    self.refresh();messagebox.showinfo('Hazır','Borc ödənişi qeydə alındı.')

 def build_suppliers(self):
    f=self.tab('🏢 Təchizatçılar')
    ttk.Label(f,text='TƏCHİZATÇI VƏ ALIŞ BORCLARI',style='Title.TLabel').pack(anchor='w',pady=(0,8))
    top=ttk.LabelFrame(f,text='Təchizatçı əlavə et')
    top.pack(fill='x',pady=5)
    r=ttk.Frame(top);r.pack(fill='x')
    self.sup_name=entry(r,'Təchizatçı adı *',25)
    self.sup_phone=entry(r,'Telefon',18)
    self.sup_notes=entry(r,'Qeyd',28)
    button(r,'Təchizatçı əlavə et',lambda:self.run(self.add_supplier))
    self.sup_table=table(f,('ID','Təchizatçı','Telefon','Qeyd','Alış borcu'),150)
    bill=ttk.LabelFrame(f,text='Seçilmiş təchizatçı üçün alış hesab-fakturası')
    bill.pack(fill='x',pady=5)
    r=ttk.Frame(bill);r.pack(fill='x')
    self.bill_no=entry(r,'Qaimə / sənəd №',16)
    self.bill_amount=entry(r,'Ümumi məbləğ ₼',14)
    self.bill_paid=entry(r,'İlkin ödəniş ₼',14);self.bill_paid.set('0')
    self.bill_notes=entry(r,'Qeyd',25)
    button(r,'Alış borcu yarat',lambda:self.run(self.add_supplier_bill))
    pay=ttk.LabelFrame(f,text='Seçilmiş alış borcuna ödəniş')
    pay.pack(fill='x',pady=5)
    r=ttk.Frame(pay);r.pack(fill='x')
    self.sup_bill_amount=entry(r,'Ödəniş ₼',14)
    self.sup_method=tk.StringVar(value='Nağd')
    ttk.Combobox(r,textvariable=self.sup_method,values=('Nağd','Kapital Bank kartı','Digər kart','Bank köçürməsi'),state='readonly',width=22).pack(side='left',padx=5,pady=5)
    button(r,'Ödəniş et',lambda:self.run(self.pay_supplier_bill))
    self.sup_bill_table=table(f,('Qaimə ID','Tarix','Təchizatçı','Sənəd №','Məbləğ','Ödənib','Qalıq','Qeyd'),125)
    self.sup_table.bind('<<TreeviewSelect>>',lambda *_:self.refresh_supplier_bills())

 def refresh_suppliers(self):
    if not hasattr(self,'sup_table'): return
    rows=conn.execute('''SELECT s.id,s.name,s.phone,s.notes,
      COALESCE((SELECT sum(b.amount-b.paid) FROM supplier_bills b WHERE b.supplier_id=s.id),0)
      FROM suppliers s ORDER BY s.name''').fetchall()
    fill(self.sup_table,[(r[0],(r[0],r[1],r[2],r[3],az(r[4]))) for r in rows])
    self.refresh_supplier_bills()

 def refresh_supplier_bills(self):
    if not hasattr(self,'sup_bill_table'): return
    sel=self.sup_table.selection() if hasattr(self,'sup_table') else ()
    if sel:
     rows=conn.execute('''SELECT b.id,b.ts,s.name,b.invoice_no,b.amount,b.paid,b.notes
       FROM supplier_bills b JOIN suppliers s ON s.id=b.supplier_id
       WHERE b.supplier_id=? ORDER BY b.id DESC''',(int(sel[0]),)).fetchall()
    else:
     rows=conn.execute('''SELECT b.id,b.ts,s.name,b.invoice_no,b.amount,b.paid,b.notes
       FROM supplier_bills b JOIN suppliers s ON s.id=b.supplier_id ORDER BY b.id DESC LIMIT 300''').fetchall()
    fill(self.sup_bill_table,[(r[0],(r[0],r[1],r[2],r[3],az(r[4]),az(r[5]),az(r[4]-r[5]),r[6])) for r in rows])

 def add_supplier(self):
    name=self.sup_name.get().strip()
    if not name: raise ValueError('Təchizatçı adı boş ola bilməz.')
    with conn:
     cur=conn.execute('INSERT INTO suppliers(name,phone,notes) VALUES(?,?,?)',
       (name,self.sup_phone.get().strip(),self.sup_notes.get().strip()))
    audit('Təchizatçı əlavə edildi',name)
    self.sup_name.set('');self.sup_phone.set('');self.sup_notes.set('')
    self.refresh_suppliers();messagebox.showinfo('Hazır','Təchizatçı əlavə edildi.')

 def add_supplier_bill(self):
    sid=self.selected_id(self.sup_table)
    amount=cents(self.bill_amount.get());paid=cents(self.bill_paid.get())
    if amount<=0: raise ValueError('Alış məbləği 0-dan böyük olmalıdır.')
    if paid>amount: raise ValueError('İlkin ödəniş alış məbləğindən çox ola bilməz.')
    if paid and not messagebox.askyesno('Təsdiq',f'İlkin ödəniş {az(paid)} kimi qeydə alınsın?'): return
    with conn:
     cur=conn.execute('INSERT INTO supplier_bills(supplier_id,ts,invoice_no,amount,paid,notes) VALUES(?,?,?,?,?,?)',
       (sid,now(),self.bill_no.get().strip(),amount,paid,self.bill_notes.get().strip()))
     bid=cur.lastrowid
     if paid:
      conn.execute('INSERT INTO supplier_payments(bill_id,ts,amount,method) VALUES(?,?,?,?)',(bid,now(),paid,self.sup_method.get()))
    audit('Təchizatçı alış borcu yaradıldı',f'Qaimə #{bid}; məbləğ={az(amount)}; ilkin ödəniş={az(paid)}')
    self.bill_no.set('');self.bill_amount.set('');self.bill_paid.set('0');self.bill_notes.set('')
    self.refresh_suppliers();self.refresh_reports()

 def pay_supplier_bill(self):
    bid=self.selected_id(self.sup_bill_table)
    amount=cents(self.sup_bill_amount.get())
    row=conn.execute('SELECT amount,paid FROM supplier_bills WHERE id=?',(bid,)).fetchone()
    if not row: raise ValueError('Alış hesabı tapılmadı.')
    remaining=row[0]-row[1]
    if amount<=0 or amount>remaining: raise ValueError(f'Ödəniş 0-dan böyük və qalıq borcdan çox olmamalıdır. Qalıq: {az(remaining)}')
    with conn:
     conn.execute('UPDATE supplier_bills SET paid=paid+? WHERE id=?',(amount,bid))
     conn.execute('INSERT INTO supplier_payments(bill_id,ts,amount,method) VALUES(?,?,?,?)',(bid,now(),amount,self.sup_method.get()))
    audit('Təchizatçıya ödəniş',f'Qaimə #{bid}; {az(amount)}; üsul={self.sup_method.get()}')
    self.sup_bill_amount.set('');self.refresh_suppliers();self.refresh_reports()
    messagebox.showinfo('Hazır','Təchizatçı ödənişi qeydə alındı.')

 def build_repairs(self):
    f=self.tab('🔧 Təmir');r=ttk.Frame(f);r.pack(fill='x');self.tcustomer=entry(r,'Müştəri',15);self.tphone=entry(r,'Telefon nömrəsi',14);self.tmodel=entry(r,'Telefon modeli',17);self.timei=entry(r,'IMEI / seriya №',18)
    r=ttk.Frame(f);r.pack(fill='x');self.tproblem=entry(r,'Nasazlıq / görüləcək iş',34);self.tprice=entry(r,'Təmir qiyməti ₼',14);self.tprice.set('0');button(r,'Təmir qəbul et',lambda:self.run(self.add_repair))
    bar=ttk.Frame(f);bar.pack(fill='x',pady=(8,0));self.tsearch=entry(bar,'Sifariş / müştəri / model / IMEI axtar',35);self.tsearch.trace_add('write',lambda *_:self.refresh_repairs());button(bar,'Yenilə',self.refresh_repairs)
    self.ttable=table(f,('ID','Tarix','Müştəri','Telefon','Model','IMEI / seriya','Nasazlıq','Status','Qiymət','Ödənib','Qalıq'),100)
    r=ttk.Frame(f);r.pack(fill='x');button(r,'Statusu dəyiş',lambda:self.run(self.change_repair))
    pay=ttk.LabelFrame(f,text='Seçilmiş təmir sifarişinə ödəniş');pay.pack(fill='x',pady=6)
    r=ttk.Frame(pay);r.pack(fill='x')
    self.repair_pay_amount=entry(r,'Ödəniş məbləği ₼',16)
    self.repair_pay_method=tk.StringVar(value='Nağd')
    ttk.Combobox(r,textvariable=self.repair_pay_method,values=('Nağd','Kapital Bank kartı','Digər kart','Bank köçürməsi'),state='readonly',width=22).pack(side='left',padx=5,pady=5)
    button(r,'Ödənişi qeyd et',lambda:self.run(self.pay_repair))
    button(r,'Ödəniş tarixçəsi',lambda:self.run(self.show_repair_payments))
    ttk.Label(f,text='IMEI-ni yalnız qanuni servis uçotu üçün qeyd edin. Müştərinin məlumatlarını ehtiyatla qoruyun.',foreground='#667085').pack(anchor='w',pady=5)
 def add_repair(self):
    if not self.tmodel.get().strip():raise ValueError('Telefon modelini yazın.')
    imei=self.timei.get().strip()
    if imei and (len(imei) not in (14,15,16) or not imei.isdigit()):raise ValueError('IMEI/seriya sahəsinə rəqəm yazın (IMEI adətən 15 rəqəmdir).')
    with conn:conn.execute('INSERT INTO repairs(ts,customer,phone,model,problem,status,price,imei) VALUES(?,?,?,?,?,?,?,?)',(now(),self.tcustomer.get().strip(),self.tphone.get().strip(),self.tmodel.get().strip(),self.tproblem.get().strip(),'Qəbul edildi',cents(self.tprice.get()),imei))
    audit('Təmir sifarişi yaradıldı',self.tmodel.get().strip()+'; IMEI='+imei+'; müştəri='+self.tcustomer.get().strip())
    self.refresh();messagebox.showinfo('Hazır','Təmir sifarişi qeydə alındı.')
 def refresh_repairs(self):
    if not hasattr(self,'ttable'): return
    q='%'+self.tsearch.get().strip()+'%'
    rows=conn.execute('SELECT id,ts,customer,phone,model,imei,problem,status,price,paid FROM repairs WHERE CAST(id AS TEXT) LIKE ? OR customer LIKE ? OR phone LIKE ? OR model LIKE ? OR imei LIKE ? OR problem LIKE ? ORDER BY id DESC',(q,q,q,q,q,q)).fetchall()
    fill(self.ttable,[(r[0],(*r[:8],az(r[8]),az(r[9]),az(max(0,r[8]-r[9])))) for r in rows])
 def change_repair(self):
    rid=self.selected_id(self.ttable);status=simpledialog.askstring('Təmir statusu','Yazın: Qəbul edildi / Təmirdədir / Hazırdır / Təhvil verildi',parent=self)
    if not status:return
    status=status.strip()
    if status not in ('Qəbul edildi','Təmirdədir','Hazırdır','Təhvil verildi'):raise ValueError('Düzgün status yazın: Qəbul edildi / Təmirdədir / Hazırdır / Təhvil verildi.')
    with conn:conn.execute('UPDATE repairs SET status=? WHERE id=?',(status,rid))
    self.refresh()

 def pay_repair(self):
    rid=self.selected_id(self.ttable)
    amount=cents(self.repair_pay_amount.get())
    row=conn.execute('SELECT price,paid,status,model FROM repairs WHERE id=?',(rid,)).fetchone()
    if not row: raise ValueError('Təmir sifarişi tapılmadı.')
    price,paid,status,model=row
    remaining=max(0,price-paid)
    if amount<=0: raise ValueError('Ödəniş 0-dan böyük olmalıdır.')
    if amount>remaining: raise ValueError(f'Ödəniş qalan məbləğdən çox ola bilməz. Qalıq: {az(remaining)}')
    method=self.repair_pay_method.get()
    if method not in ('Nağd','Kapital Bank kartı','Digər kart','Bank köçürməsi'):
     raise ValueError('Ödəniş üsulunu seçin.')
    if not messagebox.askyesno('Təmir ödənişi',f'Təmir #{rid} — {model}\nMəbləğ: {az(amount)}\nÜsul: {method}\nTəsdiqləyirsiniz?'):
     return
    with conn:
     conn.execute('UPDATE repairs SET paid=paid+? WHERE id=?',(amount,rid))
     conn.execute('INSERT INTO repair_payments(repair_id,ts,amount,method) VALUES(?,?,?,?)',(rid,now(),amount,method))
    audit('Təmir ödənişi',f'Təmir #{rid}; {model}; məbləğ={az(amount)}; üsul={method}')
    self.repair_pay_amount.set('')
    self.refresh()
    messagebox.showinfo('Hazır',f'Ödəniş qeydə alındı.\nQalan: {az(max(0,price-paid-amount))}')

 def show_repair_payments(self):
    rid=self.selected_id(self.ttable)
    rows=conn.execute('SELECT ts,amount,method FROM repair_payments WHERE repair_id=? ORDER BY id DESC',(rid,)).fetchall()
    win=tk.Toplevel(self);win.title(f'Təmir #{rid} — ödəniş tarixçəsi');win.geometry('650x400')
    t=table(win,('Tarix','Məbləğ','Ödəniş üsulu'),180)
    fill(t,[(i,(r[0],az(r[1]),r[2])) for i,r in enumerate(rows,1)])
    if not rows: messagebox.showinfo('Tarixçə','Bu təmir üçün hələ ödəniş qeydə alınmayıb.',parent=win)

 def build_expenses(self):
    f=self.tab('🧾 Xərclər');r=ttk.Frame(f);r.pack(fill='x');self.ename=entry(r,'Xərcin adı',28);self.eamount=entry(r,'Məbləğ ₼',15);button(r,'Xərc əlavə et',lambda:self.run(self.add_expense));self.etable=table(f,('ID','Tarix','Xərc','Məbləğ'),180)
 def add_expense(self):
    if not self.ename.get().strip():raise ValueError('Xərc adını yazın.')
    amount=cents(self.eamount.get())
    if amount<=0: raise ValueError('Xərc məbləği 0-dan böyük olmalıdır.')
    name=self.ename.get().strip()
    with conn:conn.execute('INSERT INTO expenses(ts,name,amount) VALUES(?,?,?)',(now(),name,amount))
    audit('Xərc əlavə edildi',f'{name}; məbləğ={az(amount)}')
    self.ename.set('');self.eamount.set('')
    self.refresh()
 def build_reports(self):
    f=self.tab('📊 Hesabat');self.report=tk.Text(f,font=('Consolas',12),height=24,wrap='word');self.report.pack(fill='both',expand=True);r=ttk.Frame(f);r.pack(fill='x');button(r,'Hesabatı yenilə',self.refresh_reports);button(r,'Məhsulları CSV çıxar',lambda:self.run(self.export_csv));button(r,'Anbar hərəkətlərini CSV çıxar',lambda:self.run(self.export_movements))
 def refresh_reports(self):
     total=conn.execute('''SELECT COALESCE(SUM(s.total-COALESCE((SELECT SUM(pr.amount) FROM partial_returns pr WHERE pr.sale_id=s.id),0)),0),COUNT(*)
       FROM sales s WHERE s.returned=0''').fetchone()
     expense=conn.execute('SELECT COALESCE(SUM(amount),0) FROM expenses').fetchone()[0]
     cost=conn.execute('''SELECT COALESCE(SUM((si.qty-COALESCE((SELECT SUM(pri.qty) FROM partial_return_items pri JOIN partial_returns pr ON pr.id=pri.return_id WHERE pr.sale_id=s.id AND pri.sale_item_id=si.id),0))*si.cost),0)
       FROM sale_items si JOIN sales s ON s.id=si.sale_id WHERE s.returned=0''').fetchone()[0]
     debt=conn.execute('SELECT COALESCE(SUM(remaining),0) FROM debts').fetchone()[0]
     customer_paid=conn.execute('SELECT COALESCE(SUM(amount),0) FROM debt_payments').fetchone()[0]
     supplier_debt=conn.execute('SELECT COALESCE(SUM(amount-paid),0) FROM supplier_bills').fetchone()[0]
     repair_paid=conn.execute('SELECT COALESCE(SUM(paid),0) FROM repairs').fetchone()[0]
     repair_due=conn.execute('SELECT COALESCE(SUM(MAX(price-paid,0)),0) FROM repairs').fetchone()[0]
     returned=conn.execute('SELECT COALESCE(SUM(amount),0) FROM partial_returns').fetchone()[0]
     today=now()[:10]
     todaytotal=conn.execute('''SELECT COALESCE(SUM(s.total-COALESCE((SELECT SUM(pr.amount) FROM partial_returns pr WHERE pr.sale_id=s.id),0)),0)
       FROM sales s WHERE substr(s.ts,1,10)=? AND s.returned=0''',(today,)).fetchone()[0]
     stock=conn.execute('SELECT COUNT(*),COALESCE(SUM(qty*cost),0) FROM products').fetchone()
     low=conn.execute('SELECT name,qty FROM products WHERE qty<=3 ORDER BY qty,name LIMIT 30').fetchall()
     s=f'''{APP}\n{'='*48}
Bugünkü xalis satış:          {az(todaytotal)}
Ümumi xalis satış:            {az(total[0])}
Aktiv satış əməliyyatları:    {total[1]}
Satılan malların maya dəyəri: {az(cost)}
Satışdan qaytarılan məbləğ:   {az(returned)}
Xərclər:                      {az(expense)}
Təxmini satış fərqi*:         {az(total[0]-cost-expense)}

Müştərilərdən qalan borc:     {az(debt)}
Müştərilərdən alınmış borc:   {az(customer_paid)}
Təmir üzrə alınan ödəniş:     {az(repair_paid)}
Təmir üzrə qalıq məbləğ:      {az(repair_due)}
Təchizatçıya qalan borc:      {az(supplier_debt)}

Anbarda məhsul çeşidi:        {stock[0]}
Anbarın alış dəyəri:          {az(stock[1])}

AZ QALAN MƏHSULLAR (0–3)
{'-'*48}
'''+('\n'.join(f'{n}: {q} ədəd' for n,q in low) or 'Yoxdur')+'\n\n* Təxmini göstəricidir; təmir gəliri, vergi və bəzi maliyyə düzəlişləri ayrıca nəzərə alınmalıdır.\n'
     self.report.delete('1.0','end');self.report.insert('1.0',s)
 def export(self,sql,filename,headers):
    target=filedialog.asksaveasfilename(defaultextension='.csv',initialfile=filename,filetypes=[('CSV','*.csv')]);
    if not target:return
    with open(target,'w',newline='',encoding='utf-8-sig') as f:
     w=csv.writer(f,delimiter=';');w.writerow(headers);w.writerows(conn.execute(sql).fetchall())
    messagebox.showinfo('Hazır','CSV faylı saxlandı.')
 def export_csv(self):self.export('SELECT id,name,coalesce(code,\'\'),category,cost/100.0,price/100.0,qty FROM products ORDER BY name','NIKO_mallar.csv',('ID','Ad','Kod','Kateqoriya','Alış AZN','Satış AZN','Say'))
 def export_movements(self):self.export('SELECT ts,product_name,delta,reason FROM movements ORDER BY id DESC','NIKO_anbar_tarixce.csv',('Tarix','Məhsul','Say dəyişikliyi','Səbəb'))
 def build_history(self):
    f=self.tab('🧾 Satış tarixçəsi')
    bar=ttk.Frame(f);bar.pack(fill='x')
    self.hsearch=entry(bar,'Satış № / müştəri axtar',35)
    self.hsearch.trace_add('write',lambda *_:self.refresh_history())
    button(bar,'Yenilə',self.refresh_history)
    self.htable=table(f,('Satış №','Tarix','Müştəri','Məbləğ','Endirim','Nağd','Kapital kartı','Digər kart','Borc','Status'),125)
    row=ttk.Frame(f);row.pack(fill='x')
    button(row,'Seçilmiş satışın qəbzini göstər',lambda:self.run(self.show_sale_receipt))
    ttk.Label(f,text='Qəbz məlumatlarını seçilmiş satışdan açır. Fiskal kassa qəbzini əvəz etmir.',foreground='#667085').pack(anchor='w',pady=6)
 def refresh_history(self):
    if not hasattr(self,'htable'): return
    q='%'+self.hsearch.get().strip()+'%'
    rows=conn.execute('SELECT id,ts,customer,total,discount,cash,kapital,other,debt,returned,COALESCE((SELECT sum(pr.amount) FROM partial_returns pr WHERE pr.sale_id=sales.id),0) FROM sales WHERE CAST(id AS TEXT) LIKE ? OR customer LIKE ? ORDER BY id DESC LIMIT 500',(q,q)).fetchall()
    fill(self.htable,[(r[0],(r[0],r[1],r[2],az(r[3]),az(r[4]),az(r[5]),az(r[6]),az(r[7]),az(r[8]),'Tam qaytarılıb' if r[9] else ('Qismən qaytarılıb' if r[10] else 'Satılıb'))) for r in rows])
 def show_sale_receipt(self):
    sid=self.selected_id(self.htable)
    sale=conn.execute('SELECT ts,customer,subtotal,discount,total,cash,kapital,other,debt FROM sales WHERE id=?',(sid,)).fetchone()
    items=conn.execute('SELECT name,qty,price FROM sale_items WHERE sale_id=? ORDER BY id',(sid,)).fetchall()
    lines=[APP,'NIKO TELEKOM','='*38,'Satış №: '+str(sid),'Tarix: '+sale[0],'Müştəri: '+sale[1],'-'*38]
    for name,qty,price in items: lines.append(f'{name} x{qty}  {az(price*qty)}')
    partial=conn.execute('SELECT COALESCE(sum(amount),0) FROM partial_returns WHERE sale_id=?',(sid,)).fetchone()[0]
    lines += ['-'*38,'Ara cəm: '+az(sale[2]),'Endirim: '+az(sale[3]),'YEKUN: '+az(sale[4]),'Qaytarılan: '+az(partial),'Xalis satış: '+az(sale[4]-partial),'Nağd: '+az(sale[5]),'Kapital kartı: '+az(sale[6]),'Digər kart: '+az(sale[7]),'Borc: '+az(sale[8]),'','Təşəkkür edirik!']
    win=tk.Toplevel(self);win.title(f'Satış #{sid} — qəbz');win.geometry('520x650')
    txt=tk.Text(win,font=('Consolas',11),wrap='none');txt.pack(fill='both',expand=True,padx=12,pady=12);txt.insert('1.0','\n'.join(lines));txt.configure(state='disabled')
    button(win,'Mətn faylı kimi saxla',lambda:self.save_receipt_text(sid,lines))
 def save_receipt_text(self,sid,lines):
    dest=filedialog.asksaveasfilename(defaultextension='.txt',initialfile=f'NIKO_qebz_{sid}.txt',filetypes=[('Mətn faylı','*.txt')])
    if not dest:return
    with open(dest,'w',encoding='utf-8') as f:f.write('\n'.join(lines))
    messagebox.showinfo('Hazır','Qəbz mətn faylı saxlanıldı.')
 def build_returns(self):
    f=self.tab('↩ Qaytarmalar')
    ttk.Label(f,text='Qismən və tam məhsul qaytarılması',style='Title.TLabel').pack(anchor='w',pady=6)
    ttk.Label(f,text='Satış seçin, sonra qaytarılacaq məhsulu və miqdarı seçin. Borclu satışlar təhlükəsizlik üçün burada bağlıdır.',foreground='#667085').pack(anchor='w',pady=4)
    bar=ttk.Frame(f);bar.pack(fill='x')
    self.return_search=entry(bar,'Satış № / müştəri axtar',32)
    self.return_search.trace_add('write',lambda *_:self.refresh_returns())
    button(bar,'Yenilə',self.refresh_returns)
    self.return_table=table(f,('Satış №','Tarix','Müştəri','Yekun','Qaytarılıb','Status'),130)
    self.return_table.bind('<<TreeviewSelect>>',lambda *_:self.refresh_return_items())
    ttk.Label(f,text='SATIŞDAN MƏHSULLAR',style='Title.TLabel').pack(anchor='w',pady=(8,2))
    self.return_items_table=table(f,('Məhsul ID','Məhsul','Satılıb','Qaytarılıb','Qalan qaytarma','Vahid qiymət'),130)
    row=ttk.Frame(f);row.pack(fill='x')
    self.return_qty=entry(row,'Qaytarılan say',12);self.return_qty.set('1')
    self.return_method=tk.StringVar(value='Nağd')
    ttk.Combobox(row,textvariable=self.return_method,values=('Nağd','Kapital Bank kartı','Digər kart'),state='readonly',width=22).pack(side='left',padx=5,pady=5)
    button(row,'Seçilmiş məhsulu qaytar',lambda:self.run(self.return_selected_item))
 def refresh_returns(self):
    if not hasattr(self,'return_table'): return
    q='%'+self.return_search.get().strip()+'%'
    rows=conn.execute("SELECT s.id,s.ts,s.customer,s.total,COALESCE((SELECT sum(pr.amount) FROM partial_returns pr WHERE pr.sale_id=s.id),0) FROM sales s WHERE s.debt=0 AND s.returned=0 AND (CAST(s.id AS TEXT) LIKE ? OR s.customer LIKE ?) ORDER BY s.id DESC LIMIT 500",(q,q)).fetchall()
    eligible=[]
    for r in rows:
     sold=conn.execute('SELECT COALESCE(sum(qty),0) FROM sale_items WHERE sale_id=?',(r[0],)).fetchone()[0]
     returned=conn.execute('SELECT COALESCE(sum(pri.qty),0) FROM partial_return_items pri JOIN partial_returns pr ON pr.id=pri.return_id WHERE pr.sale_id=?',(r[0],)).fetchone()[0]
     if returned < sold:
      eligible.append((r[0],(r[0],r[1],r[2],az(r[3]),az(r[4]),'Qismən qaytarılıb' if r[4] else 'Satılıb')))
    fill(self.return_table,eligible)
    self.refresh_return_items()
 def refresh_return_items(self):
    if not hasattr(self,'return_items_table'): return
    sel=self.return_table.selection() if hasattr(self,'return_table') else ()
    if not sel:
     fill(self.return_items_table,[]);return
    sid=int(sel[0])
    rows=conn.execute('''SELECT si.id,si.name,si.qty,si.price,
       COALESCE((SELECT sum(pri.qty) FROM partial_return_items pri JOIN partial_returns pr ON pr.id=pri.return_id WHERE pr.sale_id=? AND pri.sale_item_id=si.id),0),
       si.product_id FROM sale_items si WHERE si.sale_id=? ORDER BY si.id''',(sid,sid)).fetchall()
    fill(self.return_items_table,[(r[0],(r[0],r[1],r[2],r[4],r[2]-r[4],az(r[3]))) for r in rows if r[2]>r[4]])
 def return_selected_item(self):
    sid=self.selected_id(self.return_table);itemid=self.selected_id(self.return_items_table)
    sale=conn.execute('SELECT subtotal,total,debt,returned FROM sales WHERE id=?',(sid,)).fetchone()
    if not sale: raise ValueError('Satış tapılmadı.')
    if sale[2] != 0: raise ValueError('Nisyə/borclu satış qaytarıla bilməz. Əvvəl borc hesabını ayrıca həll edin.')
    if sale[3]: raise ValueError('Bu satış artıq tam qaytarılıb.')
    item=conn.execute('SELECT id,product_id,name,qty,price,cost FROM sale_items WHERE id=? AND sale_id=?',(itemid,sid)).fetchone()
    if not item: raise ValueError('Satış məhsulu tapılmadı.')
    already=conn.execute('SELECT COALESCE(sum(pri.qty),0),COALESCE(sum(pri.amount),0) FROM partial_return_items pri JOIN partial_returns pr ON pr.id=pri.return_id WHERE pr.sale_id=? AND pri.sale_item_id=?',(sid,itemid)).fetchone()
    remaining=item[3]-already[0]
    qty=qtyval(self.return_qty.get())
    if qty<1 or qty>remaining: raise ValueError(f'Qaytarma sayı 1 ilə {remaining} arasında olmalıdır.')
    # Allocate the sale-level discount proportionally. Cumulative rounding prevents
    # repeated partial returns from refunding more than the item's allocated net value.
    gross_cumulative=item[4]*(already[0]+qty)
    if sale[0] <= 0: raise ValueError('Satışın ara cəmi düzgün deyil; qaytarma mümkün deyil.')
    target_net=(gross_cumulative*sale[1]*2//sale[0]+1)//2
    refund=target_net-already[1]
    if refund<0: raise ValueError('Qaytarma məbləği hesablanmadı; administrator yoxlamalıdır.')
    method=self.return_method.get()
    if method not in ('Nağd','Kapital Bank kartı','Digər kart'): raise ValueError('Qaytarma üsulunu seçin.')
    if not messagebox.askyesno('Qismən qaytarma',f'Satış #{sid}\nMəhsul: {item[2]}\nSay: {qty}\nGeri ödəniş: {az(refund)}\nAnbar qalığı artırılacaq. Davam edilsin?'): return
    with conn:
     cur=conn.execute('INSERT INTO partial_returns(sale_id,ts,amount,method) VALUES(?,?,?,?)',(sid,now(),refund,method));rid=cur.lastrowid
     conn.execute('INSERT INTO partial_return_items(return_id,sale_item_id,qty,amount) VALUES(?,?,?,?)',(rid,itemid,qty,refund))
     if item[1] is not None:
      conn.execute('UPDATE products SET qty=qty+? WHERE id=?',(qty,item[1]))
      conn.execute('INSERT INTO movements(ts,product_id,product_name,delta,reason) VALUES(?,?,?,?,?)',(now(),item[1],item[2],qty,'Qismən qaytarma satış #'+str(sid)))
     total_sold=conn.execute('SELECT COALESCE(sum(qty),0) FROM sale_items WHERE sale_id=?',(sid,)).fetchone()[0]
     total_returned=conn.execute('SELECT COALESCE(sum(pri.qty),0) FROM partial_return_items pri JOIN partial_returns pr ON pr.id=pri.return_id WHERE pr.sale_id=?',(sid,)).fetchone()[0]
     if total_sold>0 and total_returned>=total_sold:
      conn.execute('UPDATE sales SET returned=1 WHERE id=?',(sid,))
    audit('Məhsul qaytarıldı',f'Satış #{sid}; {item[2]}; say={qty}; geri ödəniş={az(refund)}; üsul={method}')
    self.refresh();messagebox.showinfo('Qaytarma tamamlandı',f'{item[2]} — {qty} ədəd\nGeri ödəniş: {az(refund)}\nAnbar qalığı yeniləndi.')
 def build_audit(self):
    f=self.tab('🛡 Əməliyyat jurnalı')
    ttk.Label(f,text='Əsas əməliyyatların tarixçəsi',style='Title.TLabel').pack(anchor='w',pady=8)
    row=ttk.Frame(f);row.pack(fill='x');button(row,'Jurnalı yenilə',self.refresh_audit);button(row,'CSV ixrac',lambda:self.run(self.export_audit))
    self.atable=table(f,('ID','Tarix','Əməliyyat','Ətraflı məlumat'),180)
 def refresh_audit(self):
    if not hasattr(self,'atable'): return
    rows=conn.execute('SELECT id,ts,action,details FROM audit_log ORDER BY id DESC LIMIT 1000').fetchall()
    fill(self.atable,[(r[0],r) for r in rows])
 def export_audit(self):
    self.export('SELECT ts,action,details FROM audit_log ORDER BY id DESC','NIKO_emeliyyat_jurnali.csv',('Tarix','Əməliyyat','Məlumat'))

 def build_updates(self):
    f=self.tab('🔄 Proqram yeniləməsi')
    ttk.Label(f,text='NIKO TELEKOM — ONLAYN YENİLƏMƏ',style='Title.TLabel').pack(anchor='w',pady=(0,8))
    ttk.Label(f,text=f'Quraşdırılmış versiya: {VERSION}',font=('Segoe UI',11,'bold')).pack(anchor='w',pady=4)
    ttk.Label(f,text='İnternet vasitəsilə yeni versiyanı yoxlamaq və yenilənmiş EXE faylını endirmək üçün yeniləmə serverinin manifest ünvanını daxil edin.',wraplength=920).pack(anchor='w',pady=5)
    row=ttk.Frame(f);row.pack(fill='x',pady=8)
    self.update_url=entry(row,'Yeniləmə manifestinin HTTPS ünvanı',62)
    self.update_url.set(self.load_update_url())
    button(row,'Ünvanı yadda saxla',lambda:self.run(self.save_update_url))
    actions=ttk.Frame(f);actions.pack(anchor='w',pady=8)
    button(actions,'Yeniləməni yoxla',self.check_update)
    self.update_download_btn=ttk.Button(actions,text='Yeni EXE-ni endir',command=self.download_update,state='disabled')
    self.update_download_btn.pack(side='left',padx=5,pady=5)
    self.update_status=tk.StringVar(value='Hazırdır. Yeniləməni yoxlamaq üçün HTTPS manifest ünvanı lazımdır.')
    ttk.Label(f,textvariable=self.update_status,wraplength=930,foreground='#2457a7').pack(anchor='w',pady=8)
    info=ttk.LabelFrame(f,text='Yeniləmə necə işləyir?');info.pack(fill='x',pady=10)
    ttk.Label(info,text='1. “Yeniləməni yoxla” internetdəki latest.json faylını oxuyur.\\n2. Yeni versiya varsa, “Yeni EXE-ni endir” düyməsi aktiv olur.\\n3. Endirilən faylın SHA-256 imzası manifestdəki dəyərlə müqayisə olunur.\\n4. Proqram öz-özünü işləyərkən əvəz etmir; əvvəl ehtiyat nüsxəsi götürüb proqramı bağlayın, sonra yeni EXE-ni quraşdırın.',wraplength=900,justify='left').pack(anchor='w',padx=10,pady=8)
    ttk.Label(f,text='Təhlükəsizlik: yalnız etibar etdiyiniz HTTPS ünvanından yeniləmə endirin. İnternetin olması təkbaşına yeniləmə serveri yaratmır.',foreground='#9a3412',wraplength=930).pack(anchor='w',pady=6)
    self.latest_update=None

 def load_update_url(self):
    try:
     data=json.loads(UPDATE_CONFIG.read_text(encoding='utf-8'))
     return str(data.get('manifest_url','')).strip()
    except (OSError,ValueError,TypeError):
     return ''

 def save_update_url(self):
    url=self.update_url.get().strip()
    if url and not url.lower().startswith('https://'):
     raise ValueError('Təhlükəsizlik üçün yeniləmə ünvanı HTTPS ilə başlamalıdır.')
    UPDATE_CONFIG.write_text(json.dumps({'manifest_url':url},ensure_ascii=False,indent=2),encoding='utf-8')
    self.update_status.set('Yeniləmə ünvanı yadda saxlanıldı.')
    messagebox.showinfo('Hazır','Yeniləmə ünvanı yadda saxlanıldı.')

 def check_update(self):
    url=self.update_url.get().strip()
    if not url:
     messagebox.showwarning('Yeniləmə ünvanı yoxdur','Əvvəlcə latest.json faylının HTTPS ünvanını daxil edin.')
     return
    if not url.lower().startswith('https://'):
     messagebox.showerror('Təhlükəsizlik','Yalnız HTTPS ünvanlarından istifadə edin.')
     return
    self.update_download_btn.configure(state='disabled')
    self.update_status.set('İnternetdə yeni versiya yoxlanılır...')
    threading.Thread(target=self._check_update_worker,args=(url,),daemon=True).start()

 def _check_update_worker(self,url):
    try:
     req=urllib.request.Request(url,headers={'User-Agent':'NikoTelekom-Updater/30'})
     with urllib.request.urlopen(req,timeout=15) as response:
      if response.status!=200: raise ValueError(f'Server HTTP {response.status} qaytardı.')
      raw=response.read(1024*1024+1)
     if len(raw)>1024*1024: raise ValueError('Manifest faylı 1 MB-dan böyükdür.')
     data=json.loads(raw.decode('utf-8-sig'))
     version=str(data.get('version','')).strip()
     download_url=str(data.get('download_url','')).strip()
     sha256=str(data.get('sha256','')).strip().lower()
     if not version or not download_url or not sha256:
      raise ValueError('Manifestdə version, download_url və sha256 sahələri olmalıdır.')
     if not download_url.lower().startswith('https://'):
      raise ValueError('EXE endirmə ünvanı HTTPS olmalıdır.')
     if len(sha256)!=64 or any(c not in '0123456789abcdef' for c in sha256):
      raise ValueError('Manifestdə SHA-256 64 simvollu hexadecimal dəyər olmalıdır.')
     latest={'version':version,'download_url':download_url,'sha256':sha256,'notes':str(data.get('notes','Yeni versiya'))}
     current_tuple=self.version_tuple(VERSION);latest_tuple=self.version_tuple(version)
     if latest_tuple<=current_tuple:
      self.after(0,lambda:self._update_check_done(None,f'Yeni versiya yoxdur. Quraşdırılmış: {VERSION}; server: {version}.'))
     else:
      self.after(0,lambda:self._update_check_done(latest,f'Yeni versiya tapıldı: {version}\\nQeydlər: {latest["notes"]}'))
    except Exception as e:
     msg=f'Yeniləmə yoxlanmadı: {e}'
     self.after(0,lambda msg=msg:self._update_check_done(None,msg))

 @staticmethod
 def version_tuple(value):
    nums=[]
    for part in str(value).strip().split('.'):
     match=''.join(ch for ch in part if ch.isdigit())
     nums.append(int(match or 0))
    return tuple((nums+[0,0,0,0])[:4])

 def _update_check_done(self,latest,message):
    self.latest_update=latest
    self.update_status.set(message)
    self.update_download_btn.configure(state='normal' if latest else 'disabled')

 def download_update(self):
    latest=getattr(self,'latest_update',None)
    if not latest:
     messagebox.showwarning('Yoxlama lazımdır','Əvvəlcə yeniləməni yoxlayın.')
     return
    if not messagebox.askyesno('Yeniləməni endir',f'V{latest["version"]} versiyası endirilsin?\\n\\n{latest["notes"]}'):
     return
    self.update_download_btn.configure(state='disabled')
    self.update_status.set('Yeni EXE endirilir və SHA-256 yoxlanılır...')
    threading.Thread(target=self._download_update_worker,args=(latest,),daemon=True).start()

 def _download_update_worker(self,latest):
    try:
     downloads=pathlib.Path.home()/'Downloads'
     downloads.mkdir(parents=True,exist_ok=True)
     dest=downloads/f'NIKO_TELEKOM_V{latest["version"]}.exe'
     req=urllib.request.Request(latest['download_url'],headers={'User-Agent':'NikoTelekom-Updater/30'})
     digest=hashlib.sha256()
     total=0
     with urllib.request.urlopen(req,timeout=30) as response, open(dest,'wb') as out:
      if response.status!=200: raise ValueError(f'Endirmə serveri HTTP {response.status} qaytardı.')
      while True:
       chunk=response.read(1024*256)
       if not chunk: break
       total+=len(chunk)
       if total>300*1024*1024: raise ValueError('EXE 300 MB limitini keçir.')
       digest.update(chunk);out.write(chunk)
     if digest.hexdigest().lower()!=latest['sha256']:
      dest.unlink(missing_ok=True)
      raise ValueError('SHA-256 uyğun gəlmədi. Fayl silindi; yeniləmə etibarlı sayılmır.')
     self.after(0,lambda:self._download_done(str(dest),latest))
    except Exception as e:
     msg=f'Endirmə alınmadı: {e}'
     self.after(0,lambda msg=msg:self._download_error(msg))

 def _download_done(self,path,latest):
    self.update_status.set(f'Endirildi və SHA-256 yoxlanıldı: {path}\\nYeni EXE-ni işə salmazdan əvvəl məlumatların ehtiyat nüsxəsini götürün.')
    self.update_download_btn.configure(state='normal')
    messagebox.showinfo('Yeniləmə endirildi',f'Ve rs iya: {latest["version"]}\\nFayl: {path}\\n\\nBu proqram işləyərkən özü-özünü əvəz etmir. Proqramı bağlayın və yeni EXE-ni açmadan əvvəl ehtiyat nüsxəsi götürün.')

 def _download_error(self,message):
    self.update_status.set(message)
    self.update_download_btn.configure(state='normal')
    messagebox.showerror('Yeniləmə xətası',message)

 def build_backup(self):
    f=self.tab('💾 Yedəkləmə');ttk.Label(f,text='Məlumatlar kompüterdə SQLite bazasında saxlanılır.',style='Title.TLabel').pack(anchor='w',pady=10)
    ttk.Label(f,text='Məlumat qovluğu: '+str(BASE),wraplength=950).pack(anchor='w',pady=8)
    ttk.Label(f,text='Gündəlik işdən sonra USB yaddaşa yedək götürmək tövsiyə olunur.').pack(anchor='w',pady=8)
    r=ttk.Frame(f);r.pack(anchor='w',pady=15);button(r,'Yedək yarat (.sqlite3)',lambda:self.run(self.backup));button(r,'Yedəkdən bərpa et',lambda:self.run(self.restore))
    ttk.Label(f,text='Diqqət: Bərpa etmə hazırkı bütün məlumatları seçilən yedəklə əvəz edir.',foreground='red').pack(anchor='w')
 def backup(self):
    dest=filedialog.asksaveasfilename(defaultextension='.sqlite3',initialfile='NIKO_TELEKOM_YEDEK_'+now()[:10]+'.sqlite3',filetypes=[('SQLite yedək','*.sqlite3')]);
    if not dest:return
    with sqlite3.connect(dest) as target:conn.backup(target)
    messagebox.showinfo('Hazır','Yedək faylı yaradıldı.')
 def restore(self):
    global conn
    src=filedialog.askopenfilename(filetypes=[('SQLite yedək','*.sqlite3'),('Bütün fayllar','*.*')]);
    if not src:return
    if not messagebox.askyesno('Təsdiq','Hazırkı məlumatlar yedəklə əvəz edilsin?'):return
    check=sqlite3.connect(f'file:{pathlib.Path(src).as_posix()}?mode=ro',uri=True)
    try:
     if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Yedək zədəlidir.')
     names={r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
     if not {'products','sales','debts','repairs'}.issubset(names):raise ValueError('Bu, NIKO TELEKOM verilənlər bazası deyil.')
     with conn:check.backup(conn)
    finally:check.close()
    # Re-apply schema upgrades after restoring an older V23 backup.
    _cols={r[1] for r in conn.execute('PRAGMA table_info(sales)').fetchall()}
    if 'returned' not in _cols:
     conn.execute('ALTER TABLE sales ADD COLUMN returned INTEGER NOT NULL DEFAULT 0 CHECK(returned IN (0,1))')
    conn.execute('CREATE TABLE IF NOT EXISTS sale_returns(id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL UNIQUE, ts TEXT NOT NULL, amount INTEGER NOT NULL, method TEXT NOT NULL, FOREIGN KEY(sale_id) REFERENCES sales(id))')
    conn.execute("CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE TABLE IF NOT EXISTS supplier_bills(id INTEGER PRIMARY KEY, supplier_id INTEGER NOT NULL, ts TEXT NOT NULL, invoice_no TEXT NOT NULL DEFAULT '', amount INTEGER NOT NULL, paid INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '', FOREIGN KEY(supplier_id) REFERENCES suppliers(id))")
    conn.execute("CREATE TABLE IF NOT EXISTS supplier_payments(id INTEGER PRIMARY KEY, bill_id INTEGER NOT NULL, ts TEXT NOT NULL, amount INTEGER NOT NULL, method TEXT NOT NULL, FOREIGN KEY(bill_id) REFERENCES supplier_bills(id))")
    _repair_cols={r[1] for r in conn.execute('PRAGMA table_info(repairs)').fetchall()}
    if 'imei' not in _repair_cols: conn.execute("ALTER TABLE repairs ADD COLUMN imei TEXT NOT NULL DEFAULT ''")
    if 'paid' not in _repair_cols: conn.execute("ALTER TABLE repairs ADD COLUMN paid INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE TABLE IF NOT EXISTS repair_payments(id INTEGER PRIMARY KEY, repair_id INTEGER NOT NULL, ts TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), method TEXT NOT NULL, FOREIGN KEY(repair_id) REFERENCES repairs(id))")
    conn.commit()
    self.refresh();messagebox.showinfo('Hazır','Yedək bərpa edildi.')
 def refresh(self):
    self.refresh_products();self.refresh_receive();self.refresh_sale_products();self.refresh_cart()
    if hasattr(self,'htable'): self.refresh_history()
    if hasattr(self,'return_table'): self.refresh_returns()
    if hasattr(self,'atable'): self.refresh_audit()
    rows=conn.execute('SELECT id,sale_id,customer,amount,remaining FROM debts WHERE remaining>0 ORDER BY id DESC').fetchall();fill(self.dtable,[(r[0],(r[0],r[1],r[2],az(r[3]),az(r[4]))) for r in rows])
    if hasattr(self,'ttable'): self.refresh_repairs()
    if hasattr(self,'sup_table'): self.refresh_suppliers()
    rows=conn.execute('SELECT id,ts,name,amount FROM expenses ORDER BY id DESC').fetchall();fill(self.etable,[(r[0],(*r[:3],az(r[3]))) for r in rows]);self.refresh_reports()
 def close(self):conn.close();self.destroy()
if __name__=='__main__':
 auto_backup()
 POS().mainloop()
