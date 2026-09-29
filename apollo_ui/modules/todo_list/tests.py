from module import Module
def main():
    m=Module({"base_dir":".","validation":True})
    try:
        assert m.self_test()
        names={x["name"] for x in m.tools()}
        assert {"add_to_do_item","complete_to_do_item","achieve_to_do_list"} <= names
        print("To-Do List tests passed.")
    finally:m.close()
if __name__=="__main__":main()
