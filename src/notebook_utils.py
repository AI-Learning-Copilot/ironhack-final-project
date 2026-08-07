from __future__ import annotations


def normalize_notebook_path(path: str) -> str:
    """
    Normalize notebook paths coming from different sources
    (Slack export, repository, CSVs).

    Returns a canonical relative path that matches the repository.
    """

    path = path.strip()

    # Remove Slack prefixes
    if path.startswith("File:"):
        path = path.replace("File:", "", 1).strip()

    # Remove bullets if present
    path = path.lstrip("-•* ").strip()

    # Folder names sometimes omit the leading zero
    replacements = {
        "1_python/": "01_python/",
        "2_numpy/": "02_numpy/",
        "3_pandas/": "03_pandas/",
        "4_data_viz/": "04_data_viz/",
        "5_Machine_Learning/": "05_Machine_Learning/",
        "6_Machine_Learning_Unsupervised/": "06_Machine_Learning_Unsupervised/",
        "7_Deep_Learning/": "07_Deep_Learning/",
        "8_NLP/": "08_NLP/",
        "9_Embeddings/": "09_Embeddings/",
    }

    for old, new in replacements.items():
        if path.startswith(old):
            path = path.replace(old, new, 1)
            break

    # Slack sometimes omits the parent folder or uses older filenames.
    filename_map = {
        "3_supervised_metrics_regression.ipynb":
            "05_Machine_Learning/3_supervised_metrics_regression.ipynb",

        "4_supervised_metrics_classification.ipynb":
            "05_Machine_Learning/4_supervised_metrics_classification.ipynb",

        "5_supervised_algorithms_regression.ipynb":
            "05_Machine_Learning/5_supervised_algorithms_regression.ipynb",

        "6_supervised_algorithms_classification.ipynb":
            "05_Machine_Learning/6_supervised_algorithms_classification.ipynb",

        "11_LLM_APIs/4_guidelines-for-prompting.ipynb":
            "11_LLM_APIs/4_extra_guidelines-for-prompting.ipynb",

        "11_LLM_APIs/5_iterative-prompt-development.ipynb":
            "11_LLM_APIs/5_extra_iterative-prompt-development.ipynb",
    }

    return filename_map.get(path, path)