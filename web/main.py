from graphrag.query.cli import run_local_search
if __name__ == '__main__':
    run_local_search(
        "",
        "output",
        "/Users/yuaneg/git-source/graphrag-rag/example/userdata/www_hnpamd_com_2",
        2,
       "multiple paragraphs",
        False,
        "电话多少",
    )