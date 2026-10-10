"""Current cooperating iframe state. Single-process, owner-scoped, no file contents."""
import copy
import threading
import time

from fastapi import HTTPException


class PageSessions:
    def __init__(self):
        self._pages = {}
        self._lock = threading.RLock()

    def get(self, case_id, owner_id, fresh=False):
        with self._lock:
            page = self._pages.get(str(case_id))
            if not page or page['owner_id'] != owner_id:
                page = None
            if fresh and (not page or not page['open'] or time.monotonic() - page['seen'] > 5):
                raise HTTPException(409, detail='请先打开申请页面，等待页面连接后再填写')
            return copy.deepcopy(page)

    def update(self, case_id, owner_id, data):
        with self._lock:
            old = self._pages.get(str(case_id))
            if old and old['owner_id'] != owner_id:
                raise HTTPException(404, detail='申请页面不存在')
            if old and data['page_id'] in old['retired']:
                return copy.deepcopy(old)
            if old and old['page_id'] == data['page_id'] and data['sequence'] <= old['sequence']:
                return copy.deepcopy(old)
            retired = set(old['retired']) if old else set()
            if old and old['page_id'] != data['page_id']:
                retired.add(old['page_id'])
            page = {**data, 'owner_id': owner_id, 'seen': time.monotonic(), 'retired': retired}
            self._pages[str(case_id)] = page
            return copy.deepcopy(page)


pages = PageSessions()
