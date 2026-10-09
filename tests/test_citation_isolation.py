from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Barrier

from quest_rag.rag.citations import get_citations, register_citation, reset_citations


def add_source(ref_id):
    return register_citation(ref_id=ref_id, source_type='knowledge', title=ref_id, snippet=ref_id)


def test_concurrent_requests_do_not_clear_or_mix_citations():
    barrier = Barrier(2)

    def collect(prefix):
        reset_citations()
        add_source(prefix + '-1')
        barrier.wait(timeout=5)
        add_source(prefix + '-2')
        return get_citations()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(collect, 'first')
        second = pool.submit(collect, 'second')
        for prefix, future in [('first', first), ('second', second)]:
            sources = future.result(timeout=5)
            assert [source['ref_id'] for source in sources] == [prefix + '-1', prefix + '-2']
            assert [source['label'] for source in sources] == ['1', '2']


def test_tool_thread_with_copied_context_registers_source_in_request():
    reset_citations()
    context = copy_context()
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(context.run, add_source, 'tool-source').result(timeout=5) == '1'
    assert [source['ref_id'] for source in get_citations()] == ['tool-source']
    reset_citations()
    assert get_citations() == []
