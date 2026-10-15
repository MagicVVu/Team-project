# 回归测试报告
版本：5a056831799b-p0-review-observations；引擎：rules；适配器：adapters.local_p0
结果：{'FAIL': 7, 'PASS': 11}；本轮必测项全部通过：False

## 失败、阻塞与待定项
- p0-43-2 [FAIL]：status: expected='needs_clarification'; actual='unsupported'
- ext-076 [FAIL]：status: expected='unsupported'; actual='answered'
- ext-077 [FAIL]：status: expected='unsupported'; actual='answered'
- ext-085 [FAIL]：status not in allowed set
- ext-087 [FAIL]：draft: expected=None; actual={'action': 'ADD', 'name': '牛奶', 'quantity': '2.0', 'unit': '盒', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}；status not in allowed set
- ext-091 [FAIL]：draft: expected=None; actual={'action': 'ADD', 'name': '牛奶', 'quantity': '2.0', 'unit': '盒', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}；status not in allowed set
- ext-096 [FAIL]：draft: expected=None; actual={'action': 'ADD', 'name': '牛奶', 'quantity': '2', 'unit': '盒', 'batch_id': None, 'expected_version': None, 'location': None, 'purchased_at': None, 'label_expiry': None}；status not in allowed set