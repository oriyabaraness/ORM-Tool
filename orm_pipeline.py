"""Build the Israel/Jordan/Turkey regulatory risk comparison index (orm.db).

Usage:
  python orm_pipeline.py build            # metadata + any cached text (fast, offline)
  python orm_pipeline.py build --fetch    # also download & extract PDFs
  python orm_pipeline.py build --fetch --country IL --limit 20
  python orm_pipeline.py build --fetch --retry-errors
  python orm_pipeline.py classify         # re-tag only (after taxonomy edits)
  python orm_pipeline.py status
  python orm_pipeline.py update           # re-crawl regulators, rebuild, report changes
  python orm_pipeline.py obligations      # rebuild obligations + control suggestions
  ANTHROPIC_API_KEY=... python orm_pipeline.py obligations --llm --document IL-BOI-PC-310
                                          # have Claude read one directive (cached
                                          # in orm_texts/llm/, commit it to deploy)

Jordan: most CBJ entries have no direct PDF link in the index. Either run
`python jordan_cbj_index.py` first (it tries to scrape PDF links), or save a
PDF from the CBJ site to orm_texts/manual/<document id>.pdf -- `status --missing`
lists the ids.
"""
import argparse

from orm import db, obligations, pipeline, update


def cmd_status(args):
    with db.session(args.db) as conn:
        db.init(conn)
        rows = conn.execute(
            "SELECT jurisdiction, text_status, COUNT(*) n FROM document "
            "GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        if not rows:
            print("Empty index. Run: python orm_pipeline.py build")
            return
        for r in rows:
            print(f"{r['jurisdiction']}  {r['text_status']:<8} {r['n']}")
        n = conn.execute("SELECT COUNT(*) FROM provision").fetchone()[0]
        print(f"provisions: {n}")
        print(f"classified at: {db.get_meta(conn, 'classified_at', 'never')}")
        if args.missing:
            print("\nDocuments without text (save PDFs to orm_texts/manual/<id>.pdf):")
            for r in conn.execute(
                    "SELECT id, title FROM document WHERE text_status != 'ok' "
                    "ORDER BY id"):
                print(f"  {r['id']}  —  {r['title'][:80]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None, help="path to orm.db")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="ingest, extract text, classify")
    b.add_argument("--fetch", action="store_true", help="download PDFs")
    b.add_argument("--country", action="append", choices=["IL", "JO", "TR"],
                   help="limit to a jurisdiction (repeatable)")
    b.add_argument("--limit", type=int, help="max documents to extract this run")
    b.add_argument("--retry-errors", action="store_true")

    sub.add_parser("classify", help="re-run tagging on existing provisions")
    s = sub.add_parser("status", help="show index coverage")
    s.add_argument("--missing", action="store_true", help="list docs without text")
    sub.add_parser("update", help="re-crawl every regulator, rebuild, report "
                                  "what is new (writes update_reports/latest.txt)")

    o = sub.add_parser("obligations", help="rebuild obligations and control "
                                           "suggestions (optionally read by Claude)")
    o.add_argument("--llm", action="store_true",
                   help="have Claude read --document (needs ANTHROPIC_API_KEY)")
    o.add_argument("--document", action="append", default=[],
                   help="document id, e.g. IL-BOI-PC-310 (repeatable)")

    args = ap.parse_args()
    if args.cmd == "build":
        pipeline.build(args.db, fetch=args.fetch,
                       jurisdictions=set(args.country) if args.country else None,
                       limit=args.limit, retry_errors=args.retry_errors, log=print)
    elif args.cmd == "classify":
        with db.session(args.db) as conn:
            db.init(conn)
            pipeline.classify_all(conn, log=print)
    elif args.cmd == "obligations":
        with db.session(args.db) as conn:
            db.init(conn)
            if args.llm:
                from orm import llm
                if not args.document:
                    ap.error("--llm needs at least one --document")
                for doc_id in args.document:
                    n = llm.read_document(conn, doc_id, log=print)
                    print(f"{doc_id}: {n} obligations saved to "
                          f"{obligations.llm_cache_path(doc_id)}")
            print(f"obligations: {obligations.build_all(conn)}")
    elif args.cmd == "update":
        report = update.update(args.db, log=print)
        print("\n" + report.to_text())
    else:
        cmd_status(args)


if __name__ == "__main__":
    main()
