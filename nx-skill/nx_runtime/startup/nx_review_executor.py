import os
import runpy


def main():
    runtime_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    runpy.run_path(
        os.path.join(runtime_root, "application", "nx_review_executor.py"),
        run_name="__main__",
    )


if __name__ == "__main__":
    main()
