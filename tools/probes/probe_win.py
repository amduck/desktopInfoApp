import webview
w = webview.create_window("probe1234", url="data:text/html,<b>x</b>", width=200, height=120, frameless=True)
attrs = [a for a in dir(w) if not a.startswith("__")]
print("WIN ATTRS:", [a for a in attrs if a.startswith("_") or "form" in a.lower() or "hwnd" in a.lower() or "handle" in a.lower() or "gui" in a.lower()])
try:
    print("ewk:", type(w.ewk).__name__, [a for a in dir(w.ewk) if not a.startswith("__")])
except Exception as e:
    print("ewk err:", e)
try:
    f = w.ewk._form
    print("form type:", type(f))
except Exception as e:
    print("form err:", e)
w.destroy()
