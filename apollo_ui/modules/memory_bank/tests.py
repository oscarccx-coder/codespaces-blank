from module import Module
def main():
    m=Module({"base_dir":".","validation":True})
    try:
        assert m.self_test()
        names={x["name"] for x in m.tools()}
        assert {"store_memory","search_memory_bank","memory_bank_stats"} <= names
        print("Memory Bank tests passed.")
    finally:
        m.close()
if __name__=="__main__": main()
