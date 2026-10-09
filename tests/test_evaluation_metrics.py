import pytest

from quest_rag.api.evaluation import build_summary, calculate_generation_metrics, valid_ragas_scores


@pytest.mark.parametrize('metrics', [
    {'enabled': True},
    {'enabled': False},
    {'enabled': True, 'error': 'judge failed'},
    {'faithfulness': True, 'context_precision': float('nan'), 'context_recall': float('inf')},
])
def test_missing_or_invalid_judge_scores_are_not_perfect_scores(metrics):
    result = calculate_generation_metrics('test answer', [], {}, metrics)
    assert result['ragas_average'] is None
    assert valid_ragas_scores(metrics) == {}


def test_only_actual_ragas_metrics_contribute_to_average():
    metrics = {'enabled': True, 'faithfulness': 0.2, 'context_recall': 0.6, 'elapsed_ms': 300}
    assert calculate_generation_metrics('answer', [], {}, metrics)['ragas_average'] == 0.4


def test_summary_ignores_legacy_contaminated_average_and_failed_judge():
    items = [
        {'generation_metrics': {'passed': True, 'ragas_average': 1.0},
         'ragas_metrics': {'enabled': True, 'error': 'empty contexts'}},
        {'generation_metrics': {'passed': True, 'ragas_average': 0.8},
         'ragas_metrics': {'enabled': True, 'faithfulness': 0.2, 'context_recall': 0.6}},
    ]
    summary = build_summary(items, 2, 1)
    assert summary['ragas_average'] == 0.4
    assert summary['ragas_metric_averages'] == {'faithfulness': 0.2, 'context_recall': 0.6}


def test_summary_has_no_ragas_score_when_no_judge_completed():
    items = [{'generation_metrics': {'passed': False, 'ragas_average': 1.0},
              'ragas_metrics': {'enabled': True, 'error': 'timeout'}, 'generation_error': 'timeout'}]
    summary = build_summary(items, 0, 0)
    assert summary['ragas_average'] is None
    assert summary['ragas_metric_averages'] == {}
    assert summary['generation_error_count'] == 1
