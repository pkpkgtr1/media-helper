#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ltxdb — Jasna-LTX 资源库（ltx.libray.workers.dev）抓取 / 查询

站点只有一个公开接口，一次给全量：
    GET /api/items -> {items:[...], updated_at, nyaa:{...}, avatars:{演员: 头像URL},
                       genres:{"c5=18": [中, 英, 日]}}
条目字段：code / title / title_zh / actors[] / date / maker / cover / url(javdb) /
          score / votes / links[](ed2k|magnet) / pending_links[] / pending / shot /
          missing / waiting / added_at / director / genres[] / subtitle

用法:
    python3 ltxdb.py sync                      # 拉全量，存 SQLite + 原始 JSON
    python3 ltxdb.py stats                     # 看库里的统计
    python3 ltxdb.py lookup ADN-814            # 按番号查（支持 ssni100 / SSNI-100）
    python3 ltxdb.py search 三上悠亚            # 按标题/演员/厂商模糊查
    python3 ltxdb.py export /tmp/ltx.csv       # 导出 CSV

默认库位置是项目根下的 config/ltxdb/，与界面里的「Jasna 资源库」是同一份数据
（`LTXDB_HOME` 可覆盖）。抓取、建表与查询逻辑都在 `media_helper/ltx.py`，
这个脚本只是它的命令行外壳，两边不会各自长出一套。
"""

import argparse
import csv
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from media_helper import ltx  # noqa: E402

DATA_DIR = str(ltx.default_data_dir())
DB = str(ltx.db_path())


def log(msg):
    sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))
    sys.stderr.flush()


# 兼容旧脚本里对这些名字的引用
fetch_items = ltx.fetch_items
ed2k_size = ltx.ed2k_size
link_name = ltx.link_name
human = ltx.human_size
norm_code = ltx.normalize_code


def init_db(conn):
    ltx.init_db(conn)


def cmd_sync(args):
    try:
        report = ltx.sync(progress=log)
    except RuntimeError as exc:
        log("同步失败：%s" % exc)
        return 1
    return 0 if report["total"] else 1


def cmd_stats(args):
    status = ltx.status()
    if not status["ready"]:
        log("还没有库，先跑 sync")
        return 1
    print("条目总数      :", status["total"])
    print("有下载链接    :", status["withLinks"])
    print("信息待确认    :", status["pending"])
    print("日期范围      : %s ~ %s" % (status["dateFrom"] or "-", status["dateTo"] or "-"))
    print("厂商数        :", status["makers"])
    print("分类数        :", status["genres"])

    with ltx.connect() as conn:
        recent = conn.execute(
            "SELECT COUNT(*) FROM items WHERE date >= date('now','-30 day')").fetchone()[0]
        print("近 30 天新增  :", recent)
        print("\n厂商 Top8:")
        for name, count in conn.execute(
                "SELECT maker, COUNT(*) c FROM items WHERE maker != '' "
                "GROUP BY maker ORDER BY c DESC LIMIT 8"):
            print("   %-18s %d" % (name, count))
        ed2k = magnet = 0
        for (links,) in conn.execute("SELECT links FROM items"):
            for link in json.loads(links or "[]"):
                if link.startswith("ed2k://"):
                    ed2k += 1
                elif link.startswith("magnet:"):
                    magnet += 1
    print("\n链接类型:")
    print("   ed2k %d / magnet %d" % (ed2k, magnet))
    if status["updatedAt"]:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(status["updatedAt"] / 1000))
        print("\n接口数据更新于:", stamp)
    return 0


def cmd_lookup(args):
    try:
        item = ltx.detail(args.code)
    except KeyError as exc:
        log(str(exc).strip("'\""))
        return 2
    print("番号     :", item["code"])
    print("标题     :", item["title"])
    if item["titleZh"] and item["titleZh"] != item["title"]:
        print("中文标题 :", item["titleZh"])
    print("演员     :", "、".join(item["actors"]) or "-")
    print("厂商/日期:", (item["maker"] or "-"), "/", item["date"] or "-")
    print("导演     :", item["director"] or "-")
    print("分类     :", "、".join(item["genres"]) or "-")
    print("评分     :", item["score"], "（%s 票）" % item["votes"])
    print("javdb    :", item["url"])
    print("封面     :", item["cover"])
    if item["shot"]:
        print("长截图   :", item["shot"])
    flags = [name for name, on in (("pending", item["pending"]), ("missing", item["missing"]),
                                   ("waiting", item["waiting"])) if on]
    if flags:
        print("标记     :", ",".join(flags))
    print("链接     :")
    for link in item["links"]:
        label = "待确认" if link["kind"] == "pending" else link["kind"]
        print("   [%s] %s  %s" % (label, link["sizeText"], (link["name"] or "")[:80]))
        print("        ", link["url"][:160] + ("…" if len(link["url"]) > 160 else ""))
    return 0


def cmd_search(args):
    result = ltx.search(args.keyword, limit=args.limit)
    if not result["total"]:
        log("没有匹配 %r 的条目" % args.keyword)
        return 2
    for item in result["items"]:
        print("%-12s %-10s %-22s %-10s %.2f  links=%d" % (
            item["code"], item["date"] or "-", (item["titleZh"] or "")[:22],
            (item["maker"] or "")[:10], item["score"] or 0, item["linkCount"]))
    print("共 %d 条" % result["total"])
    return 0


def cmd_export(args):
    if not ltx.db_path().exists():
        log("还没有库，先跑 sync")
        return 1
    columns = ("code,title,title_zh,actors,date,maker,score,votes,url,cover,"
               "shot,pending,links")
    with ltx.connect() as conn:
        rows = conn.execute("SELECT %s FROM items ORDER BY date DESC" % columns).fetchall()
    with open(args.out, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["番号", "标题", "中文标题", "演员", "发行日期", "厂商", "评分", "票数",
                         "javdb", "封面", "长截图", "待确认", "链接"])
        for row in rows:
            values = list(row)
            values[3] = "、".join(json.loads(values[3] or "[]"))
            values[12] = "\n".join(json.loads(values[12] or "[]"))
            writer.writerow(values)
    log("已导出 %d 行 -> %s" % (len(rows), args.out))
    return 0


# ---------------------------------------------------------------- push（已停用）
def cmd_push(args):
    """115 离线推送功能已移除。

    保留同名子命令只是为了兼容面板 /api/ltx/push 的调用参数
    （push <code> --dir <dir> [--dry-run]），不再导入 p115client、
    不再读 config.yaml 的 115 cookie、不再请求 115 离线接口。
    """
    log("115 离线推送功能已移除，当前库只提供抓取与查询（sync/stats/lookup/search/export）")
    return 3


def main():
    parser = argparse.ArgumentParser(description="Jasna-LTX 资源库抓取/查询")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync", help="拉全量入库").set_defaults(func=cmd_sync)
    sub.add_parser("stats", help="库统计").set_defaults(func=cmd_stats)

    lookup = sub.add_parser("lookup", help="按番号查")
    lookup.add_argument("code")
    lookup.set_defaults(func=cmd_lookup)

    search = sub.add_parser("search", help="模糊搜标题/演员/厂商")
    search.add_argument("keyword")
    search.add_argument("--limit", type=int, default=20)
    search.set_defaults(func=cmd_search)

    export = sub.add_parser("export", help="导出 CSV")
    export.add_argument("out")
    export.set_defaults(func=cmd_export)

    push = sub.add_parser("push", help="（已停用）115 离线推送")
    push.add_argument("code")
    push.add_argument("--dir", default="/", help="（已停用）原 115 保存目录参数，仅为兼容保留")
    push.add_argument("--dry-run", action="store_true")
    push.set_defaults(func=cmd_push)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
