"""Print the extracted text of a stored publication.

Usage:
  python3 read_text.py boi_texts/<file>.txt.gz
  python3 read_text.py --grep "inflation" boi_texts/*.txt.gz   # search across docs
"""
import gzip
import sys


def read(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        return f.read()


def main(argv):
    if argv and argv[0] == "--grep":
        needle = argv[1].lower()
        for path in argv[2:]:
            for n, line in enumerate(read(path).splitlines(), 1):
                if needle in line.lower():
                    print(f"{path}:{n}: {line.strip()}")
    else:
        for path in argv:
            print(read(path))


if __name__ == "__main__":
    main(sys.argv[1:])
