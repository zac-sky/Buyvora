from scripts.eval_retrieval import summarize, check_report


def test_eval_does_not_count_empty_negative_cases_as_perfect_recall():
    metrics = summarize([
        {"expected":["a","b"], "retrieved":["x","b"], "violations":[]},
        {"expected":["c"], "retrieved":[], "violations":[]},
        {"expected":[], "retrieved":[], "violations":[]},
        {"expected":[], "retrieved":["bad"], "violations":["stock"]},
    ])
    assert metrics["recall_at_k"] == 0.25
    assert metrics["mrr_at_k"] == 0.25
    assert metrics["negative_accuracy"] == 0.5
    assert metrics["constraint_violations"] == 1


def test_live_evaluation_fails_when_embedding_provider_degrades():
    metrics = {"recall_at_k":1,"mrr_at_k":1,"negative_accuracy":1,"constraint_violations":0}
    report = {"mode":"configured-embeddings", "variants":{
        "keyword":{"metrics":{**metrics,"recall_at_k":0}},
        "semantic":{"metrics":metrics,"cases":[{"expected":["a"],"strategy":"keyword_2gram"}]},
    }}
    gates = {"min_recall":0.8,"min_mrr":0.7,"min_negative_accuracy":1,"min_keyword_recall_gain":0.1}
    assert not check_report(report,gates)["live_vector_used"]
