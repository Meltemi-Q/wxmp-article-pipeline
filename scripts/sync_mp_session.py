#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 wechat-article-exporter 的后台登录态同步成 wxmp-sync 认的格式。

背景: 两个工具各存一份公众号后台登录态, 格式不同但信息等价——
  exporter : /root/.openclaw/data/wxdown/kv/cookie/<hash>  {"token","cookies":[{name,value}]}
  wxmp-sync: /root/.wxmp-sync/mp-session.json              {"token","cookie","cookie_names",...}
以前扫一次码只救活一份, 另一份仍报 200003 invalid session。本脚本消除这个割裂: 
取 exporter 最新那份 -> 校验真的活着 -> 写入 mp-sync 格式(原文件先备份)。

用法:
  python3 sync_mp_session.py            # 活就同步, 死就退出(不覆盖好的)
  python3 sync_mp_session.py --check    # 只检查两份状态, 不写
只读远端(GET 一次 appmsgpublish 验活), 不做任何写操作。
"""
import argparse, glob, json, os, shutil, sys, time, urllib.parse, urllib.request
from datetime import datetime

EXPORTER_DIR = "/root/.openclaw/data/wxdown/kv/cookie"
MP_SESSION = "/root/.wxmp-sync/mp-session.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


def newest_exporter_session():
    files = [f for f in glob.glob(os.path.join(EXPORTER_DIR, "*")) if os.path.isfile(f)]
    if not files:
        return None, None
    files.sort(key=os.path.getmtime, reverse=True)
    try:
        d = json.load(open(files[0], encoding="utf-8"))
    except Exception as e:
        print("解析失败 %s: %s" % (files[0], e))
        return None, files[0]
    return d, files[0]


def to_cookie_header(cookies):
    parts = []
    for c in cookies or []:
        n = c.get("name") or c.get("key")
        v = c.get("value")
        if n and v is not None:
            parts.append("%s=%s" % (n, v))
    return "; ".join(parts)


def is_alive(token, cookie):
    """GET 一次 appmsgpublish 判断登录态是否有效。ret==0 即活。"""
    q = urllib.parse.urlencode({"sub": "list", "begin": 0, "count": 1, "token": token,
                                "lang": "zh_CN", "f": "json", "ajax": 1})
    url = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish?" + q
    req = urllib.request.Request(url, headers={
        "Cookie": cookie, "User-Agent": UA,
        "Referer": "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&token=%s&lang=zh_CN" % token,
        "X-Requested-With": "XMLHttpRequest",
    })
    try:
        raw = urllib.request.urlopen(req, timeout=25).read()
        if not raw:
            return False, "empty body"
        d = json.loads(raw.decode("utf-8"))
        ret = d.get("base_resp", {}).get("ret")
        return ret == 0, "ret=%s" % ret
    except Exception as e:
        return False, str(e)[:80]


def load_mp_session():
    if not os.path.exists(MP_SESSION):
        return None
    try:
        return json.load(open(MP_SESSION, encoding="utf-8"))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只检查, 不写入")
    args = ap.parse_args()

    exp, path = newest_exporter_session()
    if not exp:
        sys.exit("exporter 没有可用登录态, 去 wxdown.meltemi.vip 扫码")
    e_token = str(exp.get("token") or "")
    e_cookie = to_cookie_header(exp.get("cookies"))
    age_min = int((time.time() - os.path.getmtime(path)) / 60)
    e_alive, e_msg = is_alive(e_token, e_cookie)
    print("exporter 登录态: %s (%s) | %d 分钟前 | %s" %
          ("活" if e_alive else "死", e_msg, age_min, os.path.basename(path)))

    cur = load_mp_session()
    if cur:
        m_alive, m_msg = is_alive(str(cur.get("token") or ""), cur.get("cookie") or "")
        print("wxmp-sync 登录态: %s (%s)" % ("活" if m_alive else "死", m_msg))
    else:
        m_alive = False
        print("wxmp-sync 登录态: 不存在")

    if args.check:
        return
    if not e_alive:
        print("exporter 那份也不是活的, 不覆盖现有文件。去 wxdown.meltemi.vip 重扫码。")
        sys.exit(2)
    if m_alive and cur and cur.get("token") == e_token:
        print("两份已一致且有效, 无需同步。")
        return

    if cur:
        bak = MP_SESSION + ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy(MP_SESSION, bak)
        print("已备份原文件 -> " + os.path.basename(bak))

    out = {
        "token": e_token,
        "cookie": e_cookie,
        "cookie_names": [c.get("name") or c.get("key") for c in (exp.get("cookies") or [])],
        "source": "exporter-sync",
        "url": "https://mp.weixin.qq.com/cgi-bin/home?t=home/index&token=%s&lang=zh_CN" % e_token,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    os.makedirs(os.path.dirname(MP_SESSION), exist_ok=True)
    with open(MP_SESSION, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("已把 exporter 的活登录态写入 %s" % MP_SESSION)


if __name__ == "__main__":
    main()
