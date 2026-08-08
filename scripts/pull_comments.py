#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只读拉取公众号后台某篇文章的评论正文。

接口来源: res.wx.qq.com .../pages/comment/comment_list/comment_list.js
  GET /misc/appmsgcomment?action=list_latest_comment  -> 文章列表(含 comment_id)
  GET /misc/appmsgcomment?action=list_comment         -> 某文章评论列表

用法:
  python3 pull_comments.py --appmsgid 2247485899
  python3 pull_comments.py --comment-id 4440681168547561475
  python3 pull_comments.py --appmsgid 2247485899 --json out.json
本脚本只发 GET 读取请求, 不做任何写操作(不发表/不删除/不回复/不改设置)。
"""
import argparse, glob, json, os, sys, time, urllib.parse, urllib.request

COOKIE_DIR = "/root/.openclaw/data/wxdown/kv/cookie"
BASE = "https://mp.weixin.qq.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


def load_session(cookie_dir=COOKIE_DIR):
    files = [f for f in glob.glob(os.path.join(cookie_dir, "*")) if os.path.isfile(f)]
    if not files:
        sys.exit("no cookie file in %s" % cookie_dir)
    files.sort(key=os.path.getmtime, reverse=True)
    data = json.load(open(files[0]))
    token = str(data["token"])
    cookie = "; ".join("%s=%s" % (c["name"], c["value"]) for c in data["cookies"])
    return token, cookie, files[0]


def api_get(path, params, token, cookie):
    q = dict(params)
    q.update({"token": token, "lang": "zh_CN", "f": "json", "ajax": "1"})
    url = BASE + path + "?" + urllib.parse.urlencode(q)
    referer = ("%s/misc/appmsgcomment?action=list_latest_comment&begin=0&count=10"
               "&sendtype=MASSSEND&scene=1&token=%s&lang=zh_CN" % (BASE, token))
    req = urllib.request.Request(url, headers={
        "Cookie": cookie, "User-Agent": UA, "Referer": referer,
        "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
    })
    raw = urllib.request.urlopen(req, timeout=30).read()
    if not raw:
        sys.exit("empty body from %s (session expired or wrong params)" % path)
    d = json.loads(raw.decode("utf-8"))
    ret = d.get("base_resp", {}).get("ret")
    if ret != 0:
        sys.exit("api ret=%s msg=%s url=%s" % (ret, d.get("base_resp"), url))
    return d


def find_comment_id(appmsgid, token, cookie, max_pages=20):
    """遍历 list_latest_comment 找 appmsgid 对应的 comment_id"""
    appmsgid = int(appmsgid)
    for page in range(max_pages):
        d = api_get("/misc/appmsgcomment", {
            "action": "list_latest_comment", "begin": page * 20, "count": 20,
            "sort_type": 0, "sendtype": "MASSSEND",
        }, token, cookie)
        lst = json.loads(d["app_msg_list"])
        msgs = lst.get("app_msg", [])
        if not msgs:
            break
        for a in msgs:
            if int(a["id"]) == appmsgid:
                return a["item"]["comment_id"], a["item"].get("title", "")
        if (page + 1) * 20 >= int(lst.get("total_count", 0)):
            break
    sys.exit("appmsgid %s not found in comment article list" % appmsgid)


def list_comments(comment_id, token, cookie, count=20, filtertype=0, day=0, ctype=0):
    """分页拉全部评论"""
    out, begin, title, totals = [], 0, "", {}
    while True:
        d = api_get("/misc/appmsgcomment", {
            "action": "list_comment", "comment_id": comment_id,
            "begin": begin, "count": count,
            "filtertype": filtertype, "day": day, "type": ctype, "max_id": 0,
        }, token, cookie)
        cl = json.loads(d["comment_list"])
        batch = cl.get("comment", []) or []
        title = cl.get("title", title)
        totals = {k: cl.get(k) for k in
                  ("total_count", "total_count_contains_reply",
                   "total_elected_count", "total_shield_count")}
        out.extend(batch)
        begin += len(batch)
        if len(batch) < count or begin >= int(totals.get("total_count") or 0):
            break
        time.sleep(0.4)
    return title, totals, out


def fmt(c, i):
    ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(c.get("post_time", 0)))
    flags = []
    if c.get("is_elected"):
        flags.append("精选")
    if c.get("shield_status"):
        flags.append("已屏蔽")
    if c.get("is_top"):
        flags.append("置顶")
    head = "[%02d] %s  赞%s  %s  %s%s" % (
        i, c.get("nick_name", ""), c.get("like_num", 0), ts,
        c.get("ip_wording", "") or "-", ("  <%s>" % "/".join(flags)) if flags else "")
    lines = [head, "     " + (c.get("content", "") or "(无文字/图片或语音)")]
    for r in (c.get("reply", {}) or {}).get("reply_list", []) or []:
        lines.append("     └ 作者回复: " + (r.get("content", "") or ""))
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--appmsgid")
    p.add_argument("--comment-id")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--filtertype", type=int, default=0)
    p.add_argument("--day", type=int, default=0)
    p.add_argument("--type", type=int, default=0, dest="ctype")
    p.add_argument("--json", help="dump raw comment objects to this file")
    a = p.parse_args()
    if not a.appmsgid and not a.comment_id:
        p.error("need --appmsgid or --comment-id")

    token, cookie, cf = load_session()
    print("session: %s (token=%s)" % (cf, token))
    cid, title = (a.comment_id, "") if a.comment_id else find_comment_id(a.appmsgid, token, cookie)
    print("comment_id: %s" % cid)

    title, totals, cs = list_comments(cid, token, cookie, a.count, a.filtertype, a.day, a.ctype)
    print("title: %s" % title)
    print("totals: %s" % totals)
    print("fetched: %d\n" % len(cs))
    for i, c in enumerate(cs, 1):
        print(fmt(c, i))
    if a.json:
        json.dump(cs, open(a.json, "w"), ensure_ascii=False, indent=1)
        print("\nraw -> %s" % a.json)


if __name__ == "__main__":
    main()
