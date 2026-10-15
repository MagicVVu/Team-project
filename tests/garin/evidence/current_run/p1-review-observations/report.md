# 回归测试报告
版本：5a056831799b-p1-review-observations；引擎：rules；适配器：adapters.local_p1
结果：{'PASS': 13, 'FAIL': 5}；本轮必测项全部通过：False

## 失败、阻塞与待定项
- ext-076 [FAIL]：status: expected='unsupported'; actual='answered'
- ext-077 [FAIL]：status: expected='unsupported'; actual='answered'
- ext-085 [FAIL]：status not in allowed set
- ext-091 [FAIL]：draft: expected=None; actual={'action': 'ADD', 'name': '牛奶', 'quantity': '2', 'unit': '盒', 'location': None, 'purchased_at': None, 'label_expiry': None, 'batch_id': None, 'expected_version': None}；status not in allowed set
- ext-092 [FAIL]：draft: expected=None; actual={'action': 'ADD', 'name': '牛乃', 'quantity': '2', 'unit': '盒', 'location': None, 'purchased_at': None, 'label_expiry': None, 'batch_id': None, 'expected_version': None}；status not in allowed set