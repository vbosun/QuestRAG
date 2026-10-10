"""Mirror confirmed Browser Use actions to cooperating native forms, without images."""
import asyncio
from urllib.parse import urlparse


class OperationFeedback:
    def __init__(self, record, live):
        self.record = record
        self.live = live
        self.current = None
        self.sequence = 0
        self.action_id = 0

    async def fields(self):
        page = await self.live.page()
        expected, actual = urlparse(self.record.url), urlparse(page.url)
        if (actual.scheme, actual.netloc, actual.path) != (expected.scheme, expected.netloc, expected.path):
            return {}
        return await page.evaluate("""() => Object.fromEntries(
            Array.from(document.querySelectorAll('input,select,textarea'))
            .filter(el => !['file','password','hidden'].includes(el.type) && (el.name || el.id))
            .map(el => [el.name || el.id, {value:el.value,
                label:(el.labels?.[0]?.textContent || el.name || el.id).replace(/\\s+/g,' ').trim().slice(0,80)}]))""")

    def emit(self, phase, key, label, **extra):
        if getattr(self.record, 'command_id', None) and key not in self.record.requested_fields:
            return
        self.sequence += 1
        self.record.operation_events.append({"sequence": self.sequence, "action_id": self.action_id,
                                             "phase": phase, "field_key": key, "label": label, **extra})

    def target(self, source, info):
        # DOM focus/click events are only targets, never evidence of successful filling.
        if self.current is None or self.record.status != 'running':
            return
        expected, actual = urlparse(self.record.url), urlparse(source['page'].url)
        if (actual.scheme, actual.netloc, actual.path) != (expected.scheme, expected.netloc, expected.path):
            return
        key = info.get('field_key')
        if not key or key == self.current.get('key'):
            return
        self.current.update(key=key, label=info.get('label') or key)
        self.emit('started', key, self.current['label'])

    async def perform(self, action, invoke):
        self.action_id += 1
        self.current = {}
        before = await self._read()
        try:
            params = next((p for p in action.values() if isinstance(p, dict)), {})
            if isinstance(params.get('index'), int):
                try:
                    node = await self.live.browser.get_element_by_index(params['index'])
                    attrs = node.attributes if node else {}
                except Exception:
                    attrs = {}
                key = attrs.get('name') or attrs.get('id')
                if key and key in before:
                    self.current.update(key=key, label=before[key]['label'])
                    self.emit('started', key, before[key]['label'])
            result = await invoke()
            if getattr(result, 'error', None):
                self._end('failed')
                return result
            after = await self._read()
            target = self.current.get('key')
            for key, field in after.items():
                previous = before.get(key)
                if (previous and field['value'] != previous['value']) or (key == target) or (not previous and field['value']):
                    self.record.form_fields[key] = field['value']
                    self.emit('applied', key, field['label'], value=field['value'])
            return result
        except asyncio.CancelledError:
            self._end('cancelled')
            raise
        except Exception:
            self._end('failed')
            raise
        finally:
            self.current = None

    def _end(self, phase):
        if self.current and self.current.get('key'):
            self.emit(phase, self.current['key'], self.current['label'])

    async def _read(self):
        try:
            return await self.fields()
        except Exception:
            # Initial navigation may not yet have an active business page.
            return {}
